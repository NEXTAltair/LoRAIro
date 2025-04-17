from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHeaderView, QMessageBox, QTableWidgetItem, QWidget

from ...annotations.image_text_reader import ImageTextFileReader
from ...database.db_manager import ImageDatabaseManager
from ...services.configuration_service import ConfigurationService
from ...services.image_processing_service import ImageProcessingService
from ...storage.file_system import FileSystemManager
from ...utils.log import logger
from ..designer.ImageEditWidget_ui import Ui_ImageEditWidget


class ImageEditWidget(QWidget, Ui_ImageEditWidget):
    THUMBNAIL_SIZE = 64

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.main_window = None
        self.config_service = None
        self.idm = None
        self.fsm = None
        self.image_processing_service: ImageProcessingService | None = None
        self.image_text_reader: ImageTextFileReader | None = None
        self.target_resolution = 0
        self.preferred_resolutions = []
        self.upscaler = None
        self.directory_images = []

    def initialize(
        self,
        config_service: ConfigurationService,
        file_system_manager: FileSystemManager,
        image_database_manager: ImageDatabaseManager,
        image_processing_service: ImageProcessingService,
        image_text_reader: ImageTextFileReader,
        main_window=None,
    ):
        """ウィジェットの初期化を行う

        Args:
            config_service (ConfigurationService): 設定管理クラス
            file_system_manager (FileSystemManager): ファイルシステム管理クラス
            image_database_manager (ImageDatabaseManager): 画像データベース管理クラス
            image_processing_service (ImageProcessingService): 画像処理サービス
            image_text_reader (ImageTextFileReader): 画像テキストリーダー
            main_window (Optional): メインウィンドウインスタンス
        """
        self.config_service = config_service
        self.fsm = file_system_manager
        self.idm = image_database_manager
        self.image_processing_service = image_processing_service
        self.image_text_reader = image_text_reader
        self.main_window = main_window
        image_processing_config = self.config_service.get_image_processing_config()
        self.target_resolution = image_processing_config.get("target_resolution", 512)
        self.preferred_resolutions = self.config_service.get_preferred_resolutions()
        self.upscaler = None
        upscalers = [model["name"] for model in self.config_service.get_upscaler_models()]
        self.comboBoxUpscaler.blockSignals(True)
        self.comboBoxUpscaler.clear()
        self.comboBoxUpscaler.addItems(upscalers)
        self.comboBoxUpscaler.blockSignals(False)

        header = self.tableWidgetImageList.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(False)

    def showEvent(self, event):
        """ウィジェットが表示される際にメインウィンドウで選択された画像を表示する"""
        super().showEvent(event)
        if self.main_window and self.main_window.dataset_image_paths:
            self.load_images(self.main_window.dataset_image_paths)

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
            self.THUMBNAIL_SIZE, self.THUMBNAIL_SIZE, Qt.AspectRatioMode.KeepAspectRatio
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
        self.tableWidgetImageList.setItem(
            row_position, 3, QTableWidgetItem(f"{file_height} x {file_width}")
        )

        # サイズ
        file_size = file_path.stat().st_size
        self.tableWidgetImageList.setItem(row_position, 4, QTableWidgetItem(f"{file_size / 1024:.2f} KB"))

        # 既存アノテーション表示を ImageTextFileReader 経由に変更
        annotations = None
        if self.image_text_reader:
            annotations = self.image_text_reader.get_annotations_for_display(file_path)
        else:
            logger.warning("ImageTextFileReader is not initialized. Cannot fetch annotations.")

        if annotations:
            # タグをカンマ区切りの文字列に結合
            tags_str = ", ".join(annotations.get("tags", []))
            self.tableWidgetImageList.setItem(row_position, 5, QTableWidgetItem(tags_str))

            # キャプションをカンマ区切りの文字列に結合 (表示方法は要検討)
            captions_str = " | ".join(annotations.get("captions", []))
            self.tableWidgetImageList.setItem(row_position, 6, QTableWidgetItem(captions_str))
        else:
            # アノテーションが見つからない場合は空欄にする
            self.tableWidgetImageList.setItem(row_position, 5, QTableWidgetItem(""))
            self.tableWidgetImageList.setItem(row_position, 6, QTableWidgetItem(""))

    @Slot()
    def on_tableWidgetImageList_itemSelectionChanged(self):
        selected_items = self.tableWidgetImageList.selectedItems()
        if selected_items:
            row = self.tableWidgetImageList.currentRow()
            file_path = self.tableWidgetImageList.item(row, 2).text()
            self.ImagePreview.load_image(Path(file_path))

    @Slot()
    def on_comboBoxResizeOption_currentIndexChanged(self):
        """選択したリサイズオプションに応じて画像を_configのtarget_resolutionに設定する"""
        # TODO: 解像度の選択肢はコンボボックスのアイテムとして設定してないほうが今後解像度の対応が増えた時にいいかもしれない
        selected_option = self.comboBoxResizeOption.currentText()
        resolution = int(selected_option.split("x")[0])
        self.target_resolution = resolution
        self.config_service.update_image_processing_setting("target_resolution", resolution)
        logger.debug(f"目標解像度の変更: {resolution}")

    @Slot()
    def on_comboBoxUpscaler_currentIndexChanged(self):
        """選択したアップスケーラに応じて設定を更新する"""
        # config_service が初期化される前に呼び出される可能性があるのでチェック
        if self.config_service is None:
            # logger.warning("on_comboBoxUpscaler_currentIndexChanged called before config_service is initialized.")
            return

        selected_option = self.comboBoxUpscaler.currentText()
        # アイテムが空の場合も何もしない
        if not selected_option:
            return

        self.upscaler = selected_option
        # 設定更新を ConfigurationService のメソッド経由に変更
        self.config_service.update_image_processing_setting("upscaler", selected_option)
        logger.debug(f"アップスケーラーの変更: {selected_option}")

    @Slot()
    def on_pushButtonStartProcess_clicked(self):
        try:
            if not self.directory_images:
                QMessageBox.warning(self, "警告", "処理対象の画像がありません。")
                return
            if not self.image_processing_service:
                QMessageBox.critical(self, "エラー", "画像処理サービスが初期化されていません。")
                return
            if not self.main_window:
                QMessageBox.critical(self, "エラー", "メインウィンドウが見つかりません。")
                return

            selected_upscaler = (
                self.comboBoxUpscaler.currentText() if self.comboBoxUpscaler.currentIndex() >= 0 else None
            )

            self.main_window.some_long_process(
                self.image_processing_service.process_images_in_list,
                self.directory_images,
                upscaler_override=selected_upscaler,
            )

        except RuntimeError as e:
            logger.error(f"画像処理サービスの実行準備中にエラー: {e}", exc_info=True)
            QMessageBox.critical(self, "エラー", f"画像処理の開始に失敗しました: {e}")
        except Exception as e:
            logger.error(f"画像処理開始ボタンのクリック処理中に予期せぬエラー: {e}", exc_info=True)
            QMessageBox.critical(self, "エラー", f"予期せぬエラーが発生しました: {e}")


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication, QWidget

    from lorairo.annotations.image_text_reader import ImageTextFileReader
    from lorairo.database.db_core import DefaultSessionLocal
    from lorairo.database.db_repository import ImageRepository
    from lorairo.services.configuration_service import ConfigurationService
    from lorairo.services.image_processing_service import ImageProcessingService
    from lorairo.storage.file_system import FileSystemManager
    from lorairo.utils.config import get_config

    app = QApplication(sys.argv)
    config_data = get_config()
    fsm = FileSystemManager()
    db_path = Path(config_data.get("database", {}).get("path", "Image_database.db"))
    image_repo = ImageRepository(session_factory=DefaultSessionLocal)
    idm = ImageDatabaseManager(image_repo)
    config_service = ConfigurationService()
    image_processing_service = ImageProcessingService(config_service, fsm, idm)
    image_text_reader = ImageTextFileReader(idm)
    test_image_dir = Path(r"TEST/testimg/1_img")
    image_paths = fsm.get_image_files(test_image_dir) if test_image_dir.exists() else []
    widget = ImageEditWidget()
    widget.initialize(
        config_service, fsm, idm, image_processing_service, image_text_reader, main_window=None
    )
    if image_paths:
        widget.load_images(image_paths)
    widget.show()
    sys.exit(app.exec())
