from PySide6.QtWidgets import QDialog
from PySide6.QtCore import Qt,Signal, Slot, QThread, QObject, QTimer

from module.log import get_logger

from ProgressWidget_ui import Ui_ProgressWidget


class ProgressWidget(QDialog, Ui_ProgressWidget):
    """
    ProgressWidgetクラスは、進行状況を表示するためのウィジェット

    シグナル:
        canceled: キャンセルボタンがクリックされたときに発行

    メソッド:
        on_cancelButton_clicked(self): キャンセルボタンがクリックされたときに呼び出す。
        update_progress(self, value): 進行状況バーの値を更新します。
        update_status(self, status): ステータスラベルのテキストを更新します。
        process_buffer(self): バッファ内の最新の値を処理します。
    """
    canceled = Signal()

    def __init__(self, parent=None):
        self.logger = get_logger("ProgressWidget")
        super().__init__(parent, Qt.Dialog)
        self.setupUi(self)
        self.logger.debug("初期化")
        self.buffer = []
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.process_buffer)
        self.update_timer.start(50)

    @Slot()
    def on_cancelButton_clicked(self):
        self.logger.debug("Cancel button clicked")
        self.canceled.emit()

    @Slot(int)
    def update_progress(self, value):
        self.buffer.append(value)

    @Slot(str)
    def update_status(self, status):
        self.statusLabel.setText(status)

    def process_buffer(self):
        if self.buffer:
            value = self.buffer[-1]  # 最新の値を使用
            self.progressBar.setValue(value)
            self.logger.debug(f"ProgressWidget: Updating progress: {value}%")
            self.buffer.clear()

class Worker(QObject):
    """
    Workerクラスは、バックグラウンドで実行されるタスクを処理します。

    シグナル:
        progress_updated(int): 進行状況が更新されたときに発行されます。
        status_updated(str): ステータスが更新されたときに発行されます。
        finished: タスクが完了したときに発行されます。

    メソッド:
        __init__(self): Workerのインスタンスを初期化します。
        run(self): タスクを実行します。
        cancel(self): タスクをキャンセルします。
    """
    progress_updated = Signal(int)
    status_updated = Signal(str)
    finished = Signal()

    def __init__(self, process_function = None, *args, **kwargs):  # 初期化時に関数と引数を受け取る
        self.logger = get_logger(f"Worker: {process_function.__name__}")
        super().__init__()
        self._is_canceled = False
        self.process_function = process_function
        self.args = args
        self.kwargs = kwargs
        self.logger.debug("初期化")

    def run(self):
        try:
            self.logger.info("処理開始")
            if self.args or self.kwargs:
                total_images = len(self.args[0])  # 画像リストを引数として渡すことを想定
                for i, image_path in enumerate(self.args[0]): #プログレスバーの処理
                    if self._is_canceled:
                        break
                    self.process_function(image_path)
                    progress = (i + 1) / total_images * 100
                    self.progress_updated.emit(int(progress))
                    self.status_updated.emit(f"処理中: {i+1}/{total_images}")
            else:
                self.process_function()
        except Exception as e:
            self.logger.error(f"ワーカースレッドでエラーが発生しました: {e}")
        finally:
            self.logger.info("処理完了")
            self.finished.emit()

    @Slot()
    def cancel(self):
        self.logger.debug("Cancel requested")
        self._is_canceled = True

class Controller:
    """
    Controllerクラスは、ProgressWidgetとWorkerを管理し、タスクの実行を制御します。

    メソッド:
        __init__(self): Controllerのインスタンスを初期化します。
        start_process(self, process_function, *args, **kwargs): タスクの実行を開始します。
        on_worker_finished(self): タスクが完了したときに呼び出されます。
    """
    def __init__(self, progress_widget: ProgressWidget = None):
        self.logger = get_logger("Controller")
        super().__init__()
        self.progress_widget = progress_widget if progress_widget else ProgressWidget()
        self.worker = None
        self.thread = None
        self.logger.debug("初期化")

    def start_process_no_args(self, process_function):
        """
        引数を必要としないプロセスを開始します。

        Args:
            process_function (callable): 実行する関数（引数なし）
        """
        self.logger.debug("Controller: start_process_no_args called")
        self._setup_and_start_thread(process_function)

    def start_process_with_args(self, process_function, *args, **kwargs):
        """
        引数を必要とするプロセスを開始します。

        Args:
            process_function (callable): 実行する関数
            *args: 位置引数
            **kwargs: キーワード引数
        """
        self.logger.debug("Controller: start_process_with_args called")
        self._setup_and_start_thread(process_function, *args, **kwargs)

    def _setup_and_start_thread(self, process_function, *args, **kwargs):
        """
        スレッドとワーカーのセットアップと開始を行う内部メソッド
        """
        # 既存のスレッドとワーカーをクリーンアップ
        self.cleanup()

        # 新しいスレッドとワーカーを作成
        self.thread = QThread()
        if args or kwargs:
            self.logger.debug(f"Creating new worker: {process_function.__name__} \n with args: {args}, kwargs: {kwargs}")
            self.worker = Worker(process_function, *args, **kwargs)
        else:
            self.logger.debug(f"引数なしの新しいワーカー{process_function.__name__}を作成")
            self.worker = Worker(process_function)
        self.worker.moveToThread(self.thread)

        # 接続を設定
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.progress_updated.connect(self.progress_widget.update_progress)
        self.worker.status_updated.connect(self.progress_widget.update_status)
        self.worker.finished.connect(self.on_worker_finished)
        self.progress_widget.canceled.connect(self.worker.cancel)

        # スレッドを開始
        self.thread.start()

        self.logger.debug("New thread started")

    def cleanup(self):
        if self.thread and self.thread.isRunning():
            self.logger.debug("Cleaning up existing thread and worker")
            self.worker.cancel()
            self.thread.quit()
            self.thread.wait()
        self.thread = None
        self.worker = None

    @Slot()
    def on_worker_finished(self):
        self.logger.debug("Controller: on_worker_finished called")
        self.progress_widget.hide()
        self.cleanup()

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    from module.log import setup_logger
    logconf = {'level': 'DEBUG', 'file': 'ProgressWidget.log'}
    setup_logger(logconf)
    app = QApplication([])
    controller = Controller()
    controller.progress_widget.show()
    controller.start_process()
    app.exec()