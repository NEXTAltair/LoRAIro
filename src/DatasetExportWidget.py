import sys
from pathlib import Path

from PySide6.QtWidgets import QWidget, QMessageBox
from PySide6.QtCore import Qt, QDateTime, QTimeZone, QTime, Slot
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
        self.filtered_image_metadata = {}
        self.image_path_id_map = {}

    def init_ui(self):
        self.exportDirectoryPicker.set_label_text("Export Directory:")
        self.exportDirectoryPicker.set_path(self.cm.config['directories']['edited_output'])
        self.exportProgressBar.setVisible(False)
        self.dbSearchWidget.filterApplied.connect(self.on_filter_applied)

    def initialize(self, cm, fsm: FileSystemManager, idm: ImageDatabaseManager):
        self.cm = cm
        self.fsm = fsm
        self.idm = idm
        self.init_date_range()
        self.init_ui()

    def init_date_range(self):
        self.dbSearchWidget.count_range_slider.set_date_range()

    def on_filter_applied(self, filter_conditions: dict):
        filter_type = filter_conditions['filter_type']
        filter_text = filter_conditions['filter_text']
        resolution = filter_conditions['resolution']
        use_and = filter_conditions['use_and']
        start_date, end_date = filter_conditions.get('date_range', (None, None))
        include_untagged = filter_conditions['include_untagged']
        # 日付範囲の処理
        if start_date is not None and end_date is not None:
            # UTCタイムスタンプをQDateTimeに変換し、ローカルタイムゾーンに設定
            start_date_qt = QDateTime.fromSecsSinceEpoch(start_date).toLocalTime()
            end_date_qt = QDateTime.fromSecsSinceEpoch(end_date).toLocalTime()

            # ローカルタイムゾーンを使用してISO 8601形式の文字列に変換
            start_date = start_date_qt.toString(Qt.ISODate)
            end_date = end_date_qt.toString(Qt.ISODate)

        tags = []
        caption = ""
        if filter_type == "tags":
            # タグはカンマ区切りで複数指定されるため、リストに変換
            tags = [tag.strip() for tag in filter_text.split(',')]
        elif filter_type == "caption":
            caption = filter_text

        filtered_image_metadata, list_count = self.idm.get_images_by_filter(
            tags=tags,
            caption=caption,
            resolution=resolution,
            use_and=use_and,
            start_date=start_date,
            end_date=end_date,
            include_untagged=include_untagged
        )
        if not filtered_image_metadata:
            self.logger.info(f"{filter_type} に {filter_text} を含む検索結果がありません")
            QMessageBox.critical(self,  "info", f"{filter_type} に {filter_text} を含む検索結果がありません")
            return

        # idとpathの対応だけを取り出す
        self.image_path_id_map = {item['image_id']: Path(item['stored_image_path']) for item in filtered_image_metadata}

        # サムネイルセレクターを更新
        self.update_thumbnail_selector(list(self.image_path_id_map.values()), list_count)

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
        export_successful = True
        for i, image_path in enumerate(selected_images):
            try:
                image_id = self.image_path_id_map.get(image_path)
                if image_id is not None:
                    annotations = self.idm.get_image_annotations(image_id)
                    if self.latestcheckBox.isChecked():
                        # 最近のアノテーションのみをフィルタリング
                        recent_annotations = self.idm.filter_recent_annotations(annotations)
                    image_data = {
                        'path': image_path,
                        'tags': recent_annotations['tags'],
                        'captions': recent_annotations['captions']
                    }
                    if "txt_cap" in formats:
                        self.fsm.export_dataset_to_txt(image_data, export_dir)
                    if "json" in formats:
                        self.fsm.export_dataset_to_json(image_data, export_dir)
                else:
                    self.logger.warning(f"Image ID not found for {image_path}")
                    continue  # 次の画像へ

                progress = int((i + 1) / total_images * 100)
                self.exportProgressBar.setValue(progress)
                self.statusLabel.setText(f"Status: Exporting... {progress}%")

            except Exception as e:
                self.logger.error(f"エクスポート中にエラーが発生しました: {str(e)}")
                QMessageBox.critical(self, "Error", f"エクスポート中にエラーが発生しました: {str(e)}")
                export_successful = False
                break

        self.exportButton.setEnabled(True)
        if export_successful:
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

    def update_thumbnail_selector(self, image_paths: list[Path], list_count: int):
        # サムネイルセレクターに新しい画像リストをロード
        self.thumbnailSelector.load_images(image_paths)
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
