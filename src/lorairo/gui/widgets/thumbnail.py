# src/lorairo/gui/widgets/thumbnail.py

from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast, overload

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPen, QPixmap, QResizeEvent, QShortcut
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QMenu,
    QStyleOptionGraphicsItem,
    QVBoxLayout,
    QWidget,
)

from ...gui.designer.ThumbnailSelectorWidget_ui import Ui_ThumbnailSelectorWidget
from ...utils.log import logger
from ..cache.thumbnail_page_cache import ThumbnailPageCache
from ..state.dataset_state import DatasetStateManager
from ..state.pagination_state import PaginationStateManager
from ..workers.thumbnail_worker import ThumbnailLoadResult
from .pagination_nav_widget import PaginationNavWidget

if TYPE_CHECKING:
    from ..services.worker_service import WorkerService
    from ..workers.search_worker import SearchResult


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

    def __init__(self, pixmap: QPixmap, image_path: Path, image_id: int, parent: ThumbnailSelectorWidget):
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

    標準OS準拠の選択動作:
    - Click: 単一選択
    - Ctrl+Click: トグル選択
    - Shift+Click: 範囲選択
    - Ctrl+Shift+Click: 範囲追加選択
    - ドラッグ: ラバーバンド矩形選択
    - Ctrl+ドラッグ / Shift+ドラッグ: 既存選択に矩形選択を追加
    - Ctrl+A: 全選択
    """

    itemClicked = Signal(ThumbnailItem, Qt.KeyboardModifier)
    emptySpaceClicked = Signal()
    selectAllRequested = Signal()  # Ctrl+A押下時に発火

    @overload
    def __init__(self, parent: QWidget | None = None) -> None: ...

    @overload
    def __init__(self, scene: QGraphicsScene, parent: QWidget | None = None) -> None: ...

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        CustomGraphicsViewを初期化する。

        QGraphicsViewの複数の初期化形式をサポート:
        - CustomGraphicsView(parent)
        - CustomGraphicsView(scene, parent)
        """
        super().__init__(*args, **kwargs)
        self._drag_modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier
        # キーボードフォーカスを受け取れるように設定（Ctrl+A等のキー操作に必要）
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """
        マウスプレスイベントを処理する。

        左クリック時のみ選択ロジックを処理し、右クリックは無視してコンテキストメニューに委譲する。
        アイテムクリック時はitemClickedシグナルを発行し、super()を呼ばない。
        これによりQtのシーン選択が独自の選択ロジックを上書きするのを防止する。
        空スペースクリック時のみsuper()を呼び、ラバーバンドドラッグを有効にする。

        Args:
            event: マウスイベント
        """
        # 右クリックは無視（コンテキストメニューで処理）
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        item = self.itemAt(event.position().toPoint())
        if isinstance(item, ThumbnailItem):
            # アイテム上のクリック: 独自の選択ロジックで処理
            # super()を呼ばないことで、Qtのシーン選択による上書きを防止
            self.itemClicked.emit(item, event.modifiers())
        else:
            # 空スペース: ドラッグ修飾子を記録してラバーバンド開始
            self._drag_modifiers = event.modifiers()
            if not (
                event.modifiers()
                & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
            ):
                # 修飾子なしの空スペースクリック → 選択解除用シグナル
                self.emptySpaceClicked.emit()
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """
        マウスリリースイベント処理。

        ラバーバンドドラッグ終了後にドラッグ修飾子をリセットする。

        Args:
            event: マウスイベント
        """
        super().mouseReleaseEvent(event)
        self._drag_modifiers = Qt.KeyboardModifier.NoModifier

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """
        キープレスイベントを処理する。

        Ctrl+A（全選択）を処理し、selectAllRequestedシグナルを発火する。

        Args:
            event: キーイベント
        """
        # Ctrl+A: 全選択
        if event.key() == Qt.Key.Key_A and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.selectAllRequested.emit()
            event.accept()
            return

        # その他のキーイベントは親クラスに委譲
        super().keyPressEvent(event)


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
    stage_selected_requested = Signal(list)  # バッチタグのステージング追加要求（visible image_ids）
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
        self.graphics_view.emptySpaceClicked.connect(self._on_empty_space_clicked)
        self.graphics_view.selectAllRequested.connect(self._select_all_items)
        self.graphics_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.graphics_view.customContextMenuRequested.connect(self._on_context_menu_requested)

        layout = QVBoxLayout(self.widgetThumbnailsContent)
        layout.addWidget(self.graphics_view)
        self.widgetThumbnailsContent.setLayout(layout)

        # キャッシュ機構
        self.image_cache: dict[int, QPixmap] = {}  # legacy互換（平坦キャッシュ）
        self.page_cache = ThumbnailPageCache(max_pages=5)  # ページ単位キャッシュ
        self.image_metadata: dict[int, dict[str, Any]] = {}  # image_id -> メタデータ

        # ページネーション状態
        self.pagination_state: PaginationStateManager | None = None
        self.pagination_nav: PaginationNavWidget | None = None
        self._worker_service: WorkerService | None = None
        self._active_search_result: SearchResult | None = None
        self._current_display_page: int = 1
        self._display_request_id: str | None = None
        self._prefetch_request_ids: set[str] = set()
        self._request_id_to_page: dict[str, int] = {}
        self._request_id_to_worker_id: dict[str, str] = {}
        self._prefetch_queue: list[int] = []
        self._suspend_page_change: bool = False

        # レガシー互換（段階的廃止予定）
        self.image_data: list[tuple[Path, int]] = []  # (image_path, image_id)
        self.current_image_metadata: list[dict[str, Any]] = []  # フィルタリング用の画像メタデータ
        self.thumbnail_items: list[ThumbnailItem] = []  # ThumbnailItem のリスト
        self.last_selected_item: ThumbnailItem | None = None

        # ページロード中オーバーレイ（新ページ確定まで旧ページ表示維持）
        self.loading_overlay = QLabel("読み込み中...", self.graphics_view.viewport())
        self.loading_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_overlay.setStyleSheet(
            "background-color: rgba(0, 0, 0, 120); color: white; font-weight: bold;"
        )
        self.loading_overlay.hide()

        # リサイズ用のタイマーを初期化
        self.resize_timer = QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self.update_thumbnail_layout)

        # ヘッダー部分の接続設定
        self._setup_header_connections()
        self._setup_pagination_ui()

        # 状態管理との連携
        if self.dataset_state:
            self._connect_dataset_state()
            # ドラッグ選択の同期（scene → DatasetStateManager）
            self.scene.selectionChanged.connect(self._sync_selection_to_state)
            self._ensure_pagination_state()

        # キーボードフォーカスを受け取れるように設定（Ctrl+A等のキー操作に必要）
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Ctrl+A ショートカット（フォーカス位置に関わらず確実に動作）
        self.select_all_shortcut = QShortcut("Ctrl+A", self)
        self.select_all_shortcut.activated.connect(self._select_all_items)

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

    def _setup_pagination_ui(self) -> None:
        """固定フッターのページネーションUIを初期化する。"""
        if not hasattr(self, "verticalLayout"):
            return

        self.pagination_nav = PaginationNavWidget(self)
        self.pagination_nav.setVisible(False)
        self.pagination_nav.page_requested.connect(self._on_page_requested)
        self.verticalLayout.addWidget(self.pagination_nav)

    def _ensure_pagination_state(self) -> None:
        """DatasetStateManagerに紐づくPaginationStateManagerを初期化する。"""
        if not self.dataset_state:
            return

        current_dataset_state = (
            getattr(self.pagination_state, "_dataset_state", None)
            if self.pagination_state is not None
            else None
        )
        if self.pagination_state is not None and current_dataset_state is self.dataset_state:
            return

        if self.pagination_state is not None:
            try:
                self.pagination_state.page_changed.disconnect(self._on_page_changed)
            except Exception:
                pass
            self.pagination_state.deleteLater()

        self.pagination_state = PaginationStateManager(
            dataset_state=self.dataset_state,
            page_size=100,
            max_cached_pages=5,
            parent=self,
        )
        self.pagination_state.page_changed.connect(self._on_page_changed)

    def initialize_pagination_search(
        self,
        search_result: SearchResult,
        worker_service: WorkerService | None,
    ) -> None:
        """検索完了時にページネーション表示を初期化する。"""
        if not self.dataset_state:
            logger.warning("DatasetStateManager not available, pagination disabled")
            return

        self._worker_service = worker_service
        self._active_search_result = search_result
        self._ensure_pagination_state()
        if not self.pagination_state:
            return

        self._cancel_pending_thumbnail_requests()
        self.page_cache.clear()
        self.image_cache.clear()
        self.image_metadata.clear()
        self.image_data.clear()
        self._prefetch_queue.clear()
        self._prefetch_request_ids.clear()
        self._request_id_to_page.clear()
        self._request_id_to_worker_id.clear()
        self._display_request_id = None
        self._current_display_page = 1

        self._suspend_page_change = True
        self.dataset_state.update_from_search_results(search_result.image_metadata)
        self._suspend_page_change = False

        if self.pagination_nav:
            self.pagination_nav.setVisible(True)
            self.pagination_nav.update_state(
                current=1,
                total=self.pagination_state.total_pages,
                is_loading=False,
            )

        self._suspend_page_change = True
        self.pagination_state.reset_to_first_page()
        self._suspend_page_change = False
        self._display_or_request_page(1, cancel_previous=True)

    def handle_thumbnail_page_result(self, thumbnail_result: ThumbnailLoadResult) -> None:
        """ページ単位サムネイル読み込み結果を処理する。"""
        page_num = getattr(thumbnail_result, "page_num", None)
        request_id = getattr(thumbnail_result, "request_id", None)

        # 旧経路との互換: ページ識別がない結果は既存処理に委譲
        if page_num is None or request_id is None:
            self.load_thumbnails_from_result(thumbnail_result)
            return

        if request_id not in self._request_id_to_page:
            logger.debug(f"Stale thumbnail result ignored: request_id={request_id}")
            return

        self._request_id_to_page.pop(request_id, None)
        self._request_id_to_worker_id.pop(request_id, None)

        # デバッグ: ワーカーからの結果を詳細ログ
        loaded_count = len(thumbnail_result.loaded_thumbnails)
        failed_count = getattr(thumbnail_result, "failed_count", 0)
        total_count = getattr(thumbnail_result, "total_count", 0)
        logger.debug(
            f"ページ {page_num} サムネイル結果: loaded={loaded_count}, failed={failed_count}, "
            f"total={total_count}, request_id={request_id}"
        )

        thumbnails: list[tuple[int, QPixmap]] = []
        null_pixmap_count = 0
        for image_id, qimage in thumbnail_result.loaded_thumbnails:
            qpixmap = QPixmap.fromImage(qimage)
            if not qpixmap.isNull():
                thumbnails.append((image_id, qpixmap))
            else:
                null_pixmap_count += 1
                logger.warning(f"QPixmap変換失敗: image_id={image_id}, page={page_num}")

        if null_pixmap_count > 0:
            logger.warning(f"ページ {page_num}: {null_pixmap_count}件のQPixmap変換失敗")

        self.page_cache.set_page(page_num, thumbnails)

        if request_id == self._display_request_id:
            self._display_request_id = None
            self._display_page(page_num)
            self._hide_loading_overlay()
            self._start_prefetch_if_needed(page_num)
        elif request_id in self._prefetch_request_ids:
            self._prefetch_request_ids.discard(request_id)
            self._start_next_prefetch()

        if self.pagination_nav and self.pagination_state:
            is_loading = self._display_request_id is not None
            self.pagination_nav.update_state(
                current=self.pagination_state.current_page,
                total=self.pagination_state.total_pages,
                is_loading=is_loading,
            )

    @Slot(int)
    def _on_page_requested(self, page: int) -> None:
        """ページナビゲーションUIからのページ要求を処理する。"""
        if not self.pagination_state:
            return
        self.pagination_state.set_page(page)

    @Slot(int)
    def _on_page_changed(self, page: int) -> None:
        """ページ変更時の表示更新を処理する。"""
        if self._suspend_page_change:
            return
        self._display_or_request_page(page, cancel_previous=True)

    def _display_or_request_page(self, page: int, cancel_previous: bool) -> None:
        """対象ページを表示し、未キャッシュなら読み込みを要求する。"""
        self._cancel_pending_thumbnail_requests()

        if self._display_request_id:
            self._request_id_to_page.pop(self._display_request_id, None)
            self._request_id_to_worker_id.pop(self._display_request_id, None)
            self._display_request_id = None

        for request_id in self._prefetch_request_ids:
            self._request_id_to_page.pop(request_id, None)
            self._request_id_to_worker_id.pop(request_id, None)
        self._prefetch_queue.clear()
        self._prefetch_request_ids.clear()

        cached = self.page_cache.get_page(page)
        if cached is not None:
            self._display_page(page)
            self._hide_loading_overlay()
            self._start_prefetch_if_needed(page)
            return

        self._show_loading_overlay()
        self._request_page_load(page, cancel_previous=cancel_previous, mark_as_display=True)

    def _cancel_pending_thumbnail_requests(self) -> None:
        """未完了のサムネイル読み込み要求をキャンセルする。"""
        if not self._worker_service or not hasattr(self._worker_service, "cancel_thumbnail_load"):
            return

        pending_request_ids: list[str] = []
        if self._display_request_id is not None:
            pending_request_ids.append(self._display_request_id)
        pending_request_ids.extend(self._prefetch_request_ids)

        canceled_any = False
        for request_id in pending_request_ids:
            worker_id = self._request_id_to_worker_id.get(request_id)
            if not worker_id:
                continue
            try:
                self._worker_service.cancel_thumbnail_load(worker_id)
                canceled_any = True
            except Exception:
                logger.exception(f"Failed to cancel thumbnail worker: worker_id={worker_id}")

        # 念のためのフォールバック（旧状態のマッピング欠落に対応）
        if not canceled_any and pending_request_ids:
            current_worker_id = getattr(self._worker_service, "current_thumbnail_worker_id", None)
            if current_worker_id:
                try:
                    self._worker_service.cancel_thumbnail_load(current_worker_id)
                except Exception:
                    logger.exception(
                        f"Failed to cancel current thumbnail worker: worker_id={current_worker_id}"
                    )

    def _request_page_load(
        self,
        page: int,
        cancel_previous: bool,
        mark_as_display: bool,
    ) -> None:
        """ページ単位サムネイル読み込みをWorkerServiceへ要求する。"""
        if not self.pagination_state or not self._worker_service or not self._active_search_result:
            return

        image_ids = self.pagination_state.get_page_image_ids(page)
        if not image_ids:
            self.scene.clear()
            self.thumbnail_items.clear()
            self.image_data.clear()
            self._update_image_count_display()
            self._hide_loading_overlay()
            return

        # デバッグ: データ整合性チェック
        search_result_count = (
            len(self._active_search_result.image_metadata) if self._active_search_result else 0
        )
        dataset_count = len(self.dataset_state.filtered_images) if self.dataset_state else 0
        logger.debug(
            f"ページ {page} 読み込み要求: image_ids={len(image_ids)}件, "
            f"search_result={search_result_count}件, dataset_state={dataset_count}件"
        )
        if search_result_count != dataset_count:
            logger.warning(
                f"データ不整合検出: search_result ({search_result_count}件) != "
                f"dataset_state ({dataset_count}件)"
            )

        request_id = uuid.uuid4().hex[:12]
        self._request_id_to_page[request_id] = page
        if mark_as_display:
            self._display_request_id = request_id
        else:
            self._prefetch_request_ids.add(request_id)

        try:
            worker_id = self._worker_service.start_thumbnail_page_load(
                search_result=self._active_search_result,
                thumbnail_size=self.thumbnail_size,
                image_ids=image_ids,
                page_num=page,
                request_id=request_id,
                cancel_previous=cancel_previous,
            )
            self._request_id_to_worker_id[request_id] = worker_id
        except Exception:
            self._request_id_to_page.pop(request_id, None)
            self._prefetch_request_ids.discard(request_id)
            self._request_id_to_worker_id.pop(request_id, None)
            if self._display_request_id == request_id:
                self._display_request_id = None
                self._hide_loading_overlay()
            logger.exception(f"Failed to request thumbnail page load: page={page}, request_id={request_id}")
            return

        if self.pagination_nav and self.pagination_state:
            self.pagination_nav.update_state(
                current=self.pagination_state.current_page,
                total=self.pagination_state.total_pages,
                is_loading=self._display_request_id is not None,
            )

    def _start_prefetch_if_needed(self, current_page: int) -> None:
        """現在ページを基準に先読みキューを作成する。"""
        if not self.pagination_state:
            return

        pages_to_load = self.pagination_state.get_pages_to_load(
            target_page=current_page,
            cached_pages=self.page_cache.cached_pages,
        )
        self._prefetch_queue = [page for page in pages_to_load if page != current_page]
        self._start_next_prefetch()

    def _start_next_prefetch(self) -> None:
        """先読みキューの次ページを読み込む。"""
        if not self._prefetch_queue or self._display_request_id is not None:
            return

        next_page = self._prefetch_queue.pop(0)
        self._request_page_load(next_page, cancel_previous=False, mark_as_display=False)

    def _display_page(self, page: int) -> None:
        """キャッシュ済みページをUIへ表示する。"""
        if not self.pagination_state:
            return

        cached = self.page_cache.get_page(page)
        if cached is None:
            logger.warning(f"ページ {page} のキャッシュが見つかりません")
            return

        self._current_display_page = page
        page_pixmap_map = {image_id: pixmap for image_id, pixmap in cached}
        page_image_ids = self.pagination_state.get_page_image_ids(page)

        self.scene.clear()
        self.thumbnail_items.clear()
        self.image_data.clear()

        button_width = self.thumbnail_size.width()
        grid_width = max(self.scrollAreaThumbnails.viewport().width(), self.thumbnail_size.width())
        column_count = max(grid_width // button_width, 1)

        for index, image_id in enumerate(page_image_ids):
            metadata = self.dataset_state.get_image_by_id(image_id) if self.dataset_state else None
            stored_path = metadata.get("stored_image_path") if metadata else ""
            image_path = Path(stored_path) if stored_path else Path()
            self.image_data.append((image_path, image_id))

            pixmap = page_pixmap_map.get(image_id)
            if pixmap is None:
                pixmap = QPixmap(self.thumbnail_size)
                pixmap.fill(Qt.GlobalColor.lightGray)

            scaled_pixmap = pixmap.scaled(
                self.thumbnail_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._add_thumbnail_item_from_cache(
                image_path=image_path,
                image_id=image_id,
                index=index,
                column_count=column_count,
                pixmap=scaled_pixmap,
            )

        row_count = (len(page_image_ids) + column_count - 1) // column_count
        self.scene.setSceneRect(0, 0, grid_width, row_count * self.thumbnail_size.height())
        self._update_image_count_display()
        self.graphics_view.viewport().update()
        if self.pagination_nav and self.pagination_state:
            self.pagination_nav.update_state(
                current=page,
                total=self.pagination_state.total_pages,
                is_loading=self._display_request_id is not None,
            )

    def _show_loading_overlay(self) -> None:
        """ページ読み込み中のオーバーレイを表示する。"""
        self.loading_overlay.setGeometry(self.graphics_view.viewport().rect())
        self.loading_overlay.show()
        self.loading_overlay.raise_()

    def _hide_loading_overlay(self) -> None:
        """ページ読み込み中のオーバーレイを非表示にする。"""
        self.loading_overlay.hide()

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

        # ページキャッシュから再表示
        if self.pagination_state and self.page_cache.has_page(self._current_display_page):
            self._display_page(self._current_display_page)
        # レガシーキャッシュから高速再表示（ファイルI/O完全回避）
        elif self.image_cache:
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
        visible_ids = {thumb.image_id for thumb in self.thumbnail_items}
        visible_selected_ids = [id_ for id_ in selected_ids if id_ in visible_ids]

        menu = QMenu(self)

        # バッチタグへ追加
        action_stage = menu.addAction("バッチタグへ追加")
        action_stage.setEnabled(bool(visible_selected_ids))

        # クイックタグ追加
        action_quick_tag = menu.addAction("クイックタグ追加...")
        action_quick_tag.setEnabled(bool(visible_selected_ids))

        menu.addSeparator()

        # すべて選択
        action_select_all = menu.addAction("すべて選択")
        action_select_all.setEnabled(bool(self.thumbnail_items))

        # 選択解除
        action_deselect = menu.addAction("選択解除")
        action_deselect.setEnabled(bool(selected_ids))

        action = menu.exec(self.graphics_view.mapToGlobal(pos))
        if action == action_stage:
            self.stage_selected_requested.emit(visible_selected_ids)
        elif action == action_quick_tag:
            self.quick_tag_requested.emit(visible_selected_ids)
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

        元画像キャッシュからその都度スケールして返す。

        Args:
            image_id (int): 画像ID
            target_size (QSize): 目標サイズ

        Returns:
            QPixmap | None: スケール済みQPixmap、またはキャッシュにない場合None
        """
        if image_id in self.image_cache:
            original_pixmap = self.image_cache[image_id]
            return original_pixmap.scaled(
                target_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

        return None

    def clear_cache(self) -> None:
        """
        全てのキャッシュをクリアする。

        メモリ効率化のため、新しい検索結果受信時や
        大きな状態変更時に呼び出される。
        """
        self.image_cache.clear()
        self.page_cache.clear()
        self.image_metadata.clear()
        self._cancel_pending_thumbnail_requests()
        self._prefetch_queue.clear()
        self._prefetch_request_ids.clear()
        self._request_id_to_page.clear()
        self._request_id_to_worker_id.clear()
        self._display_request_id = None
        logger.debug("サムネイルキャッシュをクリアしました")

    def cache_usage_info(self) -> dict[str, int]:
        """
        キャッシュ使用状況を返す（デバッグ用）

        Returns:
            dict: キャッシュ統計情報
        """
        return {
            "original_cache_count": len(self.image_cache),
            "page_cache_count": self.page_cache.cache_size,
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
        self._ensure_pagination_state()

        # scene.selectionChanged は多重接続を避けて再接続
        try:
            self.scene.selectionChanged.disconnect(self._sync_selection_to_state)
        except Exception:
            pass
        self.scene.selectionChanged.connect(self._sync_selection_to_state)

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

        Ctrl/Shift修飾子付きドラッグの場合、既存選択を維持して追加する。

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
        selected_image_ids = [item.image_id for item in selected_items if isinstance(item, ThumbnailItem)]

        # ドラッグ開始時の修飾子を取得
        drag_modifiers = self.graphics_view._drag_modifiers

        if drag_modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            # Ctrl/Shift+ドラッグ: 既存選択を維持して追加（重複排除、順序維持）
            current_ids = self.dataset_state.selected_image_ids
            merged = list(dict.fromkeys(current_ids + selected_image_ids))
            self.dataset_state.blockSignals(True)
            self.dataset_state.set_selected_images(merged)
            self.dataset_state.blockSignals(False)
        else:
            # 通常ドラッグ: 選択を置換
            self.dataset_state.blockSignals(True)
            self.dataset_state.set_selected_images(selected_image_ids)
            self.dataset_state.blockSignals(False)

        logger.debug(
            f"Selection synced to state: {len(self.dataset_state.selected_image_ids)} images selected"
        )

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
        if self.pagination_nav:
            self.pagination_nav.setVisible(False)

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
        self._active_search_result = None
        if self.pagination_nav:
            self.pagination_nav.setVisible(False)

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
        self._current_display_page = 1

        # 新しいキャッシュもクリア（メモリ効率化）
        self.clear_cache()
        self._hide_loading_overlay()
        self._active_search_result = None
        if self.pagination_nav:
            self.pagination_nav.setVisible(False)

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
        if self.loading_overlay.isVisible():
            self.loading_overlay.setGeometry(self.graphics_view.viewport().rect())
        self.resize_timer.start(250)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """
        キープレスイベントを処理する。

        Ctrl+A（全選択）を処理し、_select_all_itemsを呼び出す。
        これによりビューにフォーカスがなくてもCtrl+Aが機能する。

        Args:
            event: キーイベント
        """
        # Ctrl+A: 全選択
        if event.key() == Qt.Key.Key_A and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self._select_all_items()
            event.accept()
            return

        # その他のキーイベントは親クラスに委譲
        super().keyPressEvent(event)

    def _on_empty_space_clicked(self) -> None:
        """空スペースクリック時の選択解除処理"""
        if self.dataset_state:
            self.dataset_state.clear_selection()

    def handle_item_selection(self, item: ThumbnailItem, modifiers: Qt.KeyboardModifier) -> None:
        """
        アイテムの選択を処理（標準OS準拠の選択動作）

        **呼び出し箇所**: CustomGraphicsView.itemClicked Signal (thumbnail.py)
        **使用意図**: ユーザーのクリック操作を選択状態に変換し、DatasetStateManagerに伝達
        **アーキテクチャ連携**:
        - UI入力 → DatasetStateManager → 全UIコンポーネント への状態伝播
        - 単一責任原則による選択ロジックのDatasetStateManager集約
        - Signal/Slotパターンによる疎結合なコンポーネント間通信

        マウスクリックとキーボード修飾子（Ctrl/Shift）の組み合わせにより、
        単一選択・複数選択・範囲選択・範囲追加選択を統一的に処理。

        Args:
            item: クリックされたサムネイルアイテム
            modifiers: キーボード修飾子
                - None: 単一選択（他を解除）
                - Ctrl: トグル選択（現在の選択状態を切り替え）
                - Shift: 範囲選択（前回選択から現在まで、既存選択を置換）
                - Ctrl+Shift: 範囲追加選択（既存選択を維持して範囲を追加）
        """
        if not self.dataset_state:
            logger.debug("状態管理が未設定のため選択操作をスキップ")
            return

        has_ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        has_shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

        if has_ctrl and has_shift and self.last_selected_item:
            # Ctrl+Shift選択: 既存選択を維持して範囲を追加
            self.select_range(self.last_selected_item, item, add_to_existing=True)
        elif has_ctrl:
            # Ctrl選択: 選択状態をトグル
            self.dataset_state.toggle_selection(item.image_id)
        elif has_shift and self.last_selected_item:
            # Shift選択: 範囲選択（既存選択を置換）
            self.select_range(self.last_selected_item, item, add_to_existing=False)
        else:
            # 通常選択: 単一選択
            self.dataset_state.set_selected_images([item.image_id])
            self.dataset_state.set_current_image(item.image_id)

        self.last_selected_item = item

    def select_range(
        self,
        start_item: ThumbnailItem,
        end_item: ThumbnailItem,
        *,
        add_to_existing: bool = False,
    ) -> None:
        """範囲選択処理（DatasetStateManager経由）

        Args:
            start_item: 範囲選択の開始アイテム
            end_item: 範囲選択の終了アイテム
            add_to_existing: Trueの場合、既存の選択を維持して範囲を追加（Ctrl+Shift+Click用）
        """
        if start_item is None or end_item is None or not self.dataset_state:
            return

        start_index = self.thumbnail_items.index(start_item)
        end_index = self.thumbnail_items.index(end_item)
        start_index, end_index = min(start_index, end_index), max(start_index, end_index)

        range_ids = [
            item.image_id for i, item in enumerate(self.thumbnail_items) if start_index <= i <= end_index
        ]

        if add_to_existing:
            # 既存選択を維持して範囲を追加（重複排除、順序維持）
            current_ids = list(self.dataset_state.selected_image_ids)
            merged = list(dict.fromkeys(current_ids + range_ids))
            self.dataset_state.set_selected_images(merged)
        else:
            self.dataset_state.set_selected_images(range_ids)

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

        # ページキャッシュが利用可能かチェック
        if self.pagination_state and self.page_cache.has_page(self._current_display_page):
            logger.debug(f"ページキャッシュからレイアウト更新: page={self._current_display_page}")
            self._display_page(self._current_display_page)
        # レガシーキャッシュが利用可能かチェック
        elif self.image_cache:
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
