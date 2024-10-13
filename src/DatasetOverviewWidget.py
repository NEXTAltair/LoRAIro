from pathlib import Path

from PySide6.QtWidgets import QWidget, QMessageBox
from PySide6.QtCore import Qt, Signal, Slot, QDateTime

from gui_file.DatasetOverviewWidget_ui import Ui_DatasetOverviewWidget

from module.file_sys import FileSystemManager
from module.db import ImageDatabaseManager
from module.log import get_logger
from caption_tags import ImageAnalyzer

class DatasetOverviewWidget(QWidget, Ui_DatasetOverviewWidget):
    dataset_loaded = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = get_logger("DatasetOverviewWidget")
        self.setupUi(self)
        self.image_files = []

        # スプリッターの初期サイズを設定
        self.mainSplitter.setSizes([self.width()  // 3, self.width() * 2 // 3])
        self.infoSplitter.setSizes([self.height() * 1 // 5, self.height() * 2 // 5])

        # シグナル/スロット接続
        self.thumbnailSelector.imageSelected.connect(self.update_preview)
        self.dbSearchWidget.filterApplied.connect(self.on_filter_applied)

    def initialize(self, cm: 'ConfigManager', idm: 'ImageDatabaseManager'):
        self.cm = cm
        self.idm = idm

    def showEvent(self, event):
        """ウィジェットが表示される際に呼び出されるイベントハンドラ"""
        if self.cm.dataset_image_paths:
            self.load_images(self.cm.dataset_image_paths)

    def load_images(self, image_files: list):
        self.image_files = image_files
        self.thumbnailSelector.load_images(image_files)
        self.dataset_loaded.emit()

        # 初期画像の表示
        if self.image_files:
            self.update_preview(Path(self.image_files[0]))

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
        self.update_thumbnail_selector(list(self.image_path_id_map.values()))

    @Slot(Path)
    def update_preview(self, image_path: Path):
        self.ImagePreview.load_image(image_path)
        self.update_metadata(image_path)

    def update_metadata(self, image_path: Path):
        if image_path:
            metadata = FileSystemManager.get_image_info(image_path)
            self.set_metadata_labels(metadata, image_path)
            self.update_annotations(image_path)

    def update_thumbnail_selector(self, image_paths: list[Path]):
        # サムネイルセレクターに新しい画像リストをロード
        self.thumbnailSelector.load_images(image_paths)

    def set_metadata_labels(self, metadata, image_path):
        self.fileNameValueLabel.setText(metadata['filename'])
        self.imagePathValueLabel.setText(str(image_path))
        self.formatValueLabel.setText(metadata['format'])
        self.modeValueLabel.setText(metadata['mode'])
        self.alphaChannelValueLabel.setText("あり" if metadata['has_alpha'] else "なし")
        self.resolutionValueLabel.setText(f"{metadata['width']} x {metadata['height']}")
        self.aspectRatioValueLabel.setText(self.calculate_aspect_ratio(metadata['width'], metadata['height']))
        self.extensionValueLabel.setText(metadata['extension'])

    def clear_metadata(self):
        labels = [
            self.fileNameValueLabel, self.imagePathValueLabel, self.formatValueLabel,
            self.modeValueLabel, self.alphaChannelValueLabel, self.resolutionValueLabel,
            self.extensionValueLabel, self.aspectRatioValueLabel,
        ]
        for label in labels:
            label.clear()
        self.tagsTextEdit.clear()
        self.captionTextEdit.clear()

    def update_annotations(self, image_path: Path):
        # この部分は実際のデータ取得方法に応じて実装する必要があります
        annotations = ImageAnalyzer.get_existing_annotations(image_path)
        if annotations:
            # タグを抽出して結合
            tags = [tag_info['tag'] for tag_info in annotations.get('tags', [])]
            tags_text = ", ".join(tags)
            self.tagsTextEdit.setPlainText(tags_text)

            # キャプションを抽出して結合
            captions = [caption_info['caption'] for caption_info in annotations.get('captions', [])]
            captions_text = " | ".join(captions)  # キャプションをパイプで区切って結合
            self.captionTextEdit.setPlainText(captions_text)

        elif annotations is None:
            # DBkからアノテーション情報を検索
            image_id = self.idm.detect_duplicate_image(image_path)
            image_data = self.idm.get_image_annotations(image_id)
            tags_text = ', '.join([tag_data.get('tag','') for tag_data in image_data['tags']])
            self.tagsTextEdit.setPlainText(tags_text)
            captions_text = ', '.join([caption_data.get('caption', '') for caption_data in image_data['captions']])
            self.captionTextEdit.setPlainText(captions_text)
        else:
            self.tagsTextEdit.clear()
            self.captionTextEdit.clear()

    @staticmethod
    def calculate_aspect_ratio(width, height):
        def gcd(a, b):
            while b:
                a, b = b, a % b
            return a
        ratio_gcd = gcd(width, height)
        return f"{width // ratio_gcd} : {height // ratio_gcd}"

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    from gui import ConfigManager
    from module.file_sys import FileSystemManager
    import sys
    from module.log import  setup_logger
    logconf = {'level': 'DEBUG', 'file': 'DatasetOverviewWidget.log'}
    setup_logger(logconf)
    cm = ConfigManager()
    fsm = FileSystemManager()
    directory = Path(r"testimg\10_shira")
    image_files: list[Path] = fsm.get_image_files(directory)
    app = QApplication(sys.argv)
    widget = DatasetOverviewWidget()
    widget.initialize(cm)
    widget.load_images(image_files)
    widget.show()
    sys.exit(app.exec())