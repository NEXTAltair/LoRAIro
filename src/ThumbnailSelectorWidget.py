from PySide6.QtWidgets import QWidget, QGraphicsScene, QGraphicsView, QGraphicsPixmapItem, QVBoxLayout, QApplication, QGraphicsItem
from PySide6.QtGui import QPixmap, QBrush, QColor, QPen
from PySide6.QtCore import Qt, QSize, Signal, Slot, QRectF
from pathlib import Path
from ThumbnailSelectorWidget_ui import Ui_ThumbnailSelectorWidget

class ThumbnailItem(QGraphicsPixmapItem):
    def __init__(self, pixmap: QPixmap, image_path: Path, parent: 'ThumbnailSelectorWidget'):
        super().__init__(pixmap)
        self.image_path = image_path
        self.parent_widget = parent
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

    def paint(self, painter, option, widget):
        super().paint(painter, option, widget)
        if self.isSelected():
            pen = QPen(QColor(0, 120, 215), 3)
            painter.setPen(pen)
            painter.drawRect(self.boundingRect().adjusted(1, 1, -1, -1))

class CustomGraphicsView(QGraphicsView):
    itemClicked = Signal(QGraphicsPixmapItem, Qt.KeyboardModifier)

    def mousePressEvent(self, event):
        item = self.itemAt(event.pos())
        if isinstance(item, ThumbnailItem):
            self.itemClicked.emit(item, event.modifiers())
        super().mousePressEvent(event)

class ThumbnailSelectorWidget(QWidget, Ui_ThumbnailSelectorWidget):
    imageSelected = Signal(Path)
    selectionChanged = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.thumbnail_size = QSize(128, 128)
        self.scene = QGraphicsScene(self)
        self.graphics_view = CustomGraphicsView(self.scene)
        self.graphics_view.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.graphics_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.graphics_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.graphics_view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.graphics_view.itemClicked.connect(self.handle_item_selection)
        
        layout = QVBoxLayout(self.widgetThumbnailsContent)
        layout.addWidget(self.graphics_view)
        self.widgetThumbnailsContent.setLayout(layout)
        
        self.image_paths = []
        self.thumbnail_items = []
        self.last_selected_item = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_thumbnail_layout()

    @Slot(list)
    def load_images(self, image_paths: list[Path]):
        self.image_paths = image_paths
        self.update_thumbnail_layout()

    def update_thumbnail_layout(self):
        self.scene.clear()
        self.thumbnail_items.clear()

        button_width = self.thumbnail_size.width()
        grid_width = self.scrollAreaThumbnails.viewport().width()
        column_count = max(grid_width // button_width, 1)

        for i, file_path in enumerate(self.image_paths):
            self.add_thumbnail_item(file_path, i, column_count)

        row_count = (len(self.image_paths) + column_count - 1) // column_count
        scene_height = row_count * self.thumbnail_size.height()
        self.scene.setSceneRect(0, 0, grid_width, scene_height)
        self.graphics_view.setFixedHeight(scene_height)

    def add_thumbnail_item(self, image_path: Path, index: int, column_count: int):
        pixmap = QPixmap(str(image_path)).scaled(
            self.thumbnail_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        item = ThumbnailItem(pixmap, image_path, self)
        self.scene.addItem(item)
        self.thumbnail_items.append(item)

        row = index // column_count
        col = index % column_count
        x = col * self.thumbnail_size.width()
        y = row * self.thumbnail_size.height()
        item.setPos(x, y)

    def handle_item_selection(self, item: ThumbnailItem, modifiers: Qt.KeyboardModifier):
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            item.setSelected(not item.isSelected())
        elif modifiers & Qt.KeyboardModifier.ShiftModifier and self.last_selected_item:
            self.select_range(self.last_selected_item, item)
        else:
            self.scene.clearSelection()
            item.setSelected(True)

        self.last_selected_item = item
        self.imageSelected.emit(item.image_path)
        self.update_selection()

    def select_range(self, start_item, end_item):
        start_index = self.thumbnail_items.index(start_item)
        end_index = self.thumbnail_items.index(end_item)
        start_index, end_index = min(start_index, end_index), max(start_index, end_index)
        for item in self.thumbnail_items[start_index:end_index+1]:
            item.setSelected(True)

    def update_selection(self):
        selected_images = self.get_selected_images()
        self.selectionChanged.emit(selected_images)

    def get_selected_images(self) -> list[Path]:
        return [item.image_path for item in self.thumbnail_items if item.isSelected()]

    def select_first_image(self):
        if self.thumbnail_items:
            first_item = self.thumbnail_items[0]
            self.scene.clearSelection()
            first_item.setSelected(True)
            self.last_selected_item = first_item
            self.imageSelected.emit(first_item.image_path)
            self.update_selection()

if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    widget = ThumbnailSelectorWidget()

    # テスト用の画像パスリスト
    image_paths = [
        Path(r"testimg/1_img/file01.png"),
        Path(r"testimg/1_img/file02.png"),
        Path(r"testimg/1_img/file03.png"),
        Path(r"testimg/1_img/file04.png"),
        Path(r"testimg/1_img/file05.png"),
        Path(r"testimg/1_img/file06.png"),
        Path(r"testimg/1_img/file07.png"),
        Path(r"testimg/1_img/file08.png"),
        Path(r"testimg/1_img/file09.png"),
    ]

    # 画像の存在確認
    for path in image_paths:
        if not path.exists():
            print(f"警告: ファイルが見つかりません: {path}")

    widget.load_images(image_paths)
    widget.imageSelected.connect(lambda path: print(f"選択された画像: {path}"))
    widget.selectionChanged.connect(lambda paths: print(f"選択された画像数: {len(paths)}"))

    widget.setMinimumSize(400, 300)  # ウィジェットの最小サイズを設定
    widget.show()
    sys.exit(app.exec())