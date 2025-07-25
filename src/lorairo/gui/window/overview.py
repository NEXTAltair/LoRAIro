from pathlib import Path

from PIL import Image
from PySide6.QtCore import QDateTime, Qt, Signal, Slot
from PySide6.QtWidgets import QMessageBox, QWidget

from lorairo.services.configuration_service import ConfigurationService

from ...annotations.caption_tags import ImageAnalyzer
from ...database.db_manager import ImageDatabaseManager
from ...storage.file_system import FileSystemManager
from ...utils.log import logger
from ..designer.DatasetOverviewWidget_ui import Ui_DatasetOverviewWidget


class DatasetOverviewWidget(QWidget, Ui_DatasetOverviewWidget):
    dataset_loaded = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.image_files = []

        # スプリッターの初期サイズを設定
        self.mainSplitter.setSizes([self.width() // 3, self.width() * 2 // 3])
        self.infoSplitter.setSizes([self.height() * 1 // 5, self.height() * 2 // 5])

        # シグナル/スロット接続
        self.thumbnailSelector.imageSelected.connect(self.update_preview)
        self.dbSearchWidget.filterApplied.connect(self.on_filter_applied)

    def initialize(self, config_service: ConfigurationService, idm: ImageDatabaseManager, main_window=None):
        self.config_service = config_service
        self.idm = idm
        self.main_window = main_window

    def showEvent(self, event):
        """ウィジェットが表示される際に呼び出されるイベントハンドラ"""
        if self.main_window and self.main_window.dataset_image_paths:
            self.load_images(self.main_window.dataset_image_paths)

    def load_images(self, image_files: list):
        self.image_files = image_files
        self.thumbnailSelector.load_images(image_files)
        self.dataset_loaded.emit()

        # 初期画像の表示
        if self.image_files:
            self.update_preview(Path(self.image_files[0]))

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
            logger.info(f"検索条件に一致する画像がありませんでした: {filter_type}  {filter_text}")
            QMessageBox.critical(
                self, "info", f"検索条件に一致する画像がありませんでした: {filter_type}  {filter_text}"
            )
            return

        # idとpathの対応だけを取り出す（stored_image_pathは既に絶対パス）
        self.image_metadata_map = {
            item["id"]: {"path": Path(item["stored_image_path"]), "metadata": item}
            for item in filtered_image_metadata
        }

        # サムネイルセレクターを更新（IDとパスのペアで渡す）
        image_data = [(Path(item["stored_image_path"]), item["id"]) for item in filtered_image_metadata]
        self.thumbnailSelector.load_images_with_ids(image_data)

    @Slot(Path)
    def update_preview(self, image_path: Path):
        # PILイメージを直接取得してプレビューに表示
        try:
            from ...database.db_core import resolve_stored_path

            resolved_path = resolve_stored_path(str(image_path))

            # PILイメージとして読み込み
            with Image.open(resolved_path) as pil_image:
                # プレビューにPILイメージを直接渡す
                self.ImagePreview.load_image_from_pil(pil_image.copy(), image_path.name)

            # メタデータも更新
            self.update_metadata(image_path)
        except Exception as e:
            logger.error(f"プレビュー更新に失敗しました: {image_path}, エラー: {e}")
            self.clear_metadata()

    def update_metadata(self, image_path: Path):
        if image_path:
            try:
                # パスを動的に解決
                from ...database.db_core import resolve_stored_path

                resolved_path = resolve_stored_path(str(image_path))
                metadata = FileSystemManager.get_image_info(resolved_path)
                self.set_metadata_labels(metadata, image_path)
                self.update_annotations(image_path)
            except Exception as e:
                logger.error(f"メタデータの取得に失敗しました: {image_path}, エラー: {e}")
                self.clear_metadata()

    def update_thumbnail_selector(self, image_data: list[tuple[Path, int]]):
        # サムネイルセレクターに新しい画像リストをロード（IDベース）
        self.thumbnailSelector.load_images_with_ids(image_data)

    def set_metadata_labels(self, metadata, image_path):
        self.fileNameValueLabel.setText(metadata["filename"])
        self.imagePathValueLabel.setText(str(image_path))
        self.formatValueLabel.setText(metadata["format"])
        self.modeValueLabel.setText(metadata["mode"])
        self.alphaChannelValueLabel.setText("あり" if metadata["has_alpha"] else "なし")
        self.resolutionValueLabel.setText(f"{metadata['width']} x {metadata['height']}")
        self.aspectRatioValueLabel.setText(
            self.calculate_aspect_ratio(metadata["width"], metadata["height"])
        )
        self.extensionValueLabel.setText(metadata["extension"])

    def clear_metadata(self):
        labels = [
            self.fileNameValueLabel,
            self.imagePathValueLabel,
            self.formatValueLabel,
            self.modeValueLabel,
            self.alphaChannelValueLabel,
            self.resolutionValueLabel,
            self.extensionValueLabel,
            self.aspectRatioValueLabel,
        ]
        for label in labels:
            label.clear()
        self.tagsTextEdit.clear()
        self.captionTextEdit.clear()

    def update_annotations(self, image_path: Path):
        # フィルター結果表示時は image_metadata_map から効率的にIDを取得
        image_id = None
        if hasattr(self, "image_metadata_map"):
            for id_key, data in self.image_metadata_map.items():
                if data["path"] == image_path:
                    image_id = id_key
                    break

        # image_metadata_map にない場合は従来の検索方法
        if image_id is None:
            image_id = self.idm.detect_duplicate_image(image_path)

        if image_id is not None:
            # データベースからアノテーション情報を取得
            image_data = self.idm.get_image_annotations(image_id)

            # タグを表示
            tags_text = ", ".join([tag_data.get("tag", "") for tag_data in image_data.get("tags", [])])
            self.tagsTextEdit.setPlainText(tags_text)

            # キャプションを表示
            captions_text = " | ".join(
                [caption_data.get("caption", "") for caption_data in image_data.get("captions", [])]
            )
            self.captionTextEdit.setPlainText(captions_text)
        else:
            # image_id が見つからない場合はクリア
            self.tagsTextEdit.clear()
            self.captionTextEdit.clear()

    @staticmethod
    def calculate_aspect_ratio(width, height):  # TODO: アスペクト比の計算がなにかおかしい
        def gcd(a, b):
            while b:
                a, b = b, a % b
            return a

        ratio_gcd = gcd(width, height)
        return f"{width // ratio_gcd} : {height // ratio_gcd}"


if __name__ == "__main__":
    import sys
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from lorairo.database.db_core import DefaultSessionLocal
    from lorairo.database.db_manager import ImageDatabaseManager
    from lorairo.database.db_repository import ImageRepository
    from lorairo.services.configuration_service import ConfigurationService
    from lorairo.storage.file_system import FileSystemManager
    from lorairo.utils.config import get_config
    from lorairo.utils.log import initialize_logging

    app = QApplication(sys.argv)
    config_data = get_config()
    log_config = config_data.get("log", {})
    initialize_logging(log_config)

    config_service = ConfigurationService()
    image_repo = ImageRepository(session_factory=DefaultSessionLocal)
    idm = ImageDatabaseManager(image_repo, config_service)
    fsm = FileSystemManager()

    directory = Path(r"testimg/10_shira")
    image_files: list[Path] = fsm.get_image_files(directory) if directory.exists() else []

    widget = DatasetOverviewWidget()
    widget.initialize(config_service, idm, main_window=None)
    if image_files:
        widget.load_images(image_files)
    widget.show()
    sys.exit(app.exec())
