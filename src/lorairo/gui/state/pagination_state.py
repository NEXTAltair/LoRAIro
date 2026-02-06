# src/lorairo/gui/state/pagination_state.py
"""
ページネーション状態を管理するクラス。

サムネイル表示のページング状態（現在ページ、ページサイズ、総ページ数）を
Single Source of Truth (SoT) として管理する。
画像IDの取得は DatasetStateManager を参照する（SoT原則）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QObject, Signal

from ...utils.log import logger

if TYPE_CHECKING:
    from .dataset_state import DatasetStateManager


class PaginationStateManager(QObject):
    """
    ページネーション状態を管理するクラス。

    DatasetStateManager を参照して画像IDを取得し、
    ページ計算とプリフェッチページの決定を行う。

    Attributes:
        page_changed: ページが変更されたときに発行（新しいページ番号）
        loading_started: ページ読み込み開始時に発行（ページ番号）
        loading_completed: ページ読み込み完了時に発行（ページ番号, 画像IDリスト）
    """

    # === シグナル ===
    page_changed = Signal(int)  # new_page
    loading_started = Signal(int)  # page_num
    loading_completed = Signal(int, list)  # page_num, image_ids

    # === 定数 ===
    DEFAULT_PAGE_SIZE = 100
    DEFAULT_MAX_CACHED_PAGES = 5

    def __init__(
        self,
        dataset_state: DatasetStateManager,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_cached_pages: int = DEFAULT_MAX_CACHED_PAGES,
        parent: QObject | None = None,
    ):
        """
        PaginationStateManager を初期化する。

        Args:
            dataset_state: DatasetStateManager インスタンス（SoT参照用）
            page_size: 1ページあたりの表示件数（デフォルト: 100）
            max_cached_pages: キャッシュする最大ページ数（デフォルト: 5）
            parent: 親QObject
        """
        super().__init__(parent)

        self._dataset_state = dataset_state
        self._page_size = page_size
        self._max_cached_pages = max_cached_pages
        self._current_page = 1

        # DatasetStateManager のフィルタ変更を監視
        self._dataset_state.images_filtered.connect(self._on_images_filtered)

        logger.debug(
            f"PaginationStateManager initialized: page_size={page_size}, "
            f"max_cached_pages={max_cached_pages}"
        )

    # === Public Properties ===

    @property
    def current_page(self) -> int:
        """現在のページ番号（1始まり）"""
        return self._current_page

    @property
    def page_size(self) -> int:
        """1ページあたりの表示件数"""
        return self._page_size

    @property
    def max_cached_pages(self) -> int:
        """キャッシュする最大ページ数"""
        return self._max_cached_pages

    @property
    def total_items(self) -> int:
        """検索結果の総件数"""
        return len(self._dataset_state.filtered_images)

    @property
    def total_pages(self) -> int:
        """総ページ数（0件の場合は1）"""
        if self.total_items == 0:
            return 1
        return (self.total_items + self._page_size - 1) // self._page_size

    # === Public Methods ===

    def set_page(self, page: int) -> bool:
        """
        現在のページを設定する。

        Args:
            page: 設定するページ番号（1始まり）

        Returns:
            ページが変更された場合は True
        """
        # 範囲チェック
        clamped_page = max(1, min(page, self.total_pages))

        if clamped_page == self._current_page:
            return False

        old_page = self._current_page
        self._current_page = clamped_page
        logger.debug(f"Page changed: {old_page} -> {self._current_page}")
        self.page_changed.emit(self._current_page)
        return True

    def reset_to_first_page(self) -> None:
        """
        最初のページにリセットする。

        検索結果が更新された場合などに呼び出す。
        """
        if self._current_page != 1:
            self._current_page = 1
            logger.debug("Page reset to 1")
            self.page_changed.emit(1)

    def get_page_image_ids(self, page: int) -> list[int]:
        """
        指定ページの画像IDリストを取得する。

        Args:
            page: ページ番号（1始まり）

        Returns:
            画像IDのリスト
        """
        if page < 1 or page > self.total_pages:
            return []

        start_idx = (page - 1) * self._page_size
        end_idx = start_idx + self._page_size

        # DatasetStateManager から filtered_images を取得
        filtered_images = self._dataset_state.filtered_images
        page_images = filtered_images[start_idx:end_idx]

        image_ids: list[int] = []
        for image in page_images:
            image_id = image.get("id")
            if isinstance(image_id, int):
                image_ids.append(image_id)
        return image_ids

    def get_prefetch_pages(self, page: int | None = None) -> list[int]:
        """
        プリフェッチすべきページ番号リストを取得する（前後均等方式）。

        現在ページを中心に、最大 max_cached_pages ページを返す。
        例: page=3, max=5 → [1, 2, 3, 4, 5]
        例: page=1, max=5 → [1, 2, 3, 4, 5]
        例: page=183, max=5, total=183 → [179, 180, 181, 182, 183]

        Args:
            page: 中心となるページ番号（None の場合は current_page）

        Returns:
            プリフェッチすべきページ番号のリスト（昇順）
        """
        if page is None:
            page = self._current_page

        total = self.total_pages

        # 前後に何ページ取るか（max_cached_pages=5 なら前後2ページずつ）
        half = (self._max_cached_pages - 1) // 2

        # 理想的な範囲
        ideal_start = page - half
        ideal_end = page + half

        # 境界調整
        if ideal_start < 1:
            # 先頭に寄せる
            start = 1
            end = min(self._max_cached_pages, total)
        elif ideal_end > total:
            # 末尾に寄せる
            end = total
            start = max(1, total - self._max_cached_pages + 1)
        else:
            start = ideal_start
            end = ideal_end

        return list(range(start, end + 1))

    def get_pages_to_load(self, target_page: int, cached_pages: set[int]) -> list[int]:
        """
        読み込みが必要なページを特定する。

        プリフェッチ対象ページのうち、キャッシュにないものを返す。
        ターゲットページを優先的に先頭に配置する。

        Args:
            target_page: 表示対象のページ
            cached_pages: キャッシュ済みページ番号のセット

        Returns:
            読み込みが必要なページ番号のリスト（ターゲットページ優先）
        """
        prefetch_pages = self.get_prefetch_pages(target_page)
        pages_to_load = [p for p in prefetch_pages if p not in cached_pages]

        # ターゲットページを先頭に移動
        if target_page in pages_to_load:
            pages_to_load.remove(target_page)
            pages_to_load.insert(0, target_page)

        return pages_to_load

    # === Private Methods ===

    def _on_images_filtered(self, _filtered_images: list[Any]) -> None:
        """
        DatasetStateManager の検索結果が更新されたときの処理。

        最初のページにリセットする。
        """
        logger.debug(f"Images filtered, total: {len(_filtered_images)}, resetting to page 1")
        self.reset_to_first_page()
