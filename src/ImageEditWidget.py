from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QWidget, QTableWidgetItem, QHeaderView, QMessageBox
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QPixmap

from gui_file.ImageEditWidget_ui import Ui_ImageEditWidget

from module.log import get_logger
from module.file_sys import FileSystemManager
from module.db import ImageDatabaseManager
from caption_tags import ImageAnalyzer
from ImageEditor import ImageProcessingManager

class ImageEditWidget(QWidget, Ui_ImageEditWidget):
    THUMBNAIL_SIZE = 64
    FILE_SIZE_UNIT = 1024  # KB
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = get_logger("ImageEditWidget")
        self.setupUi(self)
        self.idm = None

    def initialize(self, cm: 'ConfigManager', fsm: FileSystemManager,
                         idm: ImageDatabaseManager, main_window):
        self.cm = cm
        self.idm = idm
        self.fsm = fsm
        self.main_window = main_window
        self.target_resolution = self.cm.config['image_processing']['target_resolution']
        self.preferred_resolutions = self.cm.config['preferred_resolutions']
        self.comboBoxResizeOption.currentText()
        upscalers = [upscaler['name'] for upscaler in self.cm.upscaler_models.values()]
        self.comboBoxUpscaler.addItems(upscalers)

        header = self.tableWidgetImageList.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(False)

    def initialize_processing(self):
        """画像処理に必要なクラスの初期化"""
        self.fsm.initialize(Path(self.cm.config['directories']['output']), self.target_resolution)
        self.ipm = ImageProcessingManager(self.fsm, self.target_resolution,
                                          self.preferred_resolutions)

    def showEvent(self, event):
        """ウィジェットが表示される際にメインウィンドウで選択された画像を表示する"""
        super().showEvent(event)
        if self.cm.dataset_image_paths:
            self.load_images(self.cm.dataset_image_paths)

    def load_images(self, directory_images: list):
        self.directory_images = directory_images
        self.tableWidgetImageList.setRowCount(0)
        self.ImagePreview.load_image(Path(directory_images[0]))
        for image_path in directory_images:
            self._add_image_to_table(image_path)

    def _add_image_to_table(self, file_path: Path):
        str_filename = str(file_path.name)
        str_file_path = str(file_path)
        row_position = self.tableWidgetImageList.rowCount()
        self.tableWidgetImageList.insertRow(row_position)

        # サムネイル
        thumbnail = QPixmap(str(file_path)).scaled(
            self.THUMBNAIL_SIZE, self.THUMBNAIL_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio
        )
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

        # 既存アノテーション
        existing_annotations = ImageAnalyzer.get_existing_annotations(file_path)
        if existing_annotations:
            # タグをカンマ区切りの文字列に結合
            tags_str = ', '.join([tag_info['tag'] for tag_info in existing_annotations['tags']])
            self.tableWidgetImageList.setItem(row_position, 5, QTableWidgetItem(tags_str))

            # キャプションをカンマ区切りの文字列に結合
            captions_str = ', '.join([caption_info['caption'] for caption_info in existing_annotations['captions']])
            self.tableWidgetImageList.setItem(row_position, 6, QTableWidgetItem(captions_str))

    @Slot()
    def on_tableWidgetImageList_itemSelectionChanged(self):
        selected_items = self.tableWidgetImageList.selectedItems()
        if selected_items:
            row = self.tableWidgetImageList.currentRow()
            file_path = self.tableWidgetImageList.item(row, 2).text()
            self.ImagePreview.load_image(Path(file_path))

    @Slot()
    def on_comboBoxResizeOption_currentIndexChanged(self):
        """選択したリサイズオプションに応じて画像を_configのtarget_resolutionに設定する
        """
        # TODO: 解像度の選択肢はコンボボックスのアイテムとして設定してないほうが今後解像度の対応が増えた時にいいかもしれない
        selected_option = self.comboBoxResizeOption.currentText()
        resolution = int(selected_option.split('x')[0])
        self.target_resolution = resolution
        self.cm.config['image_processing']['target_resolution'] = resolution
        self.logger.debug(f"目標解像度の変更: {resolution}")

    @Slot()
    def on_comboBoxUpscaler_currentIndexChanged(self):
        """選択したアップスケーラに応じて_configのupscalerに設定する
        """
        selected_option = self.comboBoxUpscaler.currentText()
        self.upscaler = selected_option
        self.cm.config['image_processing']['upscaler'] = selected_option
        self.logger.debug(f"アップスケーラーの変更: {selected_option}")

    @Slot()
    def on_pushButtonStartProcess_clicked(self):
        try:
            self.initialize_processing()
            self.main_window.some_long_process(self.process_all_images)
        except Exception as e:
            self.logger.error(f"画像処理中にエラーが発生しました: {str(e)}")
            QMessageBox.critical(self, "エラー", f"処理中にエラーが発生しました: {str(e)}")

    def process_all_images(self, progress_callback=None, status_callback=None, is_canceled=None):
        try:
            total_images = len(self.directory_images)
            for index, image_path in enumerate(self.directory_images):
                if is_canceled and is_canceled():
                    break
                self.process_image(image_path)
                # 進捗の更新
                if progress_callback:
                    progress = int((index + 1) / total_images * 100)
                    progress_callback(progress)
                # ステータスの更新
                if status_callback:
                    status_callback(f"画像 {index + 1}/{total_images} を処理中")
        except Exception as e:
            self.logger.error(f"画像処理中にエラーが発生しました: {str(e)}")
            raise e

    def process_image(self, image_file: Path):
        image_id = self.idm.detect_duplicate_image(image_file)
        if not image_id:
            image_id, original_image_metadata = self.idm.register_original_image(image_file, self.fsm)
        else:
            original_image_metadata = self.idm.get_image_metadata(image_id)

        existing_annotations = ImageAnalyzer.get_existing_annotations(image_file)
        if existing_annotations:
            self.idm.save_annotations(image_id, existing_annotations)
        else:
            self.idm.save_annotations(image_id, {'tags': [], 'captions': []})

        existing_processed_image = self.idm.check_processed_image_exists(image_id, self.target_resolution)
        if existing_processed_image:
            self.logger.info(f"指定解像度の画像は保存済みです: {image_file}")
            return

        processed_image = self.ipm.process_image(
            image_file,
            original_image_metadata['has_alpha'],
            original_image_metadata['mode'],
            upscaler=self.upscaler
        )
        if processed_image:
            self.handle_processing_result(processed_image, image_file, image_id)
        else:
            self.logger.warning(f"画像処理スキップ: {image_file}")

    def handle_processing_result(self, processed_image, image_file, image_id):
        processed_path = self.fsm.save_processed_image(processed_image, image_file)
        processed_metadata = self.fsm.get_image_info(processed_path)
        self.idm.register_processed_image(image_id, processed_path, processed_metadata)
        self.logger.info(f"画像処理完了: {image_file} -> {processed_path}")

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    from gui import MainWindow, ConfigManager
    from module.config import get_config
    import sys

    app = QApplication(sys.argv)
    config = get_config()
    fsm = FileSystemManager()
    idm = ImageDatabaseManager()
    cm = ConfigManager()
    main_window = MainWindow()
    image_paths = fsm.get_image_files(Path(r"testimg\10_Kaya")) # 画像ファイルのディレクトリを指定
    widget = ImageEditWidget()
    widget.initialize(cm, fsm, idm, main_window)
    widget.load_images(image_paths)
    widget.show()
    sys.exit(app.exec())