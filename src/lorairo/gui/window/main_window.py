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
        self.dataset_image_paths = FileSystemManager.get_image_files(Path(new_path))

        if not self.dataset_image_paths:
            return
        current_page = self.contentStackedWidget.currentWidget()
        if hasattr(current_page, "load_images"):
            self.some_long_process(current_page.load_images, self.dataset_image_paths)

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
