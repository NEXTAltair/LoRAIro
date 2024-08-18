import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMainWindow, QStatusBar
from PySide6.QtCore import Signal, Slot

from gui_ui import Ui_mainWindow
from ImageEditor import ImageProcessingManager
from caption_tags import ImageAnalyzer
from module.log import setup_logger, get_logger
from module.config import get_config
from module.file_sys import FileSystemManager
from module.db import ImageDatabaseManager
from module.api_utils import APIClientFactory

class MainWindow(QMainWindow, Ui_mainWindow):
    def __init__(self):
        super().__init__()
        self.config = get_config()  # 設定を直接保持
        self.current_dataset_dir = None
        self.fsm = None
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
        self.datasetSelector.set_path(self.config['directories']['dataset'])

        # ステータスバーの初期化
        if not hasattr(self, 'statusbar') or self.statusbar is None:
            self.statusbar = QStatusBar(self)
            self.setStatusBar(self.statusbar)
        self.statusbar.showMessage("準備完了")

    def init_logging(self):
        setup_logger(self.config['log'])
        self.logger = get_logger(__name__)

    def init_managers(self):
        self.fsm = FileSystemManager()
        output_dir = Path(self.config['directories']['output'])
        target_resolution = self.config['image_processing']['target_resolution']
        self.fsm.initialize(output_dir, target_resolution)

        self.idm = ImageDatabaseManager()
        self.ipm = ImageProcessingManager(self.fsm, target_resolution, self.config['preferred_resolutions'])

        prompt = self.config['prompts']['main']
        add_prompt = self.config['prompts']['additional']
        api_keys = self.config['api']
        self.acf = APIClientFactory(api_keys, prompt, add_prompt)

        vision_models = self.idm.get_models()
        self.ia = ImageAnalyzer()

    def init_pages(self):
        self.pageImageEdit.initialize(self.config, self.ia, self.fsm, self.idm)
        self.pageSettings.initialize(self.config)
        self.pageImageTagger.initialize(self.config, self.idm)

    def init_file_system(self):
        # TODO: target_resolutionはウィジェットの操作で変更されるので別のばしょで初期化
        # FileSystemManager.initialize(output_dir, target_resolution)
        if self.fsm is None:
            self.fsm = FileSystemManager()
            output_dir = Path(self.config['directories']['output'])
            target_resolution = self.config['image_processing']['target_resolution']
            self.fsm.initialize(output_dir, target_resolution)

    def init_image_database(self):
        self.idm = ImageDatabaseManager()
        connection_status = self.idm.db_manager.connect()
        if not connection_status:
            self.logger.error("データベースへの接続に失敗しました。")
            return

    def init_image_processing(self):
        # 画像処理マネージャーの初期化
        target_resolution = self.config['image_processing']['target_resolution']
        preferred_resolutions = self.config['image_processing']['preferred_resolutions']
        # TODO: preferred_resolutionsは推奨アスペクトレートのほうがいいんじゃないかと思う
        # 設定もconfig以外のほうがいいかも､ImageProcessingManagerのなかとか
        self.ipm = ImageProcessingManager(self.fsm, target_resolution, preferred_resolutions)

    def init_api_client(self):
        # TODO: タグ付けを実行するウィジェット内で初期化するほうが良さそう？
        prompt = self.config['prompts']['main']
        add_prompt = self.config['prompts']['additional']
        api_keys = self.config['api']
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
        self.current_dataset_dir = new_path
        self.load_images(new_path)

    def load_images(self, directory: str):
        """
        指定されたディレクトリから画像を読み込み、

        Args:
            directory (str): 画像が保存されているディレクトリのパス
        """
        self.init_file_system()  # fsm が必要になった時点で初期化
        image_files: list[Path] = self.fsm.get_image_files(Path(directory))
        self.pageDatasetOverview.load_images(self.fsm, image_files)
        self.pageImageEdit.load_images(image_files)
        self.pageImageTagger.load_images(image_files)

if __name__ == "__main__":
    app = QApplication([])
    window = MainWindow()
    window.show()
    sys.exit(app.exec())