import inspect

from PySide6.QtWidgets import QDialog
from PySide6.QtCore import Qt, Signal, Slot, QThread, QObject

from gui_file.ProgressWidget_ui import Ui_ProgressWidget

from module.log import get_logger

class ProgressWidget(QDialog, Ui_ProgressWidget):
    """
    処理の進捗状況を表示するダイアログウィジェット。

    Attributes:
        canceled (Signal): キャンセルボタンがクリックされたときに発行されるシグナル。
        logger (Logger): ロガーオブジェクト。

    Signals:
        canceled: キャンセルボタンクリック時に発行されるシグナル。

    Methods:
        update_status(status: str): ステータスラベルのテキストを更新する。
        update_progress(value: int): プログレスバーの値を更新する。
    """
    canceled = Signal()

    def __init__(self, parent=None):
        """ProgressWidgetの初期化"""
        super().__init__(parent, Qt.Dialog)  # 親ウィジェットとダイアログフラグを設定して初期化
        self.logger = get_logger("ProgressWidget")
        self.setupUi(self)
        self.setModal(True)  # モーダルに設定して他の操作を受け付けないようにする
        self.logger.debug("ProgressWidget initialized")

    @Slot()
    def on_cancelButton_clicked(self):
        """キャンセルボタンがクリックされたときの処理"""
        self.logger.debug("Cancel button clicked")
        self.canceled.emit()  # canceledシグナルを発行

    @Slot(str)
    def update_status(self, status):
        """
        ステータスラベルのテキストを更新する。

        Args:
            status (str): 新しいステータステキスト。
        """
        self.statusLabel.setText(status)

    @Slot(int)
    def update_progress(self, value):
        """
        プログレスバーの値を更新する。

        Args:
            value (int): プログレスバーの新しい値（0から100の範囲）。
        """
        self.progressBar.setValue(value)

class Worker(QObject):
    """
    バックグラウンドで長時間実行されるタスクを処理するワーカークラス。

    Attributes:
        progress_updated (Signal): 進捗状況が更新されたときに発行されるシグナル。
        status_updated (Signal): ステータスが更新されたときに発行されるシグナル。
        finished (Signal): タスクが完了したときに発行されるシグナル。
        error_occurred (Signal): エラーが発生したときに発行されるシグナル。
        logger (Logger): ロガーオブジェクト。
        _is_canceled (bool): キャンセルリクエストを受けたかどうかを示すフラグ。
        function (callable): 実行する処理の関数。
        args (tuple): 関数に渡す位置引数。
        kwargs (dict): 関数に渡すキーワード引数。

    Signals:
        progress_updated(int): 進捗値が更新されたときに発行。
        status_updated(str): ステータスラベルが更新されたときに発行。
        finished: 処理が完了したときに発行。
        error_occurred(str): エラーが発生したときに発行。

    Methods:
        run(): ワーカースレッドで実行する処理。
        cancel(): ワーカースレッドのキャンセル処理。
    """
    progress_updated = Signal(int)
    status_updated = Signal(str)
    finished = Signal()
    error_occurred = Signal(str)

    def __init__(self, function, *args, **kwargs):
        """Workerの初期化

        Args:
            function (callable): 実行する関数。
            *args: 関数に渡す位置引数。
            **kwargs: 関数に渡すキーワード引数。
        """
        super().__init__()
        self.logger = get_logger(f"Worker: {function.__name__}")
        self._is_canceled = False  # キャンセルリクエストを受けたかどうかを示すフラグ
        self.function = function  # 実行する処理の関数
        self.args = args  # 関数に渡す位置引数
        self.kwargs = kwargs  # 関数に渡すキーワード引数
        self.logger.debug("Worker initialized")

    @Slot()
    def run(self):
        """
        ワーカースレッドで実行する処理。
        外部から渡された関数を実行します。
        """
        self.logger.info("Worker: 処理開始")
        try:
            if self._is_canceled:
                self.logger.info("Worker: キャンセルされました")
                return

            # 関数のシグネチャを取得
            sig = inspect.signature(self.function)
            params = sig.parameters

            # 渡すキーワード引数を準備
            kwargs = dict(self.kwargs)
            if 'progress_callback' in params:
                kwargs['progress_callback'] = self.progress_updated.emit
            if 'status_callback' in params:
                kwargs['status_callback'] = self.status_updated.emit
            if 'is_canceled' in params:
                kwargs['is_canceled'] = lambda: self._is_canceled

            # 関数を実行
            self.function(*self.args, **kwargs)

        except Exception as e:
            self.logger.error(f"Worker: エラーが発生しました: {e}")
            self.error_occurred.emit(str(e))
        finally:
            self.logger.info("Worker: 処理完了")
            self.finished.emit()  # 処理完了シグナルを発行

    @Slot()
    def cancel(self):
        """
        ワーカースレッドのキャンセル処理。
        _is_canceled フラグを True に設定して、処理を中断します。
        """
        self.logger.debug("Worker: キャンセルリクエストを受け付けました")
        self._is_canceled = True

class Controller(QObject):
    """
    ProgressWidgetとWorkerを管理し、タスクの実行を制御するコントローラクラス。

    Attributes:
        progress_widget (ProgressWidget): 進捗状況を表示する ProgressWidget。
        worker (Worker): バックグラウンド処理を実行する Worker。
        thread (QThread): ワーカースレッド。
        logger (Logger): ロガーオブジェクト。

    Methods:
        start_process(self, function, *args, **kwargs): 処理を開始する。
        cleanup(self): スレッドとワーカーのリソースを解放する。

    Signals:
        None
    """
    def __init__(self, progress_widget=None):
        """Controllerの初期化

        Args:
            progress_widget (ProgressWidget, optional): 既存のProgressWidgetを使用する場合に指定。
        """
        super().__init__()
        self.logger = get_logger("Controller")
        self.progress_widget = progress_widget if progress_widget else ProgressWidget()
        self.worker = None
        self.thread = None
        self.logger.debug("Controller initialized")

    def start_process(self, function, *args, **kwargs):
        """
        処理を開始する。

        Args:
            function (callable): 実行する関数。
            *args: 関数に渡す位置引数。
            **kwargs: 関数に渡すキーワード引数。
        """
        # 既存のスレッドとワーカーをクリーンアップ
        self.cleanup()

        # 新しいスレッドとワーカーを作成
        self.thread = QThread()
        self.worker = Worker(function, *args, **kwargs)
        self.worker.moveToThread(self.thread)

        # シグナルとスロットの接続
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.progress_updated.connect(self.progress_widget.update_progress)
        self.worker.status_updated.connect(self.progress_widget.update_status)
        self.worker.error_occurred.connect(self.on_error)
        self.worker.finished.connect(self.on_worker_finished)
        self.progress_widget.canceled.connect(self.worker.cancel)

        # スレッドを開始
        self.thread.start()
        self.logger.debug("Controller: スレッドを開始しました")

    @Slot()
    def on_worker_finished(self):
        """
        Workerの処理が終了したときに呼び出されるスロット。
        ProgressWidgetを非表示にし、リソースを解放します。
        """
        self.logger.debug("Controller: Workerが完了しました")
        self.progress_widget.hide()
        self.cleanup()

    @Slot(str)
    def on_error(self, message):
        """
        Workerでエラーが発生したときに呼び出されるスロット。

        Args:
            message (str): エラーメッセージ。
        """
        self.logger.error(f"Controller: エラーが発生しました: {message}")
        # ここでエラーをユーザーに通知するための処理を追加できます
        # 例えば、QMessageBoxを表示するなど
        self.progress_widget.hide()
        self.cleanup()

    def cleanup(self):
        """
        スレッドとワーカーのリソースを解放する。
        """
        if self.thread and self.thread.isRunning():
            self.logger.debug("Controller: スレッドとワーカーをクリーンアップします")
            self.worker.cancel()
            self.thread.quit()
            self.thread.wait()
        self.thread = None
        self.worker = None
