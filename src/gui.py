import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMainWindow, QStatusBar

from gui_ui import Ui_mainWindow
from caption_tags import ImageAnalyzer
from module.log import setup_logger, get_logger
from module.config import get_config
from module.db import ImageDatabaseManager
from module.api_utils import APIClientFactory
from module.file_sys import FileSystemManager

class ConfigManager:
    _instance = None
    config = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance.config = cls.load_config_from_file()
        return cls._instance

    @staticmethod
    def load_config_from_file():
        return get_config()

class MainWindow(QMainWindow, Ui_mainWindow):
    def __init__(self):
        self.cm = ConfigManager()
        self.init_logging()
        super().__init__()
        self.setupUi(self)
        self.init_managers()
        self.init_pages()

        self.mainWindowSplitter.setSizes([self.width() * 2 // 5, self.width() * 3 // 5])

        self.connect_signals()
        self.init_dataset_selector()
        self.init_statusbar()

    def init_logging(self):
        setup_logger(self.cm.config['log'])
        self.logger = get_logger(__name__)

    def init_managers(self):
        self.idm = ImageDatabaseManager()
        prompt = self.cm.config['prompts']['main']
        add_prompt = self.cm.config['prompts']['additional']
        api_keys = self.cm.config['api']
        self.acf = APIClientFactory(api_keys, prompt, add_prompt)
        self.fsm = FileSystemManager()
        self.init_image_analyzer()

    def init_image_analyzer(self):
        models = self.idm.get_models()
        self.ia = ImageAnalyzer()
        self.ia.initialize(self.acf, models)

    def init_pages(self):
        self.pageImageEdit.initialize(self.cm, self.idm)
        self.pageImageTagger.initialize(self.cm, self.idm)
        self.pageSettings.initialize(self.cm)

    def connect_signals(self):
        self.sidebarList.currentRowChanged.connect(self.contentStackedWidget.setCurrentIndex)
        self.datasetSelector.DirectoryPicker.lineEditPicker.textChanged.connect(self.dataset_dir_changed)
        self.actionExit.triggered.connect(self.close)

    def init_dataset_selector(self):
        self.datasetSelector.set_label_text("データセット:")
        self.datasetSelector.set_path(self.cm.config['directories']['dataset'])

    def init_statusbar(self):
        if not hasattr(self, 'statusbar') or self.statusbar is None:
            self.statusbar = QStatusBar(self)
            self.setStatusBar(self.statusbar)
        self.statusbar.showMessage("準備完了")

    def dataset_dir_changed(self, new_path):
        self.logger.info(f"データセットディレクトリが変更されました: {new_path}")
        self.cm.config['directories']['dataset'] = new_path
        self.load_images(new_path)

    def load_images(self, directory: str):
        image_files = self.fsm.get_image_files(Path(directory))
        self.pageDatasetOverview.load_images(self.fsm, image_files)
        self.pageImageEdit.load_images(image_files)
        self.pageImageTagger.load_images(image_files)

if __name__ == "__main__":
    app = QApplication([])
    window = MainWindow()
    window.show()
    sys.exit(app.exec())