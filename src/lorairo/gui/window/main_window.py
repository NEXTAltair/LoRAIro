import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QStatusBar

from ...database.db_core import DefaultSessionLocal
from ...database.db_manager import ImageDatabaseManager
from ...database.db_repository import ImageRepository
from ...gui.designer.MainWindow_ui import Ui_MainWindow
from ...storage.file_system import FileSystemManager
from ...utils.config import get_config
from ...utils.log import logger
from .progress import Controller, ProgressWidget


class ConfigManager:
    _instance = None
    config = None
    dataset_image_paths = (
        None  # REVIEW: ここで保持するのは適切か？なぜこうしたかw擦れた理由をコメントで書く
    )

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance.config = cls.load_config_from_file()
            cls._instance.dataset_image_paths = []
        return cls._instance

    @staticmethod
    def load_config_from_file():
        return get_config()


class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        self.cm = ConfigManager()
        super().__init__()
        self.setupUi(self)

        self.init_managers()
        self.init_pages()

        # ここでサイドメニューのウィンドウ上での割合を決めないと表示が汚くなる
        self.mainWindowSplitter.setSizes([self.width() * 1 // 5, self.width() * 4 // 5])

        self.connect_signals()
        self.init_dataset_selector()
        self.init_statusbar()

    def init_managers(self):
        # DB_COREのデフォルトセッションファクトリを使用してImagerePositoryを作成します
        image_repo = ImageRepository(session_factory=DefaultSessionLocal)
        # ImageRepositoryインスタンスでImagedatabaseManagerを初期化します
        self.idm = ImageDatabaseManager(image_repo)

        self.fsm = FileSystemManager()
        self.progress_widget = ProgressWidget()
        self.progress_controller = Controller(self.progress_widget)
        # タイプ別にモデルを取得するように変更
        llm_models = self.idm.get_llm_models()
        score_models = self.idm.get_score_models()
        upscaler_models = self.idm.get_upscaler_models()
        tagger_models = self.idm.get_tagger_models()
        captioner_models = self.idm.get_captioner_models()
        tagger_models = self.idm.get_tagger_models()
        captioner_models = self.idm.get_captioner_models()

        # ConfigManager に格納する際のキー名を新しいタイプ名に合わせる
        self.cm.llm_models = llm_models
        self.cm.score_models = score_models
        self.cm.upscaler_models = upscaler_models
        self.cm.tagger_models = tagger_models
        self.cm.captioner_models = captioner_models

    def init_pages(self):
        self.pageImageEdit.initialize(self.cm, self.fsm, self.idm, self)
        self.pageImageTagger.initialize(self.cm, self.idm)
        self.pageDatasetOverview.initialize(self.cm, self.idm)
        self.pageExport.initialize(self.cm, self.fsm, self.idm)
        self.pageSettings.initialize(self.cm)

    def connect_signals(self):
        self.sidebarList.currentRowChanged.connect(self.contentStackedWidget.setCurrentIndex)
        self.datasetSelector.DirectoryPicker.lineEditPicker.textChanged.connect(self.dataset_dir_changed)
        self.actionExit.triggered.connect(self.close)

    def init_dataset_selector(self):
        self.datasetSelector.set_label_text("データセット:")
        default_conf_path = self.cm.config["directories"]["dataset"]
        # default_conf_path が空文字列の場合は何もしない｡でないとカレントディクトリ内の画像全部対象とする
        if default_conf_path == "":
            return
        self.datasetSelector.set_path(default_conf_path)
        self.cm.dataset_image_paths = FileSystemManager.get_image_files(Path(default_conf_path))

    def init_statusbar(self):
        if not hasattr(self, "statusbar") or self.statusbar is None:
            self.statusbar = QStatusBar(self)
            self.setStatusBar(self.statusbar)
        self.statusbar.showMessage("準備完了")

    def dataset_dir_changed(self, new_path):
        logger.info(f"データセットディレクトリが変更されました: {new_path}")
        self.cm.config["directories"]["dataset"] = new_path
        self.cm.dataset_image_paths = FileSystemManager.get_image_files(Path(new_path))
        # path がない場合は何もしない
        if not self.cm.dataset_image_paths:
            return
        # 現在表示されているページを更新するため current_page の load_images メソッドを呼び出す
        current_page = self.contentStackedWidget.currentWidget()
        if hasattr(current_page, "load_images"):
            self.some_long_process(current_page.load_images, self.cm.dataset_image_paths)

    def some_long_process(self, process_function, *args, **kwargs):
        self.progress_widget.show()
        try:
            self.progress_controller.start_process(process_function, *args, **kwargs)
        except Exception as e:
            logger.error(f"ProgressWidgetを使用した処理中にエラーが発生しました: {e}")

    def closeEvent(self, event):
        if (
            hasattr(self, "progress_controller")
            and self.progress_controller
            and hasattr(self.progress_controller, "thread")
            and self.progress_controller.thread
            and self.progress_controller.thread.isRunning()
        ):
            event.ignore()
            QMessageBox.warning(self, "Warning", "Process is still running.")
        else:
            event.accept()


if __name__ == "__main__":
    app = QApplication([])
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
