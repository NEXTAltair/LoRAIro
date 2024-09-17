from PySide6.QtWidgets import QDialog
from PySide6.QtCore import Qt,Signal, Slot, QThread, QObject

from gui_file.ProgressWidget_ui import Ui_ProgressWidget

from module.log import get_logger


class ProgressWidget(QDialog, Ui_ProgressWidget):
    """
    処理の進捗状況を表示するダイアログウィジェット。

    Attributes:
        canceled (Signal): キャンセルボタンがクリックされたときに発行されるシグナル。
        logger: ロガー
        buffer: 進捗値を一時的に保存するバッファ

    Signals:
        canceled: キャンセルボタンクリック時に発行

    Slots:
        on_cancelButton_clicked(): キャンセルボタンクリック時の処理
        update_status(str): ステータスラベルの更新
    """
    canceled = Signal()

    def __init__(self, parent=None):
        """ProgressWidgetの初期化"""
        self.logger = get_logger("ProgressWidget")
        super().__init__(parent, Qt.Dialog)  # 親ウィジェットとダイアログフラグを設定して初期化
        self.setupUi(self)
        self.setModal(True) # 補湯侍中操作を受け付けないようにする
        self.logger.debug("初期化")

        # プログレスバーの機能を無効化
        self.progressBar.setVisible(False)

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
            status (str): 新しいステータステキスト
        """
        self.statusLabel.setText(status)

class Worker(QObject):
    """
    バックグラウンドで長時間実行されるタスクを処理するワーカースレッド。

    Attributes:
        progress_updated (Signal): 進捗状況が更新されたときに発行されるシグナル。
        status_updated (Signal): ステータスが更新されたときに発行されるシグナル。
        finished (Signal): タスクが完了したときに発行されるシグナル。
        logger: ロガー
        _is_canceled: キャンセルリクエストを受けたかどうかを示すフラグ
        process_function: 実行する処理の関数
        args: 関数に渡す位置引数
        kwargs: 関数に渡すキーワード引数

    Signals:
        progress_updated(int): 進捗値更新時に発行
        status_updated(str): ステータスラベル更新時に発行
        finished: 処理終了時に発行

    Slots:
        run(): ワーカースレッドの処理実行
        cancel(): キャンセルリクエスト処理
    """
    progress_updated = Signal(int)
    status_updated = Signal(str)
    finished = Signal()

    def __init__(self, process_function=None, *args, **kwargs):  # 初期化時に関数と引数を受け取る
        """Workerの初期化"""
        self.logger = get_logger(f"Worker: {process_function.__name__}")
        super().__init__()
        self._is_canceled = False  # キャンセルリクエストを受けたかどうかを示すフラグ
        self.process_function = process_function  # 実行する処理の関数
        self.args = args  # 関数に渡す位置引数
        self.kwargs = kwargs  # 関数に渡すキーワード引数
        self.logger.debug("初期化")

    @Slot()
    def run(self):
        """
        Worker スレッドで実行する処理。
        外部から渡された関数を実行します。
        """
        self.logger.info("Worker: 処理開始")
        try:
            if self._is_canceled:
                return
            self.process_function(*self.args, **self.kwargs)  # process_function を実行
        except Exception as e:
            self.logger.error(f"ワーカースレッドでエラーが発生しました: {e}")
        finally:
            self.logger.info("処理完了")
            self.finished.emit()  # 処理完了シグナルを発行

    @Slot()
    def cancel(self):
        """
        ワーカースレッドのキャンセル処理。
        _is_canceled フラグを True に設定して、処理を中断します。
        """
        self.logger.debug("Cancel requested")
        self._is_canceled = True

class Controller:
    """
    ProgressWidgetとWorkerを管理し、タスクの実行を制御するコントローラクラス。

    Attributes:
        logger: ロガー
        progress_widget: 進捗状況を表示する ProgressWidget
        worker: バックグラウンド処理を実行する Worker
        thread: ワーカースレッド

    Methods:
        __init__(self, progress_widget: ProgressWidget = None): コンストラクタ
        start_process_no_args(self, process_function): 引数なしの処理を実行
        start_process_with_args(self, process_function, *args, **kwargs): 引数ありの処理を実行
        _setup_and_start_thread(self, process_function, *args, **kwargs): スレッドとワーカーのセットアップと開始
        cleanup(self): スレッドとワーカーのリソースを解放
        on_worker_finished(self): ワーカースレッド終了時の処理
    """
    def __init__(self, progress_widget: ProgressWidget = None):  # ProgressWidget を受け取るように修正
        """Controllerの初期化"""
        self.logger = get_logger("Controller")
        super().__init__()
        self.progress_widget = progress_widget if progress_widget else ProgressWidget() # ProgressWidgetを初期化または引数から取得
        self.worker = None
        self.thread = QThread()  # ワーカースレッド
        self.logger.debug("初期化")

    def setup_connections(self):
        """Worker、ProgressWidget、スレッド間のシグナルとスロットを接続する"""
        self.worker.status_updated.connect(self.progress_widget.update_status)  # WorkerのステータスをProgressWidgetに接続
        self.worker.finished.connect(self.on_worker_finished) # Workerの終了シグナルをon_worker_finishedスロットに接続
        self.progress_widget.canceled.connect(self.worker.cancel) # ProgressWidgetのキャンセルシグナルをWorkerのcancelスロットに接続
        self.thread.started.connect(lambda: self.worker.run())  # スレッド開始シグナルをWorkerのrunスロットに接続

    def start_process_no_args(self, process_function):
        """
        引数を必要としないプロセスを開始します。

        Args:
            process_function (callable): 実行する関数（引数なし）
        """
        self.logger.debug("Controller: start_process_no_args called")
        self._setup_and_start_thread(process_function) # スレッドとワーカーのセットアップと開始

    def start_process_with_args(self, process_function, *args, **kwargs):
        """
        引数を必要とするプロセスを開始します。

        Args:
            process_function (callable): 実行する関数
            *args: 位置引数
            **kwargs: キーワード引数
        """
        self.logger.debug("Controller: start_process_with_args called")
        self._setup_and_start_thread(process_function, *args, **kwargs) # スレッドとワーカーのセットアップと開始

    def _setup_and_start_thread(self, process_function, *args, **kwargs):
        """
        スレッドとワーカーのセットアップと開始を行う内部メソッド
        """
        # 既存のスレッドとワーカーをクリーンアップ
        self.cleanup()

        # 新しいスレッドとワーカーを作成
        self.thread = QThread()
        if args or kwargs: # 引数がある場合
            self.logger.debug(f"Creating new worker: {process_function.__name__} \n with args: {args}, kwargs: {kwargs}")
            self.worker = Worker(process_function, *args, **kwargs)
        else: # 引数がない場合
            self.logger.debug(f"引数なしの新しいワーカー{process_function.__name__}を作成")
            self.worker = Worker(process_function)
        self.worker.moveToThread(self.thread) # Workerオブジェクトをスレッドに移動

        # 接続を設定
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.status_updated.connect(self.progress_widget.update_status)
        self.worker.finished.connect(self.on_worker_finished)
        self.progress_widget.canceled.connect(self.worker.cancel)

        # スレッドを開始
        self.thread.start()
        self.logger.debug("New thread started")

    @Slot()
    def on_worker_finished(self):
        """
        Workerの処理が終了したときに呼び出されるスロット。
        スレッドをクリーンアップし、progress_widgetを非表示にします。
        """
        self.logger.debug("Controller: on_worker_finished called")
        self.progress_widget.hide()
        self.cleanup() # スレッドとワーカーのリソースを解放

    def cleanup(self):
        """
        スレッドとワーカーのリソースを解放する。
        """
        if self.thread and self.thread.isRunning():
            self.logger.debug("Cleaning up existing thread and worker")
            self.worker.cancel() # ワーカースレッドにキャンセルリクエストを送信
            self.thread.quit() # スレッドを終了
            self.thread.wait() # スレッドが完全に終了するまで待機
        self.thread = None
        self.worker = None

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    from module.log import setup_logger
    logconf = {'level': 'DEBUG', 'file': 'ProgressWidget.log'}
    setup_logger(logconf)
    app = QApplication([])
    controller = Controller()
    controller.progress_widget.show()
    app.exec()