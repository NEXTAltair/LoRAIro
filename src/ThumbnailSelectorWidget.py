from PySide6.QtWidgets import QWidget, QGraphicsScene, QGraphicsView, QGraphicsPixmapItem, QGridLayout
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt, QSize, Signal, Slot
from pathlib import Path

from ThumbnailSelectorWidget_ui import Ui_ThumbnailSelectorWidget

class ThumbnailSelectorWidget(QWidget, Ui_ThumbnailSelectorWidget):
    imageSelected = Signal(Path)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        self.thumbnail_size = QSize(128, 128)

        # QGraphicsScene と QGraphicsView を設定
        self.scene = QGraphicsScene(self)
        self.graphics_view = QGraphicsView(self.scene)
        self.scrollAreaThumbnails.setWidget(self.graphics_view)
        self.graphics_view.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.graphics_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.graphics_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # データ
        self.image_paths = []

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_thumbnail_layout()

    @Slot(list)
    def load_images(self, image_paths: list[Path]):
        self.image_paths = image_paths
        self.update_thumbnail_layout()

    def select_first_image(self):
        if self.image_paths:
            self.on_thumbnail_clicked(self.image_paths[0])

    def update_thumbnail_layout(self):
        self.scene.clear()

        # グリッドレイアウトのカラム数を再計算
        button_width = self.thumbnail_size.width()
        grid_width = self.graphics_view.viewport().width()
        column_count = max(grid_width // button_width, 1)

        # サムネイル画像を配置
        for i, file_path in enumerate(self.image_paths):
            self.add_thumbnail_item(file_path, i, column_count)

        # シーンのサイズを更新 (簡略化)
        row_count = (len(self.image_paths) + column_count - 1) // column_count  # 行数を計算
        self.scene.setSceneRect(0, 0, column_count * button_width, row_count * self.thumbnail_size.height())

    def add_thumbnail_item(self, image_path: Path, index: int, column_count: int):
        pixmap = QPixmap(str(image_path)).scaled(
            self.thumbnail_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        item = ThumbnailItem(pixmap, image_path, self)
        self.scene.addItem(item)

        # グリッドレイアウトに追加
        row = index // column_count
        col = index % column_count
        x = col * self.thumbnail_size.width()
        y = row * self.thumbnail_size.height()
        item.setPos(x, y)
        return x, y

    def on_thumbnail_clicked(self, image_path: Path):
        self.imageSelected.emit(image_path)  # imageSelected シグナルを発火

class ThumbnailItem(QGraphicsPixmapItem):
    def __init__(self, pixmap: QPixmap, image_path: Path, parent: QWidget):
        super().__init__(pixmap)
        self.image_path = image_path
        self.parent_widget = parent
        self.setAcceptHoverEvents(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.parent_widget.imageSelected.emit(self.image_path)


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    app = QApplication([])
    widget = ThumbnailSelectorWidget()
    # テスト用の画像パスリスト (様々なサイズの画像を10枚用意)
    image_paths = [
        Path(r"testimg\1_img\file01.png"),
        Path(r"testimg\1_img\file02.png"),
        Path(r"testimg\1_img\file03.png"),
        Path(r"testimg\1_img\file04.png"),
        Path(r"testimg\1_img\file05.png"),
        Path(r"testimg\1_img\file06.png"),
        Path(r"testimg\1_img\file07.png"),
        Path(r"testimg\1_img\file08.png"),
        Path(r"testimg\1_img\file09.png"),
    ]
    widget.load_images(image_paths)
    # imageSelected シグナルに接続して、選択された画像パスを表示
    widget.imageSelected.connect(lambda path: print(f"選択された画像: {path}"))

    widget.show()
    app.exec()