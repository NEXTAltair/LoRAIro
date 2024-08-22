from PySide6.QtWidgets import QWidget, QTableWidgetItem, QHeaderView, QMessageBox
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QPixmap
from pathlib import Path
from module.log import get_logger
from ImageEditWidget_ui import Ui_ImageEditWidget

from module.file_sys import FileSystemManager
from module.db import ImageDatabaseManager
from caption_tags import ImageAnalyzer
from ImageEditor import ImageProcessingManager

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gui import ConfigManager
class ImageEditWidget(QWidget, Ui_ImageEditWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = get_logger(__name__)
        self.setupUi(self)
        self.idm = None

    def initialize(self, cm: 'ConfigManager', idm: ImageDatabaseManager):
        self.cm = cm
        self.idm = idm
        self.target_resolution = self.cm.config['image_processing']['target_resolution']
        self.preferred_resolutions = self.cm.config['preferred_resolutions']
        self.comboBoxResizeOption.currentText()

        header = self.tableWidgetImageList.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(False)
        # シグナル/スロット接続
        self.tableWidgetImageList.itemSelectionChanged.connect(self.update_preview)

    @Slot(list)
    def load_images(self, image_paths: list):
        self.tableWidgetImageList.setRowCount(0)
        self.ImagePreview.load_image(Path(image_paths[0]))
        for image_path in image_paths:
            self._add_image_to_table(image_path)

    @Slot()
    def update_preview(self):
        selected_items = self.tableWidgetImageList.selectedItems()
        if selected_items:
            row = self.tableWidgetImageList.currentRow()  # 選択されている行のインデックスを取得
            file_path = self.tableWidgetImageList.item(row, 2).text()  # 3列目からファイルパスを取得
            self.ImagePreview.load_image(Path(file_path))  # ImagePreview の load_image を呼び出す

    def _add_image_to_table(self, file_path: Path):
        str_filename = str(file_path.name)
        str_file_path = str(file_path)
        row_position = self.tableWidgetImageList.rowCount()
        self.tableWidgetImageList.insertRow(row_position)

        # サムネイル
        thumbnail = QPixmap(str_file_path).scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio)
        thumbnail_item = QTableWidgetItem()
        thumbnail_item.setData(Qt.ItemDataRole.DecorationRole, thumbnail)
        self.tableWidgetImageList.setItem(row_position, 0, thumbnail_item)

        # ファイル名
        self.tableWidgetImageList.setItem(row_position, 1, QTableWidgetItem(str_filename))
        # パス
        self.tableWidgetImageList.setItem(row_position, 2, QTableWidgetItem(str_file_path))

        # 高と幅
        pixmap = QPixmap(str_file_path)
        file_height = pixmap.height()
        file_width = pixmap.width()
        self.tableWidgetImageList.setItem(row_position, 3, QTableWidgetItem(f"{file_height} x {file_width}"))

        # サイズ
        file_size = file_path.stat().st_size
        self.tableWidgetImageList.setItem(row_position, 4, QTableWidgetItem(f"{file_size / 1024:.2f} KB"))

        #既存タグ
        existing_annotations = ImageAnalyzer.get_existing_annotations(file_path)
        if existing_annotations:
            # existing_annotationsから 'tag' キーの値を取り出してカンマ区切りの文字列にする
            tags_str = ', '.join([tag['tag'] for tag in existing_annotations['tags']])
            self.tableWidgetImageList.setItem(row_position, 5, QTableWidgetItem(tags_str))
            captions_str = ', '.join([caption['caption'] for caption in existing_annotations['captions']])
            self.tableWidgetImageList.setItem(row_position, 6, QTableWidgetItem(captions_str))

    @Slot()
    def on_comboBoxResizeOption_currentIndexChanged(self):
        """選択したリサイズオプションに応じて画像を_configのtarget_resolutionに設定する
        """
        # TODO: 解像度の選択肢はコンボボックスのアイテムとして設定してないほうがいいかもしれない
        selected_option = self.comboBoxResizeOption.currentText()
        try:
            resolution = int(selected_option.split('x')[0])
            self.target_resolution = resolution
            self.cm.config['image_processing']['target_resolution'] = resolution
            # print(f"Target resolution updated to: {resolution}")  # デバッグ用

        except ValueError:
            self.logger.error(f"Invalid resolution: {selected_option}")
            self.comboBoxResizeOption.setCurrentIndex(0)  # デフォルト値に戻す

    @Slot()
    def on_comboBoxUpscaler_currentIndexChanged(self):
        """選択したアップスケーラに応じて_configのrealesrgan_modelに設定する
        """
        # TODO: アップスケーラの選択肢はdb_managerから取得するべきかもしれない
        selected_option = self.comboBoxUpscaler.currentText()
        self.cm.config['image_processing']['upscaler'] = selected_option
        # print(f"Upscaler updated to: {selected_option}")  # デバッグ用

    @Slot()
    def on_pushButtonStartProcess_clicked(self):
        try:
            self.fsm = FileSystemManager()
            self.fsm.initialize(Path(self.cm.config['directories']['output']), self.target_resolution)
            self.ipm = ImageProcessingManager(self.fsm, self.target_resolution, 
                                              self.preferred_resolutions)
            # 処理対象の画像を取得
            image_files = self.get_selected_images()

            if not image_files:
                QMessageBox.warning(self, "警告", "処理する画像が選択されていません。")
                return

            for image_file in image_files:
                image_file = Path(image_file)
                # 元画像の情報を取得
                original_metadata = self.fsm.get_image_info(image_file)
                # データベースに画像情報を保存
                db_stored_original_path = self.fsm.save_original_image(image_file)
                image_id, _ = self.idm.save_original_metadata(db_stored_original_path, original_metadata)
                existing_annotations = ImageAnalyzer.get_existing_annotations(image_file)
                if existing_annotations:
                    self.idm.save_annotations(image_id, existing_annotations)

                # 画像処理を実行
                processed_image = self.ipm.process_image(
                    image_file,
                    original_metadata['has_alpha'],
                    original_metadata['mode']
                )

                if processed_image:
                    # 処理済み画像を保存
                    processed_path = self.fsm.save_processed_image(processed_image, image_file)

                    # 処理済み画像のメタデータを取得
                    processed_metadata = self.fsm.get_image_info(processed_path)

                    # データベースに処理済み画像情報を保存
                    self.idm.save_processed_metadata(image_id, processed_path, processed_metadata)

                    self.logger.info(f"画像処理完了: {image_file} -> {processed_path}")
                else:
                    self.logger.warning(f"画像処理スキップ: {image_file}")

            QMessageBox.information(self, "完了", "すべての画像の処理が完了しました。")

        except Exception as e:
            self.logger.error(f"画像処理中にエラーが発生しました: {str(e)}")
            QMessageBox.critical(self, "エラー", f"処理中にエラーが発生しました: {str(e)}")

    def get_selected_images(self):
        # 現在はすべての画像を処理対象とする
        # 後々、選択された画像のみを処理するように変更可能
        return [self.tableWidgetImageList.item(row, 2).text()
                for row in range(self.tableWidgetImageList.rowCount())]

    def refresh_config(self, new_config):
        self.cm.config = new_config
        # 必要に応じてUIを更新

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    from gui import ConfigManager
    from module.config import get_config
    import sys

    app = QApplication(sys.argv)
    config = get_config()
    fsm = FileSystemManager()
    ia = ImageAnalyzer()
    idm = ImageDatabaseManager()
    cm = ConfigManager()
    image_paths = fsm.get_image_files(Path(r"testimg\10_Kaya")) # 画像ファイルのディレクトリを指定
    widget = ImageEditWidget()
    widget.initialize(cm, ia, idm)
    widget.load_images(image_paths)
    widget.show()
    sys.exit(app.exec())