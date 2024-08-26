from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Signal, Slot
from pathlib import Path
from DatasetOverviewWidget_ui import Ui_DatasetOverviewWidget
from module.file_sys import FileSystemManager
from caption_tags import ImageAnalyzer

class DatasetOverviewWidget(QWidget, Ui_DatasetOverviewWidget):
    dataset_loaded = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.image_files = []

        # スプリッターの初期サイズを設定
        self.mainSplitter.setSizes([self.width()  // 3, self.width() * 2 // 3])
        self.infoSplitter.setSizes([self.height() * 1 // 5, self.height() * 2 // 5])

        # シグナル/スロット接続
        self.thumbnailSelector.imageSelected.connect(self.update_preview)

    def load_images(self, image_files: list):
        self.image_files = image_files
        self.thumbnailSelector.load_images(image_files)
        self.dataset_loaded.emit()

        # 初期画像の表示
        if self.image_files:
            self.update_preview(Path(self.image_files[0]))

    @Slot(Path)
    def update_preview(self, image_path: Path):
        self.ImagePreview.load_image(image_path)
        self.update_metadata(image_path)

    def update_metadata(self, image_path: Path):
        if image_path:
            metadata = FileSystemManager.get_image_info(image_path)
            self.set_metadata_labels(metadata, image_path)
            self.update_annotations(image_path)

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
    from module.file_sys import FileSystemManager
    import sys

    fsm = FileSystemManager()
    directory = Path(r"testimg\10_shira")
    image_files: list[Path] = fsm.get_image_files(directory)
    app = QApplication(sys.argv)
    widget = DatasetOverviewWidget()
    widget.load_images(fsm, image_files)
    widget.show()
    sys.exit(app.exec())