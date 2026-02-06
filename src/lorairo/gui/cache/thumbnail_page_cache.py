# src/lorairo/gui/cache/thumbnail_page_cache.py
"""
ページ単位のサムネイルキャッシュ。

LRUアルゴリズムでページを管理し、最大ページ数を超えた場合は
最も古いページを自動的に削除する。
"""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING

from ...utils.log import logger

if TYPE_CHECKING:
    from PySide6.QtGui import QPixmap


class ThumbnailPageCache:
    """
    ページ単位のサムネイルLRUキャッシュ。

    各ページは (image_id, QPixmap) のタプルリストとして保存される。
    最大ページ数を超えた場合、最も長くアクセスされていないページを削除する。

    Attributes:
        max_pages: キャッシュする最大ページ数
    """

    def __init__(self, max_pages: int = 5):
        """
        ThumbnailPageCache を初期化する。

        Args:
            max_pages: キャッシュする最大ページ数（デフォルト: 5）
        """
        self._max_pages = max_pages
        # OrderedDict で LRU を実現（最後にアクセスしたものが末尾）
        self._cache: OrderedDict[int, list[tuple[int, QPixmap]]] = OrderedDict()

        logger.debug(f"ThumbnailPageCache initialized: max_pages={max_pages}")

    @property
    def max_pages(self) -> int:
        """キャッシュする最大ページ数"""
        return self._max_pages

    @property
    def cached_pages(self) -> set[int]:
        """キャッシュ済みページ番号のセット"""
        return set(self._cache.keys())

    @property
    def cache_size(self) -> int:
        """キャッシュされているページ数"""
        return len(self._cache)

    def get_page(self, page_num: int) -> list[tuple[int, QPixmap]] | None:
        """
        指定ページのサムネイルを取得する。

        取得時にLRU順序を更新する（最近使用としてマーク）。

        Args:
            page_num: ページ番号

        Returns:
            (image_id, QPixmap) のタプルリスト、キャッシュミスの場合は None
        """
        if page_num not in self._cache:
            logger.debug(f"Cache miss: page {page_num}")
            return None

        # LRU更新: 末尾に移動
        self._cache.move_to_end(page_num)
        logger.debug(f"Cache hit: page {page_num}")
        return self._cache[page_num]

    def set_page(self, page_num: int, thumbnails: list[tuple[int, QPixmap]]) -> None:
        """
        ページのサムネイルをキャッシュに保存する。

        最大ページ数を超えた場合、最も古いページを自動的に削除する。

        Args:
            page_num: ページ番号
            thumbnails: (image_id, QPixmap) のタプルリスト
        """
        # 既存エントリの場合は更新してLRU順序も更新
        if page_num in self._cache:
            self._cache[page_num] = thumbnails
            self._cache.move_to_end(page_num)
            logger.debug(f"Cache updated: page {page_num}, {len(thumbnails)} thumbnails")
            return

        # 容量オーバーの場合、最も古いページを削除
        if len(self._cache) >= self._max_pages:
            evicted_page, evicted_data = self._cache.popitem(last=False)
            logger.debug(
                f"Cache evicted: page {evicted_page} ({len(evicted_data)} thumbnails)"
            )

        # 新規エントリを追加
        self._cache[page_num] = thumbnails
        logger.debug(f"Cache set: page {page_num}, {len(thumbnails)} thumbnails")

    def has_page(self, page_num: int) -> bool:
        """
        指定ページがキャッシュされているか確認する。

        この操作はLRU順序を更新しない（peek操作）。

        Args:
            page_num: ページ番号

        Returns:
            キャッシュされている場合は True
        """
        return page_num in self._cache

    def remove_page(self, page_num: int) -> bool:
        """
        指定ページをキャッシュから削除する。

        Args:
            page_num: ページ番号

        Returns:
            削除した場合は True、存在しなかった場合は False
        """
        if page_num in self._cache:
            del self._cache[page_num]
            logger.debug(f"Cache removed: page {page_num}")
            return True
        return False

    def clear(self) -> None:
        """
        キャッシュを全てクリアする。
        """
        page_count = len(self._cache)
        self._cache.clear()
        logger.debug(f"Cache cleared: {page_count} pages removed")

    def get_thumbnail_by_id(self, image_id: int) -> QPixmap | None:
        """
        画像IDからサムネイルを検索する。

        全ページを検索するため、頻繁な呼び出しには向かない。
        この操作はLRU順序を更新しない。

        Args:
            image_id: 画像ID

        Returns:
            QPixmap、見つからない場合は None
        """
        for thumbnails in self._cache.values():
            for tid, pixmap in thumbnails:
                if tid == image_id:
                    return pixmap
        return None

    def get_stats(self) -> dict[str, int | list[int]]:
        """
        キャッシュの統計情報を取得する。

        Returns:
            統計情報の辞書
        """
        total_thumbnails = sum(len(page) for page in self._cache.values())
        return {
            "cached_pages": len(self._cache),
            "max_pages": self._max_pages,
            "total_thumbnails": total_thumbnails,
            "pages": list(self._cache.keys()),
        }
