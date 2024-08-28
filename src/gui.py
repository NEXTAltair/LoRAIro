import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMainWindow, QStatusBar

from gui_ui import Ui_mainWindow
from module.log import setup_logger, get_logger
from module.config import get_config
from module.db import ImageDatabaseManager
from module.api_utils import APIClientFactory
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
        api_keys = self.cm.config['api']
        self.acf = APIClientFactory(api_keys)
        self.fsm = FileSystemManager()

    def init_pages(self):
        self.pageImageEdit.initialize(self.cm, self.fsm, self.idm)
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

if __name__ == "__main__":
    app = QApplication([])
    window = MainWindow()
    window.show()
    sys.exit(app.exec())