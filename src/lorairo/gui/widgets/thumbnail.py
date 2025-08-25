# src/lorairo/gui/widgets/thumbnail_enhanced.py

from pathlib import Path
from typing import Any

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QPen, QPixmap
from PySide6.QtWidgets import (
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

    # === Unified Modern Signals（統一snake_case命名規約） ===
    image_selected = Signal(Path)  # 単一画像選択時
    multiple_images_selected = Signal(list)  # 複数画像選択時
    selection_cleared = Signal()  # 選択クリア時

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
        self.current_image_metadata: list[dict[str, Any]] = []  # フィルタリング用の画像メタデータ
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
    def _on_images_filtered(self, image_metadata: list[dict[str, Any]]) -> None:
        """
        データセット状態管理からの画像フィルタリング通知
        Args:
            image_metadata: 画像メタデータリスト
        """
        # フィルタリング用にメタデータを保持
        self.current_image_metadata = image_metadata.copy()

        # 画像データのみ準備（実際の読み込みは行わない）
        self.image_data = [
            (Path(item["stored_image_path"]), item["id"])
            for item in image_metadata
            if "stored_image_path" in item and "id" in item
        ]

        # 大量の場合はプレースホルダー、少量の場合はサムネイル読み込み
        if len(self.image_data) > 200:
            logger.info(f"フィルタリング結果受信: {len(self.image_data)}件 - プレースホルダー表示中")
            self._setup_placeholder_layout()
        else:
            logger.info(f"フィルタリング結果受信: {len(self.image_data)}件 - サムネイル読み込み開始")
            self.update_thumbnail_layout()

    def get_current_image_data(self) -> list[dict[str, Any]]:
        """
        現在表示中の画像メタデータを返す（フィルタリング用）

        Returns:
            list[dict]: 現在表示中の画像メタデータリスト
        """
        return self.current_image_metadata.copy()

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
        if len(self.image_data) > 200:
            logger.info(f"大量データ({len(self.image_data)}件) - サムネイル読み込みをスキップ")
            # プレースホルダーのみ表示
            self._setup_placeholder_layout()
        else:
            # 少量の場合は通常の読み込み
            self.update_thumbnail_layout()

    @Slot(list)
    def _on_state_selection_changed(self, selected_image_ids: list[int]) -> None:
        """状態管理からの選択変更通知 - UI更新トリガー"""
        # 選択状態は動的取得されるため、再描画のみトリガー
        for item in self.thumbnail_items:
            item.update()  # 再描画トリガー

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

    # === Modern Loading Interface ===

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

        # QImageからQPixmapへの変換マップを作成（null pixmapチェック付き）
        thumbnail_map = {}
        for image_id, qimage in thumbnail_result.loaded_thumbnails:
            try:
                # QImageからQPixmapに変換（メインスレッドで実行）
                from PySide6.QtGui import QPixmap

                qpixmap = QPixmap.fromImage(qimage)

                # Critical Fix: Null pixmap validation
                if not qpixmap.isNull():
                    thumbnail_map[image_id] = qpixmap
                else:
                    logger.warning(f"Failed to create pixmap from QImage for image_id: {image_id}")
                    continue

            except Exception as e:
                logger.error(f"QImage to QPixmap conversion failed for image_id {image_id}: {e}")
                continue

        # 元の画像データからレイアウトを作成
        button_width = self.thumbnail_size.width()
        grid_width = self.scrollAreaThumbnails.viewport().width()
        column_count = max(grid_width // button_width, 1)

        valid_thumbnails = 0
        for i, (image_path, image_id) in enumerate(self.image_data):
            if image_id in thumbnail_map:
                self.add_thumbnail_item_with_pixmap(
                    image_path, image_id, i, column_count, thumbnail_map[image_id]
                )
                valid_thumbnails += 1

        row_count = (len(self.image_data) + column_count - 1) // column_count
        scene_height = row_count * self.thumbnail_size.height()
        self.scene.setSceneRect(0, 0, grid_width, scene_height)

        logger.info(f"サムネイル表示完了: {valid_thumbnails}/{len(self.image_data)}件")

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

        # 選択状態はThumbnailItem.isSelected()で動的取得

    def clear_thumbnails(self) -> None:
        """全てのサムネイルをクリア"""
        self.scene.clear()
        self.thumbnail_items.clear()
        self.image_data.clear()
        logger.debug("サムネイル表示をクリアしました")

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
        # DatasetStateManagerを使用した統一選択処理
        if not self.dataset_state:
            logger.warning("状態管理が未設定です")
            return

        if modifiers & Qt.KeyboardModifier.ControlModifier:
            # Ctrl選択: 選択状態をトグル
            self.dataset_state.toggle_selection(item.image_id)
        elif modifiers & Qt.KeyboardModifier.ShiftModifier and self.last_selected_item:
            # Shift選択: 範囲選択
            self.select_range(self.last_selected_item, item)
        else:
            # 通常選択: 単一選択
            self.dataset_state.set_selected_images([item.image_id])
            self.dataset_state.set_current_image(item.image_id)

        self.last_selected_item = item

    def select_range(self, start_item: ThumbnailItem, end_item: ThumbnailItem) -> None:
        """範囲選択処理（DatasetStateManager経由）"""
        if start_item is None or end_item is None or not self.dataset_state:
            return

        start_index = self.thumbnail_items.index(start_item)
        end_index = self.thumbnail_items.index(end_item)
        start_index, end_index = min(start_index, end_index), max(start_index, end_index)

        selected_ids = [
            item.image_id for i, item in enumerate(self.thumbnail_items) if start_index <= i <= end_index
        ]
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
        # 渡されたパスをそのまま使用（最適化は呼び出し側で実施済み）
        pixmap = QPixmap(str(image_path)).scaled(
            self.thumbnail_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        # Critical Fix: Null pixmap validation for legacy direct loading path
        if pixmap.isNull():
            logger.warning(f"Failed to load pixmap from image path: {image_path}")
            # Create a placeholder pixmap to maintain UI consistency
            pixmap = QPixmap(self.thumbnail_size)
            pixmap.fill(Qt.GlobalColor.gray)  # Gray placeholder for failed loads

        item = ThumbnailItem(pixmap, image_path, image_id, self)
        self.scene.addItem(item)
        self.thumbnail_items.append(item)

        row = index // column_count
        col = index % column_count
        x = col * self.thumbnail_size.width()
        y = row * self.thumbnail_size.height()
        item.setPos(x, y)

        # 選択状態はThumbnailItem.isSelected()で動的取得

    # === Utility Methods ===

    def get_selected_images(self) -> list[Path]:
        """選択中画像パスをDatasetStateManagerから取得"""
        if not self.dataset_state:
            return []

        selected_ids = self.dataset_state.selected_image_ids
        return [item.image_path for item in self.thumbnail_items if item.image_id in selected_ids]

    def select_first_image(self) -> None:
        """最初の画像を選択（DatasetStateManager経由）"""
        if not self.thumbnail_items or not self.dataset_state:
            return

        first_item = self.thumbnail_items[0]
        self.dataset_state.set_selected_images([first_item.image_id])
        self.dataset_state.set_current_image(first_item.image_id)
        self.last_selected_item = first_item

    def _emit_selection_signals(self) -> None:
        """選択状態変更に応じた統一Signalを発行

        現代化された統一命名規約のSignalのみを発行します。
        """
        selected_images = self.get_selected_images()

        if len(selected_images) > 1:
            self.multiple_images_selected.emit(selected_images)
            logger.debug(f"Multiple images selected: {len(selected_images)} images")

        elif len(selected_images) == 1:
            self.image_selected.emit(selected_images[0])
            logger.debug(f"Single image selected: {selected_images[0]}")

        else:
            self.selection_cleared.emit()
            logger.debug("Selection cleared")


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    from ...utils.log import initialize_logging

    logconf = {"level": "DEBUG", "file": "ThumbnailSelectorWidget.log"}
    initialize_logging(logconf)
    app = QApplication(sys.argv)
    widget = ThumbnailSelectorWidget()
    image_paths = [
        Path("tests/resources/img/1_img/file01.webp"),
        Path("tests/resources/img/1_img/file02.webp"),
        Path("tests/resources/img/1_img/file03.webp"),
        Path("tests/resources/img/1_img/file04.webp"),
        Path("tests/resources/img/1_img/file05.webp"),
        Path("tests/resources/img/1_img/file06.webp"),
        Path("tests/resources/img/1_img/file07.webp"),
        Path("tests/resources/img/1_img/file08.webp"),
        Path("tests/resources/img/1_img/file09.webp"),
    ]
    # Convert paths to metadata format for modern loading method
    image_metadata = [{"stored_image_path": str(path), "id": i} for i, path in enumerate(image_paths)]
    widget.load_images_from_metadata(image_metadata)
    widget.setMinimumSize(400, 300)  # ウィジェットの最小サイズを設定
    widget.show()
    sys.exit(app.exec())
