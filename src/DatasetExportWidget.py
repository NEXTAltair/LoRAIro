from PySide6.QtWidgets import QWidget, QMessageBox, QFileDialog
from PySide6.QtCore import Slot, Signal, QThread
from module.file_sys import FileSystemManager
from module.db import ImageDatabaseManager
from DatasetExportWidget_ui import Ui_DatasetExportWidget
from module.log import get_logger
from pathlib import Path

class ExportWorker(QThread):
    progressUpdated = Signal(int)
    exportFinished = Signal()
    exportError = Signal(str)

    def __init__(self, export_function, *args):
        super().__init__()
        self.export_function = export_function
        self.args = args

    def run(self):
        try:
            self.export_function(*self.args, progress_callback=self.progressUpdated.emit)
            self.exportFinished.emit()
        except Exception as e:
            self.exportError.emit(str(e))

class DatasetExportWidget(QWidget, Ui_DatasetExportWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.logger = get_logger(__name__)
        self.fsm = None
        self.idm = None
        self.init_ui()

    def init_ui(self):
        self.exportDirectoryPicker.set_label_text("Export Directory:")
        self.exportProgressBar.setVisible(False)

    def initialize(self, fsm: FileSystemManager, idm: ImageDatabaseManager):
        self.fsm = fsm
        self.idm = idm

    @Slot()
    def on_exportButton_clicked(self):
        export_directory = self.exportDirectoryPicker.get_selected_path()
        if not export_directory:
            QMessageBox.warning(self, "Warning", "出力先ディレクトリを選択してください")
            return

        export_formats = []
        if self.checkBoxTxtCap.isChecked():
            export_formats.append("txt_cap")
        if self.checkBoxJson.isChecked():
            export_formats.append("json")

        if not export_formats:
            QMessageBox.warning(self, "Warning", "出力形式を選択してください")
            return
        self.start_export(Path(export_directory), export_formats)

    def start_export(self, export_dir: Path, export_formats: list):
        self.exportButton.setEnabled(False)
        self.exportProgressBar.setVisible(True)
        self.statusLabel.setText("Status: Exporting...")

        selected_images = self.thumbnailSelector.get_selected_images()
        if not selected_images:
            QMessageBox.warning(self, "Warning", "出力する画像を選択してください")
            return

        self.export_worker = ExportWorker(
            self.export_dataset, export_dir, selected_images, export_formats
        )
        self.export_worker.progressUpdated.connect(self.update_export_progress)
        self.export_worker.exportFinished.connect(self.export_finished)
        self.export_worker.exportError.connect(self.export_error)
        self.export_worker.start()

    def export_dataset(self, export_dir: Path, images: list, formats: list, progress_callback):
        total_images = len(images)
        for i, image in enumerate(images):
            image_path = Path(image['path'])
            if "txt_cap" in formats:
                self.fsm.export_dataset_to_txt(
                    [image_path],
                    [self.idm.get_image_annotations(image['id'])['tags']],
                    [self.idm.get_image_annotations(image['id'])['captions']],
                    export_dir
                )
            if "json" in formats:
                self.fsm.export_dataset_to_json(
                    [image_path],
                    [self.idm.get_image_annotations(image['id'])['tags']],
                    [self.idm.get_image_annotations(image['id'])['captions']],
                    export_dir
                )
            progress_callback(int((i + 1) / total_images * 100))

    @Slot(int)
    def update_export_progress(self, value: int):
        self.exportProgressBar.setValue(value)

    @Slot()
    def export_finished(self):
        self.exportButton.setEnabled(True)
        self.exportProgressBar.setVisible(False)
        self.statusLabel.setText("Status: Export completed")
        QMessageBox.information(self, "Success", "Dataset export completed successfully.")

    @Slot(str)
    def export_error(self, error_message: str):
        self.exportButton.setEnabled(True)
        self.exportProgressBar.setVisible(False)
        self.statusLabel.setText("Status: Export failed")
        QMessageBox.critical(self, "Error", f"An error occurred during export: {error_message}")

    @Slot()
    def on_applyFilterButton_clicked(self):
        filter_type = self.filterTypeComboBox.currentText().lower()
        filter_text = self.filterLineEdit.text()
        resolution = self.resolutionComboBox.currentText()
        min_resolution = int(resolution.split('x')[0])

        tags = []
        caption = ""
        if filter_type == "tags":
            tags = [tag.strip() for tag in filter_text.split(',')]
        elif filter_type == "caption":
            caption = filter_text

        use_and = self.andRadioButton.isChecked()

        filtered_images = self.idm.get_images_by_filter(
            tags=tags,
            caption=caption,
            resolution=min_resolution,
            use_and=use_and
        )
        self.update_thumbnail_selector(filtered_images)

    def update_thumbnail_selector(self, images):
        image_path_list = []
        for image in images:
            image_path_list.append(Path(image['stored_image_path']))
        self.thumbnailSelector.load_images(image_path_list)
        self.update_image_count_label(len(images))

    def update_image_count_label(self, count):
        total = self.idm.get_total_image_count()
        self.imageCountLabel.setText(f"Selected Images: {count} / Total Images: {total}")

    @Slot(Path)
    def on_thumbnailSelector_imageSelected(self, image_path: Path):
        self.imagePreview.load_image(image_path)

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys

    fsm = FileSystemManager()
    idm = ImageDatabaseManager()

    app = QApplication(sys.argv)
    widget = DatasetExportWidget()
    widget.initialize(fsm, idm)
    widget.show()
    sys.exit(app.exec())