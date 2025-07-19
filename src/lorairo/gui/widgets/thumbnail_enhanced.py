# src/lorairo/gui/widgets/thumbnail_enhanced.py

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QVBoxLayout,
    QWidget,
)

from ...utils.log import logger
from ..designer.ThumbnailSelectorWidget_ui import Ui_ThumbnailSelectorWidget
from ..state.dataset_state import DatasetStateManager


class ThumbnailItem(QGraphicsObject):
    """
    サムネイル画像を表すクラス。
    選択されたときに枠を表示します。
    """

    def __init__(self, pixmap: QPixmap, image_path: Path, image_id: int, parent: "ThumbnailSelectorWidget"):
        super().__init__()
        self.pixmap = pixmap
        self.image_path = image_path
        self.image_id = image_id
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
    DatasetStateManager との統合により状態管理を統一。
    """

    # レガシーシグナル（互換性維持）
    imageSelected = Signal(Path)
    multipleImagesSelected = Signal(list)
    deselected = Signal()

    def __init__(self, parent=None, dataset_state: DatasetStateManager | None = None):
        """
        コンストラクタ
        Args:
            parent (QWidget, optional): 親ウィジェット. Defaults to None.
            dataset_state (DatasetStateManager, optional): データセット状態管理. Defaults to None.
        """
        super().__init__(parent)
        self.setupUi(self)

        # 状態管理
        self.dataset_state = dataset_state

        # UI設定
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

        # 内部状態
        self.image_data: list[tuple[Path, int]] = []  # (image_path, image_id)
        self.thumbnail_items: list[ThumbnailItem] = []  # ThumbnailItem のリスト
        self.last_selected_item: ThumbnailItem | None = None

        # リサイズ用のタイマーを初期化
        self.resize_timer = QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self.update_thumbnail_layout)

        # 状態管理との連携
        if self.dataset_state:
            self._connect_dataset_state()

    def set_dataset_state(self, dataset_state: DatasetStateManager) -> None:
        """データセット状態管理を設定"""
        if self.dataset_state:
            self._disconnect_dataset_state()

        self.dataset_state = dataset_state
        self._connect_dataset_state()

    def _connect_dataset_state(self) -> None:
        """データセット状態管理との連携を設定"""
        if not self.dataset_state:
            return

        # 状態変更シグナル接続
        self.dataset_state.images_filtered.connect(self._on_images_filtered)
        self.dataset_state.selection_changed.connect(self._on_state_selection_changed)
        self.dataset_state.current_image_changed.connect(self._on_state_current_image_changed)
        self.dataset_state.thumbnail_size_changed.connect(self._on_thumbnail_size_changed)

    def _disconnect_dataset_state(self) -> None:
        """データセット状態管理との連携を解除"""
        if not self.dataset_state:
            return

        # シグナル切断
        self.dataset_state.images_filtered.disconnect(self._on_images_filtered)
        self.dataset_state.selection_changed.disconnect(self._on_state_selection_changed)
        self.dataset_state.current_image_changed.disconnect(self._on_state_current_image_changed)
        self.dataset_state.thumbnail_size_changed.disconnect(self._on_thumbnail_size_changed)

    # === State Manager Integration ===

    @Slot(list)
    def _on_images_filtered(self, image_metadata: list[dict]) -> None:
        """
        データセット状態管理からの画像フィルタリング通知
        Args:
            image_metadata: 画像メタデータリスト
        """
        # 画像データのみ準備（実際の読み込みは行わない）
        self.image_data = [
            (Path(item["stored_image_path"]), item["id"])
            for item in image_metadata
            if "stored_image_path" in item and "id" in item
        ]

        # プレースホルダーを表示
        self._setup_placeholder_layout()
        logger.info(f"フィルタリング結果受信: {len(self.image_data)}件 - プレースホルダー表示中")

    @Slot(list)
    def load_images_from_metadata(self, image_metadata: list[dict]) -> None:
        """
        メタデータからサムネイルをロード（状態管理統合版）
        Args:
            image_metadata: 画像メタデータリスト
        """
        self.image_data = [
            (Path(item["stored_image_path"]), item["id"])
            for item in image_metadata
            if "stored_image_path" in item and "id" in item
        ]
        # 大量の場合は画像データのみ準備してサムネイル読み込みはスキップ
        if len(self.image_data) > 50:
            logger.info(f"大量データ({len(self.image_data)}件) - サムネイル読み込みをスキップ")
            # プレースホルダーのみ表示
            self._setup_placeholder_layout()
        else:
            # 少量の場合は通常の読み込み
            self.update_thumbnail_layout()

    @Slot(list)
    def _on_state_selection_changed(self, selected_image_ids: list[int]) -> None:
        """状態管理からの選択変更通知"""
        # UI選択状態を更新
        for item in self.thumbnail_items:
            item.setSelected(item.image_id in selected_image_ids)

    @Slot(int)
    def _on_state_current_image_changed(self, current_image_id: int) -> None:
        """状態管理からの現在画像変更通知"""
        # 現在画像を視覚的にハイライト（実装は今後拡張）
        logger.debug(f"現在画像変更: ID {current_image_id}")

    @Slot(int)
    def _on_thumbnail_size_changed(self, new_size: int) -> None:
        """サムネイルサイズ変更通知"""
        self.thumbnail_size = QSize(new_size, new_size)
        self.update_thumbnail_layout()

    # === Legacy Interface (互換性維持) ===

    @Slot(list)
    def load_images(self, image_paths: list[Path]) -> None:
        """
        画像パスリストからサムネイルをロード（レガシー互換）
        Args:
            image_paths: 画像パスリスト
        """
        # IDなしの場合は仮IDを割り当て
        self.image_data = [(path, i) for i, path in enumerate(image_paths)]
        self.update_thumbnail_layout()

    def load_images_with_ids(self, image_data: list[tuple[Path, int]]) -> None:
        """
        画像パスとIDのペアでサムネイルをロード（レガシー互換）
        Args:
            image_data: (画像パス, 画像ID) のタプルリスト
        """
        self.image_data = image_data
        self.update_thumbnail_layout()

    def load_thumbnails_from_result(self, thumbnail_result) -> None:
        """
        ThumbnailLoadResultからサムネイルをロード（ワーカー版）
        Args:
            thumbnail_result: ThumbnailLoadResult オブジェクト
        """
        self.scene.clear()
        self.thumbnail_items.clear()

        if not thumbnail_result.loaded_thumbnails:
            return

        # 事前にサムネイルデータを準備
        thumbnail_map = {image_id: pixmap for image_id, pixmap in thumbnail_result.loaded_thumbnails}

        # 元の画像データからレイアウトを作成
        button_width = self.thumbnail_size.width()
        grid_width = self.scrollAreaThumbnails.viewport().width()
        column_count = max(grid_width // button_width, 1)

        for i, (image_path, image_id) in enumerate(self.image_data):
            if image_id in thumbnail_map:
                self.add_thumbnail_item_with_pixmap(
                    image_path, image_id, i, column_count, thumbnail_map[image_id]
                )

        row_count = (len(self.image_data) + column_count - 1) // column_count
        scene_height = row_count * self.thumbnail_size.height()
        self.scene.setSceneRect(0, 0, grid_width, scene_height)

        logger.info(f"サムネイル表示完了: {len(thumbnail_result.loaded_thumbnails)}件")

    def add_thumbnail_item_with_pixmap(
        self, image_path: Path, image_id: int, index: int, column_count: int, pixmap: QPixmap
    ) -> None:
        """
        事前に読み込まれたPixmapでサムネイルアイテムを追加
        """
        item = ThumbnailItem(pixmap, image_path, image_id, self)
        self.scene.addItem(item)
        self.thumbnail_items.append(item)

        row = index // column_count
        col = index % column_count
        x = col * self.thumbnail_size.width()
        y = row * self.thumbnail_size.height()
        item.setPos(x, y)

        # 状態管理から選択状態を反映
        if self.dataset_state:
            is_selected = self.dataset_state.is_image_selected(image_id)
            item.setSelected(is_selected)

    def clear_thumbnails(self) -> None:
        """全てのサムネイルをクリア"""
        self.scene.clear()
        self.thumbnail_items.clear()
        self.image_data.clear()
        logger.debug("サムネイル表示をクリアしました")

    def _update_display_mode(self, mode: str) -> None:
        """表示モードを更新（grid/list）"""
        self.display_mode = mode
        logger.debug(f"表示モードを変更: {mode}")

        # レイアウトを再計算して更新
        if self.image_data:
            self.update_thumbnail_layout()

    def _setup_placeholder_layout(self) -> None:
        """大量データ用のプレースホルダーレイアウトを設定"""
        self.scene.clear()
        self.thumbnail_items.clear()

        if not self.image_data:
            return

        # プレースホルダーメッセージを表示
        from PySide6.QtGui import QFont
        from PySide6.QtWidgets import QGraphicsTextItem

        text_item = QGraphicsTextItem(f"サムネイル読み込み中... ({len(self.image_data)}件)")
        font = QFont()
        font.setPointSize(12)
        text_item.setFont(font)

        # 中央に配置
        text_rect = text_item.boundingRect()
        scene_width = self.scrollAreaThumbnails.viewport().width()
        x = (scene_width - text_rect.width()) / 2
        text_item.setPos(x, 50)

        self.scene.addItem(text_item)
        self.scene.setSceneRect(0, 0, scene_width, 150)

    # === UI Event Handlers ===

    def resizeEvent(self, event):
        """
        ウィジェットがリサイズされたときにタイマーをリセット
        """
        super().resizeEvent(event)
        self.resize_timer.start(250)

    def handle_item_selection(self, item: ThumbnailItem, modifiers: Qt.KeyboardModifier) -> None:
        """
        アイテムの選択を処理（状態管理統合版）
        """
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            # Ctrl選択: 選択状態をトグル
            if self.dataset_state:
                self.dataset_state.toggle_selection(item.image_id)
            else:
                item.setSelected(not item.isSelected())

        elif modifiers & Qt.KeyboardModifier.ShiftModifier and self.last_selected_item:
            # Shift選択: 範囲選択
            self.select_range(self.last_selected_item, item)

        else:
            # 通常選択: 単一選択
            if self.dataset_state:
                self.dataset_state.set_selected_images([item.image_id])
                self.dataset_state.set_current_image(item.image_id)
            else:
                for other_item in self.thumbnail_items:
                    other_item.setSelected(other_item == item)

        self.last_selected_item = item

        # レガシーシグナル発行（互換性維持）
        self._emit_legacy_signals()

    def select_range(self, start_item: ThumbnailItem, end_item: ThumbnailItem) -> None:
        """
        開始アイテムと終了アイテムの間の範囲を選択
        """
        if start_item is None or end_item is None:
            return

        start_index = self.thumbnail_items.index(start_item)
        end_index = self.thumbnail_items.index(end_item)
        start_index, end_index = min(start_index, end_index), max(start_index, end_index)

        selected_ids = []
        for i, item in enumerate(self.thumbnail_items):
            is_selected = start_index <= i <= end_index
            if is_selected:
                selected_ids.append(item.image_id)
            if not self.dataset_state:
                item.setSelected(is_selected)

        if self.dataset_state:
            self.dataset_state.set_selected_images(selected_ids)

    # === Layout Management ===

    def update_thumbnail_layout(self) -> None:
        """
        シーン内のサムネイルをグリッドレイアウトで配置
        """
        self.scene.clear()
        self.thumbnail_items.clear()

        if not self.image_data:
            return

        button_width = self.thumbnail_size.width()
        grid_width = self.scrollAreaThumbnails.viewport().width()
        column_count = max(grid_width // button_width, 1)

        for i, (image_path, image_id) in enumerate(self.image_data):
            self.add_thumbnail_item(image_path, image_id, i, column_count)

        row_count = (len(self.image_data) + column_count - 1) // column_count
        scene_height = row_count * self.thumbnail_size.height()
        self.scene.setSceneRect(0, 0, grid_width, scene_height)

    def add_thumbnail_item(self, image_path: Path, image_id: int, index: int, column_count: int) -> None:
        """
        指定されたグリッド位置にサムネイルアイテムをシーンに追加
        """
        # サムネイル画像パス取得
        thumbnail_path = self._get_thumbnail_path(image_path, image_id)

        pixmap = QPixmap(str(thumbnail_path)).scaled(
            self.thumbnail_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        item = ThumbnailItem(pixmap, image_path, image_id, self)
        self.scene.addItem(item)
        self.thumbnail_items.append(item)

        row = index // column_count
        col = index % column_count
        x = col * self.thumbnail_size.width()
        y = row * self.thumbnail_size.height()
        item.setPos(x, y)

        # 状態管理から選択状態を反映
        if self.dataset_state:
            is_selected = self.dataset_state.is_image_selected(image_id)
            item.setSelected(is_selected)

    def _get_thumbnail_path(self, image_path: Path, image_id: int) -> Path:
        """
        サムネイル用の最適な画像パスを取得
        """
        try:
            # 512px画像が利用可能な場合はそれを使用
            db_manager = self._get_database_manager()
            if db_manager:
                existing_512px = db_manager.check_processed_image_exists(image_id, 512)
                if existing_512px and "stored_image_path" in existing_512px:
                    from ...database.db_core import resolve_stored_path

                    path = resolve_stored_path(existing_512px["stored_image_path"])
                    if path.exists():
                        return path

            # フォールバック: 元画像を使用
            from ...database.db_core import resolve_stored_path

            return resolve_stored_path(str(image_path))

        except Exception as e:
            logger.warning(f"サムネイルパス取得エラー、元画像を使用: {e}")
            return image_path

    # === Utility Methods ===

    def get_selected_images(self) -> list[Path]:
        """
        現在選択されている画像のパスのリストを返す（レガシー互換）
        """
        if self.dataset_state:
            selected_ids = self.dataset_state.selected_image_ids
            return [item.image_path for item in self.thumbnail_items if item.image_id in selected_ids]
        else:
            return [item.image_path for item in self.thumbnail_items if item.isSelected()]

    def select_first_image(self) -> None:
        """
        リスト内の最初の画像を選択
        """
        if self.thumbnail_items:
            first_item = self.thumbnail_items[0]
            if self.dataset_state:
                self.dataset_state.set_selected_images([first_item.image_id])
                self.dataset_state.set_current_image(first_item.image_id)
            else:
                for item in self.thumbnail_items:
                    item.setSelected(item == first_item)

            self.last_selected_item = first_item
            self._emit_legacy_signals()

    def _emit_legacy_signals(self) -> None:
        """レガシーシグナルを発行（互換性維持）"""
        selected_images = self.get_selected_images()
        if len(selected_images) > 1:
            self.multipleImagesSelected.emit(selected_images)
        elif len(selected_images) == 1:
            self.imageSelected.emit(selected_images[0])
        else:
            self.deselected.emit()

    def _get_database_manager(self):
        """親ウィジェットの階層からデータベースマネージャーを取得"""
        widget = self.parent()
        while widget:
            if hasattr(widget, "idm") and widget.idm:
                return widget.idm
            widget = widget.parent()
        return None
