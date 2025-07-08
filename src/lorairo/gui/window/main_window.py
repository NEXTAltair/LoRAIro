import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QStatusBar

from ...annotations.image_text_reader import ImageTextFileReader
from ...database.db_core import DefaultSessionLocal
from ...database.db_manager import ImageDatabaseManager
from ...database.db_repository import ImageRepository
from ...gui.designer.MainWindow_ui import Ui_MainWindow
from ...services.configuration_service import ConfigurationService
from ...services.image_processing_service import ImageProcessingService
from ...storage.file_system import FileSystemManager
from ...utils.log import logger
from .configuration_window import ConfigurationWindow
from .edit import ImageEditWidget
from .export import DatasetExportWidget
from .overview import DatasetOverviewWidget
from .progress import Controller, ProgressWidget
from .tagger import ImageTaggerWidget


class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.config_service = ConfigurationService()
        self.setupUi(self)
        self.dataset_image_paths = []

        self.init_managers()
        self.init_pages()

        self.mainWindowSplitter.setSizes([self.width() * 1 // 5, self.width() * 4 // 5])

        self.connect_signals()
        self.init_dataset_selector()
        self.init_statusbar()

    def init_managers(self):
        image_repo = ImageRepository(session_factory=DefaultSessionLocal)
        self.idm = ImageDatabaseManager(image_repo)
        self.fsm = FileSystemManager()
        self.image_text_reader = ImageTextFileReader(self.idm)
        self.image_processing_service = ImageProcessingService(self.config_service, self.fsm, self.idm)
        self.progress_widget = ProgressWidget()
        self.progress_controller = Controller(self.progress_widget)

    def init_pages(self):
        self.pageImageEdit.initialize(
            self.config_service,
            self.fsm,
            self.idm,
            self.image_processing_service,
            self.image_text_reader,
            self,
        )
        self.pageImageTagger.initialize(self.config_service, self.idm, self)
        self.pageDatasetOverview.initialize(self.config_service, self.idm, self)
        self.pageExport.initialize(self.config_service, self.fsm, self.idm, self)
        self.pageSettings.initialize(self.config_service)

    def connect_signals(self):
        self.sidebarList.currentRowChanged.connect(self.contentStackedWidget.setCurrentIndex)
        self.datasetSelector.DirectoryPicker.lineEditPicker.textChanged.connect(self.dataset_dir_changed)
        self.actionExit.triggered.connect(self.close)

    def init_dataset_selector(self):
        self.datasetSelector.set_label_text("データセット:")
        default_conf_path = self.config_service.get_setting("directories", "dataset", "")
        if default_conf_path == "":
            return
        self.datasetSelector.set_path(default_conf_path)
        self.dataset_image_paths = FileSystemManager.get_image_files(Path(default_conf_path))

    def init_statusbar(self):
        if not hasattr(self, "statusbar") or self.statusbar is None:
            self.statusbar = QStatusBar(self)
            self.setStatusBar(self.statusbar)
        self.statusbar.showMessage("準備完了")

    def dataset_dir_changed(self, new_path):
        logger.info(f"データセットディレクトリが変更されました: {new_path}")
        self.config_service.update_setting("directories", "dataset", new_path)

        # バッチ処理を開始
        self.start_batch_processing(Path(new_path))

    def some_long_process(self, process_function, *args, **kwargs):
        self.progress_widget.show()
        try:
            self.progress_controller.start_process(process_function, *args, **kwargs)
        except Exception as e:
            logger.error(f"ProgressWidgetを使用した処理中にエラーが発生しました: {e}")

    def start_batch_processing(self, directory_path: Path):
        """バッチ処理を開始する"""
        from ..services.batch_processor import process_directory_batch

        # プログレスウィジェットを表示
        self.progress_widget.show()

        # バッチ進捗シグナルの接続
        if hasattr(self.progress_controller, "worker") and self.progress_controller.worker:
            # 既存ワーカーがあれば接続
            self.progress_controller.worker.batch_progress.connect(self.on_batch_progress)

        # バッチ処理関数を実行
        self.some_long_process(
            process_directory_batch, directory_path, self.config_service, self.fsm, self.idm
        )

        # バッチ進捗シグナルの接続（ワーカー作成後）
        if hasattr(self.progress_controller, "worker") and self.progress_controller.worker:
            self.progress_controller.worker.batch_progress.connect(self.on_batch_progress)

    def on_batch_progress(self, current: int, total: int, filename: str):
        """バッチ進捗の詳細表示"""
        # ステータスバーに詳細進捗を表示
        self.statusbar.showMessage(f"処理中: {filename} ({current}/{total})")

        # プログレスバーのタイトル更新（可能であれば）
        if hasattr(self.progress_widget, "setWindowTitle"):
            percentage = int((current / total) * 100) if total > 0 else 0
            self.progress_widget.setWindowTitle(f"バッチ処理 - {percentage}% 完了")

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
