from PySide6.QtWidgets import QWidget, QPushButton, QGraphicsScene, QGraphicsPixmapItem
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtCore import Qt, QSize, Signal, Slot, QTimer
from pathlib import Path

from DatasetOverviewWidget_ui import Ui_DatasetOverviewWidget
from module.file_sys import FileSystemManager

class DatasetOverviewWidget(QWidget, Ui_DatasetOverviewWidget):
    dataset_loaded = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.minimum_thumbnail_size = QSize(150, 150)
        self.current_pixmap = None
        self.graphics_scene = QGraphicsScene(self)
        self.previewgraphicsView.setScene(self.graphics_scene)
        self.mainSplitter.splitterMoved.connect(self.on_splitter_moved)

        # スプリッターの初期サイズを設定
        self.mainSplitter.setSizes([self.width() * 2 // 3, self.width() // 3])
        self.infoSplitter.setSizes([self.height() * 2 // 10, self.height() * 2 // 10 + self.height() * 6 // 10])


    def load_images(self, fsm: FileSystemManager, image_files: list):
        self.fsm = fsm
        self.image_files = image_files
        self.display_dataset_info()
        self.dataset_loaded.emit()

        # 初期画像の表示
        if self.image_files:
            self.update_preview(Path(self.image_files[0]))

    @Slot(int, int)
    def on_splitter_moved(self, pos, index):
        self.adjust_preview_size()

    def adjust_preview_size(self):
        if self.current_pixmap:
            self.resize_preview()
            self.previewgraphicsView.invalidateScene()

    def resize_preview(self):
        if self.current_pixmap:
            QTimer.singleShot(0, self._do_resize_preview)

    def _do_resize_preview(self):
        if self.current_pixmap:
            view_size = self.previewScrollArea.viewport().size()
            scaled_pixmap = self.current_pixmap.scaled(
                view_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.graphics_scene.clear()
            self.graphics_scene.addPixmap(scaled_pixmap)
            self.graphics_scene.setSceneRect(scaled_pixmap.rect())
            self.previewgraphicsView.setSceneRect(self.graphics_scene.sceneRect())
            self.previewgraphicsView.fitInView(self.graphics_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def update_preview(self, image_path: Path):
        self.current_pixmap = QPixmap(str(image_path))
        self.resize_preview()
        # ここで明示的に fitInView を呼び出す
        self.previewgraphicsView.fitInView(self.graphics_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def display_dataset_info(self):
        self.clear_layout(self.gridLayout)
        num_columns = 4  # 例: 4列のグリッドを作成
        for i, image_path in enumerate(self.image_files):
            row = i // num_columns
            col = i % num_columns
            self.add_thumbnail_item(image_path, row, col)
        if self.image_files:
            self.update_metadata(self.image_files[0])

    def clear_layout(self, layout):
        """レイアウトからウィジェットを削除する"""
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def add_thumbnail_item(self, image_path: Path, row: int, col: int):
        try:
            button = self.create_thumbnail_button(image_path)
            self.gridLayout.addWidget(button, row, col)
        except Exception as e:
            print(f"サムネイル追加エラー: {e}")

    def create_thumbnail_button(self, image_path: Path):
        button = QPushButton(self.thumbnailContainer)
        # テンプレートの設定を継承
        button.setIconSize(self.thumbnailButtonTemplate.iconSize())
        button.setFlat(self.thumbnailButtonTemplate.isFlat())
        button.setSizePolicy(self.thumbnailButtonTemplate.sizePolicy())

        # 個別の設定
        button.setToolTip(str(image_path))
        button.clicked.connect(self.onThumbnailClicked)

        pixmap = QPixmap(str(image_path))
        scaled_pixmap = self.scale_pixmap(pixmap, button.iconSize().width())
        button.setIcon(QIcon(scaled_pixmap))

        return button

    def scale_pixmap(self, pixmap, size):
        return pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, 
                             Qt.TransformationMode.SmoothTransformation)

    def onThumbnailClicked(self):
        """サムネイルボタンのクリックを処理する"""
        clicked_button = self.sender()
        if isinstance(clicked_button, QPushButton):
            image_path = clicked_button.toolTip()
            self.update_metadata(Path(image_path))

    def calculate_aspect_ratio(self, width, height):
        """アスペクト比を計算する"""
        def gcd(a, b):
            while b:
                a, b = b, a % b
            return a

        ratio_gcd = gcd(width, height)
        return f"{width // ratio_gcd} : {height // ratio_gcd}"

    def update_metadata(self, image_path: Path):
        """メタデータを更新する"""
        if image_path and self.fsm:
            metadata = self.fsm.get_image_info(image_path)
            self.set_metadata_labels(metadata, image_path)
            self.update_preview(image_path)
        else:
            self.clear_metadata()

    def set_metadata_labels(self, metadata, image_path):
        """メタデータラベルを設定する"""
        self.fileNameValueLabel.setText(metadata['filename'])
        self.imagePathValueLabel.setText(str(image_path))
        self.formatValueLabel.setText(metadata['format'])
        self.modeValueLabel.setText(metadata['mode'])
        self.alphaChannelValueLabel.setText("あり" if metadata['has_alpha'] else "なし")
        self.resolutionValueLabel.setText(f"{metadata['width']} x {metadata['height']}")
        self.aspectRatioValueLabel.setText(self.calculate_aspect_ratio(metadata['width'], metadata['height']))
        self.extensionValueLabel.setText(metadata['extension'])

    def clear_metadata(self):
        """メタデータをクリアする"""
        labels = [
            self.fileNameValueLabel, self.imagePathValueLabel, self.formatValueLabel,
            self.modeValueLabel, self.alphaChannelValueLabel, self.resolutionValueLabel,
            self.extensionValueLabel, self.aspectRatioValueLabel,
        ]
        for label in labels:
            label.clear()
        self.clear_preview()

    def clear_preview(self):
        self.current_pixmap = None
        self.graphics_scene.clear()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resize_preview()

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    widget = DatasetOverviewWidget()
    widget.show()
    sys.exit(app.exec())