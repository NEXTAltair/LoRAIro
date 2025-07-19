# src/lorairo/gui/workers/base.py

from dataclasses import dataclass
from typing import Generic, TypeVar

from PySide6.QtCore import QObject, QRunnable, Signal

from ...utils.log import logger

T = TypeVar("T")


@dataclass
class WorkerProgress:
    """ワーカー進捗情報"""

    percentage: int
    message: str
    current_item: str = ""
    processed_count: int = 0
    total_count: int = 0


class WorkerSignals(QObject):
    """ワーカー用統一シグナル"""

    progress = Signal(WorkerProgress)
    finished = Signal(object)
    error = Signal(str)


class SimpleWorkerBase(QRunnable, Generic[T]):
    """
    PySide6標準機能ベースの簡素化ワーカー

    QRunnable + QThreadPool を使用した効率的な非同期処理。
    従来の複雑な実装（164行）を30行で実現。
    """

    def __init__(self) -> None:
        super().__init__()
        self.signals = WorkerSignals()
        self._is_canceled = False
        self._worker_id = f"{self.__class__.__name__}_{id(self)}"
        logger.debug(f"ワーカー初期化: {self._worker_id}")

    def run(self) -> None:
        """QThreadPoolから呼び出される実行メソッド"""
        try:
            logger.info(f"ワーカー実行開始: {self._worker_id}")
            result = self.execute()
            if not self._is_canceled:
                self.signals.finished.emit(result)
                logger.info(f"ワーカー実行完了: {self._worker_id}")
        except Exception as e:
            error_msg = f"ワーカー実行エラー: {e}"
            logger.error(f"{self._worker_id}: {error_msg}", exc_info=True)
            self.signals.error.emit(error_msg)

    def execute(self) -> T:
        """サブクラスで実装する実際の処理"""
        raise NotImplementedError("execute() must be implemented by subclass")

    def cancel(self) -> None:
        """ワーカーキャンセル要求"""
        self._is_canceled = True
        logger.info(f"ワーカーキャンセル要求: {self._worker_id}")

    def is_canceled(self) -> bool:
        """キャンセル状態確認"""
        return self._is_canceled

    def report_progress(
        self,
        percentage: int,
        message: str,
        current_item: str = "",
        processed_count: int = 0,
        total_count: int = 0,
    ) -> None:
        """進捗報告"""
        progress = WorkerProgress(
            percentage=percentage,
            message=message,
            current_item=current_item,
            processed_count=processed_count,
            total_count=total_count,
        )
        self.signals.progress.emit(progress)
        logger.debug(f"{self._worker_id}: {percentage}% - {message}")
