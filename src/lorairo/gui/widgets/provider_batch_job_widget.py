"""Provider Batch job management widget.

ADR 0041: 個別実行フロー (BatchTagAddWidget) と同形の
「ステージング → モデル選択 → 実行」統一フローに改修した Provider Batch タブ。

- 左: StagingWidget (サムネイルステージング、個別実行と共通)
- 右上: 実行設定 (task_type フィルタ → 単一選択 batch-capable ModelSelectionWidget → Submit)
- 右下: batch 固有の job 状態表示 (Jobs / Detail / Items)

batch-capable 判定ロジックは Qt-free helper (provider_batch_capability) と
ModelSelectionWidget に集約済みで、本 widget では submit 時のパラメータ解決にのみ helper を再利用する。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from PySide6.QtCore import QObject, QPoint, Qt, QThread, Signal, Slot
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QMessageBox, QTableWidget, QTableWidgetItem, QWidget

from lorairo.gui.designer.ProviderBatchJobWidget_ui import Ui_ProviderBatchJobWidget
from lorairo.gui.widgets.model_selection_widget import ModelSelectionWidget
from lorairo.gui.widgets.staging_widget import StagingWidget
from lorairo.services.provider_batch_capability import (
    direct_provider_for_model,
    endpoint_for_task,
)
from lorairo.services.provider_batch_service import ProviderBatchError
from lorairo.utils.log import logger

_TASK_TYPES = ("annotation", "rating_preflight")
_ITEM_STATUSES = ("all", "failed", "expired", "canceled")
_CANCELABLE_STATUSES = {"submitted", "validating", "running", "canceling"}
_COMPLETED_STATUS = "completed"
_IMPORTED_STATUS = "imported"
_ACTIVE_SUBMIT_THREADS: set[QThread] = set()


@dataclass(frozen=True)
class _ProviderBatchSubmitParams:
    provider: str
    endpoint: str
    litellm_model_id: str
    prompt_profile: str
    image_ids: list[int]
    model_id: int
    description: str | None
    task_type: str


class _ProviderBatchSubmitWorker(QObject):
    """Run provider batch submission off the GUI thread."""

    succeeded = Signal(int)
    failed = Signal(object)
    finished = Signal()

    def __init__(self, workflow_service: Any, params: _ProviderBatchSubmitParams) -> None:
        super().__init__()
        self._workflow_service = workflow_service
        self._params = params

    @Slot()
    def run(self) -> None:
        try:
            job_id = self._workflow_service.submit_images(
                provider=self._params.provider,
                endpoint=self._params.endpoint,
                litellm_model_id=self._params.litellm_model_id,
                prompt_profile=self._params.prompt_profile,
                image_ids=self._params.image_ids,
                model_id=self._params.model_id,
                description=self._params.description,
                task_type=self._params.task_type,
            )
            self.succeeded.emit(int(job_id))
        except Exception as e:
            self.failed.emit(e)
        finally:
            self.finished.emit()


class ProviderBatchJobWidget(QWidget, Ui_ProviderBatchJobWidget):
    """Provider Batch job submit/list/detail widget (統一フロー)."""

    staged_images_changed = Signal(list)
    staging_cleared = Signal()
    submit_completed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        setup_ui = cast(Callable[[QWidget], None], self.setupUi)
        setup_ui(self)
        self.setObjectName("providerBatchJobWidget")

        self._workflow_service: Any = None
        self._repository: Any = None
        self._model_repository: Any = None
        self._model_source: Any = None
        self._dataset_state_manager: Any = None
        self._current_job_id: int | None = None
        # Issue #571: submit 中に再配信されたクリックを無視し、同一対象の二重ジョブ作成を防ぐ。
        self._submit_in_progress = False
        self._submit_thread: QThread | None = None
        self._submit_worker: _ProviderBatchSubmitWorker | None = None
        self._submitted_image_ids: list[int] = []
        self._submit_button_default_text = self.buttonSubmit.text()
        self._submit_button_default_style = self.buttonSubmit.styleSheet()

        # ADR 0041: placeholder を単一選択 batch-capable ModelSelectionWidget に差替
        self._staging_widget = self.stagingWidget
        self._staging_widget.staged_images_changed.connect(self.staged_images_changed)
        self._staging_widget.staging_cleared.connect(self.staging_cleared)
        self._model_selection_widget = self._inject_model_selection_widget()
        self._model_selection_widget.set_single_selection_mode(True)

        self._setup_combos_and_tables()
        self._setup_job_context_menu()
        self._connect_signals()
        self._update_target_label()
        self._update_job_action_state()

    def _inject_model_selection_widget(self) -> ModelSelectionWidget:
        """modelSelectionPlaceholder を ModelSelectionWidget に差替える。

        widget_setup_service の placeholder 差替パターンに準拠する。

        Returns:
            実行設定グループに組み込んだ ModelSelectionWidget。
        """
        placeholder = self.modelSelectionPlaceholder
        layout = self.executionLayout
        index = layout.indexOf(placeholder)
        layout.removeWidget(placeholder)
        placeholder.setParent(None)
        placeholder.deleteLater()

        widget = ModelSelectionWidget(mode="advanced")
        widget.setObjectName("providerBatchModelSelection")
        widget.setParent(self.groupBoxExecution)
        layout.insertWidget(index, widget)
        return widget

    def _setup_combos_and_tables(self) -> None:
        """combo / table の項目・ヘッダを設定する。"""
        self.comboBoxTaskType.addItems(_TASK_TYPES)
        self.comboBoxTaskType.setCurrentText("annotation")
        self.comboBoxItemStatus.addItems(_ITEM_STATUSES)

        self.tableJobs.setColumnCount(5)
        self.tableJobs.setHorizontalHeaderLabels(
            ["ID", "Provider", "Status", "Provider Status", "Requests"]
        )
        self.tableJobs.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tableJobs.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self.tableItems.setColumnCount(5)
        self.tableItems.setHorizontalHeaderLabels(
            ["Custom ID", "Image ID", "Status", "Error Type", "Error Message"]
        )
        self.tableItems.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

    def _setup_job_context_menu(self) -> None:
        """Set up recovery actions that stay out of the normal job flow."""
        self._action_fetch_results = QAction("結果を取得", self)
        self._action_import_results = QAction("結果を取り込み", self)
        self._action_fetch_results.triggered.connect(self.fetch_selected_job)
        self._action_import_results.triggered.connect(self.import_selected_job)
        self.tableJobs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tableJobs.customContextMenuRequested.connect(self._show_job_context_menu)

    def set_dependencies(
        self,
        workflow_service: Any,
        repository: Any,
        model_source: Any = None,
        model_repository: Any = None,
    ) -> None:
        """Inject services used by the widget."""
        self._workflow_service = workflow_service
        self._repository = repository
        self._model_source = model_source
        self._model_repository = model_repository
        self._model_selection_widget.set_batch_capable_filtering(
            True, self._selected_task_type(), model_source
        )
        self.refresh_jobs()

    def set_dataset_state_manager(self, dataset_state_manager: Any) -> None:
        """Set shared dataset state for staging import."""
        self._dataset_state_manager = dataset_state_manager
        self._staging_widget.set_dataset_state_manager(dataset_state_manager)

    def connect_shared_staging(self, source: StagingWidget) -> None:
        """通常アノテーションと同じステージング状態を共有する。"""
        self._staging_widget.connect_shared_staging(source)
        self._update_target_label()

    def get_staging_widget(self) -> StagingWidget:
        """内部 StagingWidget を返す。"""
        return self._staging_widget

    def get_model_selection_widget(self) -> ModelSelectionWidget:
        """差し込み済み ModelSelectionWidget を返す。"""
        return self._model_selection_widget

    def _connect_signals(self) -> None:
        self.buttonAddSelected.clicked.connect(self._staging_widget.add_selected_images)
        self.buttonSubmit.clicked.connect(self.submit_job)
        self.comboBoxTaskType.currentTextChanged.connect(self._on_task_type_changed)
        self._staging_widget.staged_images_changed.connect(self._update_target_label)
        self.buttonRefreshStatus.clicked.connect(self.refresh_selected_job_status)
        self.buttonCancel.clicked.connect(self.cancel_selected_job)
        self.tableJobs.itemSelectionChanged.connect(self._on_job_selection_changed)
        self.comboBoxItemStatus.currentTextChanged.connect(self.refresh_items)

    def _selected_task_type(self) -> str:
        task_type = self.comboBoxTaskType.currentText()
        if task_type in _TASK_TYPES:
            return task_type
        return "annotation"

    @Slot(str)
    def _on_task_type_changed(self, _task_type: str) -> None:
        """task_type 変更時に batch-capable フィルタを再評価する。"""
        if self._model_source is None:
            return
        self._model_selection_widget.set_batch_capable_filtering(
            True, self._selected_task_type(), self._model_source
        )

    @Slot()
    def _update_target_label(self, _image_ids: list[int] | None = None) -> None:
        """ステージング枚数ラベルを更新する。"""
        count = self._staging_widget.count()
        self.labelTarget.setText(f"◎ ステージング: {count} 枚")

    def _set_submit_button_busy(self, busy: bool) -> None:
        """Reflect provider submit state on the submit button."""
        self.buttonSubmit.setEnabled(not busy)
        if busy:
            self.buttonSubmit.setText("送信中...")
            self.buttonSubmit.setStyleSheet(
                "QPushButton { background-color: #2f7de1; color: white; font-weight: bold; }"
            )
            return
        self.buttonSubmit.setText(self._submit_button_default_text)
        self.buttonSubmit.setStyleSheet(self._submit_button_default_style)

    def _start_submit_worker(self, params: _ProviderBatchSubmitParams) -> None:
        """Start provider batch submission in a dedicated QThread."""
        thread = QThread()
        worker = _ProviderBatchSubmitWorker(self._workflow_service, params)
        worker.moveToThread(thread)
        _ACTIVE_SUBMIT_THREADS.add(thread)

        thread.started.connect(worker.run)
        worker.succeeded.connect(self._on_submit_succeeded)
        worker.failed.connect(self._on_submit_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_submit_thread_finished)
        thread.finished.connect(lambda: _ACTIVE_SUBMIT_THREADS.discard(thread))
        thread.finished.connect(thread.deleteLater)

        self._submit_thread = thread
        self._submit_worker = worker
        thread.start()

    @Slot(int)
    def _on_submit_succeeded(self, job_id: int) -> None:
        # Issue #571: submit_images 成功 = provider job 作成済み。後続の表示更新が
        # 失敗しても送信成功を覆さないよう、送信済み対象の除外を先に確定する。
        # image_ids は submit 直前の snapshot なので、送信中に追加された画像は残す。
        image_ids = list(self._submitted_image_ids)
        self._staging_widget.remove_image_ids(image_ids)
        try:
            self.refresh_jobs(update_label=False)
            self.select_job(job_id)
        except Exception as e:
            logger.warning(f"バッチAPI 送信後の一覧更新に失敗しました: {e}")
        # refresh_jobs は list 失敗時に labelStatus を上書きする (例外は内部で握る) ため、
        # 送信成功表示は表示更新の後に最後に確定する。
        self.labelStatus.setText(f"バッチAPIジョブ {job_id} を送信しました")

    @Slot(object)
    def _on_submit_failed(self, error: object) -> None:
        if isinstance(error, (ProviderBatchError, ValueError)):
            QMessageBox.warning(self, "バッチAPI", str(error))
            self.labelStatus.setText(str(error))
            return
        logger.error(f"バッチAPI submit failed: {error}", exc_info=True)
        QMessageBox.critical(self, "バッチAPI", str(error))
        self.labelStatus.setText("送信に失敗しました")

    @Slot()
    def _on_submit_thread_finished(self) -> None:
        self._set_submit_button_busy(False)
        self._submit_in_progress = False
        self._submitted_image_ids = []
        self._submit_worker = None
        self._submit_thread = None
        self.submit_completed.emit()

    @Slot()
    def submit_job(self) -> None:
        if self._workflow_service is None:
            self.labelStatus.setText("バッチAPIサービスを利用できません")
            return
        # Issue #571: submit 中に再配信されたクリックを無視し、同一対象の二重ジョブ作成を防ぐ。
        if self._submit_in_progress:
            return
        litellm_model_id = self._model_selection_widget.get_selected_model()
        if not litellm_model_id:
            QMessageBox.warning(self, "バッチAPI", "バッチ対応モデルを選択してください。")
            return
        self._submit_in_progress = True
        try:
            image_ids = self._staging_widget.get_image_ids()
            if not image_ids:
                raise ValueError("ステージングに画像を追加してください。")
            task_type = self._selected_task_type()
            model = (
                self._model_repository.get_model_by_litellm_id(litellm_model_id)
                if self._model_repository is not None
                else None
            )
            if model is None:
                raise ValueError(f"モデル情報が見つかりません: {litellm_model_id}")
            provider = direct_provider_for_model(model)
            if provider is None:
                raise ValueError(f"direct provider を解決できません: {litellm_model_id}")
            endpoint = endpoint_for_task(provider, task_type)
            params = _ProviderBatchSubmitParams(
                provider=provider,
                endpoint=endpoint,
                litellm_model_id=litellm_model_id,
                prompt_profile=self.lineEditPromptProfile.text().strip() or "default",
                image_ids=list(image_ids),
                model_id=model.id,
                description=self.lineEditDescription.text().strip() or None,
                task_type=task_type,
            )
            self._submitted_image_ids = list(image_ids)
            self._set_submit_button_busy(True)
            self._start_submit_worker(params)
        except (ProviderBatchError, ValueError) as e:
            self._submit_in_progress = False
            self._submitted_image_ids = []
            QMessageBox.warning(self, "バッチAPI", str(e))
            self.labelStatus.setText(str(e))
        except Exception as e:
            self._submit_in_progress = False
            self._submitted_image_ids = []
            logger.error(f"バッチAPI submit failed: {e}", exc_info=True)
            QMessageBox.critical(self, "バッチAPI", str(e))
            self.labelStatus.setText("送信に失敗しました")

    @Slot()
    def refresh_jobs(self, update_label: bool = True) -> None:
        if self._repository is None:
            return
        try:
            jobs = self._repository.list_provider_batch_jobs(limit=100, offset=0)
        except Exception as e:
            logger.warning(f"バッチAPI job list failed: {e}")
            self.tableJobs.setRowCount(0)
            self.labelStatus.setText("バッチAPIジョブを取得できません")
            return
        self.tableJobs.setRowCount(0)
        for job in jobs:
            row = self.tableJobs.rowCount()
            self.tableJobs.insertRow(row)
            job_id = int(job.id)
            values = [
                str(job_id),
                str(getattr(job, "provider", "")),
                str(getattr(job, "status", "")),
                str(getattr(job, "provider_status", "") or ""),
                str(getattr(job, "request_count", 0)),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, job_id)
                self.tableJobs.setItem(row, column, item)
        if update_label:
            self.labelStatus.setText(f"バッチAPIジョブ {len(jobs)} 件を読み込みました")
        self._update_job_action_state()

    def select_job(self, job_id: int) -> None:
        for row in range(self.tableJobs.rowCount()):
            item = self.tableJobs.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == job_id:
                self.tableJobs.selectRow(row)
                return

    @Slot()
    def _on_job_selection_changed(self) -> None:
        selected = self.tableJobs.selectedItems()
        if not selected:
            self._current_job_id = None
            self.textEditJobDetail.clear()
            self.tableItems.setRowCount(0)
            self._update_job_action_state()
            return
        job_id = selected[0].data(Qt.ItemDataRole.UserRole)
        self._current_job_id = int(job_id)
        self.refresh_detail()
        self.refresh_items()
        self._update_job_action_state()

    @Slot()
    def refresh_detail(self) -> None:
        if self._repository is None or self._current_job_id is None:
            return
        job = self._repository.get_provider_batch_job(self._current_job_id)
        if job is None:
            self.textEditJobDetail.clear()
            return
        fields = [
            "id",
            "provider",
            "provider_job_id",
            "status",
            "provider_status",
            "endpoint",
            "model_id",
            "request_count",
            "succeeded_count",
            "failed_count",
            "canceled_count",
            "expired_count",
            "submitted_at",
            "completed_at",
            "canceled_at",
            "expires_at",
            "imported_at",
        ]
        self.textEditJobDetail.setPlainText(
            "\n".join(f"{field}: {getattr(job, field, '')}" for field in fields)
        )

    @Slot()
    def refresh_items(self) -> None:
        if self._repository is None or self._current_job_id is None:
            return
        status = self.comboBoxItemStatus.currentText()
        status_filter = None if status == "all" else status
        items = self._repository.list_provider_batch_items(self._current_job_id, status=status_filter)
        self.tableItems.setRowCount(0)
        for item_obj in items:
            row = self.tableItems.rowCount()
            self.tableItems.insertRow(row)
            values = [
                str(getattr(item_obj, "custom_id", "")),
                str(getattr(item_obj, "image_id", "") or ""),
                str(getattr(item_obj, "status", "")),
                str(getattr(item_obj, "error_type", "") or ""),
                str(getattr(item_obj, "error_message", "") or ""),
            ]
            for column, value in enumerate(values):
                self.tableItems.setItem(row, column, QTableWidgetItem(value))

    def _require_current_job_id(self) -> int | None:
        if self._current_job_id is None:
            QMessageBox.information(self, "バッチAPI", "先にバッチAPIジョブを選択してください。")
            return None
        return self._current_job_id

    def _handle_action_error(self, action: str, error: Exception) -> None:
        logger.error(f"バッチAPI {action} failed: {error}", exc_info=True)
        QMessageBox.critical(self, "バッチAPI", str(error))
        self.labelStatus.setText(f"{action} に失敗しました")

    def _current_job(self) -> Any | None:
        if self._repository is None or self._current_job_id is None:
            return None
        return self._repository.get_provider_batch_job(self._current_job_id)

    @staticmethod
    def _job_status(job: Any) -> str:
        return str(getattr(job, "status", "") or "")

    @staticmethod
    def _job_imported(job: Any) -> bool:
        return ProviderBatchJobWidget._job_status(job) == _IMPORTED_STATUS or (
            getattr(job, "imported_at", None) is not None
        )

    @staticmethod
    def _job_cancelable(job: Any | None) -> bool:
        return job is not None and ProviderBatchJobWidget._job_status(job) in _CANCELABLE_STATUSES

    def _update_job_action_state(self) -> None:
        job = self._current_job()
        has_job = job is not None
        self.buttonRefreshStatus.setEnabled(has_job)
        self.buttonCancel.setEnabled(self._job_cancelable(job))
        self._action_fetch_results.setEnabled(has_job)
        self._action_import_results.setEnabled(has_job and not self._job_imported(job))

    @Slot(QPoint)
    def _show_job_context_menu(self, position: QPoint) -> None:
        index = self.tableJobs.indexAt(position)
        if not index.isValid():
            return
        self.tableJobs.selectRow(index.row())
        if self._current_job_id is None:
            return
        self._update_job_action_state()
        menu = QMenu(self)
        menu.addAction(self._action_fetch_results)
        menu.addAction(self._action_import_results)
        menu.exec(self.tableJobs.viewport().mapToGlobal(position))

    def _status_message_for_job(self, job_id: int, job: Any) -> str:
        status = self._job_status(job)
        provider_status = str(getattr(job, "provider_status", "") or status)
        if status in {"submitted", "validating"}:
            return f"バッチAPIジョブ {job_id} は検証中です ({provider_status})"
        if status in {"running", "canceling"}:
            return f"バッチAPIジョブ {job_id} は処理中です ({provider_status})"
        if status == "failed":
            return f"バッチAPIジョブ {job_id} は失敗しました ({provider_status})"
        if status == "expired":
            return f"バッチAPIジョブ {job_id} は期限切れです ({provider_status})"
        if status == "canceled":
            return f"バッチAPIジョブ {job_id} はキャンセル済みです ({provider_status})"
        return f"バッチAPIジョブ {job_id} の状態を確認しました ({provider_status})"

    @staticmethod
    def _import_result_message(job_id: int, result: Any) -> str:
        imported_count = int(getattr(result, "imported_count", 0))
        skipped_count = int(getattr(result, "skipped_count", 0))
        error_count = int(getattr(result, "error_count", 0))
        total_count = int(getattr(result, "total_count", 0))
        if skipped_count or error_count:
            return (
                f"バッチAPIジョブ {job_id} の処理完了を確認し、DB保存を実行しました: "
                f"保存 {imported_count}/{total_count} 件, スキップ {skipped_count} 件, エラー {error_count} 件"
            )
        return f"バッチAPIジョブ {job_id} の処理完了を確認し、DB保存が完了しました: {imported_count}/{total_count} 件"

    @Slot()
    def refresh_selected_job_status(self) -> None:
        job_id = self._require_current_job_id()
        if job_id is None or self._workflow_service is None:
            return
        try:
            current_job = self._current_job()
            if current_job is not None and self._job_imported(current_job):
                self.labelStatus.setText(f"バッチAPIジョブ {job_id} は保存済みです")
                self._update_job_action_state()
                return
            job = self._workflow_service.refresh(job_id)
            if self._job_imported(job):
                message = f"バッチAPIジョブ {job_id} は保存済みです"
            elif self._job_status(job) == _COMPLETED_STATUS:
                fetch_result = self._workflow_service.fetch_results(job_id)
                import_result = self._workflow_service.import_results(job_id, fetch_result)
                message = self._import_result_message(job_id, import_result)
            else:
                message = self._status_message_for_job(job_id, job)
            self.refresh_jobs(update_label=False)
            self.select_job(job_id)
            self.labelStatus.setText(message)
        except ProviderBatchError as e:
            QMessageBox.warning(self, "バッチAPI", str(e))
            self.labelStatus.setText(str(e))
        except Exception as e:
            self._handle_action_error("refresh", e)

    @Slot()
    def cancel_selected_job(self) -> None:
        job_id = self._require_current_job_id()
        if job_id is None or self._workflow_service is None:
            return
        try:
            self._workflow_service.cancel(job_id)
            self.refresh_jobs(update_label=False)
            self.select_job(job_id)
            self.labelStatus.setText(f"バッチAPIジョブ {job_id} のキャンセルを要求しました")
        except ProviderBatchError as e:
            QMessageBox.warning(self, "バッチAPI", str(e))
            self.labelStatus.setText(str(e))
        except Exception as e:
            self._handle_action_error("cancel", e)

    @Slot()
    def fetch_selected_job(self) -> None:
        job_id = self._require_current_job_id()
        if job_id is None or self._workflow_service is None:
            return
        try:
            result = self._workflow_service.fetch_results(job_id)
            self.labelStatus.setText(
                f"バッチAPIジョブ {job_id} の結果 {len(getattr(result, 'items', ()) or ())} 件を取得しました"
            )
            self.refresh_detail()
            self.refresh_items()
            self._update_job_action_state()
        except ProviderBatchError as e:
            QMessageBox.warning(self, "バッチAPI", str(e))
            self.labelStatus.setText(str(e))
        except Exception as e:
            self._handle_action_error("fetch", e)

    @Slot()
    def import_selected_job(self) -> None:
        job_id = self._require_current_job_id()
        if job_id is None or self._workflow_service is None:
            return
        try:
            result = self._workflow_service.import_results(job_id)
            self.labelStatus.setText(
                f"バッチAPI結果 {result.imported_count}/{result.total_count} 件をDB保存しました"
            )
            self.refresh_detail()
            self.refresh_items()
            self._update_job_action_state()
        except ProviderBatchError as e:
            QMessageBox.warning(self, "バッチAPI", str(e))
            self.labelStatus.setText(str(e))
        except Exception as e:
            self._handle_action_error("import", e)
