# src/lorairo/gui/widgets/thumbnail_selector_widget.py

from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QPixmap, QResizeEvent
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QLabel, QMenu, QVBoxLayout, QWidget

from ...gui.designer.ThumbnailSelectorWidget_ui import Ui_ThumbnailSelectorWidget
from ...utils.log import logger
from .. import theme
from ..cache.thumbnail_page_cache import ThumbnailPageCache
from ..state.dataset_state import DatasetStateManager
from ..state.pagination_state import PaginationStateManager
from ..workers.terminal import CancelReason
from ..workers.thumbnail_worker import ThumbnailLoadResult
from .custom_graphics_view import CustomGraphicsView
from .pagination_nav_widget import PaginationNavWidget
from .thumbnail_item import ThumbnailItem

if TYPE_CHECKING:
    from ..services.worker_service import WorkerService
    from ..workers.search_worker import SearchResult


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
        self.graphics_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.graphics_view.customContextMenuRequested.connect(self._on_context_menu_requested)

        layout = QVBoxLayout(self.widgetThumbnailsContent)
        layout.addWidget(self.graphics_view)
        self.widgetThumbnailsContent.setLayout(layout)

        # ページ単位キャッシュ（検索結果サムネイル表示のSSoT）
        self.page_cache = ThumbnailPageCache(max_pages=5)  # ページ単位キャッシュ

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

        # 表示中アイテム状態
        self.thumbnail_items: list[ThumbnailItem] = []  # ThumbnailItem のリスト
        self._explicit_path_items: list[tuple[Path, int]] = []  # stagingなど小規模明示パス表示用
        self.last_selected_item: ThumbnailItem | None = None

        # ページロード中オーバーレイ（新ページ確定まで旧ページ表示維持）
        self.loading_overlay = QLabel("読み込み中...", self.graphics_view.viewport())
        self.loading_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_overlay.setStyleSheet(theme.LOADING_OVERLAY_QSS)
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
        self._explicit_path_items.clear()
        self.thumbnail_items.clear()
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
                total_items=self.pagination_state.total_items,
                page_size=self.pagination_state.page_size,
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
                total_items=self.pagination_state.total_items,
                page_size=self.pagination_state.page_size,
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
                reason = (
                    CancelReason.PREFETCH_REPLACED
                    if request_id in self._prefetch_request_ids
                    else CancelReason.THUMBNAIL_REPLACED
                )
                self._worker_service.cancel_thumbnail_load(worker_id, reason=reason)
                canceled_any = True
            except Exception:
                logger.exception(f"Failed to cancel thumbnail worker: worker_id={worker_id}")

        # 念のためのフォールバック（旧状態のマッピング欠落に対応）
        if not canceled_any and pending_request_ids:
            current_worker_id = getattr(self._worker_service, "current_thumbnail_worker_id", None)
            if current_worker_id:
                try:
                    self._worker_service.cancel_thumbnail_load(
                        current_worker_id,
                        reason=CancelReason.THUMBNAIL_REPLACED,
                    )
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
            self._explicit_path_items.clear()
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
                total_items=self.pagination_state.total_items,
                page_size=self.pagination_state.page_size,
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
        page_pixmap_map = dict(cached)
        page_image_ids = self.pagination_state.get_page_image_ids(page)

        self.scene.clear()
        self.thumbnail_items.clear()
        self._explicit_path_items.clear()

        button_width = self.thumbnail_size.width()
        grid_width = max(self.scrollAreaThumbnails.viewport().width(), self.thumbnail_size.width())
        column_count = max(grid_width // button_width, 1)

        for index, image_id in enumerate(page_image_ids):
            metadata = self.dataset_state.get_image_by_id(image_id) if self.dataset_state else None
            stored_path = metadata.get("stored_image_path") if metadata else ""
            image_path = Path(stored_path) if stored_path else Path()

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
                total_items=self.pagination_state.total_items,
                page_size=self.pagination_state.page_size,
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
        サムネイルサイズスライダーの値変更を処理する。

        Args:
            value (int): 新しいサムネイルサイズ値
        """
        self.thumbnail_size = QSize(value, value)

        # 画像件数表示を更新
        self._update_image_count_display()

        # 検索結果はページキャッシュから再表示する。staging等の明示パス表示は小規模用途として再構築する。
        if self.pagination_state and self.page_cache.has_page(self._current_display_page):
            self._display_page(self._current_display_page)
        elif self._explicit_path_items:
            self._display_explicit_path_items()

    def _update_image_count_display(self) -> None:
        """
        画像件数表示を更新する。

        現在読み込まれている画像数をヘッダーに表示する。
        """
        if hasattr(self, "labelThumbnailCount"):
            count = len(self.thumbnail_items)
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

    def clear_cache(self) -> None:
        """
        ページキャッシュと未完了リクエスト状態をクリアする。

        メモリ効率化のため、新しい検索結果受信時や
        大きな状態変更時に呼び出される。
        """
        self.page_cache.clear()
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
            "page_cache_count": self.page_cache.cache_size,
        }

    def _display_explicit_path_items(self) -> None:
        """stagingなど小規模な明示パスリストからサムネイル表示を構築する。"""
        self.scene.clear()
        self.thumbnail_items.clear()

        if not self._explicit_path_items:
            self._update_image_count_display()
            return

        button_width = self.thumbnail_size.width()
        grid_width = max(self.scrollAreaThumbnails.viewport().width(), self.thumbnail_size.width())
        column_count = max(grid_width // button_width, 1)

        for index, (image_path, image_id) in enumerate(self._explicit_path_items):
            pixmap = QPixmap(str(image_path)).scaled(
                self.thumbnail_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            if pixmap.isNull():
                logger.warning(f"Failed to load staging thumbnail from image path: {image_path}")
                pixmap = QPixmap(self.thumbnail_size)
                pixmap.fill(Qt.GlobalColor.gray)
            self._add_thumbnail_item_from_cache(image_path, image_id, index, column_count, pixmap)

        row_count = (len(self._explicit_path_items) + column_count - 1) // column_count
        scene_height = row_count * self.thumbnail_size.height()
        self.scene.setSceneRect(0, 0, grid_width, scene_height)
        self._update_image_count_display()

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
        """DatasetStateManagerの画像更新通知を受ける。表示更新はページネーション経路で行う。"""
        logger.debug(f"DatasetStateManager images_filtered received: {len(image_metadata)} images")

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

    def _reset_thumbnail_display(self) -> None:
        """サムネイル表示状態を完全にクリアする。"""
        self.scene.clear()
        self.thumbnail_items.clear()
        self.clear_cache()
        self._explicit_path_items.clear()
        if self.pagination_nav:
            self.pagination_nav.setVisible(False)

    def _sync_dataset_state_from_result(self, thumbnail_result: Any) -> None:
        """thumbnail_result の画像メタデータを DatasetStateManager に同期する。"""
        if (
            self.dataset_state
            and hasattr(thumbnail_result, "image_metadata")
            and thumbnail_result.image_metadata
        ):
            self.dataset_state.update_from_search_results(thumbnail_result.image_metadata)
            logger.debug("検索結果をDatasetStateManagerに同期完了")

    def _pixmaps_from_result(self, thumbnail_result: Any) -> list[tuple[int, QPixmap]]:
        """ThumbnailLoadResultのQImageリストをページキャッシュ用QPixmapリストへ変換する。

        Args:
            thumbnail_result: ThumbnailLoadResultオブジェクト。

        Returns:
            (image_id, QPixmap) のリスト。
        """
        pixmaps: list[tuple[int, QPixmap]] = []
        for image_id, qimage in thumbnail_result.loaded_thumbnails:
            try:
                qpixmap = QPixmap.fromImage(qimage)
            except Exception as e:
                logger.error(f"QImage→QPixmap変換エラー image_id={image_id}: {e}")
                continue

            if qpixmap.isNull():
                logger.warning(f"QPixmap変換失敗: image_id={image_id}")
                continue

            pixmaps.append((image_id, qpixmap))
        return pixmaps

    def load_thumbnails_from_result(self, thumbnail_result: Any) -> None:
        """
        ページ情報を持たないThumbnailLoadResultを1ページ表示としてロードする。

        通常の検索結果表示は initialize_pagination_search() と handle_thumbnail_page_result()
        を使う。このメソッドはページ情報なしの既存呼び出しを page cache 経路に寄せる。

        Args:
            thumbnail_result: ThumbnailLoadResultオブジェクト
                loaded_thumbnails: list[(image_id, QImage)] - プリロード済み画像データ
                image_metadata: list[dict[str, Any]] - 画像メタデータリスト
                failed_count: int - 読み込み失敗数
                total_count: int - 処理対象総数
        """
        logger.info(f"サムネイル表示開始: {len(thumbnail_result.loaded_thumbnails)}件")

        self._reset_thumbnail_display()

        if not thumbnail_result.loaded_thumbnails:
            logger.info("表示する画像がありません")
            self._update_image_count_display()
            if hasattr(self, "graphics_view"):
                self.graphics_view.viewport().update()
            return

        self._sync_dataset_state_from_result(thumbnail_result)
        if self.dataset_state:
            self._ensure_pagination_state()

        pixmaps = self._pixmaps_from_result(thumbnail_result)
        self.page_cache.set_page(1, pixmaps)
        self._current_display_page = 1
        self._display_page(1)
        self._update_image_count_display()
        if hasattr(self, "graphics_view"):
            self.graphics_view.viewport().update()

        logger.info(
            f"サムネイル表示完了: {len(pixmaps)}件表示, page_cache={self.page_cache.cache_size}ページ"
        )

        # 選択状態はThumbnailItem.isSelected()で動的取得

    def load_thumbnails_from_paths(self, items: list[tuple[str, int]]) -> None:
        """
        ファイルパスとIDの一覧からサムネイルをロードする（stagingなど小規模表示用）。

        Args:
            items: [(stored_path, image_id), ...]
        """
        self.scene.clear()
        self.thumbnail_items.clear()
        self.clear_cache()
        self._explicit_path_items.clear()
        self._active_search_result = None
        if self.pagination_nav:
            self.pagination_nav.setVisible(False)

        for path_str, image_id in items:
            path = Path(path_str) if path_str else Path()
            self._explicit_path_items.append((path, image_id))

        self._display_explicit_path_items()
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

        GraphicsSceneとthumbnail_items、およびページキャッシュを完全にクリアし、
        新しい検索結果受信に備える。
        """
        self.scene.clear()
        self.thumbnail_items.clear()
        self._explicit_path_items.clear()
        self._current_display_page = 1

        # 新しいキャッシュもクリア（メモリ効率化）
        self.clear_cache()
        self._hide_loading_overlay()
        self._active_search_result = None
        if self.pagination_nav:
            self.pagination_nav.setVisible(False)

        logger.debug("サムネイル表示とキャッシュをクリアしました")

    # === UI Event Handlers ===

    def resizeEvent(self, event: QResizeEvent) -> None:
        """
        ウィジェットがリサイズされたときにタイマーをリセット
        """
        super().resizeEvent(event)
        if self.loading_overlay.isVisible():
            self.loading_overlay.setGeometry(self.graphics_view.viewport().rect())
        self.resize_timer.start(250)

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
        現在表示中サムネイルのグリッドレイアウトを更新する。

        **呼び出し箇所**:
        - QTimer.timeout Signal (thumbnail.py:183) - リサイズ遅延実行
        - _on_thumbnail_size_changed (thumbnail.py:296) - サムネイルサイズ変更時
        - _on_images_filtered (thumbnail.py:260) - 少量データフィルタ結果表示時
        検索結果はページキャッシュから再表示する。staging等の明示パス表示は
        小規模用途として private な明示パスリストから再構築する。
        """
        if self.pagination_state and self.page_cache.has_page(self._current_display_page):
            logger.debug(f"ページキャッシュからレイアウト更新: page={self._current_display_page}")
            self._display_page(self._current_display_page)
        elif self._explicit_path_items:
            self._display_explicit_path_items()

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
    widget.load_thumbnails_from_paths([(str(path), i) for i, path in enumerate(image_paths)])
    widget.setMinimumSize(400, 300)  # ウィジェットの最小サイズを設定
    widget.show()
    sys.exit(app.exec())
