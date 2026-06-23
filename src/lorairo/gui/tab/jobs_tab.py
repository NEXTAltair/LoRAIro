"""ジョブタブ (Provider Batch) の専用ウィジェット (Epic #867 / #874)。

MainWindow のジョブタブ — Provider Batch ジョブの投入・監視・キャンセル・同期ジョブ台帳・
Batch API 結果インポート — のオーケストレーションを ``JobsTabWidget`` へ集約する。
MainWindow には worker dispatch とタブ間遷移・共有サービス (statusbar / error_notification /
ProgressStateService) への橋渡しだけを残す。

本タブの中身 (左: StagingWidget / 右上: モデル選択+Submit / 右下: ジョブ状態) は
独立 widget ``ProviderBatchJobWidget`` が所有する。``JobsTabWidget`` はそれを単一の
子として配置し、サービス注入・WorkerService シグナルの self-wire・Batch インポートの
実ロジック (ファイル選択ダイアログ / Dry-Run 選択 / 結果ダイアログ) を所有する。

== 凍結契約 ==
- コンストラクタ: ``JobsTabWidget(*, service_container, db_manager,
  dataset_state_manager, staging_state_manager, worker_service, parent=None)``
- Signal (タブ → MainWindow glue):
    - ``status_message_requested = Signal(str, int)`` — statusbar 表示 (メッセージ, ms)
    - ``batch_import_error_occurred = Signal(str)`` — Batch インポートエラー
      (MainWindow が QMessageBox 表示 + error_notification 更新)
    - ``batch_import_canceled = Signal(str)`` — Batch インポートキャンセル
      (MainWindow が ProgressStateService へ委譲, worker_id)
- スロット (MainWindow → タブ):
    - ``refresh() -> None`` — タブ表示時のジョブ一覧再読込
    - ``start_batch_import() -> None`` — File メニューからの Batch 結果インポート起動
- プロパティ (タブ内配線・テスト用):
    - ``provider_batch_job_widget`` — 内部の ProviderBatchJobWidget
"""

from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...database.db_manager import ImageDatabaseManager
from ...services.service_container import ServiceContainer
from ...utils.log import logger
from ..services.worker_service import WorkerService
from ..state.dataset_state import DatasetStateManager
from ..state.staging_state import StagingStateManager
from ..widgets.provider_batch_job_widget import ProviderBatchJobWidget


class JobsTabWidget(QWidget):
    """ジョブタブのルートウィジェット (Wireframes v11 · Jobs / Provider Batch)。

    ``ProviderBatchJobWidget`` を単一の子として配置し、サービス注入・WorkerService
    シグナル接続・Batch API 結果インポートをタブ内に閉じ込める。共有サービス
    (statusbar / error_notification / ProgressStateService) への作用は Signal で
    MainWindow へ委譲する (glue)。
    """

    status_message_requested = Signal(str, int)
    batch_import_error_occurred = Signal(str)
    batch_import_canceled = Signal(str)

    def __init__(
        self,
        *,
        service_container: ServiceContainer,
        db_manager: ImageDatabaseManager | None,
        dataset_state_manager: DatasetStateManager | None,
        staging_state_manager: StagingStateManager | None,
        worker_service: WorkerService | None,
        parent: QWidget | None = None,
    ) -> None:
        """ジョブタブを初期化する。

        Args:
            service_container: provider_batch_workflow_service / provider_batch_repo /
                annotator_library / model_repo の供給元。
            db_manager: provider_batch_repo / model_repo へのアクセス元。
            dataset_state_manager: ステージング import 用の選択 SSoT。
            staging_state_manager: Annotate タブと共有するステージング集合 (ADR 0074)。
            worker_service: 同期ジョブ台帳 (ADR 0066) / Batch インポート worker driver。
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self._service_container = service_container
        self._db_manager = db_manager
        self._dataset_state_manager = dataset_state_manager
        self._staging_state_manager = staging_state_manager
        self._worker_service = worker_service

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._provider_batch_job_widget = ProviderBatchJobWidget(parent=self)
        layout.addWidget(self._provider_batch_job_widget)

        self._setup_widget()
        self._connect_worker_signals()
        logger.info("✅ ジョブタブ (JobsTabWidget) 初期化完了")

    # -- 初期化: widget 依存注入 ----------------------------------------------

    def _setup_widget(self) -> None:
        """ProviderBatchJobWidget へサービス・状態管理を注入する。"""
        widget = self._provider_batch_job_widget
        if self._dataset_state_manager is not None:
            widget.set_dataset_state_manager(self._dataset_state_manager)
        widget.set_dependencies(
            workflow_service=self._service_container.provider_batch_workflow_service,
            repository=self._service_container.db_manager.provider_batch_repo,
            model_source=self._service_container.annotator_library,
            model_repository=self._service_container.db_manager.model_repo,
        )
        # 共有 SSoT を注入 (Annotate タブと同一の StagingStateManager を共有、ADR 0074)。
        # fan-out は staging_state_manager 側で一括接続済みのため widget シグナルは繋がない。
        if self._staging_state_manager is not None:
            widget.set_staging_state_manager(self._staging_state_manager)

    def _connect_worker_signals(self) -> None:
        """WorkerService の同期ジョブ台帳 / Batch インポートシグナルを接続する。

        worker_service はタブ生成前に初期化済みのためコンストラクタ時点で self-wire
        できる。ProgressStateService / error_notification は MainWindow が後から生成・
        所有するため、それらへの作用は Signal で MainWindow へ委譲する。
        """
        if self._worker_service is None:
            logger.warning("WorkerService未初期化 - ジョブタブの worker 接続をスキップ")
            return
        widget = self._provider_batch_job_widget
        # ADR 0066: 同期ジョブ台帳 (実行中/履歴) を Jobs タブへ接続
        widget.set_job_ledger(self._worker_service.job_ledger)
        self._worker_service.job_ledger_changed.connect(widget.refresh_sync_jobs)
        widget.sync_job_cancel_requested.connect(self._on_sync_job_cancel_requested)
        # Batch API 結果インポート worker の完了/エラー/キャンセル
        self._worker_service.batch_import_finished.connect(self._on_batch_import_finished)
        self._worker_service.batch_import_error.connect(self._on_batch_import_error)
        self._worker_service.batch_import_canceled.connect(self._on_batch_import_canceled)

    # -- プロパティ (タブ内配線・テスト用) ------------------------------------

    @property
    def provider_batch_job_widget(self) -> ProviderBatchJobWidget:
        """内部の ProviderBatchJobWidget を返す。"""
        return self._provider_batch_job_widget

    # -- スロット (MainWindow → タブ) ----------------------------------------

    @Slot()
    def refresh(self) -> None:
        """ジョブタブ表示時にジョブ一覧を再読込する。"""
        self._provider_batch_job_widget.refresh_jobs()

    # -- 同期ジョブのキャンセル (ADR 0066 §4) --------------------------------

    @Slot(str)
    def _on_sync_job_cancel_requested(self, job_id: str) -> None:
        """同期ジョブ行からのキャンセル要求を WorkerService へ委譲する (ADR 0066 §4)。

        進捗ポップアップ廃止に伴い、キャンセル操作は Jobs 行のボタンへ移設された。

        Args:
            job_id: 台帳の job_id (= worker_id)。
        """
        if self._worker_service is None:
            logger.warning("WorkerService未初期化 - ジョブキャンセルをスキップ")
            return
        if self._worker_service.cancel_job(job_id):
            self.status_message_requested.emit(f"ジョブをキャンセルしています: {job_id}", 5000)
        else:
            logger.warning(f"ジョブキャンセル要求に失敗: {job_id}")

    # -- Batch API 結果インポート --------------------------------------------

    @Slot()
    def start_batch_import(self) -> None:
        """Batch APIインポートダイアログを開いてワーカーを起動する。"""
        if self._worker_service is None:
            QMessageBox.warning(self, "エラー", "WorkerServiceが初期化されていません")
            return

        # JSONLファイル選択（複数可）
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Batch API結果ファイルを選択 (JSONL)",
            "",
            "JSONL Files (*.jsonl)",
        )
        if not file_paths:
            return

        jsonl_files = [Path(p) for p in file_paths]

        # Dry-Run確認
        dry_run_box = QMessageBox(self)
        dry_run_box.setWindowTitle("インポートモード選択")
        dry_run_box.setText(
            f"{len(jsonl_files)}ファイルをインポートします。\n\n"
            "Dry-Run: 照合結果のみ確認（DB書き込みなし）\n"
            "インポート: DBに保存"
        )
        dry_run_btn = dry_run_box.addButton("Dry-Run", QMessageBox.ButtonRole.AcceptRole)
        import_btn = dry_run_box.addButton("インポート", QMessageBox.ButtonRole.AcceptRole)
        dry_run_box.addButton("キャンセル", QMessageBox.ButtonRole.RejectRole)
        dry_run_box.exec()

        clicked = dry_run_box.clickedButton()
        if clicked is None or (clicked is not dry_run_btn and clicked is not import_btn):
            return

        dry_run = clicked is dry_run_btn
        self._worker_service.start_batch_import(jsonl_files, dry_run=dry_run)

    @Slot(object)
    def _on_batch_import_finished(self, result: Any) -> None:
        """バッチインポート完了ハンドラ。結果をダイアログで表示する。"""
        from ...services.batch_image_matcher import BatchImageMatcher
        from ...services.batch_import_service import BatchImportResult

        if not isinstance(result, BatchImportResult):
            logger.warning(f"Unexpected batch import result type: {type(result)}")
            return

        mode = "DRY-RUN" if result.saved == 0 and result.matched > 0 else "LIVE"
        message = (
            f"バッチインポート完了 ({mode})\n\n"
            f"総レコード: {result.total_records}\n"
            f"パース成功: {result.parsed_ok}\n"
            f"照合成功: {result.matched}\n"
            f"照合失敗: {result.unmatched}\n"
            f"保存: {result.saved}\n"
            f"モデル: {result.model_name}"
        )

        if result.unmatched_ids:
            message += f"\n\n照合失敗 ({len(result.unmatched_ids)}件):"
            message += "\n(custom_idから抽出したファイル名がDBに未登録)"
            for uid in result.unmatched_ids[:5]:
                stem = BatchImageMatcher.extract_stem(uid)
                message += f"\n  - {stem}  ← {uid}"
            if len(result.unmatched_ids) > 5:
                message += f"\n  ... 他 {len(result.unmatched_ids) - 5} 件"

        # コピー可能なダイアログで結果表示
        dlg = QDialog(self)
        dlg.setWindowTitle("バッチインポート結果")
        dlg.setMinimumSize(520, 360)
        layout = QVBoxLayout(dlg)
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(message)
        layout.addWidget(text_edit)
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btn_box.accepted.connect(dlg.accept)
        layout.addWidget(btn_box)
        dlg.exec()

        self.status_message_requested.emit(
            f"バッチインポート完了: {result.saved}件保存, {result.unmatched}件アンマッチ", 10000
        )

    @Slot(str)
    def _on_batch_import_error(self, error_message: str) -> None:
        """バッチインポートエラーハンドラ → MainWindow へ委譲する。"""
        self.batch_import_error_occurred.emit(error_message)

    @Slot(str)
    def _on_batch_import_canceled(self, worker_id: str) -> None:
        """バッチインポートキャンセルハンドラ → MainWindow へ委譲する（エラー通知は出さない）。"""
        self.batch_import_canceled.emit(worker_id)
