# src/lorairo/workers/manager.py

from PySide6.QtCore import QObject, QThread, Signal

from ...utils.log import logger
from .base import LoRAIroWorkerBase


class WorkerManager(QObject):
    """
    ワーカーの生成・管理を担当するマネージャー。
    複数ワーカーの並行実行、リソース管理、ライフサイクル制御を行う。
    """

    # === ワーカー管理シグナル ===
    worker_started = Signal(str)  # worker_id
    worker_finished = Signal(str, object)  # worker_id, result
    worker_error = Signal(str, str)  # worker_id, error_message
    worker_canceled = Signal(str)  # worker_id

    # === 全体管理シグナル ===
    all_workers_finished = Signal()
    active_worker_count_changed = Signal(int)  # active_count

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.active_workers: dict[str, dict[str, Any]] = {}
        logger.debug("WorkerManager initialized")

    # === Worker Management ===

    def start_worker(
        self,
        worker_id: str,
        worker: LoRAIroWorkerBase[Any],
        auto_cleanup: bool = True,
    ) -> bool:
        """
        ワーカーを新しいスレッドで開始

        Args:
            worker_id: 一意のワーカーID
            worker: 実行するワーカーインスタンス
            auto_cleanup: 完了時の自動クリーンアップ

        Returns:
            bool: 開始成功/失敗
        """
        if worker_id in self.active_workers:
            logger.warning(f"ワーカー {worker_id} は既に実行中です")
            return False

        # スレッド作成・設定
        thread = QThread()
        worker.moveToThread(thread)

        # シグナル接続
        thread.started.connect(worker.run)
        worker.finished.connect(lambda result: self._on_worker_finished(worker_id, result))
        worker.error_occurred.connect(lambda error: self._on_worker_error(worker_id, error))

        if auto_cleanup:
            worker.finished.connect(thread.quit)
            worker.finished.connect(worker.deleteLater)
            worker.error_occurred.connect(thread.quit)
            worker.error_occurred.connect(worker.deleteLater)
            # スレッドの適切な終了処理
            thread.finished.connect(lambda: self._cleanup_thread(worker_id, thread))
            thread.finished.connect(thread.deleteLater)

        # ワーカー登録・開始
        self.active_workers[worker_id] = {
            "worker": worker,
            "thread": thread,
            "auto_cleanup": auto_cleanup,
        }

        thread.start()
        self.worker_started.emit(worker_id)
        self.active_worker_count_changed.emit(len(self.active_workers))

        logger.info(f"ワーカー開始: {worker_id} ({worker.__class__.__name__})")
        return True

    def cancel_worker(self, worker_id: str) -> bool:
        """
        指定ワーカーをキャンセル

        Args:
            worker_id: キャンセルするワーカーID

        Returns:
            bool: キャンセル成功/失敗
        """
        if worker_id not in self.active_workers:
            logger.warning(f"ワーカー {worker_id} が見つかりません")
            return False

        worker_info = self.active_workers[worker_id]
        worker_info["worker"].cancel()

        # スレッドの適切な終了
        thread = worker_info["thread"]
        if thread.isRunning():
            thread.quit()
            if not thread.wait(2000):  # 2秒待機
                logger.warning(f"キャンセルされたワーカーの終了タイムアウト: {worker_id}")
                thread.terminate()
                thread.wait(1000)  # 強制終了後も1秒待機

        self.worker_canceled.emit(worker_id)

        logger.info(f"ワーカーキャンセル: {worker_id}")
        return True

    def cancel_all_workers(self) -> None:
        """全ワーカーをキャンセル"""
        worker_ids = list(self.active_workers.keys())
        for worker_id in worker_ids:
            self.cancel_worker(worker_id)

        logger.info(f"全ワーカーキャンセル: {len(worker_ids)}個")

    def is_worker_active(self, worker_id: str) -> bool:
        """ワーカーがアクティブかチェック"""
        return worker_id in self.active_workers

    def get_active_worker_count(self) -> int:
        """アクティブワーカー数を取得"""
        return len(self.active_workers)

    def get_active_worker_ids(self) -> list[str]:
        """アクティブワーカーIDリストを取得"""
        return list(self.active_workers.keys())

    def get_worker(self, worker_id: str) -> LoRAIroWorkerBase[Any] | None:
        """ワーカーインスタンスを取得"""
        worker_info = self.active_workers.get(worker_id)
        return worker_info["worker"] if worker_info else None

    # === Manual Cleanup ===

    def cleanup_worker(self, worker_id: str) -> bool:
        """
        ワーカーを手動クリーンアップ

        Args:
            worker_id: クリーンアップするワーカーID

        Returns:
            bool: クリーンアップ成功/失敗
        """
        if worker_id not in self.active_workers:
            return False

        worker_info = self.active_workers.pop(worker_id)
        thread = worker_info["thread"]
        worker = worker_info["worker"]

        # スレッド終了待機
        if thread.isRunning():
            thread.quit()
            thread.wait(3000)  # 3秒でタイムアウト

        # リソース解放
        worker.deleteLater()
        thread.deleteLater()

        self.active_worker_count_changed.emit(len(self.active_workers))
        logger.debug(f"ワーカークリーンアップ: {worker_id}")
        return True

    def cleanup_all_workers(self) -> None:
        """全ワーカーをクリーンアップ"""
        worker_ids = list(self.active_workers.keys())
        for worker_id in worker_ids:
            self.cleanup_worker(worker_id)

        logger.info(f"全ワーカークリーンアップ: {len(worker_ids)}個")

    # === Private Event Handlers ===

    def _on_worker_finished(self, worker_id: str, result: Any) -> None:
        """ワーカー完了イベントハンドラー"""
        if worker_id in self.active_workers:
            worker_info = self.active_workers.pop(worker_id)
            self.worker_finished.emit(worker_id, result)
            self.active_worker_count_changed.emit(len(self.active_workers))

            # 全ワーカー完了チェック
            if len(self.active_workers) == 0:
                self.all_workers_finished.emit()

            logger.info(f"ワーカー完了: {worker_id}")

    def _cleanup_thread(self, worker_id: str, thread: QThread) -> None:
        """スレッドのクリーンアップ処理"""
        try:
            if thread.isRunning():
                # スレッドが まだ実行中の場合は適切に終了を待機
                if not thread.wait(1000):  # 1秒待機
                    logger.warning(f"スレッド終了タイムアウト: {worker_id}")
                    thread.terminate()
                    thread.wait(1000)  # 強制終了後も1秒待機
            logger.debug(f"スレッドクリーンアップ完了: {worker_id}")
        except Exception as cleanup_error:
            logger.error(f"スレッドクリーンアップエラー ({worker_id}): {cleanup_error}")

    def _on_worker_error(self, worker_id: str, error: str) -> None:
        """ワーカーエラーイベントハンドラー"""
        if worker_id in self.active_workers:
            worker_info = self.active_workers.pop(worker_id)
            self.worker_error.emit(worker_id, error)
            self.active_worker_count_changed.emit(len(self.active_workers))

            # 全ワーカー完了チェック
            if len(self.active_workers) == 0:
                self.all_workers_finished.emit()

            logger.error(f"ワーカーエラー: {worker_id} - {error}")

    # === Utility Methods ===

    def wait_for_all_workers(self, timeout_ms: int = 30000) -> bool:
        """
        全ワーカーの完了を待機

        Args:
            timeout_ms: タイムアウト時間（ミリ秒）

        Returns:
            bool: 全ワーカー完了/タイムアウト
        """
        if len(self.active_workers) == 0:
            return True

        # 全ワーカーのスレッド終了を待機
        for worker_info in self.active_workers.values():
            thread = worker_info["thread"]
            if thread.isRunning():
                if not thread.wait(timeout_ms):
                    logger.warning("ワーカースレッド終了タイムアウト")
                    return False

        return True

    def get_worker_summary(self) -> dict[str, Any]:
        """ワーカー状態サマリーを取得"""
        return {
            "active_worker_count": len(self.active_workers),
            "active_worker_ids": list(self.active_workers.keys()),
            "worker_details": {
                worker_id: {
                    "class_name": worker_info["worker"].__class__.__name__,
                    "status": worker_info["worker"].status.value,
                    "auto_cleanup": worker_info["auto_cleanup"],
                }
                for worker_id, worker_info in self.active_workers.items()
            },
        }
