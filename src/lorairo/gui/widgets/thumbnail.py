# src/lorairo/gui/widgets/thumbnail.py

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsScene,
    QGraphicsView,
    QMenu,
    QStyleOptionGraphicsItem,
    QVBoxLayout,
    QWidget,
)

from ...gui.designer.ThumbnailSelectorWidget_ui import Ui_ThumbnailSelectorWidget
from ...utils.log import logger
from ..state.dataset_state import DatasetStateManager


class ThumbnailItem(QGraphicsObject):
    """
    サムネイル画像を表示するGraphicsアイテム。

    Qt Graphics Viewフレームワークを使用してサムネイル画像を描画し、
    マウスイベントによる選択状態の管理と視覚的フィードバックを提供する。

    Attributes:
        pixmap (QPixmap): 表示する画像データ
        image_path (Path): 画像ファイルのパス
        image_id (int): データベース内での画像ID
        parent_widget (ThumbnailSelectorWidget): 親ウィジェット
    """

    def __init__(self, pixmap: QPixmap, image_path: Path, image_id: int, parent: "ThumbnailSelectorWidget"):
        """
        ThumbnailItemを初期化する。

        Args:
            pixmap (QPixmap): 表示する画像データ（既にスケール済み）
            image_path (Path): 元画像ファイルのパス
            image_id (int): データベース内での一意な画像ID
            parent (ThumbnailSelectorWidget): 親となるサムネイルセレクターウィジェット
        """
        super().__init__()
        self.pixmap = pixmap
        self.image_path = image_path
        self.image_id = image_id
        self.parent_widget = parent
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self._is_selected = False

    def isSelected(self) -> bool:
        """
        現在の選択状態をDatasetStateManagerから動的に取得する。

        Returns:
            bool: このアイテムが選択されている場合True
        """
        if self.parent_widget.dataset_state:
            return self.parent_widget.dataset_state.is_image_selected(self.image_id)
        return False

    def setSelected(self, selected: bool) -> None:
        """
        アイテムの選択状態を設定し、必要に応じて再描画をトリガーする。

        Args:
            selected (bool): 設定する選択状態
        """
        current_selected = self.isSelected()
        if current_selected != selected:
            self.update()  # 再描画をトリガー

    def boundingRect(self) -> QRectF:
        """
        このアイテムの境界矩形を返す（Qt Graphics View必須メソッド）。

        Returns:
            QRectF: pixmapのサイズに基づく境界矩形
        """
        return QRectF(self.pixmap.rect())

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        painter.drawPixmap(self.boundingRect().toRect(), self.pixmap)
        if self.isSelected():
            pen = QPen(QColor(0, 120, 215), 3)
            painter.setPen(pen)
            painter.drawRect(self.boundingRect().adjusted(1, 1, -1, -1))


class CustomGraphicsView(QGraphicsView):
    """
    アイテムのクリックを処理し、信号を発行するカスタムQGraphicsView。
    """

    itemClicked = Signal(ThumbnailItem, Qt.KeyboardModifier)

    def mousePressEvent(self, event: QMouseEvent) -> None:
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
    画像のサムネイル表示と選択操作を管理するメインウィジェット。

    このウィジェットは以下の責任を持つ：
    - 画像メタデータからサムネイル画像の表示
    - ユーザーの選択操作（単一選択・複数選択・範囲選択）の処理
    - DatasetStateManagerとの状態同期
    - 動的レイアウト調整（ウィンドウリサイズ対応）
    - WorkerからのThumbnailLoadResult処理

    Signals:
        image_selected (Path): 単一画像が選択された時に発火
        multiple_images_selected (list[Path]): 複数画像が選択された時に発火
        selection_cleared (): 選択がクリアされた時に発火

    Attributes:
        dataset_state (DatasetStateManager): データセット状態管理オブジェクト
        thumbnail_size (QSize): サムネイル画像のサイズ
        image_data (list[tuple[Path, int]]): 表示中の画像データ（パスとID）
        thumbnail_items (list[ThumbnailItem]): 表示中のサムネイルアイテム
    """

    # === Unified Modern Signals（統一snake_case命名規約） ===
    image_selected = Signal(Path)  # 単一画像選択時
    multiple_images_selected = Signal(list)  # 複数画像選択時
    selection_cleared = Signal()  # 選択クリア時
    stage_selected_requested = Signal()  # バッチタグのステージング追加要求
    quick_tag_requested = Signal(list)  # クイックタグ追加要求（image_ids）

    def __init__(
        self,
        parent: QWidget | None = None,
        dataset_state: DatasetStateManager | None = None,
    ) -> None:
        """
        ThumbnailSelectorWidgetを初期化する。

        UIコンポーネントの設定、Graphics Viewの初期化、
        DatasetStateManagerとの接続を行う。

        Args:
            parent (QWidget, optional): 親ウィジェット。Qtの親子関係管理用。
            dataset_state (DatasetStateManager, optional): データセット状態管理オブジェクト。
                画像選択状態、フィルタ状態などの中央管理を行う。Noneの場合は状態管理なしで動作。
        """
        super().__init__(parent)
        setup_ui = cast(Callable[[QWidget], None], self.setupUi)
        setup_ui(self)

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
        self.graphics_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.graphics_view.customContextMenuRequested.connect(self._on_context_menu_requested)

        layout = QVBoxLayout(self.widgetThumbnailsContent)
        layout.addWidget(self.graphics_view)
        self.widgetThumbnailsContent.setLayout(layout)

        # キャッシュ機構（新設計）
        self.image_cache: dict[int, QPixmap] = {}  # image_id -> 元QPixmap
        self.scaled_cache: dict[
            tuple[int, int, int], QPixmap
        ] = {}  # (image_id, width, height) -> スケールされたQPixmap
        self.image_metadata: dict[int, dict[str, Any]] = {}  # image_id -> メタデータ

        # レガシー互換（段階的廃止予定）
        self.image_data: list[tuple[Path, int]] = []  # (image_path, image_id)
        self.current_image_metadata: list[dict[str, Any]] = []  # フィルタリング用の画像メタデータ
        self.thumbnail_items: list[ThumbnailItem] = []  # ThumbnailItem のリスト
        self.last_selected_item: ThumbnailItem | None = None

        # リサイズ用のタイマーを初期化
        self.resize_timer = QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self.update_thumbnail_layout)

        # ヘッダー部分の接続設定
        self._setup_header_connections()

        # 状態管理との連携
        if self.dataset_state:
            self._connect_dataset_state()
            # ドラッグ選択の同期（scene → DatasetStateManager）
            self.scene.selectionChanged.connect(self._sync_selection_to_state)

    def _setup_header_connections(self) -> None:
        """
        ヘッダー部分のUI接続を設定する。

        サムネイルサイズスライダーと画像件数表示の初期化と接続を行う。
        """
        # サムネイルサイズスライダーの接続
        if hasattr(self, "sliderThumbnailSize"):
            self.sliderThumbnailSize.valueChanged.connect(self._on_thumbnail_size_slider_changed)

        # 画像件数表示の初期化
        self._update_image_count_display()

    def _on_thumbnail_size_slider_changed(self, value: int) -> None:
        """
        サムネイルサイズスライダーの値変更を処理する（高速キャッシュ版）。

        キャッシュされた元画像から新サイズにスケールし、ファイルI/Oを
        完全回避した高速なサイズ変更を実現する。

        Args:
            value (int): 新しいサムネイルサイズ値
        """
        old_size = self.thumbnail_size
        self.thumbnail_size = QSize(value, value)

        # 画像件数表示を更新
        self._update_image_count_display()

        # キャッシュから高速再表示（ファイルI/O完全回避）
        if self.image_cache:
            logger.debug(f"サムネイルサイズ変更: {old_size.width()}x{old_size.height()} → {value}x{value}")
            # UI要素クリア（古い画像残存問題の修正）
            self.scene.clear()
            self.thumbnail_items.clear()

            # 選択状態同期（ImagePreview警告解決）
            if self.dataset_state:
                self.dataset_state.clear_current_image()
                self.dataset_state.clear_selection()

            self._display_cached_thumbnails()
        else:
            # キャッシュが空の場合は従来方式（フォールバック）
            if len(self.image_data) <= 50:
                self.update_thumbnail_layout()
            # 大量データの場合は何もしない（Worker再実行待ち）
        # 大量データの場合、既存のWorkerワークフローに依存（何もしない）

    def _update_image_count_display(self) -> None:
        """
        画像件数表示を更新する。

        現在読み込まれている画像数をヘッダーに表示する。
        """
        if hasattr(self, "labelThumbnailCount"):
            count = len(self.image_data)
            self.labelThumbnailCount.setText(f"画像: {count}件")

    def _on_context_menu_requested(self, pos: QPoint) -> None:
        """サムネイル一覧の右クリックメニューを表示"""
        # 右クリックしたアイテムが未選択なら単一選択に切替
        item = self.graphics_view.itemAt(pos)
        if isinstance(item, ThumbnailItem) and self.dataset_state:
            if not self.dataset_state.is_image_selected(item.image_id):
                self.dataset_state.set_selected_images([item.image_id])
                self.dataset_state.set_current_image(item.image_id)

        selected_ids = self.dataset_state.selected_image_ids if self.dataset_state else []

        menu = QMenu(self)

        # バッチタグへ追加
        action_stage = menu.addAction("バッチタグへ追加")
        action_stage.setEnabled(bool(selected_ids))

        # クイックタグ追加
        action_quick_tag = menu.addAction("クイックタグ追加...")
        action_quick_tag.setEnabled(bool(selected_ids))

        menu.addSeparator()

        # すべて選択
        action_select_all = menu.addAction("すべて選択")
        action_select_all.setEnabled(bool(self.thumbnail_items))

        # 選択解除
        action_deselect = menu.addAction("選択解除")
        action_deselect.setEnabled(bool(selected_ids))

        action = menu.exec(self.graphics_view.mapToGlobal(pos))
        if action == action_stage:
            self.stage_selected_requested.emit()
        elif action == action_quick_tag:
            # 表示中のサムネイルに存在するIDのみに制限
            visible_ids = {item.image_id for item in self.thumbnail_items}
            filtered_ids = [id_ for id_ in selected_ids if id_ in visible_ids]
            self.quick_tag_requested.emit(filtered_ids)
        elif action == action_select_all:
            self._select_all_items()
        elif action == action_deselect:
            self._deselect_all_items()

    def _select_all_items(self) -> None:
        """すべてのサムネイルアイテムを選択する。"""
        if not self.dataset_state or not self.thumbnail_items:
            return

        all_image_ids = [item.image_id for item in self.thumbnail_items]
        self.dataset_state.set_selected_images(all_image_ids)
        logger.debug(f"Selected all {len(all_image_ids)} items")

    def _deselect_all_items(self) -> None:
        """すべてのサムネイルアイテムの選択を解除する。"""
        if not self.dataset_state:
            return

        self.dataset_state.clear_selection()
        logger.debug("Deselected all items")

    def cache_thumbnail(self, image_id: int, pixmap: QPixmap, metadata: dict[str, Any]) -> None:
        """
        サムネイル画像をキャッシュに保存する。

        ThumbnailWorkerからの結果やファイル読み込み結果を効率的にキャッシュし、
        サイズ変更時の高速処理を可能にする。

        Args:
            image_id (int): 画像ID
            pixmap (QPixmap): キャッシュする元画像のQPixmap
            metadata (dict): 画像メタデータ
        """
        if not pixmap.isNull():
            self.image_cache[image_id] = pixmap
            self.image_metadata[image_id] = metadata.copy()

    def get_cached_thumbnail(self, image_id: int, target_size: QSize) -> QPixmap | None:
        """
        指定サイズのサムネイルをキャッシュから取得する。

        スケール済みキャッシュに存在すればそれを返し、なければ元画像から
        スケールして新しいキャッシュエントリを作成する。

        Args:
            image_id (int): 画像ID
            target_size (QSize): 目標サイズ

        Returns:
            QPixmap | None: スケール済みQPixmap、またはキャッシュにない場合None
        """
        cache_key = (image_id, target_size.width(), target_size.height())

        # スケール済みキャッシュをチェック
        if cache_key in self.scaled_cache:
            return self.scaled_cache[cache_key]

        # 元画像からスケール
        if image_id in self.image_cache:
            original_pixmap = self.image_cache[image_id]
            scaled_pixmap = original_pixmap.scaled(
                target_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

            # スケール済みキャッシュに保存
            self.scaled_cache[cache_key] = scaled_pixmap
            return scaled_pixmap

        return None

    def clear_cache(self) -> None:
        """
        全てのキャッシュをクリアする。

        メモリ効率化のため、新しい検索結果受信時や
        大きな状態変更時に呼び出される。
        """
        self.image_cache.clear()
        self.scaled_cache.clear()
        self.image_metadata.clear()
        logger.debug("サムネイルキャッシュをクリアしました")

    def cache_usage_info(self) -> dict[str, int]:
        """
        キャッシュ使用状況を返す（デバッグ用）

        Returns:
            dict: キャッシュ統計情報
        """
        return {
            "original_cache_count": len(self.image_cache),
            "scaled_cache_count": len(self.scaled_cache),
            "metadata_count": len(self.image_metadata),
        }

    def _display_cached_thumbnails(self) -> None:
        """
        キャッシュされた画像からサムネイル表示を構築する。

        image_data の順序に従って、キャッシュから適切なサイズの
        サムネイルを取得してUIに配置する。

        注意: 呼び出し元で事前にscene.clear()とthumbnail_items.clear()が
        実行されている前提で動作する。
        """

        if not self.image_data:
            return

        button_width = self.thumbnail_size.width()
        grid_width = max(self.scrollAreaThumbnails.viewport().width(), self.thumbnail_size.width())
        column_count = max(grid_width // button_width, 1)

        displayed_count = 0
        for i, (image_path, image_id) in enumerate(self.image_data):
            # キャッシュから適切サイズのサムネイルを取得
            scaled_pixmap = self.get_cached_thumbnail(image_id, self.thumbnail_size)

            if scaled_pixmap and not scaled_pixmap.isNull():
                self._add_thumbnail_item_from_cache(image_path, image_id, i, column_count, scaled_pixmap)
                displayed_count += 1
            else:
                # キャッシュにない場合のフォールバック（プレースホルダー）
                placeholder_pixmap = QPixmap(self.thumbnail_size)
                placeholder_pixmap.fill(Qt.GlobalColor.lightGray)
                self._add_thumbnail_item_from_cache(
                    image_path, image_id, i, column_count, placeholder_pixmap
                )

        # シーンサイズを調整
        row_count = (len(self.image_data) + column_count - 1) // column_count
        scene_height = row_count * self.thumbnail_size.height()
        self.scene.setSceneRect(0, 0, grid_width, scene_height)

        logger.debug(f"キャッシュからサムネイル表示: {displayed_count}/{len(self.image_data)}件")

    def _add_thumbnail_item_from_cache(
        self, image_path: Path, image_id: int, index: int, column_count: int, pixmap: QPixmap
    ) -> None:
        """
        キャッシュから取得したPixmapでThumbnailItemを作成・配置する。

        Args:
            image_path (Path): 画像パス（メタデータ用）
            image_id (int): 画像ID
            index (int): グリッド内インデックス
            column_count (int): グリッド列数
            pixmap (QPixmap): 表示するPixmap
        """
        item = ThumbnailItem(pixmap, image_path, image_id, self)
        self.scene.addItem(item)
        self.thumbnail_items.append(item)

        row = index // column_count
        col = index % column_count
        x = col * self.thumbnail_size.width()
        y = row * self.thumbnail_size.height()
        item.setPos(x, y)

    def set_dataset_state(self, dataset_state: DatasetStateManager) -> None:
        """
        DatasetStateManagerを設定または更新する。

        **呼び出し箇所**: MainWindow初期化時 (main_window.py:228)
        **使用意図**: メインウィンドウ設定時にDatasetStateManagerとの連携を確立
        **アーキテクチャ連携**:
        - MainWindow → ThumbnailSelectorWidget の依存性注入
        - DatasetStateManagerとのSignal/Slot双方向通信開始
        - 状態同期により複数コンポーネント間の一貫性保証

        既存の状態管理オブジェクトがある場合は切断してから新しいものを設定し、
        Signal接続を再構築する。これにより他のUIコンポーネントとの状態同期が可能になる。

        Args:
            dataset_state (DatasetStateManager): 新しい状態管理オブジェクト。
                画像選択状態、フィルタ結果、サムネイルサイズなどを中央管理する。
        """
        if self.dataset_state:
            self._disconnect_dataset_state()

        self.dataset_state = dataset_state
        self._connect_dataset_state()

    def _connect_dataset_state(self) -> None:
        """
        DatasetStateManagerとのSignal接続を確立する。

        状態変更通知を受信するため、以下のSignalを接続する：
        - selection_changed: 選択状態変更時の同期
        - current_image_changed: 現在画像変更時の表示更新
        - thumbnail_size_changed: サムネイルサイズ変更時のレイアウト更新
        - images_filtered: フィルタ結果適用時の表示更新
        """
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
        データセット状態管理からの画像フィルタリング通知（互換性維持）

        Args:
            image_metadata: 画像メタデータリスト
        """
        logger.debug("_on_images_filtered 呼び出し - apply_filtered_metadata() 削除により処理をスキップ")
        # Note: apply_filtered_metadata() は削除されました

    def get_current_image_data(self) -> list[dict[str, Any]]:
        """
        [DEPRECATED] 冗長データ管理のため削除予定

        DatasetStateManager.all_images プロパティを直接使用してください。
        """
        logger.warning(
            "get_current_image_data() は非推奨です。DatasetStateManager.all_images を直接使用してください。"
        )
        return []

    @Slot(list)
    def _on_state_selection_changed(self, selected_image_ids: list[int]) -> None:
        """状態管理からの選択変更通知 - UI更新トリガー"""
        # 選択状態は動的取得されるため、再描画のみトリガー
        for item in self.thumbnail_items:
            item.update()  # 再描画トリガー

    @Slot()
    def _sync_selection_to_state(self) -> None:
        """
        QGraphicsScene 選択状態を DatasetStateManager に同期

        ドラッグ選択（RubberBandDrag）による複数選択時に、
        選択された image_ids を DatasetStateManager に反映。

        循環参照防止:
            scene.selectionChanged → blockSignals(True) → dataset_state.set_selected_images()
            → blockSignals(False) により、selection_changed シグナルの再発火を防ぐ。

        DatasetStateManager を真の状態として扱う:
            この同期により、GUI選択とデータモデルの整合性を保つ。
        """
        if not self.dataset_state:
            return

        # 選択中のアイテムから image_id を抽出
        selected_items = self.scene.selectedItems()
        selected_image_ids = []
        for item in selected_items:
            if isinstance(item, ThumbnailItem):
                selected_image_ids.append(item.image_id)

        # 循環参照防止: DatasetStateManager への更新時、シグナルをブロック
        self.dataset_state.blockSignals(True)
        self.dataset_state.set_selected_images(selected_image_ids)
        self.dataset_state.blockSignals(False)

        logger.debug(f"Selection synced to state: {len(selected_image_ids)} images selected")

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

    def load_thumbnails_from_result(self, thumbnail_result: Any) -> None:
        """
        ThumbnailLoadResultからサムネイルをロード（クリーンアーキテクチャ版）

        **新設計原則**:
        - DatasetStateManagerによる統一データ管理
        - ThumbnailSelectorWidgetは表示のみに専念
        - 冗長なデータ管理の完全削除

        Args:
            thumbnail_result: ThumbnailLoadResultオブジェクト
                loaded_thumbnails: list[(image_id, QImage)] - プリロード済み画像データ
                image_metadata: list[dict[str, Any]] - 画像メタデータリスト
                failed_count: int - 読み込み失敗数
                total_count: int - 処理対象総数
        """
        logger.info(f"サムネイル表示開始: {len(thumbnail_result.loaded_thumbnails)}件")

        # UI表示のクリア
        self.scene.clear()
        self.thumbnail_items.clear()
        self.clear_cache()
        self.image_data.clear()

        if not thumbnail_result.loaded_thumbnails:
            logger.info("表示する画像がありません")
            self._update_image_count_display()
            if hasattr(self, "graphics_view"):
                self.graphics_view.viewport().update()
            return

        # **クリーンアーキテクチャ**: DatasetStateManagerに統一データ管理を委譲
        if (
            self.dataset_state
            and hasattr(thumbnail_result, "image_metadata")
            and thumbnail_result.image_metadata
        ):
            self.dataset_state.update_from_search_results(thumbnail_result.image_metadata)
            logger.debug("検索結果をDatasetStateManagerに同期完了")

        # 表示順序を先に確定（_display_cached_thumbnails が image_data を参照するため）
        if hasattr(thumbnail_result, "image_metadata") and thumbnail_result.image_metadata:
            self.image_data = [
                (Path(item["stored_image_path"]), item["id"])
                for item in thumbnail_result.image_metadata
                if "stored_image_path" in item and "id" in item
            ]

        # **表示専念**: UI表示のみに集中
        valid_thumbnails = 0
        for image_id, qimage in thumbnail_result.loaded_thumbnails:
            try:
                qpixmap = QPixmap.fromImage(qimage)
                if not qpixmap.isNull():
                    # シンプルなキャッシュ保存（メタデータはDatasetStateManagerから取得）
                    metadata = {}
                    if self.dataset_state:
                        metadata = self.dataset_state.get_image_by_id(image_id) or {}

                    self.cache_thumbnail(image_id, qpixmap, metadata)
                    valid_thumbnails += 1
                else:
                    logger.warning(f"QPixmap変換失敗: image_id={image_id}")

            except Exception as e:
                logger.error(f"QImage→QPixmap変換エラー image_id={image_id}: {e}")

        # UI表示を構築
        self._display_cached_thumbnails()
        self._update_image_count_display()
        if hasattr(self, "graphics_view"):
            self.graphics_view.viewport().update()

        cache_info = self.cache_usage_info()
        logger.info(
            f"サムネイル表示完了: {valid_thumbnails}件表示, "
            f"キャッシュ: {cache_info['original_cache_count']}件"
        )

        # 選択状態はThumbnailItem.isSelected()で動的取得

    def load_thumbnails_from_paths(self, items: list[tuple[str, int]]) -> None:
        """
        ファイルパスとIDの一覧からサムネイルをロードする（簡易表示用）。

        Args:
            items: [(stored_path, image_id), ...]
        """
        self.scene.clear()
        self.thumbnail_items.clear()
        self.clear_cache()
        self.image_data.clear()

        for path_str, image_id in items:
            path = Path(path_str) if path_str else Path()
            self.image_data.append((path, image_id))

        self.update_thumbnail_layout()
        self._update_image_count_display()
        if hasattr(self, "graphics_view"):
            self.graphics_view.viewport().update()

    def clear_thumbnails(self) -> None:
        """
        全てのサムネイルをクリア（キャッシュ統合版）

        **呼び出し箇所**:
        - MainWindow._on_pipeline_search_started (main_window.py:357)
        - MainWindow._on_search_started (main_window.py:421)
        - MainWindow._on_search_canceled (main_window.py:430)
        - MainWindow._on_search_error (main_window.py:461)
        **使用意図**: 検索処理の開始・終了・エラー時の表示リセット
        **新設計**: キャッシュも含めた完全クリアによるメモリ効率化

        GraphicsSceneとthumbnail_items、image_data、および新しいキャッシュを
        完全にクリアし、新しい検索結果受信に備える。
        """
        self.scene.clear()
        self.thumbnail_items.clear()
        self.image_data.clear()

        # 新しいキャッシュもクリア（メモリ効率化）
        self.clear_cache()

        logger.debug("サムネイル表示とキャッシュをクリアしました")

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

    def resizeEvent(self, event: QResizeEvent) -> None:
        """
        ウィジェットがリサイズされたときにタイマーをリセット
        """
        super().resizeEvent(event)
        self.resize_timer.start(250)

    def handle_item_selection(self, item: ThumbnailItem, modifiers: Qt.KeyboardModifier) -> None:
        """
        アイテムの選択を処理（状態管理統合版）

        **呼び出し箇所**: CustomGraphicsView.itemClicked Signal (thumbnail.py:168)
        **使用意図**: ユーザーのクリック操作を選択状態に変換し、DatasetStateManagerに伝達
        **アーキテクチャ連携**:
        - UI入力 → DatasetStateManager → 全UIコンポーネント への状態伝播
        - 単一責任原則による選択ロジックのDatasetStateManager集約
        - Signal/Slotパターンによる疎結合なコンポーネント間通信

        マウスクリックとキーボード修飾子（Ctrl/Shift）の組み合わせにより、
        単一選択・複数選択・範囲選択を統一的に処理。選択状態はDatasetStateManagerで
        一元管理され、他のUIコンポーネント（プレビュー、詳細表示）にも自動的に反映される。

        Args:
            item (ThumbnailItem): クリックされたサムネイルアイテム
            modifiers (Qt.KeyboardModifier): キーボード修飾子
                - None: 単一選択
                - Ctrl: トグル選択（現在の選択状態を切り替え）
                - Shift: 範囲選択（前回選択から現在まで）
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
        現在のimage_dataに基づいてサムネイルグリッドレイアウトを更新する（キャッシュ優先版）。

        **呼び出し箇所**:
        - QTimer.timeout Signal (thumbnail.py:183) - リサイズ遅延実行
        - _on_thumbnail_size_changed (thumbnail.py:296) - サムネイルサイズ変更時
        - _on_images_filtered (thumbnail.py:260) - 少量データフィルタ結果表示時
        **新設計**: キャッシュ優先でファイルI/O最小化

        キャッシュが利用可能な場合は高速表示、なければ従来のファイル読み込みに
        フォールバック。段階的にキャッシュベース処理への移行を図る。
        """
        self.scene.clear()
        self.thumbnail_items.clear()

        if not self.image_data:
            return

        # キャッシュが利用可能かチェック
        if self.image_cache:
            logger.debug("キャッシュからレイアウト更新を実行")
            self._display_cached_thumbnails()
        else:
            logger.debug("キャッシュなし - ファイルから直接読み込み（レガシーパス）")
            self._legacy_file_based_layout()

    def _legacy_file_based_layout(self) -> None:
        """
        レガシーファイル読み込みベースのレイアウト処理（フォールバック用）

        段階的廃止予定だが、キャッシュが利用できない場合の
        後方互換性確保のため一時的に維持。
        """
        button_width = self.thumbnail_size.width()
        grid_width = max(self.scrollAreaThumbnails.viewport().width(), self.thumbnail_size.width())
        column_count = max(grid_width // button_width, 1)

        for i, (image_path, image_id) in enumerate(self.image_data):
            self.add_thumbnail_item(image_path, image_id, i, column_count)

        row_count = (len(self.image_data) + column_count - 1) // column_count
        scene_height = row_count * self.thumbnail_size.height()
        self.scene.setSceneRect(0, 0, grid_width, scene_height)

    def add_thumbnail_item(self, image_path: Path, image_id: int, index: int, column_count: int) -> None:
        """
        指定されたパスから直接ファイルを読み込んでサムネイルアイテムを作成する。

        **呼び出し箇所**: update_thumbnail_layout (thumbnail.py:525内のループ)
        **使用意図**: 小〜中規模データの直接ファイル読み込みによる即座表示
        **アーキテクチャ連携**:
        - update_thumbnail_layout → add_thumbnail_item のシーケンシャル実行
        - メインスレッド同期処理による即座UI反映
        - load_thumbnails_from_result（ワーカー版）との役割分担

        与えられたパスからQPixmapを作成し、サムネイルサイズにスケール。
        ファイル読み込みに失敗した場合は灰色のプレースホルダーを作成。
        メインスレッドでの同期処理のため、大量の画像ではUIフリーズの原因となる。
        レスポンシブレイアウト更新や少量データの即座表示が主な用途。

        Args:
            image_path (Path): 読み込む画像ファイルのパス
            image_id (int): データベース内の画像ID
            index (int): グリッド内での順序インデックス
            column_count (int): グリッドの列数（位置計算用）
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
        """
        現在選択中の画像パスリストを取得する。

        **呼び出し箇所**: テストコード (test_thumbnail_selector_widget.py:303)
        **使用意図**: 選択状態の外部確認・シグナル発火時のデータ取得
        **アーキテクチャ連携**:
        - DatasetStateManagerの選択状態とThumbnailItemsの照合処理
        - 他UIコンポーネントへの選択情報提供（プレビュー更新等）
        - Signal発火時のペイロード生成

        DatasetStateManagerの状態とthumbnail_itemsを照合して、
        選択状態の画像IDに対応するパスを抽出。Signal発火や外部コンポーネントへの
        情報提供で使用される。

        Returns:
            list[Path]: 選択中の画像ファイルパスのリスト。
                DatasetStateManagerがない場合は空リストを返す。
        """
        if not self.dataset_state:
            return []

        selected_ids = set(self.dataset_state.selected_image_ids)
        return [item.image_path for item in self.thumbnail_items if item.image_id in selected_ids]


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
    # Convert paths to image_data format
    widget.image_data = [(path, i) for i, path in enumerate(image_paths)]
    widget.setMinimumSize(400, 300)  # ウィジェットの最小サイズを設定
    widget.show()
    sys.exit(app.exec())
