# tests/unit/gui/state/test_pagination_state.py
"""PaginationStateManager のユニットテスト"""

from unittest.mock import MagicMock, PropertyMock

import pytest

from lorairo.gui.state.pagination_state import PaginationStateManager


@pytest.fixture
def mock_dataset_state():
    """DatasetStateManager のモック"""
    mock = MagicMock()
    # images_filtered シグナルをモック
    mock.images_filtered = MagicMock()
    mock.images_filtered.connect = MagicMock()
    return mock


@pytest.fixture
def sample_images():
    """テスト用の画像メタデータリスト（250件）"""
    return [{"id": i, "filename": f"image_{i}.png"} for i in range(1, 251)]


@pytest.fixture
def pagination_state(mock_dataset_state, sample_images):
    """PaginationStateManager インスタンス"""
    # filtered_images プロパティをモック
    type(mock_dataset_state).filtered_images = PropertyMock(return_value=sample_images)
    return PaginationStateManager(mock_dataset_state, page_size=100, max_cached_pages=5)


class TestPaginationStateManagerInit:
    """初期化テスト"""

    def test_init_default_values(self, mock_dataset_state, sample_images):
        """デフォルト値で初期化できる"""
        type(mock_dataset_state).filtered_images = PropertyMock(return_value=sample_images)
        state = PaginationStateManager(mock_dataset_state)

        assert state.current_page == 1
        assert state.page_size == 100
        assert state.max_cached_pages == 5

    def test_init_custom_values(self, mock_dataset_state, sample_images):
        """カスタム値で初期化できる"""
        type(mock_dataset_state).filtered_images = PropertyMock(return_value=sample_images)
        state = PaginationStateManager(
            mock_dataset_state, page_size=50, max_cached_pages=3
        )

        assert state.page_size == 50
        assert state.max_cached_pages == 3

    def test_connects_to_images_filtered_signal(self, mock_dataset_state, sample_images):
        """images_filtered シグナルに接続する"""
        type(mock_dataset_state).filtered_images = PropertyMock(return_value=sample_images)
        PaginationStateManager(mock_dataset_state)

        mock_dataset_state.images_filtered.connect.assert_called_once()


class TestPaginationStateManagerProperties:
    """プロパティテスト"""

    def test_total_items(self, pagination_state):
        """total_items が正しく計算される"""
        assert pagination_state.total_items == 250

    def test_total_pages(self, pagination_state):
        """total_pages が正しく計算される（250件 / 100件 = 3ページ）"""
        assert pagination_state.total_pages == 3

    def test_total_pages_empty(self, mock_dataset_state):
        """0件の場合は1ページ"""
        type(mock_dataset_state).filtered_images = PropertyMock(return_value=[])
        state = PaginationStateManager(mock_dataset_state)

        assert state.total_pages == 1

    def test_total_pages_exact_division(self, mock_dataset_state):
        """ちょうど割り切れる場合（200件 / 100件 = 2ページ）"""
        images = [{"id": i} for i in range(1, 201)]
        type(mock_dataset_state).filtered_images = PropertyMock(return_value=images)
        state = PaginationStateManager(mock_dataset_state, page_size=100)

        assert state.total_pages == 2


class TestSetPage:
    """set_page テスト"""

    def test_set_page_success(self, pagination_state):
        """ページを正常に設定できる"""
        result = pagination_state.set_page(2)

        assert result is True
        assert pagination_state.current_page == 2

    def test_set_page_same_page(self, pagination_state):
        """同じページを設定した場合は False"""
        result = pagination_state.set_page(1)

        assert result is False
        assert pagination_state.current_page == 1

    def test_set_page_clamp_to_max(self, pagination_state):
        """最大ページを超えた場合はクランプされる"""
        result = pagination_state.set_page(100)  # 実際は3ページまで

        assert result is True
        assert pagination_state.current_page == 3

    def test_set_page_clamp_to_min(self, pagination_state):
        """0以下の場合は1にクランプされる"""
        pagination_state.set_page(2)  # まず2ページに移動
        result = pagination_state.set_page(0)

        assert result is True
        assert pagination_state.current_page == 1

    def test_set_page_emits_signal(self, pagination_state, qtbot):
        """ページ変更時にシグナルが発行される"""
        with qtbot.waitSignal(pagination_state.page_changed, timeout=1000) as blocker:
            pagination_state.set_page(2)

        assert blocker.args == [2]


class TestResetToFirstPage:
    """reset_to_first_page テスト"""

    def test_reset_from_other_page(self, pagination_state, qtbot):
        """他のページから1ページ目にリセットできる"""
        pagination_state.set_page(3)

        with qtbot.waitSignal(pagination_state.page_changed, timeout=1000) as blocker:
            pagination_state.reset_to_first_page()

        assert pagination_state.current_page == 1
        assert blocker.args == [1]

    def test_reset_from_first_page(self, pagination_state, qtbot):
        """既に1ページ目の場合はシグナルを発行しない"""
        with qtbot.assertNotEmitted(pagination_state.page_changed):
            pagination_state.reset_to_first_page()


class TestGetPageImageIds:
    """get_page_image_ids テスト"""

    def test_get_first_page(self, pagination_state):
        """最初のページの画像IDを取得できる"""
        ids = pagination_state.get_page_image_ids(1)

        assert len(ids) == 100
        assert ids[0] == 1
        assert ids[-1] == 100

    def test_get_middle_page(self, pagination_state):
        """中間ページの画像IDを取得できる"""
        ids = pagination_state.get_page_image_ids(2)

        assert len(ids) == 100
        assert ids[0] == 101
        assert ids[-1] == 200

    def test_get_last_page_partial(self, pagination_state):
        """最後のページ（端数）の画像IDを取得できる"""
        ids = pagination_state.get_page_image_ids(3)

        assert len(ids) == 50  # 250 - 200 = 50件
        assert ids[0] == 201
        assert ids[-1] == 250

    def test_get_invalid_page(self, pagination_state):
        """無効なページ番号は空リストを返す"""
        assert pagination_state.get_page_image_ids(0) == []
        assert pagination_state.get_page_image_ids(100) == []


class TestGetPrefetchPages:
    """get_prefetch_pages テスト（前後均等方式）"""

    def test_prefetch_middle_page(self, pagination_state):
        """中間ページの場合は前後均等に取得"""
        # page=2, max_cached_pages=5 → [1, 2, 3] (total=3なので)
        # でも total=3 なので実際は [1, 2, 3]
        pages = pagination_state.get_prefetch_pages(2)

        # 3ページしかないので [1, 2, 3]
        assert pages == [1, 2, 3]

    def test_prefetch_first_page(self, pagination_state):
        """最初のページの場合は先頭から5ページ（または全ページ）"""
        pages = pagination_state.get_prefetch_pages(1)

        # 3ページしかないので [1, 2, 3]
        assert pages == [1, 2, 3]

    def test_prefetch_last_page(self, pagination_state):
        """最後のページの場合は末尾から5ページ（または全ページ）"""
        pages = pagination_state.get_prefetch_pages(3)

        assert pages == [1, 2, 3]

    def test_prefetch_with_many_pages(self, mock_dataset_state):
        """多くのページがある場合のプリフェッチ"""
        # 1000件 = 10ページ
        images = [{"id": i} for i in range(1, 1001)]
        type(mock_dataset_state).filtered_images = PropertyMock(return_value=images)
        state = PaginationStateManager(mock_dataset_state, page_size=100, max_cached_pages=5)

        # page=5 → [3, 4, 5, 6, 7]
        pages = state.get_prefetch_pages(5)
        assert pages == [3, 4, 5, 6, 7]

        # page=1 → [1, 2, 3, 4, 5]
        pages = state.get_prefetch_pages(1)
        assert pages == [1, 2, 3, 4, 5]

        # page=10 → [6, 7, 8, 9, 10]
        pages = state.get_prefetch_pages(10)
        assert pages == [6, 7, 8, 9, 10]

    def test_prefetch_default_current_page(self, pagination_state):
        """引数なしの場合は current_page を使用"""
        pagination_state.set_page(2)
        pages = pagination_state.get_prefetch_pages()

        assert 2 in pages


class TestGetPagesToLoad:
    """get_pages_to_load テスト"""

    def test_all_pages_need_loading(self, pagination_state):
        """全ページが読み込み必要な場合"""
        pages = pagination_state.get_pages_to_load(2, cached_pages=set())

        # ターゲットページが先頭
        assert pages[0] == 2
        assert set(pages) == {1, 2, 3}

    def test_some_pages_cached(self, pagination_state):
        """一部がキャッシュ済みの場合"""
        pages = pagination_state.get_pages_to_load(2, cached_pages={1, 3})

        # ページ2のみ読み込み必要
        assert pages == [2]

    def test_all_pages_cached(self, pagination_state):
        """全ページがキャッシュ済みの場合"""
        pages = pagination_state.get_pages_to_load(2, cached_pages={1, 2, 3})

        assert pages == []

    def test_target_page_prioritized(self, mock_dataset_state):
        """ターゲットページが先頭に来る"""
        images = [{"id": i} for i in range(1, 1001)]
        type(mock_dataset_state).filtered_images = PropertyMock(return_value=images)
        state = PaginationStateManager(mock_dataset_state, page_size=100, max_cached_pages=5)

        pages = state.get_pages_to_load(5, cached_pages={3, 4})

        # ターゲットページ5が先頭
        assert pages[0] == 5
        # 残りは6, 7
        assert set(pages) == {5, 6, 7}


class TestImagesFilteredHandler:
    """images_filtered シグナルハンドラのテスト"""

    def test_resets_to_first_page_on_filter(self, pagination_state, qtbot):
        """フィルタ変更時に1ページ目にリセットされる"""
        pagination_state.set_page(3)

        with qtbot.waitSignal(pagination_state.page_changed, timeout=1000):
            # images_filtered シグナルをシミュレート
            pagination_state._on_images_filtered([])

        assert pagination_state.current_page == 1
