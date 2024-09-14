from pathlib import Path

from PySide6.QtWidgets import QWidget, QMessageBox
from PySide6.QtCore import Slot
from gui_file.DatasetExportWidget_ui import Ui_DatasetExportWidget

from module.file_sys import FileSystemManager
from module.db import ImageDatabaseManager
from module.log import get_logger

class DatasetExportWidget(QWidget, Ui_DatasetExportWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.logger = get_logger("DatasetExportWidget")
        self.fsm = None
        self.idm = None
        self.image_selection_data = {}

    def init_ui(self):
        self.exportDirectoryPicker.set_label_text("Export Directory:")
        self.exportDirectoryPicker.set_path(self.cm.config['directories']['edited_output'])
        self.exportProgressBar.setVisible(False)
        self.filterWidget.filterApplied.connect(self.on_filter_applied)
        self.filterWidget.countRangeGroupBox.hide() # ここでは使わないを非表示にする

    def initialize(self, cm, fsm: FileSystemManager, idm: ImageDatabaseManager):
        self.cm = cm
        self.fsm = fsm
        self.idm = idm
        self.init_ui()

    def on_filter_applied(self, filter_conditions: dict):
        filter_type = filter_conditions['filter_type']
        filter_text = filter_conditions['filter_text']
        min_resolution, _ = filter_conditions['resolution']
        use_and = filter_conditions['use_and']

        tags = []
        caption = ""
        if filter_type == "tags":
            tags = [tag.strip() for tag in filter_text.split(',')]
        elif filter_type == "caption":
            caption = filter_text

        image_selection_data, list_count = self.idm.get_images_by_filter(
            tags=tags,
            caption=caption,
            resolution=int(min_resolution),
            use_and=use_and
        )
        if not image_selection_data:
            self.logger.info(f"{filter_type} に {filter_text} を含む検索結果がありません")
            QMessageBox.critical(self,  "info", f"{filter_type} に {filter_text} を含む検索結果がありません")

        self.update_thumbnail_selector(list_count)

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
        self.export_dataset(Path(export_directory), export_formats)

    def export_dataset(self, export_dir: Path, formats: list):
        self.exportButton.setEnabled(False)
        self.statusLabel.setText("Status: Exporting...")

        selected_images = self.thumbnailSelector.get_selected_images()
        if not selected_images:
            QMessageBox.warning(self, "Warning", "出力する画像を選択してください")
            self.exportButton.setEnabled(True)
            return

        total_images = len(selected_images)
        for i, image_path in enumerate(selected_images):
            try:
                image_id = self.image_selection_data.get(image_path)
                if image_id is not None:
                    annotations = self.idm.get_image_annotations(image_id)
                    image_data = {
                        'path': image_path,
                        'tags': annotations['tags'],
                        'captions': annotations['captions']
                    }
                    if "txt_cap" in formats:
                        self.fsm.export_dataset_to_txt(image_data, export_dir)
                    if "json" in formats:
                        self.fsm.export_dataset_to_json(image_data, export_dir)

                progress = int((i + 1) / total_images * 100)
                self.exportProgressBar.setValue(progress)
                self.statusLabel.setText(f"Status: Exporting... {progress}%")
                # GUIの更新を強制
                QApplication.processEvents()

            except Exception as e:
                self.logger.error(f"エクスポート中にエラーが発生しました: {str(e)}")
                QMessageBox.critical(self, "Error", f"エクスポート中にエラーが発生しました: {str(e)}")
                break

        self.exportButton.setEnabled(True)
        QMessageBox.information(self, "Success", "Dataset export completed successfully.")

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

    def update_thumbnail_selector(self, list_count):
        self.image_selection_data.clear()
        self.update_image_count_label(list_count)

    def update_image_count_label(self, count):
        total = self.idm.get_total_image_count()
        self.imageCountLabel.setText(f"Selected Images: {count} / Total Images: {total}")

    @Slot(Path)
    def on_thumbnailSelector_imageSelected(self, image_path: Path):
        self.imagePreview.load_image(image_path)

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    from gui import ConfigManager
    from module.config import get_config
    from module.log import setup_logger
    import sys

    app = QApplication(sys.argv)
    config = get_config()
    logconf = {'level': 'DEBUG', 'file': 'DatasetExportWidget.log'}
    setup_logger(logconf)

    cm = ConfigManager()
    fsm = FileSystemManager()
    idm = ImageDatabaseManager()

    widget = DatasetExportWidget()
    widget.initialize(cm, fsm, idm)
    widget.show()
    sys.exit(app.exec())