import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMainWindow, QStatusBar, QMessageBox

from gui_ui import Ui_mainWindow
from ProgressWidget import ProgressWidget, Controller

from module.log import setup_logger, get_logger
from module.config import get_config
from module.db import ImageDatabaseManager
from module.file_sys import FileSystemManager

class ConfigManager:
    _instance = None
    config = None
    dataset_image_paths = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance.config = cls.load_config_from_file()
            cls._instance.dataset_image_paths = []
        return cls._instance

    @staticmethod
    def load_config_from_file():
        return get_config()

class MainWindow(QMainWindow, Ui_mainWindow):
    def __init__(self):
        self.cm = ConfigManager()
        setup_logger(self.cm.config['log'])
        self.logger = get_logger("MainWindow")
        super().__init__()
        self.setupUi(self)

        self.init_managers()
        self.init_pages()

        # ここでサイドメニューのウィンドウ上での割合を決めないと表示が汚くなる
        self.mainWindowSplitter.setSizes([self.width() * 3 // 10, self.width() * 7 // 10])

        self.connect_signals()
        self.init_dataset_selector()
        self.init_statusbar()

    def init_managers(self):
        self.idm = ImageDatabaseManager() #.db のパスはハードコーディングなので変わらない
        self.fsm = FileSystemManager()
        self.progress_widget = ProgressWidget()
        self.progress_controller = Controller(self.progress_widget)

    def init_pages(self):
        self.pageImageEdit.initialize(self.cm, self.fsm, self.idm, self)
        self.pageImageTagger.initialize(self.cm, self.idm)
        self.pageDatasetOverview.initialize(self.cm)
        self.pageExport.initialize(self.cm, self.fsm, self.idm)
        self.pageSettings.initialize(self.cm)

    def connect_signals(self):
        self.sidebarList.currentRowChanged.connect(self.contentStackedWidget.setCurrentIndex)
        self.datasetSelector.DirectoryPicker.lineEditPicker.textChanged.connect(self.dataset_dir_changed)
        self.actionExit.triggered.connect(self.close)

    def init_dataset_selector(self):
        self.datasetSelector.set_label_text("データセット:")
        default_conf_path = self.cm.config['directories']['dataset']
        self.datasetSelector.set_path(default_conf_path)
        self.cm.dataset_image_paths = FileSystemManager.get_image_files(Path(default_conf_path))

    def init_statusbar(self):
        if not hasattr(self, 'statusbar') or self.statusbar is None:
            self.statusbar = QStatusBar(self)
            self.setStatusBar(self.statusbar)
        self.statusbar.showMessage("準備完了")

    def dataset_dir_changed(self, new_path):
        self.logger.info(f"データセットディレクトリが変更されました: {new_path}")
        self.cm.config['directories']['dataset'] = new_path
        self.cm.dataset_image_paths = FileSystemManager.get_image_files(Path(new_path))
        # 現在表示されているページを更新するため current_page の load_images メソッドを呼び出す
        current_page = self.contentStackedWidget.currentWidget()
        if hasattr(current_page, 'load_images'):
            current_page.load_images(self.cm.dataset_image_paths)

    def some_long_process(self, process_function, *args, **kwargs):
        self.progress_widget.show()  # プログレスウィジェットを表示

        # process_function が引数を必要とするかチェック
        if callable(process_function):
            import inspect
            sig = inspect.signature(process_function)
            if len(sig.parameters) == 0:
                # 引数が不要な場合
                self.progress_controller.start_process_no_args(process_function)
            else:
                # 引数が必要な場合
                self.progress_controller.start_process_with_args(process_function, *args, **kwargs)
        else:
            raise ValueError("process_function must be callable")

    def closeEvent(self, event):
        if self.progress_controller.thread.isRunning():
            event.ignore()
            QMessageBox.warning(self, "Warning", "Process is still running.")
        else:
            event.accept()

if __name__ == "__main__":
    app = QApplication([])
    window = MainWindow()
    window.show()
    sys.exit(app.exec())