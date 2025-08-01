import sys
from pathlib import Path

from PySide6.QtCore import QDateTime, Qt, Slot
from PySide6.QtWidgets import QMessageBox, QWidget

from lorairo.database.db_core import DefaultSessionLocal
from lorairo.database.db_repository import ImageRepository
from lorairo.services.configuration_service import ConfigurationService

from ...database.db_manager import ImageDatabaseManager
from ...storage.file_system import FileSystemManager
from ...utils.log import logger
from ..designer.DatasetExportWidget_ui import Ui_DatasetExportWidget


class DatasetExportWidget(QWidget, Ui_DatasetExportWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.fsm = None
        self.idm = None
        self.filtered_image_metadata = {}
        self.image_path_id_map = {}

    def init_ui(self):
        self.exportDirectoryPicker.set_label_text("Export Directory:")
        edited_output_path = self.config_service._config.get("directories", {}).get("edited_output", "")
        self.exportDirectoryPicker.set_path(edited_output_path)
        self.exportProgressBar.setVisible(False)
        self.dbSearchWidget.filterApplied.connect(self.on_filter_applied)

    def initialize(
        self,
        config_service: ConfigurationService,
        file_system_manager: FileSystemManager | None = None,
        image_database_manager: ImageDatabaseManager | None = None,
        main_window=None,
    ):
        self.config_service = config_service
        self.fsm = file_system_manager
        self.idm = image_database_manager
        self.main_window = main_window
        self.init_date_range()
        self.init_ui()

    def init_date_range(self):
        self.dbSearchWidget.count_range_slider.set_date_range()

    def on_filter_applied(self, filter_conditions: dict):
        filter_type = filter_conditions["filter_type"]
        filter_text = filter_conditions["filter_text"]
        resolution = filter_conditions["resolution"]
        use_and = filter_conditions["use_and"]
        start_date, end_date = filter_conditions.get("date_range", (None, None))
        include_untagged = filter_conditions["include_untagged"]
        # 日付範囲の処理
        if start_date is not None and end_date is not None:
            # UTCタイムスタンプをQDateTimeに変換し、ローカルタイムゾーンに設定
            start_date_qt = QDateTime.fromSecsSinceEpoch(start_date).toLocalTime()
            end_date_qt = QDateTime.fromSecsSinceEpoch(end_date).toLocalTime()

            # ローカルタイムゾーンを使用してISO 8601形式の文字列に変換 (Qt.ISODate -> Qt.DateFormat.ISODate)
            start_date = start_date_qt.toString(Qt.DateFormat.ISODate)
            end_date = end_date_qt.toString(Qt.DateFormat.ISODate)

        tags = []
        caption = ""
        if filter_type == "tags":
            # タグはカンマ区切りで複数指定されるため、リストに変換
            tags = [tag.strip() for tag in filter_text.split(",")]
        elif filter_type == "caption":
            caption = filter_text

        filtered_image_metadata, list_count = self.idm.get_images_by_filter(
            tags=tags,
            caption=caption,
            resolution=resolution,
            use_and=use_and,
            start_date=start_date,
            end_date=end_date,
            include_untagged=include_untagged,
        )
        if not filtered_image_metadata:
            logger.info(f"{filter_type} に {filter_text} を含む検索結果がありません")
            QMessageBox.critical(self, "info", f"{filter_type} に {filter_text} を含む検索結果がありません")
            return

        # idとpathの対応だけを取り出す
        self.image_path_id_map = {
            Path(item["stored_image_path"]): item["image_id"] for item in filtered_image_metadata
        }

        # サムネイルセレクターを更新
        self.update_thumbnail_selector(list(self.image_path_id_map.keys()), list_count)

    @Slot()
    def on_exportButton_clicked(self):
        export_directory = self.exportDirectoryPicker.get_selected_path()
        if not export_directory:
            QMessageBox.warning(self, "Warning", "出力先ディレクトリを選択してください")
            return

        self.export_dataset(Path(export_directory))

    def export_dataset(self, export_dir: Path):
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
                        annotations = self.idm.filter_recent_annotations(annotations)
                    image_data = {
                        "path": image_path,
                        "tags": annotations.get("tags", []),
                        "captions": annotations.get("captions", []),
                    }
                    if self.checkBoxTxtCap.isChecked():
                        self.fsm.export_dataset_to_txt(
                            image_data,
                            export_dir,
                            mearge_caption=self.MergeCaptionWithTagscheckBox.isChecked(),
                        )
                    if self.checkBoxJson.isChecked():
                        self.fsm.export_dataset_to_json(image_data, export_dir)
                else:
                    logger.error(f"Image ID not found for {image_path}")
                    continue  # 次の画像へ

                progress = int((i + 1) / total_images * 100)
                self.exportProgressBar.setValue(progress)
                self.statusLabel.setText(f"Status: Exporting... {progress}%")

            except Exception as e:
                logger.error(f"エクスポート中にエラーが発生しました: {e!s}")
                QMessageBox.critical(self, "Error", f"エクスポート中にエラーが発生しました: {e!s}")
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
    import sys

    from PySide6.QtWidgets import QApplication

    from lorairo.database.db_manager import ImageDatabaseManager
    from lorairo.services.configuration_service import ConfigurationService
    from lorairo.storage.file_system import FileSystemManager
    from lorairo.utils.config import get_config
    from lorairo.utils.log import initialize_logging

    app = QApplication(sys.argv)
    config_data = get_config()
    log_config = config_data.get("log", {})
    initialize_logging(log_config)

    config_service = ConfigurationService()
    fsm = FileSystemManager()
    db_path = Path(config_data.get("database", {}).get("path", "Image_database.db"))
    image_repo = ImageRepository(session_factory=DefaultSessionLocal)
    idm = ImageDatabaseManager(image_repo, config_service)

    widget = DatasetExportWidget()
    widget.initialize(config_service, fsm, idm)
    widget.show()
    sys.exit(app.exec())
