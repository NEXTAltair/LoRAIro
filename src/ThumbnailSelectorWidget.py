from PySide6.QtWidgets import (QWidget, QGraphicsObject, QGraphicsScene, QGraphicsView, QGraphicsPixmapItem,
                               QVBoxLayout, QApplication, QGraphicsItem)
from PySide6.QtGui import QPixmap, QColor, QPen
from PySide6.QtCore import Qt, QSize, Signal, Slot, QRectF
from pathlib import Path
from ThumbnailSelectorWidget_ui import Ui_ThumbnailSelectorWidget

class ThumbnailItem(QGraphicsObject):
    """
    サムネイル画像を表すクラス。
    選択されたときに枠を表示します。
    """

    def __init__(self, pixmap: QPixmap, image_path: Path, parent: 'ThumbnailSelectorWidget'):
        super().__init__()
        self.pixmap = pixmap
        self.image_path = image_path
        self.parent_widget = parent
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self._is_selected = False

    def isSelected(self) -> bool:
        return self._is_selected

    def setSelected(self, selected: bool):
        if self._is_selected != selected:
            self._is_selected = selected
            self.update()  # 再描画をトリガー

    def boundingRect(self) -> QRectF:
        return QRectF(self.pixmap.rect())

    def paint(self, painter, option, widget):
        painter.drawPixmap(self.boundingRect().toRect(), self.pixmap)
        if self.isSelected():
            pen = QPen(QColor(0, 120, 215), 3)
            painter.setPen(pen)
            painter.drawRect(self.boundingRect().adjusted(1, 1, -1, -1))

class CustomGraphicsView(QGraphicsView):
    """
    アイテムのクリックを処理し、信号を発行するカスタムQGraphicsView。
    """
    itemClicked = Signal(QGraphicsPixmapItem, Qt.KeyboardModifier)

    def mousePressEvent(self, event):
        """
        アイテムがクリックされたときに信号を発行します。

        Args:
            event (QMouseEvent): マウスイベント
        """
        item = self.itemAt(event.position().toPoint())
        if isinstance(item, ThumbnailItem):
            self.itemClicked.emit(item, event.modifiers())
        super().mousePressEvent(event)

class ThumbnailSelectorWidget(QWidget, Ui_ThumbnailSelectorWidget):
    """
    サムネイル画像を表示し、選択操作を管理するウィジェット。
    """
    imageSelected = Signal(Path)
    selectionChanged = Signal(list)

    def __init__(self, parent=None):
        """
        コンストラクタ

        Args:
            parent (QWidget, optional): 親ウィジェット. Defaults to None.
        """
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
        """
        ウィジェットがリサイズされたときにサムネイルのレイアウトを更新します。

        Args:
            event (QResizeEvent): リサイズイベント
        """
        super().resizeEvent(event)
        self.update_thumbnail_layout()

    @Slot(list)
    def load_images(self, image_paths: list[Path]):
        """
        画像のリストをウィジェットにロードし、サムネイルとして表示します。

        Args:
            image_paths (list[Path]): 画像のパスのリスト
        """
        self.image_paths = image_paths
        self.update_thumbnail_layout()

    def update_thumbnail_layout(self):
        """
        シーン内のサムネイルをグリッドレイアウトで配置します。
        """
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
        """
        指定されたグリッド位置にサムネイルアイテムをシーンに追加します。

        Args:
            image_path (Path): 画像のファイルパス
            index (int): アイテムのインデックス
            column_count (int): グリッドの列数
        """
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
        """
        アイテムの選択を処理し、単一選択、コントロール選択、シフト選択をサポートします。

        Args:
            item (ThumbnailItem): 選択されたサムネイルアイテム
            modifiers (Qt.KeyboardModifier): キーボード修飾キー
        """
        # print(f"Selection: {item.image_path}, Ctrl: {bool(modifiers & Qt.KeyboardModifier.ControlModifier)}, Shift: {bool(modifiers & Qt.KeyboardModifier.ShiftModifier)}")
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            item.setSelected(not item.isSelected())
        elif modifiers & Qt.KeyboardModifier.ShiftModifier and self.last_selected_item:
            self.select_range(self.last_selected_item, item)
        else:
            for other_item in self.thumbnail_items:
                if other_item != item:
                    other_item.setSelected(False)
            item.setSelected(True)

        self.last_selected_item = item
        self.imageSelected.emit(item.image_path)
        self.update_selection()
        self.scene.update()  # シーン全体の更新を強制

    def select_range(self, start_item, end_item):
        if start_item is None or end_item is None:
            return
        start_index = self.thumbnail_items.index(start_item)
        end_index = self.thumbnail_items.index(end_item)
        start_index, end_index = min(start_index, end_index), max(start_index, end_index)
        for i, item in enumerate(self.thumbnail_items):
            item.setSelected(start_index <= i <= end_index)
        self.scene.update()

    def update_selection(self):
        selected_images = self.get_selected_images()
        # print(f"Selected images: {[str(path) for path in selected_images]}")
        # print("Selection state of all items:")
        for item in self.thumbnail_items:
            print(f"  {item.image_path}: {item.isSelected()}")
        self.selectionChanged.emit(selected_images)
        self.scene.update()

    def get_selected_images(self) -> list[Path]:
        """
        現在選択されている画像のパスのリストを返します。

        Returns:
            list[Path]: 選択された画像のパスのリスト
        """
        return [item.image_path for item in self.thumbnail_items if item.isSelected()]

    def select_first_image(self):
        """
        リスト内の最初の画像を選択します（存在する場合）。
        """
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
    widget.imageSelected.connect(lambda path:  print(f"選択された画像: {path}"))
    widget.selectionChanged.connect(lambda paths:  print(f"選択された画像数: {len(paths)}"))
    widget.setMinimumSize(400, 300)  # ウィジェットの最小サイズを設定
    widget.show()
    sys.exit(app.exec())