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
    config = None  # クラス属性として宣言

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
        super().__init__()
        self.cm = ConfigManager()
        self.cm.config = self.cm.config
        self.setupUi(self)
        self.init_managers()
        self.init_pages()
        self.init_logging()

        # スプリッターの初期サイズを設定
        self.mainWindowSplitter.setSizes([self.width() // 5, self.width() * 4 // 5])

        # シグナル/スロットの接続
        self.sidebarList.currentRowChanged.connect(self.contentStackedWidget.setCurrentIndex)
        self.datasetSelector.DirectoryPicker.lineEditPicker.textChanged.connect(self.dataset_dir_changed)
        self.actionExit.triggered.connect(self.close)

        # データセット選択用の DirectoryPickerWidget の設定
        self.datasetSelector.set_label_text("データセット:")
        self.datasetSelector.set_path(self.cm.config['directories']['dataset'])

        # ステータスバーの初期化
        if not hasattr(self, 'statusbar') or self.statusbar is None:
            self.statusbar = QStatusBar(self)
            self.setStatusBar(self.statusbar)
        self.statusbar.showMessage("準備完了")

    def init_logging(self):
        setup_logger(self.cm.config['log'])
        self.logger = get_logger(__name__)

    def init_managers(self):
        self.idm = ImageDatabaseManager()
        prompt = self.cm.config['prompts']['main']
        add_prompt = self.cm.config['prompts']['additional']
        api_keys = self.cm.config['api']
        vision_models = self.idm.get_models()
        self.acf = APIClientFactory(api_keys, vision_models, prompt, add_prompt)

        self.ia = ImageAnalyzer()

    def init_pages(self):
        # 各ウィジェットにconfigを渡す
        self.pageImageEdit.initialize(self.cm, self.ia, self.idm)
        self.pageSettings.initialize(self.cm)
        self.pageImageTagger.initialize(self.cm, self.idm)

    def init_image_database(self):
        self.idm = ImageDatabaseManager()
        connection_status = self.idm.db_manager.connect()
        if not connection_status:
            self.logger.error("データベースへの接続に失敗しました。")
            return

    def init_api_client(self):
        # TODO: タグ付けを実行するウィジェット内で初期化するほうが良さそう？
        prompt = self.cm.config['prompts']['main']
        add_prompt = self.cm.config['prompts']['additional']
        api_keys = self.cm.config['api']
        self.acf = APIClientFactory(api_keys, prompt, add_prompt)

    def init_image_analyzer(self):
        vision_models = self.idm.get_models()
        self.image_analyzer = ImageAnalyzer(self.acf, vision_models)

    def dataset_dir_changed(self, new_path):
        """
        データセットディレクトリが変更されたときに呼び出されるスロット

        Args:
            new_path (str): 変更後のデータセットディレクトリのパス
        """
        print(f"データセットディレクトリが変更されました: {new_path}")
        self.cm.config['directories']['dataset']= new_path
        self.load_images(new_path)

    def load_images(self, directory: str):
        """
        指定されたディレクトリから画像を読み込み、

        Args:
            directory (str): 画像が保存されているディレクトリのパス
        """
        self.fsm = FileSystemManager()
        image_files: list[Path] = self.fsm.get_image_files(Path(directory))
        self.pageDatasetOverview.load_images(self.fsm, image_files)
        self.pageImageEdit.load_images(image_files)
        self.pageImageTagger.load_images(image_files)

if __name__ == "__main__":
    app = QApplication([])
    window = MainWindow()
    window.show()
    sys.exit(app.exec())