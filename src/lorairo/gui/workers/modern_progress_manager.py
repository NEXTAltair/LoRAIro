# src/lorairo/gui/workers/modern_progress_manager.py

"""
ModernProgressManager - ポップアップ式プログレス表示管理

QProgressDialogを使用したモーダルプログレス表示を提供し、
WorkerServiceとの統合によりワーカー進捗の視認性を大幅に改善します。
"""

from typing import Optional
from uuid import uuid4

from loguru import logger
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QProgressDialog, QWidget

from .base import WorkerProgress, WorkerStatus


class ModernProgressManager(QObject):
    """
    ポップアップ式プログレス表示管理クラス

    特徴:
    - QProgressDialog基盤のモーダル表示
    - ワーカーID管理とキャンセレーション
    - WorkerServiceとの統合インターフェース
    - 自動リソース管理
    """

    # WorkerServiceに転送するシグナル
    cancellation_requested = Signal(str)  # worker_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._progress_dialogs: dict[str, QProgressDialog] = {}
        self._active_workers: dict[str, str] = {}  # worker_id -> operation_name
        self._cleanup_timer = QTimer()
        self._cleanup_timer.setSingleShot(True)
        self._cleanup_timer.timeout.connect(self._cleanup_completed_dialogs)

    def start_worker_progress(
        self,
        worker_id: str,
        operation_name: str,
        initial_message: str = "処理を開始しています...",
        parent: QWidget | None = None,
    ) -> None:
        """
        ワーカー用プログレスダイアログ開始

        Args:
            worker_id: ワーカー識別子
            operation_name: 操作名（キャンセルボタンラベル用）
            initial_message: 初期メッセージ
            parent: 親ウィジェット
        """
        if worker_id in self._progress_dialogs:
            logger.warning(f"既存のプログレスダイアログを置換: {worker_id}")
            self._close_dialog(worker_id)

        # QProgressDialog作成
        dialog = QProgressDialog(parent or self.parent())
        dialog.setWindowTitle(f"LoRAIro - {operation_name}")
        dialog.setLabelText(initial_message)
        dialog.setMinimum(0)
        dialog.setMaximum(100)
        dialog.setValue(0)
        dialog.setCancelButtonText("キャンセル")
        dialog.setModal(True)
        dialog.setMinimumDuration(500)  # 500ms後に表示

        # キャンセル処理
        dialog.canceled.connect(lambda: self._on_cancel_requested(worker_id))

        # 管理データ登録
        self._progress_dialogs[worker_id] = dialog
        self._active_workers[worker_id] = operation_name

        logger.info(f"プログレスダイアログ開始: {operation_name} (ID: {worker_id})")

    def update_worker_progress(self, worker_id: str, progress: WorkerProgress) -> None:
        """
        ワーカー進捗更新

        Args:
            worker_id: ワーカー識別子
            progress: 進捗情報
        """
        dialog = self._progress_dialogs.get(worker_id)
        if not dialog:
            logger.debug(f"プログレスダイアログが見つかりません: {worker_id}")
            return

        # プログレス値更新
        dialog.setValue(progress.percentage)

        # メッセージ構築
        if progress.total_count > 0:
            detail_text = f"({progress.processed_count}/{progress.total_count})"
            if progress.current_item:
                detail_text += f" - {progress.current_item}"
            message = f"{progress.status_message} {detail_text}"
        else:
            message = progress.status_message

        dialog.setLabelText(message)

        logger.debug(f"プログレス更新: {worker_id} - {progress.percentage}% - {message}")

    def update_batch_progress(self, worker_id: str, current: int, total: int, filename: str) -> None:
        """
        バッチ進捗更新

        Args:
            worker_id: ワーカー識別子
            current: 現在の処理数
            total: 総処理数
            filename: 現在のファイル名
        """
        dialog = self._progress_dialogs.get(worker_id)
        if not dialog:
            return

        percentage = int((current / total) * 100) if total > 0 else 0
        dialog.setValue(percentage)

        message = f"処理中 ({current}/{total}) - {filename}"
        dialog.setLabelText(message)

        logger.debug(f"バッチ進捗更新: {worker_id} - {current}/{total} - {filename}")

    def finish_worker_progress(self, worker_id: str, success: bool = True) -> None:
        """
        ワーカー完了処理

        Args:
            worker_id: ワーカー識別子
            success: 成功フラグ
        """
        dialog = self._progress_dialogs.get(worker_id)
        if not dialog:
            return

        operation_name = self._active_workers.get(worker_id, "不明な操作")

        if success:
            dialog.setValue(100)
            dialog.setLabelText("完了しました")
            logger.info(f"プログレス完了: {operation_name} (ID: {worker_id})")
        else:
            dialog.setLabelText("処理が中断されました")
            logger.warning(f"プログレス中断: {operation_name} (ID: {worker_id})")

        # 完了後は即座にキャンセルボタンを無効化してクラッシュを防止
        dialog.setCancelButton(None)
        logger.debug(f"キャンセルボタン無効化完了: {worker_id}")

        # 短時間表示後にクリーンアップ
        self._cleanup_timer.start(1000)  # 1秒後

    def cancel_worker_progress(self, worker_id: str) -> None:
        """
        ワーカープログレス強制終了

        Args:
            worker_id: ワーカー識別子
        """
        self._close_dialog(worker_id)

    def _on_cancel_requested(self, worker_id: str) -> None:
        """キャンセル要求処理"""
        # Qt イベントキュー遅延による完了後キャンセル要求をガード
        if worker_id not in self._active_workers:
            logger.debug(f"遅延キャンセル要求を無視: {worker_id} (既にワーカー完了)")
            return

        operation_name = self._active_workers.get(worker_id, "不明な操作")
        logger.info(f"キャンセル要求: {operation_name} (ID: {worker_id})")

        # WorkerServiceに転送
        self.cancellation_requested.emit(worker_id)

        # ダイアログ更新
        dialog = self._progress_dialogs.get(worker_id)
        if dialog:
            dialog.setLabelText("キャンセル処理中...")
            dialog.setCancelButton(None)  # キャンセルボタン無効化  # キャンセルボタン無効化

    def _close_dialog(self, worker_id: str) -> None:
        """ダイアログクローズとリソース解放"""
        dialog = self._progress_dialogs.pop(worker_id, None)
        self._active_workers.pop(worker_id, None)

        if dialog:
            dialog.close()
            dialog.deleteLater()

    def _cleanup_completed_dialogs(self) -> None:
        """完了済みダイアログの遅延クリーンアップ"""
        completed_workers = []

        for worker_id, dialog in self._progress_dialogs.items():
            if dialog.value() >= 100 or not dialog.isVisible():
                completed_workers.append(worker_id)

        for worker_id in completed_workers:
            self._close_dialog(worker_id)

        if completed_workers:
            logger.debug(f"完了済みダイアログをクリーンアップ: {len(completed_workers)}件")

    def has_active_progress(self, worker_id: str) -> bool:
        """アクティブプログレス確認"""
        return worker_id in self._progress_dialogs

    def get_active_worker_count(self) -> int:
        """アクティブワーカー数取得"""
        return len(self._progress_dialogs)

    def close_all_dialogs(self) -> None:
        """全ダイアログ強制終了"""
        worker_ids = list(self._progress_dialogs.keys())
        for worker_id in worker_ids:
            self._close_dialog(worker_id)

        logger.info(f"全プログレスダイアログを終了: {len(worker_ids)}件")


def create_worker_id(prefix: str = "worker") -> str:
    """
    ワーカーID生成ユーティリティ

    Args:
        prefix: ID接頭辞

    Returns:
        一意なワーカーID
    """
    return f"{prefix}_{uuid4().hex[:8]}"
