# src/lorairo/gui/workers/progress_manager.py

from typing import Optional

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import QProgressDialog, QWidget

from ...utils.log import logger
from .base import SimpleWorkerBase, WorkerProgress


class ProgressManager:
    """
    QProgressDialog を使用した進捗管理

    従来の複雑な進捗システムを PySide6 標準機能で置き換え。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        self.parent = parent
        self.progress_dialog: QProgressDialog | None = None
        self.current_worker: SimpleWorkerBase | None = None
        logger.debug("ProgressManager initialized")

    def start_worker_with_progress(
        self, worker: SimpleWorkerBase, title: str, max_value: int = 100
    ) -> None:
        """
        ワーカーを進捗ダイアログ付きで実行

        Args:
            worker: 実行するワーカー
            title: 進捗ダイアログのタイトル
            max_value: 進捗の最大値
        """
        logger.info(f"進捗付きワーカー開始: {title}")

        # プログレスダイアログ作成
        self.progress_dialog = QProgressDialog(title, "キャンセル", 0, max_value, self.parent)
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.setAutoClose(True)
        self.progress_dialog.setAutoReset(True)

        # ワーカーシグナル接続
        worker.signals.progress.connect(self._update_progress)
        worker.signals.finished.connect(self._on_finished)
        worker.signals.error.connect(self._on_error)

        # キャンセル処理
        self.progress_dialog.canceled.connect(worker.cancel)

        # 実行開始
        self.current_worker = worker
        self.progress_dialog.show()
        QThreadPool.globalInstance().start(worker)

    def _update_progress(self, progress: WorkerProgress) -> None:
        """進捗更新"""
        if self.progress_dialog:
            self.progress_dialog.setValue(progress.percentage)
            self.progress_dialog.setLabelText(progress.message)

            # 詳細情報の表示
            if progress.current_item:
                detail = f"{progress.message}\n現在: {progress.current_item}"
                if progress.total_count > 0:
                    detail += f"\n進捗: {progress.processed_count}/{progress.total_count}"
                self.progress_dialog.setLabelText(detail)

    def _on_finished(self, result) -> None:
        """完了処理"""
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None

        self.current_worker = None
        logger.info("ワーカー進捗管理完了")

    def _on_error(self, error_message: str) -> None:
        """エラー処理"""
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None

        self.current_worker = None
        logger.error(f"ワーカーエラー: {error_message}")

    def is_active(self) -> bool:
        """進捗管理中か確認"""
        return self.progress_dialog is not None and self.current_worker is not None

    def cancel_current_worker(self) -> None:
        """現在のワーカーをキャンセル"""
        if self.current_worker:
            self.current_worker.cancel()
            logger.info("現在のワーカーをキャンセル")
