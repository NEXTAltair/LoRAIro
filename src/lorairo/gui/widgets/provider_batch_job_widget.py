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
from typing import Any, cast

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import QMessageBox, QTableWidget, QTableWidgetItem, QWidget

from lorairo.gui.designer.ProviderBatchJobWidget_ui import Ui_ProviderBatchJobWidget
from lorairo.gui.widgets.model_selection_widget import ModelSelectionWidget
from lorairo.services.provider_batch_capability import (
    direct_provider_for_model,
    endpoint_for_task,
)
from lorairo.services.provider_batch_service import ProviderBatchError
from lorairo.utils.log import logger

_TASK_TYPES = ("annotation", "rating_preflight")
_ITEM_STATUSES = ("all", "failed", "expired", "canceled")


class ProviderBatchJobWidget(QWidget, Ui_ProviderBatchJobWidget):
    """Provider Batch job submit/list/detail widget (統一フロー)."""

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

        # ADR 0041: placeholder を単一選択 batch-capable ModelSelectionWidget に差替
        self._staging_widget = self.stagingWidget
        self._model_selection_widget = self._inject_model_selection_widget()
        self._model_selection_widget.set_single_selection_mode(True)

        self._setup_combos_and_tables()
        self._connect_signals()
        self._update_target_label()

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

    def _connect_signals(self) -> None:
        self.buttonAddSelected.clicked.connect(self._staging_widget.add_selected_images)
        self.buttonSubmit.clicked.connect(self.submit_job)
        self.comboBoxTaskType.currentTextChanged.connect(self._on_task_type_changed)
        self._staging_widget.staged_images_changed.connect(self._update_target_label)
        self.buttonRefreshJobs.clicked.connect(self.refresh_jobs)
        self.buttonRefreshStatus.clicked.connect(self.refresh_selected_job_status)
        self.buttonCancel.clicked.connect(self.cancel_selected_job)
        self.buttonFetch.clicked.connect(self.fetch_selected_job)
        self.buttonImport.clicked.connect(self.import_selected_job)
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

    @Slot()
    def submit_job(self) -> None:
        if self._workflow_service is None:
            self.labelStatus.setText("Provider Batch service is not available")
            return
        litellm_model_id = self._model_selection_widget.get_selected_model()
        if not litellm_model_id:
            QMessageBox.warning(self, "Provider Batch", "バッチ対応モデルを選択してください。")
            return
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
            job_id = self._workflow_service.submit_images(
                provider=provider,
                endpoint=endpoint,
                litellm_model_id=litellm_model_id,
                prompt_profile=self.lineEditPromptProfile.text().strip() or "default",
                image_ids=image_ids,
                model_id=model.id,
                description=self.lineEditDescription.text().strip() or None,
                task_type=task_type,
            )
            self.refresh_jobs()
            self.select_job(job_id)
            self.labelStatus.setText(f"Submitted Provider Batch job {job_id}")
        except (ProviderBatchError, ValueError) as e:
            QMessageBox.warning(self, "Provider Batch", str(e))
            self.labelStatus.setText(str(e))
        except Exception as e:
            logger.error(f"Provider Batch submit failed: {e}", exc_info=True)
            QMessageBox.critical(self, "Provider Batch", str(e))
            self.labelStatus.setText("Submit failed")

    @Slot()
    def refresh_jobs(self) -> None:
        if self._repository is None:
            return
        try:
            jobs = self._repository.list_provider_batch_jobs(limit=100, offset=0)
        except Exception as e:
            logger.warning(f"Provider Batch job list failed: {e}")
            self.tableJobs.setRowCount(0)
            self.labelStatus.setText("Provider Batch jobs unavailable")
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
        self.labelStatus.setText(f"Loaded {len(jobs)} Provider Batch job(s)")

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
            return
        job_id = selected[0].data(Qt.ItemDataRole.UserRole)
        self._current_job_id = int(job_id)
        self.refresh_detail()
        self.refresh_items()

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
            QMessageBox.information(self, "Provider Batch", "Select a Provider Batch job first.")
            return None
        return self._current_job_id

    def _handle_action_error(self, action: str, error: Exception) -> None:
        logger.error(f"Provider Batch {action} failed: {error}", exc_info=True)
        QMessageBox.critical(self, "Provider Batch", str(error))
        self.labelStatus.setText(f"{action.capitalize()} failed")

    @Slot()
    def refresh_selected_job_status(self) -> None:
        job_id = self._require_current_job_id()
        if job_id is None or self._workflow_service is None:
            return
        try:
            self._workflow_service.refresh(job_id)
            self.labelStatus.setText(f"Refreshed Provider Batch job {job_id}")
            self.refresh_jobs()
            self.select_job(job_id)
        except ProviderBatchError as e:
            QMessageBox.warning(self, "Provider Batch", str(e))
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
            self.labelStatus.setText(f"Cancel requested for Provider Batch job {job_id}")
            self.refresh_jobs()
            self.select_job(job_id)
        except ProviderBatchError as e:
            QMessageBox.warning(self, "Provider Batch", str(e))
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
                f"Fetched Provider Batch job {job_id}: {len(getattr(result, 'items', ()) or ())} item(s)"
            )
            self.refresh_detail()
            self.refresh_items()
        except ProviderBatchError as e:
            QMessageBox.warning(self, "Provider Batch", str(e))
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
                f"Imported {result.imported_count}/{result.total_count} Provider Batch result(s)"
            )
            self.refresh_detail()
            self.refresh_items()
        except ProviderBatchError as e:
            QMessageBox.warning(self, "Provider Batch", str(e))
            self.labelStatus.setText(str(e))
        except Exception as e:
            self._handle_action_error("import", e)
