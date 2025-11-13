"""進捗状態管理サービス

Worker進捗表示とステータスバー更新の統一管理を担当。
MainWindowから分離し、進捗管理ロジックを集約。

Phase 2.6 Stage 1で作成。
"""

from typing import Any

from loguru import logger
from PySide6.QtWidgets import QStatusBar


class ProgressStateService:
    """進捗状態管理サービス

    Worker進捗管理、バッチ処理進捗、ステータスバー更新を統一管理。
    MainWindowから進捗管理ロジックを分離。

    Phase 2.6 Stage 1で作成。
    """

    def __init__(self, status_bar: QStatusBar | None = None):
        """初期化

        Args:
            status_bar: ステータスバー（進捗表示に使用）
        """
        self.status_bar = status_bar

    # ============================================================
    # Phase 2.6 Stage 1: バッチ登録進捗管理
    # ============================================================

    def on_batch_registration_started(self, worker_id: str) -> None:
        """バッチ登録開始時の進捗表示

        Args:
            worker_id: ワーカーID

        Phase 2.6 Stage 1で実装。
        """
        logger.info(f"バッチ登録開始: worker_id={worker_id}")

        # UI feedback - show user that processing has started
        if self.status_bar:
            try:
                self.status_bar.showMessage("データベース登録処理を開始しています...")
            except Exception as e:
                logger.debug(f"Status bar update failed: {e}")

    def on_batch_registration_error(self, error_message: str) -> None:
        """バッチ登録エラー時の進捗表示

        Args:
            error_message: エラーメッセージ

        Phase 2.6 Stage 1で実装。

        Note:
            QMessageBoxは呼び出し側（MainWindow）で表示する。
            このServiceはステータスバー更新のみ担当。
        """
        logger.error(f"バッチ登録エラー: {error_message}")

        if self.status_bar:
            try:
                self.status_bar.showMessage(f"バッチ登録エラー: {error_message}", 8000)
            except Exception as e:
                logger.debug(f"Status bar update failed: {e}")

    # ============================================================
    # Phase 2.6 Stage 1: Worker進捗管理
    # ============================================================

    def on_worker_progress_updated(self, worker_id: str, progress: Any) -> None:
        """Worker進捗更新時のステータスバー表示

        Args:
            worker_id: ワーカーID
            progress: 進捗情報（current, total属性を持つオブジェクト）

        Phase 2.6 Stage 1で実装。
        """
        if not self.status_bar:
            return

        try:
            # Extract progress information
            if hasattr(progress, "current") and hasattr(progress, "total"):
                current = progress.current
                total = progress.total
                percentage = int((current / total) * 100) if total > 0 else 0

                # Update status bar with progress
                status_message = f"処理中... {current}/{total} ({percentage}%)"
                self.status_bar.showMessage(status_message)

                logger.debug(f"ワーカー進捗更新: {worker_id} - {current}/{total} ({percentage}%)")

            else:
                logger.debug(f"ワーカー進捗更新: {worker_id} - {progress}")

        except Exception as e:
            logger.warning(f"進捗更新処理エラー: {e}")

    def on_worker_batch_progress(
        self, worker_id: str, current: int, total: int, filename: str
    ) -> None:
        """Workerバッチ進捗更新時のステータスバー表示

        Args:
            worker_id: ワーカーID
            current: 現在の処理数
            total: 総処理数
            filename: 処理中のファイル名

        Phase 2.6 Stage 1で実装。
        """
        if not self.status_bar:
            return

        try:
            percentage = int((current / total) * 100) if total > 0 else 0

            # Update status bar with detailed batch progress
            status_message = f"バッチ処理中... {current}/{total} ({percentage}%) - {filename}"
            self.status_bar.showMessage(status_message)

            logger.debug(
                f"バッチ進捗更新: {worker_id} - {current}/{total} ({percentage}%) - {filename}"
            )

        except Exception as e:
            logger.warning(f"バッチ進捗更新処理エラー: {e}")

    # ============================================================
    # Phase 2.6 Stage 1: アノテーション進捗管理
    # ============================================================

    def on_batch_annotation_started(self, total_images: int) -> None:
        """バッチアノテーション開始時の進捗表示

        Args:
            total_images: 総画像数

        Phase 2.6 Stage 1で実装。
        """
        try:
            logger.info(f"バッチアノテーション開始: {total_images}画像")

            # ステータスバー表示
            if self.status_bar:
                self.status_bar.showMessage(f"アノテーション処理開始: {total_images}画像を処理中...", 10000)

        except Exception as e:
            logger.error(f"バッチ開始ハンドラエラー: {e}", exc_info=True)

    def on_batch_annotation_progress(self, processed: int, total: int) -> None:
        """バッチアノテーション進捗更新時のステータスバー表示

        Args:
            processed: 処理済み画像数
            total: 総画像数

        Phase 2.6 Stage 1で実装。
        """
        if not self.status_bar:
            return

        try:
            percentage = int((processed / total) * 100) if total > 0 else 0

            # ステータスバー更新
            self.status_bar.showMessage(f"アノテーション処理中... {processed}/{total} ({percentage}%)")

            logger.info(f"バッチアノテーション進捗: {processed}/{total} ({percentage}%)")

        except Exception as e:
            logger.error(f"バッチ進捗ハンドラエラー: {e}", exc_info=True)
