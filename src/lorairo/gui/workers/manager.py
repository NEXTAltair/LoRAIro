# src/lorairo/workers/manager.py

from typing import Any

from PySide6.QtCore import QCoreApplication, QObject, QThread, Signal

from ...utils.log import logger
from .base import LoRAIroWorkerBase
from .terminal import CancelReason, WorkerOutcome, WorkerTerminalEvent


class WorkerManager(QObject):
    """
    ワーカーの生成・管理を担当するマネージャー。
    複数ワーカーの並行実行、リソース管理、ライフサイクル制御を行う。
    """

    # === ワーカー管理シグナル ===
    worker_started = Signal(str)  # worker_id
    # Compatibility signals derived from worker_terminal. New code should consume
    # worker_terminal so it can inspect outcome and cancel_reason.
    worker_finished = Signal(str, object)  # worker_id, result
    worker_error = Signal(str, str)  # worker_id, error_message
    worker_canceled = Signal(str)  # worker_id
    worker_terminal = Signal(object)  # WorkerTerminalEvent

    _CANCEL_GRACE_MS = 2000
    _CANCEL_DRAIN_GRACE_MS = 250
    _TERMINATE_WAIT_MS = 1000
    _CLEANUP_GRACE_MS = 1000

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
        worker.canceled.connect(lambda: self._on_worker_canceled(worker_id))

        if auto_cleanup:
            worker.finished.connect(thread.quit)
            worker.finished.connect(worker.deleteLater)
            worker.error_occurred.connect(thread.quit)
            worker.error_occurred.connect(worker.deleteLater)
            worker.canceled.connect(thread.quit)
            worker.canceled.connect(worker.deleteLater)
            # スレッドの適切な終了処理
            thread.finished.connect(lambda: self._cleanup_thread(worker_id, thread))
            thread.finished.connect(thread.deleteLater)

        # ワーカー登録・開始
        self.active_workers[worker_id] = {
            "worker": worker,
            "thread": thread,
            "auto_cleanup": auto_cleanup,
            "cancel_reason": None,
            "terminal_emitted": False,
            "unresponsive": False,
        }

        thread.start()
        self.worker_started.emit(worker_id)
        self.active_worker_count_changed.emit(len(self.active_workers))

        logger.debug(f"ワーカー開始: {worker_id} ({worker.__class__.__name__})")
        return True

    def cancel_worker(
        self,
        worker_id: str,
        reason: CancelReason = CancelReason.USER_REQUESTED,
    ) -> bool:
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
        worker_info["cancel_reason"] = reason
        worker_info["worker"].cancel()

        # スレッドの適切な終了
        thread = worker_info["thread"]
        if thread.isRunning():
            thread.quit()
            if thread.wait(self._CANCEL_GRACE_MS):
                self._finalize_canceled_if_no_terminal_signal(worker_id)
            else:
                logger.warning(
                    f"キャンセルされたワーカーの終了待機がタイムアウト: {worker_id}; "
                    "queued terminal event を確認して cooperative wait を延長します"
                )
                self._process_pending_events()
                if worker_id not in self.active_workers:
                    logger.info(f"キャンセル中の queued terminal event を優先しました: {worker_id}")
                elif thread.wait(self._CANCEL_DRAIN_GRACE_MS):
                    self._finalize_canceled_if_no_terminal_signal(worker_id)
                elif self._terminate_thread_last_resort(worker_id, thread):
                    self._finalize_canceled_if_no_terminal_signal(
                        worker_id,
                        fallback_outcome=WorkerOutcome.TERMINATED,
                        fallback_error=f"ワーカーを強制終了しました: {worker_id}",
                    )
                else:
                    logger.error(f"キャンセルされたワーカーの強制終了失敗: {worker_id}")
                    self._mark_worker_unresponsive(
                        worker_id,
                        error=f"ワーカー強制終了後も停止確認できませんでした: {worker_id}",
                        cancel_reason=reason,
                    )
        else:
            self._finalize_canceled_if_no_terminal_signal(worker_id)

        logger.debug(f"ワーカーキャンセル: {worker_id} (理由: {reason.value})")
        return True

    def cancel_all_workers(self, reason: CancelReason = CancelReason.SHUTDOWN) -> None:
        """全ワーカーをキャンセル"""
        worker_ids = list(self.active_workers.keys())
        for worker_id in worker_ids:
            self.cancel_worker(worker_id, reason=reason)

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
        if self._finalize_terminal(worker_id, WorkerOutcome.SUCCEEDED, result=result):
            logger.debug(f"ワーカー完了: {worker_id}")

    def _cleanup_thread(self, worker_id: str, thread: QThread) -> None:
        """スレッドのクリーンアップ処理"""
        try:
            if thread.isRunning():
                # スレッドが まだ実行中の場合は適切に終了を待機
                if not thread.wait(self._CLEANUP_GRACE_MS):
                    logger.warning(f"スレッド終了タイムアウト: {worker_id}")
                    self._terminate_thread_last_resort(worker_id, thread)
            logger.debug(f"スレッドクリーンアップ完了: {worker_id}")
        except Exception as cleanup_error:
            logger.error(f"スレッドクリーンアップエラー ({worker_id}): {cleanup_error}")

    def _on_worker_error(self, worker_id: str, error: str) -> None:
        """ワーカーエラーイベントハンドラー"""
        if self._finalize_terminal(worker_id, WorkerOutcome.FAILED, error=error):
            logger.error(f"ワーカーエラー: {worker_id} - {error}")

    def _on_worker_canceled(self, worker_id: str) -> None:
        """ワーカーキャンセル完了イベントハンドラー"""
        cancel_reason = self._get_cancel_reason(worker_id)
        if self._finalize_terminal(
            worker_id,
            WorkerOutcome.CANCELED,
            cancel_reason=cancel_reason,
        ):
            # ユーザーが明示的にキャンセルした場合のみ INFO。内部的な置換
            # (SEARCH_REPLACED 等) は運用ログを汚さないよう DEBUG に留める。
            if cancel_reason == CancelReason.USER_REQUESTED:
                logger.info(f"ユーザー操作でワーカーをキャンセル: {worker_id}")
            else:
                reason_label = cancel_reason.value if cancel_reason else "unknown"
                logger.debug(f"ワーカーキャンセル完了: {worker_id} (理由: {reason_label})")

    def _finalize_canceled_if_no_terminal_signal(
        self,
        worker_id: str,
        *,
        fallback_outcome: WorkerOutcome = WorkerOutcome.CANCELED,
        fallback_error: str | None = None,
    ) -> None:
        """queued terminal signal を優先し、未確定なら cancel fallback で終端する。"""
        self._process_pending_events()

        if worker_id in self.active_workers:
            self._finalize_terminal(
                worker_id,
                fallback_outcome,
                error=fallback_error,
                cancel_reason=self._get_cancel_reason(worker_id),
            )

    def _process_pending_events(self) -> None:
        """Process queued Qt signals before falling back to synthetic terminal outcomes."""
        app = QCoreApplication.instance()
        if app is not None:
            app.processEvents()

    def _terminate_thread_last_resort(self, worker_id: str, thread: QThread) -> bool:
        """Terminate a thread only after cooperative cancellation and queued events did not finish it."""
        logger.error(f"最終手段としてワーカースレッドを強制終了します: {worker_id}")
        thread.terminate()
        stopped = thread.wait(self._TERMINATE_WAIT_MS)
        if stopped:
            logger.warning(f"ワーカー強制終了後に停止確認: {worker_id}")
        else:
            logger.error(f"ワーカー強制終了後も停止確認できません: {worker_id}")
        return stopped

    def _finalize_terminal(
        self,
        worker_id: str,
        outcome: WorkerOutcome,
        *,
        result: Any | None = None,
        error: str | None = None,
        cancel_reason: CancelReason | None = None,
    ) -> bool:
        """Emit exactly one worker fact terminal event and derived compatibility signals."""
        worker_info = self.active_workers.get(worker_id)
        if worker_info is None:
            return False

        worker_type = self._resolve_worker_type(worker_id)
        if cancel_reason is None:
            cancel_reason = worker_info.get("cancel_reason")

        if worker_info.get("terminal_emitted"):
            self._pop_active_worker(worker_id)
            return False

        event = WorkerTerminalEvent(
            worker_id=worker_id,
            worker_type=worker_type,
            outcome=outcome,
            result=result,
            error=error,
            cancel_reason=cancel_reason,
        )
        if not self._emit_terminal_once(worker_id, event):
            return False

        if not self._pop_active_worker(worker_id):
            return False

        self._emit_compat_terminal_signal(event)

        return True

    def _mark_worker_unresponsive(
        self,
        worker_id: str,
        *,
        error: str,
        cancel_reason: CancelReason | None = None,
    ) -> bool:
        """Emit an abnormal observation but keep the still-running worker tracked."""
        worker_info = self.active_workers.get(worker_id)
        if worker_info is None:
            return False

        worker_info["unresponsive"] = True
        worker_type = self._resolve_worker_type(worker_id)
        if cancel_reason is None:
            cancel_reason = worker_info.get("cancel_reason")

        event = WorkerTerminalEvent(
            worker_id=worker_id,
            worker_type=worker_type,
            outcome=WorkerOutcome.UNRESPONSIVE,
            error=error,
            cancel_reason=cancel_reason,
        )
        if not self._emit_terminal_once(worker_id, event):
            return False

        self._emit_compat_terminal_signal(event)
        return True

    def _emit_terminal_once(self, worker_id: str, event: WorkerTerminalEvent) -> bool:
        worker_info = self.active_workers.get(worker_id)
        if worker_info is None or worker_info.get("terminal_emitted"):
            return False

        worker_info["terminal_emitted"] = True
        self.worker_terminal.emit(event)
        return True

    def _emit_compat_terminal_signal(self, event: WorkerTerminalEvent) -> None:
        """Emit legacy manager signals from the canonical worker terminal fact."""
        if event.outcome is WorkerOutcome.SUCCEEDED:
            self.worker_finished.emit(event.worker_id, event.result)
        elif event.outcome is WorkerOutcome.CANCELED:
            self.worker_canceled.emit(event.worker_id)
        else:
            self.worker_error.emit(
                event.worker_id,
                event.error or f"ワーカー異常終了: {event.outcome.value}",
            )

    def _get_cancel_reason(self, worker_id: str) -> CancelReason | None:
        worker_info = self.active_workers.get(worker_id)
        return worker_info.get("cancel_reason") if worker_info else None

    def _resolve_worker_type(self, worker_id: str) -> str:
        for prefix in ("batch_reg_", "batch_import_", "annotation_", "search_", "thumbnail_"):
            if worker_id.startswith(prefix):
                return prefix.rstrip("_")
        return "unknown"

    def _pop_active_worker(self, worker_id: str) -> bool:
        """ワーカー終端を一度だけ確定し、管理状態を更新する。"""
        if worker_id not in self.active_workers:
            return False

        self.active_workers.pop(worker_id)
        self.active_worker_count_changed.emit(len(self.active_workers))

        if len(self.active_workers) == 0:
            self.all_workers_finished.emit()

        return True

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
                    "unresponsive": worker_info.get("unresponsive", False),
                }
                for worker_id, worker_info in self.active_workers.items()
            },
        }
