"""Provider Batch job monitoring widget.

ADR 0076 §3: 作成入口 (ステージング + モデルピッカー + Submit) を Annotate の dispatch
射影へ移し、本 widget は **純粋な監視台帳** に徹する。

- 上: 同期ジョブ台帳 (SyncJobLedgerWidget、ADR 0066、runtime 挿入)
- 下: Provider Batch ジョブの監視 (Jobs / Detail / Items) と lifecycle / 復旧操作

残す操作は lifecycle / 事故復旧系に限る (ADR 0076 §1): 主操作 ``状態を確認`` /
``キャンセル``、context menu の ``結果を取得`` / ``結果を取り込み`` (ADR 0041 §7)。
作成入口 (Submit フォーム・モデルピッカー・ステージング) は持たない。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from PySide6.QtCore import QPoint, Qt, Signal, Slot
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import QMenu, QMessageBox, QTableWidget, QTableWidgetItem, QWidget

from lorairo.gui import theme
from lorairo.gui.designer.ProviderBatchJobWidget_ui import Ui_ProviderBatchJobWidget
from lorairo.gui.widgets.sync_job_ledger_widget import SyncJobLedgerWidget
from lorairo.services.job_ledger_service import JobLedgerService
from lorairo.services.provider_batch_service import ProviderBatchError
from lorairo.utils.log import logger

_ITEM_STATUSES = ("all", "failed", "expired", "canceled")
_CANCELABLE_STATUSES = {"submitted", "validating", "running", "canceling"}
_COMPLETED_STATUS = "completed"
_IMPORTED_STATUS = "imported"


class ProviderBatchJobWidget(QWidget, Ui_ProviderBatchJobWidget):
    """Provider Batch job 監視台帳 widget (ADR 0076 §3 — 監視専用)."""

    sync_job_cancel_requested = Signal(str)  # ADR 0066 §4: 同期ジョブ行のキャンセル (job_id)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        setup_ui = cast(Callable[[QWidget], None], self.setupUi)
        setup_ui(self)
        self.setObjectName("providerBatchJobWidget")

        self._workflow_service: Any = None
        self._repository: Any = None
        self._current_job_id: int | None = None

        # ADR 0066: 統一 Jobs lifecycle ビュー — 同期ジョブ台帳セクション (拡張方式)
        self._job_ledger: JobLedgerService | None = None
        self._sync_jobs_widget = SyncJobLedgerWidget(parent=self.splitterRight)
        self.splitterRight.insertWidget(0, self._sync_jobs_widget)
        self._sync_jobs_widget.cancel_requested.connect(self.sync_job_cancel_requested)

        self._setup_combos_and_tables()
        self._setup_job_context_menu()
        self._connect_signals()
        self._update_job_action_state()

    def _setup_combos_and_tables(self) -> None:
        """combo / table の項目・ヘッダを設定する。"""
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

    def set_dependencies(self, workflow_service: Any, repository: Any) -> None:
        """Inject services used by the monitoring widget.

        ADR 0076 §3: 作成入口を撤去したため model_source / model_repository は不要。
        監視・lifecycle / 復旧操作に必要な workflow_service と repository のみ受ける。

        Args:
            workflow_service: refresh / cancel / fetch / import を提供する workflow service。
            repository: ジョブ・項目の一覧 / 詳細を提供する provider_batch_repo。
        """
        self._workflow_service = workflow_service
        self._repository = repository
        self.refresh_jobs()

    def get_sync_jobs_widget(self) -> SyncJobLedgerWidget:
        """同期ジョブ台帳セクション widget を返す。"""
        return self._sync_jobs_widget

    def set_job_ledger(self, job_ledger: JobLedgerService) -> None:
        """同期ジョブ台帳 (ADR 0066) を注入し、初期表示を行う。

        Args:
            job_ledger: WorkerService が所有する in-memory 台帳。
        """
        self._job_ledger = job_ledger
        self.refresh_sync_jobs()

    @Slot()
    def refresh_sync_jobs(self) -> None:
        """同期ジョブ台帳セクション (サマリ帯・ステージ進捗・履歴) を再描画する。"""
        if self._job_ledger is None:
            return
        self._sync_jobs_widget.set_summary(self._job_ledger.summary())
        self._sync_jobs_widget.set_entries(self._job_ledger.list_entries())

    def _connect_signals(self) -> None:
        self.buttonRefreshStatus.clicked.connect(self.refresh_selected_job_status)
        self.buttonCancel.clicked.connect(self.cancel_selected_job)
        self.tableJobs.itemSelectionChanged.connect(self._on_job_selection_changed)
        self.comboBoxItemStatus.currentTextChanged.connect(self.refresh_items)

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
            status_color = QColor(theme.job_status_color(values[2]))
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, job_id)
                # Theme v1 (Issue #760): 状態列をトークン色で表示 (実行中=info/完了=ok/失敗=err)
                if column in (2, 3):
                    item.setForeground(status_color)
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
