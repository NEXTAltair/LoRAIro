# src/lorairo/workers/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Generic, TypeVar

from PySide6.QtCore import QObject, Signal

from ...utils.log import logger

T = TypeVar("T")


class WorkerStatus(Enum):
    """ワーカー状態定義"""

    IDLE = "idle"
    RUNNING = "running"
    CANCELING = "canceling"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class WorkerProgress:
    """ワーカー進捗情報"""

    percentage: int
    status_message: str
    current_item: str = ""
    processed_count: int = 0
    total_count: int = 0


class CancellationController:
    """キャンセル制御クラス"""

    def __init__(self):
        self._is_canceled = False

    def cancel(self) -> None:
        """キャンセル要求"""
        self._is_canceled = True

    def is_canceled(self) -> bool:
        """キャンセル状態確認"""
        return self._is_canceled

    def reset(self) -> None:
        """キャンセル状態リセット"""
        self._is_canceled = False


class ProgressReporter(QObject):
    """進捗報告クラス"""

    progress_updated = Signal(WorkerProgress)
    batch_progress = Signal(int, int, str)  # current, total, filename

    def report(self, progress: WorkerProgress) -> None:
        """進捗報告"""
        self.progress_updated.emit(progress)

    def report_batch(self, current: int, total: int, filename: str) -> None:
        """バッチ進捗報告"""
        self.batch_progress.emit(current, total, filename)


class LoRAIroWorkerBase(QObject, Generic[T]):
    """
    LoRAIro専用ワーカー基底クラス。
    コマンドパターン + コンポジションによる設計。
    """

    # === 統一シグナル ===
    progress_updated = Signal(WorkerProgress)
    batch_progress = Signal(int, int, str)
    status_changed = Signal(WorkerStatus)
    finished = Signal(object)  # result: T
    error_occurred = Signal(str)

    def __init__(self):
        super().__init__()
        self.cancellation = CancellationController()
        self.progress = ProgressReporter()
        self.status = WorkerStatus.IDLE

        # 内部シグナル接続
        self.progress.progress_updated.connect(self.progress_updated)
        self.progress.batch_progress.connect(self.batch_progress)

    @abstractmethod
    def execute(self) -> T:
        """
        実際の処理実行（サブクラスで実装）

        Returns:
            T: 処理結果
        """
        pass

    def run(self) -> None:
        """
        QThread.started に接続される実行メソッド
        """
        try:
            self._set_status(WorkerStatus.RUNNING)
            logger.info(f"ワーカー実行開始: {self.__class__.__name__}")

            result = self.execute()

            if not self.cancellation.is_canceled():
                self._set_status(WorkerStatus.COMPLETED)
                self.finished.emit(result)
                logger.info(f"ワーカー実行完了: {self.__class__.__name__}")
            else:
                logger.info(f"ワーカー実行キャンセル: {self.__class__.__name__}")

        except Exception as e:
            self._set_status(WorkerStatus.FAILED)
            error_msg = f"ワーカー実行エラー: {e!s}"
            logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)

    def cancel(self) -> None:
        """ワーカーキャンセル要求"""
        self._set_status(WorkerStatus.CANCELING)
        self.cancellation.cancel()
        logger.info(f"ワーカーキャンセル要求: {self.__class__.__name__}")

    def _set_status(self, status: WorkerStatus) -> None:
        """ステータス更新"""
        if self.status != status:
            self.status = status
            self.status_changed.emit(status)

    def _check_cancellation(self) -> None:
        """キャンセルチェック（サブクラスで使用）"""
        if self.cancellation.is_canceled():
            raise RuntimeError("処理がキャンセルされました")

    def _report_progress(
        self,
        percentage: int,
        status_message: str,
        current_item: str = "",
        processed_count: int = 0,
        total_count: int = 0,
    ) -> None:
        """進捗報告ヘルパー"""
        progress = WorkerProgress(
            percentage=percentage,
            status_message=status_message,
            current_item=current_item,
            processed_count=processed_count,
            total_count=total_count,
        )
        self.progress.report(progress)

    def _report_batch_progress(self, current: int, total: int, filename: str) -> None:
        """バッチ進捗報告ヘルパー"""
        self.progress.report_batch(current, total, filename)


# Alias for backward compatibility with import statements
SimpleWorkerBase = LoRAIroWorkerBase
