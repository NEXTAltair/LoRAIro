# tests/unit/gui/cache/test_thumbnail_page_cache.py
"""ThumbnailPageCache のユニットテスト"""

from unittest.mock import MagicMock

import pytest

from lorairo.gui.cache.thumbnail_page_cache import ThumbnailPageCache


@pytest.fixture
def cache():
    """ThumbnailPageCache インスタンス（max_pages=3）"""
    return ThumbnailPageCache(max_pages=3)


@pytest.fixture
def mock_pixmap():
    """QPixmap のモック"""
    return MagicMock()


def make_thumbnails(start_id: int, count: int) -> list[tuple[int, MagicMock]]:
    """テスト用サムネイルリストを生成"""
    return [(start_id + i, MagicMock()) for i in range(count)]


class TestThumbnailPageCacheInit:
    """初期化テスト"""

    def test_init_default(self):
        """デフォルト値で初期化できる"""
        cache = ThumbnailPageCache()

        assert cache.max_pages == 5
        assert cache.cache_size == 0

    def test_init_custom(self):
        """カスタム値で初期化できる"""
        cache = ThumbnailPageCache(max_pages=10)

        assert cache.max_pages == 10


class TestSetPage:
    """set_page テスト"""

    def test_set_page_basic(self, cache):
        """ページを保存できる"""
        thumbnails = make_thumbnails(1, 100)
        cache.set_page(1, thumbnails)

        assert cache.has_page(1)
        assert cache.cache_size == 1

    def test_set_multiple_pages(self, cache):
        """複数ページを保存できる"""
        cache.set_page(1, make_thumbnails(1, 100))
        cache.set_page(2, make_thumbnails(101, 100))
        cache.set_page(3, make_thumbnails(201, 100))

        assert cache.cache_size == 3
        assert cache.cached_pages == {1, 2, 3}

    def test_set_page_evicts_oldest(self, cache):
        """最大数を超えると最も古いページが削除される"""
        cache.set_page(1, make_thumbnails(1, 100))
        cache.set_page(2, make_thumbnails(101, 100))
        cache.set_page(3, make_thumbnails(201, 100))
        cache.set_page(4, make_thumbnails(301, 100))  # page 1 が削除される

        assert cache.cache_size == 3
        assert not cache.has_page(1)
        assert cache.cached_pages == {2, 3, 4}

    def test_set_page_update_existing(self, cache):
        """既存ページを更新できる"""
        old_thumbnails = make_thumbnails(1, 50)
        new_thumbnails = make_thumbnails(1, 100)

        cache.set_page(1, old_thumbnails)
        cache.set_page(1, new_thumbnails)

        assert cache.cache_size == 1
        result = cache.get_page(1)
        assert len(result) == 100


class TestGetPage:
    """get_page テスト"""

    def test_get_page_hit(self, cache):
        """キャッシュヒット時にデータを返す"""
        thumbnails = make_thumbnails(1, 100)
        cache.set_page(1, thumbnails)

        result = cache.get_page(1)

        assert result == thumbnails

    def test_get_page_miss(self, cache):
        """キャッシュミス時に None を返す"""
        result = cache.get_page(1)

        assert result is None

    def test_get_page_updates_lru_order(self, cache):
        """get_page がLRU順序を更新する"""
        cache.set_page(1, make_thumbnails(1, 100))
        cache.set_page(2, make_thumbnails(101, 100))
        cache.set_page(3, make_thumbnails(201, 100))

        # page 1 にアクセス（最新になる）
        cache.get_page(1)

        # page 4 を追加すると page 2 が削除される（1は最新なので残る）
        cache.set_page(4, make_thumbnails(301, 100))

        assert cache.has_page(1)  # 最近アクセスしたので残る
        assert not cache.has_page(2)  # 最も古いので削除
        assert cache.has_page(3)
        assert cache.has_page(4)


class TestHasPage:
    """has_page テスト"""

    def test_has_page_true(self, cache):
        """存在するページは True"""
        cache.set_page(1, make_thumbnails(1, 100))

        assert cache.has_page(1) is True

    def test_has_page_false(self, cache):
        """存在しないページは False"""
        assert cache.has_page(1) is False

    def test_has_page_does_not_update_lru(self, cache):
        """has_page はLRU順序を更新しない"""
        cache.set_page(1, make_thumbnails(1, 100))
        cache.set_page(2, make_thumbnails(101, 100))
        cache.set_page(3, make_thumbnails(201, 100))

        # has_page で確認（LRU更新なし）
        cache.has_page(1)

        # page 4 を追加すると page 1 が削除される
        cache.set_page(4, make_thumbnails(301, 100))

        assert not cache.has_page(1)  # has_page はLRU更新しないので削除される


class TestRemovePage:
    """remove_page テスト"""

    def test_remove_existing_page(self, cache):
        """存在するページを削除できる"""
        cache.set_page(1, make_thumbnails(1, 100))

        result = cache.remove_page(1)

        assert result is True
        assert not cache.has_page(1)

    def test_remove_nonexistent_page(self, cache):
        """存在しないページの削除は False"""
        result = cache.remove_page(1)

        assert result is False


class TestClear:
    """clear テスト"""

    def test_clear_removes_all(self, cache):
        """全ページを削除できる"""
        cache.set_page(1, make_thumbnails(1, 100))
        cache.set_page(2, make_thumbnails(101, 100))

        cache.clear()

        assert cache.cache_size == 0
        assert cache.cached_pages == set()


class TestGetThumbnailById:
    """get_thumbnail_by_id テスト"""

    def test_find_thumbnail_in_page(self, cache, mock_pixmap):
        """ページ内のサムネイルを検索できる"""
        thumbnails = [(1, mock_pixmap), (2, MagicMock()), (3, MagicMock())]
        cache.set_page(1, thumbnails)

        result = cache.get_thumbnail_by_id(1)

        assert result == mock_pixmap

    def test_find_thumbnail_across_pages(self, cache, mock_pixmap):
        """複数ページにまたがって検索できる"""
        cache.set_page(1, [(1, MagicMock()), (2, MagicMock())])
        cache.set_page(2, [(3, mock_pixmap), (4, MagicMock())])

        result = cache.get_thumbnail_by_id(3)

        assert result == mock_pixmap

    def test_thumbnail_not_found(self, cache):
        """見つからない場合は None"""
        cache.set_page(1, [(1, MagicMock()), (2, MagicMock())])

        result = cache.get_thumbnail_by_id(999)

        assert result is None


class TestGetStats:
    """get_stats テスト"""

    def test_stats_empty(self, cache):
        """空キャッシュの統計"""
        stats = cache.get_stats()

        assert stats["cached_pages"] == 0
        assert stats["max_pages"] == 3
        assert stats["total_thumbnails"] == 0
        assert stats["pages"] == []

    def test_stats_with_data(self, cache):
        """データがある場合の統計"""
        cache.set_page(1, make_thumbnails(1, 50))
        cache.set_page(2, make_thumbnails(51, 100))

        stats = cache.get_stats()

        assert stats["cached_pages"] == 2
        assert stats["total_thumbnails"] == 150
        assert set(stats["pages"]) == {1, 2}


class TestCachedPagesProperty:
    """cached_pages プロパティテスト"""

    def test_cached_pages_returns_set(self, cache):
        """キャッシュ済みページ番号のセットを返す"""
        cache.set_page(1, make_thumbnails(1, 100))
        cache.set_page(3, make_thumbnails(201, 100))
        cache.set_page(5, make_thumbnails(401, 100))

        assert cache.cached_pages == {1, 3, 5}
