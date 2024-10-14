from pathlib import Path

from PySide6.QtWidgets import (QWidget, QGraphicsObject, QGraphicsScene, QGraphicsView, QGraphicsPixmapItem,
                               QVBoxLayout, QApplication, QGraphicsItem)
from PySide6.QtGui import QPixmap, QColor, QPen
from PySide6.QtCore import Qt, QSize, Signal, Slot, QRectF, QTimer

from module.log import get_logger

from gui_file.ThumbnailSelectorWidget_ui import Ui_ThumbnailSelectorWidget

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
    multipleImagesSelected = Signal(list)
    deselected = Signal()

    def __init__(self, parent=None):
        """
        コンストラクタ
        Args:
            parent (QWidget, optional): 親ウィジェット. Defaults to None.
        """
        self.logger = get_logger("ThumbnailSelectorWidget")
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

        # リサイズ用のタイマーを初期化
        self.resize_timer = QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self.update_thumbnail_layout)

    def resizeEvent(self, event):
        """
        ウィジェットがリサイズされたときにタイマーをリセットします。
        Args:
            event (QResizeEvent): リサイズイベント
        """
        super().resizeEvent(event)
        # タイマーをリセットし、250ミリ秒後にupdate_thumbnail_layoutを呼び出す
        self.resize_timer.start(250)

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

    def add_thumbnail_item(self, image_path: Path, index: int, column_count: int):
        """
        指定されたグリッド位置にサムネイルアイテムをシーンに追加します。
        Args:
            image_path (Path): 画像のファイルパス
            index (int): アイテムのインデックス #TODO: 何に対してのインデックスか俺もわかってない
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
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            item.setSelected(not item.isSelected())
            self.logger.debug(f"画像がCtrl+クリックで{'選択' if item.isSelected() else '選択解除'}: \n item.image_path: {item.image_path}")
        elif modifiers & Qt.KeyboardModifier.ShiftModifier and self.last_selected_item:
            self.select_range(self.last_selected_item, item)
            self.logger.debug(f"画像がShift+クリックで範囲選択")
        else:
            for other_item in self.thumbnail_items:
                if other_item != item:
                    other_item.setSelected(False)
            item.setSelected(True)
            self.logger.debug(f"画像が選択: \n item.image_path: {item.image_path}")
        self.last_selected_item = item
        self.update_selection()

    def select_range(self, start_item, end_item):
        """
        開始アイテムと終了アイテムの間の範囲を選択します。
        Args:
            start_item (ThumbnailItem): 範囲選択の開始アイテム
            end_item (ThumbnailItem): 範囲選択の終了アイテム
        """
        if start_item is None or end_item is None:
            return
        start_index = self.thumbnail_items.index(start_item)
        end_index = self.thumbnail_items.index(end_item)
        start_index, end_index = min(start_index, end_index), max(start_index, end_index)
        for i, item in enumerate(self.thumbnail_items):
            item.setSelected(start_index <= i <= end_index)
        self.update_selection()

    def update_selection(self):
        """
        現在選択されている画像のリストを取得し、対応するシグナルを発行します。
        """
        selected_images = self.get_selected_images()
        if len(selected_images) > 1:
            self.multipleImagesSelected.emit(selected_images)
        elif len(selected_images) == 1:
            self.imageSelected.emit(selected_images[0])
        else:
            self.deselected.emit()

    def get_selected_images(self) -> list[Path]:
        """
        現在選択されている画像のパスのリストを返します。
        Returns:
            list[Path]: 選択された画像のパスのリスト
        """
        selected_images = [item.image_path for item in self.thumbnail_items if item.isSelected()]
        self.logger.debug(f"選択された画像のリスト: \n selected_images: {selected_images}")
        return selected_images

    def select_first_image(self):
        """
        リスト内の最初の画像を選択します（存在する場合）。
        ディレクトリ選択時最初の画像をプレビューに表示するため｡
        """
        if self.thumbnail_items:
            first_item = self.thumbnail_items[0]
            self.scene.clearSelection()
            first_item.setSelected(True)
            self.last_selected_item = first_item
            self.update_selection()

if __name__ == "__main__":
    import sys
    from module.log import setup_logger
    from PySide6.QtWidgets import QApplication


    logconf = {'level': 'DEBUG', 'file': 'ThumbnailSelectorWidget.log'}
    setup_logger(logconf)
    app = QApplication(sys.argv)
    widget = ThumbnailSelectorWidget()
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
    widget.load_images(image_paths)
    widget.setMinimumSize(400, 300)  # ウィジェットの最小サイズを設定
    widget.show()
    sys.exit(app.exec())