# src/lorairo/services/base_worker.py
import abc
import traceback

from PySide6.QtCore import QObject, Signal

from lorairo.utils.log import logger


class BaseWorker(QObject):
    """
    非同期処理を実行するための基底ワーカクラス。

    共通のシグナル、キャンセル処理、実行ロジックの枠組みを提供します。
    具体的な処理はサブクラスで `run_task` メソッドを実装します。
    """

    finished = Signal(object)  # 完了シグナル (結果 or 例外)
    progress = Signal(int)  # 進捗シグナル (0-100)

    def __init__(self, parent: QObject | None = None) -> None:
        """
        BaseWorkerのコンストラクタ。

        Args:
            parent: 親オブジェクト。
        """
        super().__init__(parent)
        self._is_cancelled = False

    @abc.abstractmethod
    def run_task(self) -> object:
        """
        サブクラスで実装される具体的な処理。

        Returns:
            処理結果オブジェクト。エラー発生時は例外を送出する必要があります。

        Raises:
            NotImplementedError: サブクラスでこのメソッドが実装されていない場合。
            Exception: 処理中にエラーが発生した場合。
        """
        raise NotImplementedError("サブクラスはrun_taskメソッドを実装する必要があります。")

    def run(self) -> None:
        """
        ワーカースレッドのエントリポイント。
        キャンセル状態を確認し、`run_task` を実行して結果をシグナルで通知します。
        """
        logger.debug(f"{self.__class__.__name__}: Worker thread started.")
        result: object = None
        try:
            if self._is_cancelled:
                logger.info(f"{self.__class__.__name__}: タスクは開始する前にキャンセルされました。")
                # キャンセル時は特定の例外や値を返すなど、仕様に応じて変更可能
                # ここでは None を結果として finished シグナルで送る
                result = None  # Consider a specific CancelledError exception or similar
            else:
                # Execute the specific task implemented by the subclass
                result = self.run_task()

            # Check cancellation status again after task completion
            if self._is_cancelled:
                logger.info(f"{self.__class__.__name__}:完了後にタスクがキャンセルされました。")
                # If cancelled after completion, decide whether to emit the result or None/Cancelled status
                result = None  # Or handle as needed

            if result is not None:  # Avoid logging success if cancelled
                logger.info(f"{self.__class__.__name__}:タスクが正常に完了しました。")

        except Exception as e:
            logger.error(f"{self.__class__.__name__}:タスク実行中にエラーが発生しました: {e!r}")
            logger.debug(traceback.format_exc())  # デバッグのための詳細なトレースバック
            result = e  # エラー時は例外オブジェクトを結果として emit

        finally:
            # Always emit the finished signal, regardless of success, failure, or cancellation
            logger.debug(f"{self.__class__.__name__}: 完了シグナルを emit します。")
            self.finished.emit(result)
            logger.debug(f"{self.__class__.__name__}: ワーカースレッドが終了します。")

    def cancel(self) -> None:
        """タスクのキャンセルを要求します。"""
        logger.info(f"{self.__class__.__name__}: キャンセル要求されました。")
        self._is_cancelled = True
        # サブクラスはこのメソッドをオーバーライドして、特定のキャンセルロジックを追加できます。
        # (e.g., 外部プロセスの中断、I/O操作の中断など)
        # オーバーライドする場合は、必ず super().cancel() を呼び出してください。
