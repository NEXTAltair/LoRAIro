"""
StagingWidget Unit Tests

StagingWidget コンポーネントの包括的テストスイート。

Test Coverage:
- 初期化・セットアップ
- add_image_ids / add_selected_images による追加
- 重複排除・順序保持
- MAX_STAGING_IMAGES (500枚) 上限の強制
- clear による全削除
- count / get_image_ids / get_staged_items アクセサ
- staged_images_changed / staging_cleared シグナル
- DatasetStateManager 未設定時のエラーハンドリング

Target: 80%+ coverage
"""

import pytest

from lorairo.gui.state.dataset_state import DatasetStateManager
from lorairo.gui.widgets.staging_widget import StagingWidget


class TestStagingWidgetInitialization:
    """初期化・セットアップテスト"""

    @pytest.mark.gui
    def test_initialization(self, qtbot):
        """ウィジェットが正しく初期化されること"""
        widget = StagingWidget()
        qtbot.addWidget(widget)

        assert widget is not None
        assert hasattr(widget, "ui")
        assert widget.count() == 0
        assert widget.get_image_ids() == []
        assert widget._dataset_state_manager is None

    @pytest.mark.gui
    def test_staging_thumbnail_uses_content_height(self, qtbot):
        """#1097: staging のサムネ枠はコンテンツ準拠高さ (最大3行) を有効化する。"""
        widget = StagingWidget()
        qtbot.addWidget(widget)

        thumb = widget._staging_thumbnail_widget
        assert thumb is not None
        assert thumb._content_height_enabled is True
        assert thumb._content_height_max_rows == 3
        # 旧実装の固定 150px 下限は撤廃され 1 行相当まで縮む
        assert thumb.minimumHeight() < 150

    @pytest.mark.gui
    def test_ui_components_present(self, qtbot):
        """UI コンポーネントが存在すること"""
        widget = StagingWidget()
        qtbot.addWidget(widget)

        assert hasattr(widget.ui, "labelStagingCount")
        assert hasattr(widget.ui, "pushButtonClearStaging")
        assert hasattr(widget.ui, "listWidgetStaging")
        assert hasattr(widget.ui, "groupBoxStagingList")

    @pytest.mark.gui
    def test_initial_staging_count_label(self, qtbot):
        """初期カウントラベルが 0 / 500 枚を表示すること"""
        widget = StagingWidget()
        qtbot.addWidget(widget)

        expected_text = f"0 / {widget.MAX_STAGING_IMAGES} 枚"
        assert widget.ui.labelStagingCount.text() == expected_text

    @pytest.mark.gui
    def test_max_staging_images_constant(self, qtbot):
        """MAX_STAGING_IMAGES が 500 であること"""
        widget = StagingWidget()
        qtbot.addWidget(widget)

        assert widget.MAX_STAGING_IMAGES == 500

    def test_exact_set_max_matches_staging_limit(self):
        """repo の exact-set 上限が GUI のステージング上限と一致すること (drift 防止, ADR 0056)。

        ImageRepository は Qt-free (ADR 0001) のため GUI 定数を import せず独自に
        EXACT_SET_MAX_IDS を持つ。両者の値が乖離すると exact-set エクスポートが
        ステージング上限と食い違うため、本 test で同値を保証する。
        """
        from lorairo.database.repository.image import ImageRepository

        assert ImageRepository.EXACT_SET_MAX_IDS == StagingWidget.MAX_STAGING_IMAGES


class TestDatasetStateManagerIntegration:
    """DatasetStateManager 統合テスト"""

    @pytest.mark.gui
    def test_set_dataset_state_manager(self, qtbot):
        """DatasetStateManager 参照が設定されること"""
        widget = StagingWidget()
        qtbot.addWidget(widget)

        state_manager = DatasetStateManager()
        widget.set_dataset_state_manager(state_manager)

        assert widget._dataset_state_manager is state_manager

    @pytest.mark.gui
    def test_add_image_ids_without_state_manager(self, qtbot):
        """DatasetStateManager 未設定時に add_image_ids が安全に終了すること"""
        widget = StagingWidget()
        qtbot.addWidget(widget)

        # DatasetStateManager 未設定で例外が発生しないこと
        widget.add_image_ids([1, 2, 3])

        assert widget.count() == 0

    @pytest.mark.gui
    def test_add_selected_images_without_state_manager(self, qtbot):
        """DatasetStateManager 未設定時に add_selected_images が安全に終了すること"""
        widget = StagingWidget()
        qtbot.addWidget(widget)

        widget.add_selected_images()

        assert widget.count() == 0

    @pytest.mark.gui
    def test_add_selected_images_with_empty_selection(self, qtbot):
        """選択画像が空の場合に add_selected_images が何もしないこと"""
        widget = StagingWidget()
        qtbot.addWidget(widget)

        state_manager = DatasetStateManager()
        widget.set_dataset_state_manager(state_manager)
        # selected_image_ids は空

        widget.add_selected_images()

        assert widget.count() == 0


class TestStagingListManagement:
    """ステージングリスト管理テスト"""

    @pytest.fixture
    def widget_with_state(self, qtbot):
        """DatasetStateManager 付きウィジェット"""
        widget = StagingWidget()
        qtbot.addWidget(widget)

        state_manager = DatasetStateManager()
        mock_images = [
            {"id": 1, "stored_image_path": "/path/to/image1.jpg"},
            {"id": 2, "stored_image_path": "/path/to/image2.jpg"},
            {"id": 3, "stored_image_path": "/path/to/image3.jpg"},
        ]
        state_manager._all_images = mock_images
        state_manager._selected_image_ids = [1, 2]

        widget.set_dataset_state_manager(state_manager)
        return widget, state_manager

    @pytest.mark.gui
    def test_add_image_ids_basic(self, qtbot, widget_with_state):
        """add_image_ids で画像が追加されること"""
        widget, _ = widget_with_state

        with qtbot.waitSignal(widget.staged_images_changed, timeout=1000) as blocker:
            widget.add_image_ids([1, 2])

        assert blocker.args == [[1, 2]]
        assert widget.count() == 2
        assert 1 in widget.get_image_ids()
        assert 2 in widget.get_image_ids()

    @pytest.mark.gui
    def test_add_selected_images(self, qtbot, widget_with_state):
        """add_selected_images で選択画像が追加されること"""
        widget, _ = widget_with_state

        with qtbot.waitSignal(widget.staged_images_changed, timeout=1000) as blocker:
            widget.add_selected_images()

        assert blocker.args == [[1, 2]]
        assert widget.count() == 2

    @pytest.mark.gui
    def test_deduplication(self, qtbot, widget_with_state):
        """同じ画像 ID が重複追加されないこと"""
        widget, _ = widget_with_state

        widget.add_image_ids([1, 2])
        assert widget.count() == 2

        # 同じ画像を再度追加
        widget.add_image_ids([1, 2])
        assert widget.count() == 2  # 重複なし

    @pytest.mark.gui
    def test_insertion_order_preserved(self, qtbot, widget_with_state):
        """追加順序が保持されること"""
        widget, _state_manager = widget_with_state

        widget.add_image_ids([1])
        widget.add_image_ids([3])
        widget.add_image_ids([2])

        assert widget.get_image_ids() == [1, 3, 2]

    @pytest.mark.gui
    def test_max_staging_images_limit(self, qtbot):
        """500枚上限が強制されること"""
        widget = StagingWidget()
        qtbot.addWidget(widget)

        state_manager = DatasetStateManager()
        # 550枚のモック画像
        mock_images = [{"id": i, "stored_image_path": f"/path/to/image{i}.jpg"} for i in range(1, 551)]
        state_manager._all_images = mock_images
        state_manager._selected_image_ids = list(range(1, 551))

        widget.set_dataset_state_manager(state_manager)

        with qtbot.waitSignal(widget.staged_images_changed, timeout=1000):
            widget.add_selected_images()

        assert widget.count() == widget.MAX_STAGING_IMAGES

    @pytest.mark.gui
    def test_clear_empties_staging(self, qtbot, widget_with_state):
        """clear() でステージングが空になること"""
        widget, _ = widget_with_state

        widget.add_image_ids([1, 2])
        assert widget.count() == 2

        with qtbot.waitSignal(widget.staging_cleared, timeout=1000):
            with qtbot.waitSignal(widget.staged_images_changed, timeout=1000) as blocker:
                widget.clear()

        assert blocker.args == [[]]
        assert widget.count() == 0

    @pytest.mark.gui
    def test_clear_button_triggers_clear(self, qtbot, widget_with_state):
        """クリアボタンクリックで clear() が呼ばれること"""
        widget, _ = widget_with_state

        widget.add_image_ids([1, 2])
        assert widget.count() == 2

        with qtbot.waitSignal(widget.staging_cleared, timeout=1000):
            widget.ui.pushButtonClearStaging.click()

        assert widget.count() == 0

    @pytest.mark.gui
    def test_remove_image_ids_removes_only_specified(self, qtbot, widget_with_state):
        """remove_image_ids が指定 ID のみ除外し、他を保持すること (Issue #571)"""
        widget, _ = widget_with_state
        widget.add_image_ids([1, 2, 3])
        assert widget.count() == 3

        with qtbot.waitSignal(widget.staged_images_changed, timeout=1000) as blocker:
            widget.remove_image_ids([1, 3])

        assert blocker.args == [[2]]
        assert widget.get_image_ids() == [2]

    @pytest.mark.gui
    def test_remove_image_ids_ignores_unknown_ids(self, qtbot, widget_with_state):
        """remove_image_ids が未登録 ID では何も変更せずシグナルも出さないこと"""
        widget, _ = widget_with_state
        widget.add_image_ids([1, 2])

        # 未登録 ID のみ指定したときは staged_images_changed を発行しない
        received: list[list[int]] = []
        widget.staged_images_changed.connect(received.append)
        widget.remove_image_ids([99])

        assert received == []
        assert widget.get_image_ids() == [1, 2]


class TestAccessors:
    """アクセサメソッドテスト"""

    @pytest.fixture
    def widget_with_images(self, qtbot):
        """画像追加済みウィジェット"""
        widget = StagingWidget()
        qtbot.addWidget(widget)

        state_manager = DatasetStateManager()
        mock_images = [
            {"id": 1, "stored_image_path": "/path/to/image1.jpg"},
            {"id": 2, "stored_image_path": "/path/to/image2.jpg"},
        ]
        state_manager._all_images = mock_images

        widget.set_dataset_state_manager(state_manager)
        widget.add_image_ids([1, 2])
        return widget

    @pytest.mark.gui
    def test_count_returns_correct_count(self, qtbot, widget_with_images):
        """count() が正しい枚数を返すこと"""
        widget = widget_with_images
        assert widget.count() == 2

    @pytest.mark.gui
    def test_get_image_ids_returns_list(self, qtbot, widget_with_images):
        """get_image_ids() が追加順の ID リストを返すこと"""
        widget = widget_with_images
        assert widget.get_image_ids() == [1, 2]

    @pytest.mark.gui
    def test_get_staged_items_returns_ordered_dict(self, qtbot, widget_with_images):
        """get_staged_items() が OrderedDict を返すこと"""
        from collections import OrderedDict

        widget = widget_with_images
        items = widget.get_staged_items()

        assert isinstance(items, OrderedDict)
        assert list(items.keys()) == [1, 2]

    @pytest.mark.gui
    def test_get_staged_items_contains_metadata(self, qtbot, widget_with_images):
        """get_staged_items() がファイル名・パスのタプルを含むこと"""
        widget = widget_with_images
        items = widget.get_staged_items()

        for _image_id, (filename, stored_path) in items.items():
            assert isinstance(filename, str)
            assert isinstance(stored_path, str)


class TestSignals:
    """シグナルテスト"""

    @pytest.fixture
    def widget_with_state(self, qtbot):
        """DatasetStateManager 付きウィジェット"""
        widget = StagingWidget()
        qtbot.addWidget(widget)

        state_manager = DatasetStateManager()
        mock_images = [
            {"id": 1, "stored_image_path": "/path/to/image1.jpg"},
            {"id": 2, "stored_image_path": "/path/to/image2.jpg"},
        ]
        state_manager._all_images = mock_images

        widget.set_dataset_state_manager(state_manager)
        return widget

    @pytest.mark.gui
    def test_staged_images_changed_on_add(self, qtbot, widget_with_state):
        """add_image_ids 後に staged_images_changed が発行されること"""
        widget = widget_with_state

        with qtbot.waitSignal(widget.staged_images_changed, timeout=1000) as blocker:
            widget.add_image_ids([1, 2])

        assert blocker.signal_triggered
        assert set(blocker.args[0]) == {1, 2}

    @pytest.mark.gui
    def test_staged_images_changed_on_clear(self, qtbot, widget_with_state):
        """clear() 後に staged_images_changed([]) が発行されること"""
        widget = widget_with_state
        widget.add_image_ids([1, 2])

        with qtbot.waitSignal(widget.staged_images_changed, timeout=1000) as blocker:
            widget.clear()

        assert blocker.signal_triggered
        assert blocker.args == [[]]

    @pytest.mark.gui
    def test_staging_cleared_on_clear(self, qtbot, widget_with_state):
        """clear() 後に staging_cleared が発行されること"""
        widget = widget_with_state
        widget.add_image_ids([1, 2])

        with qtbot.waitSignal(widget.staging_cleared, timeout=1000):
            widget.clear()

    @pytest.mark.gui
    def test_no_signal_when_no_images_added(self, qtbot):
        """DatasetStateManager 未設定時にシグナルが発行されないこと"""
        widget = StagingWidget()
        qtbot.addWidget(widget)

        signal_received = []
        widget.staged_images_changed.connect(lambda ids: signal_received.append(ids))

        widget.add_image_ids([1, 2])

        assert len(signal_received) == 0


class TestCountLabel:
    """カウントラベル更新テスト"""

    @pytest.fixture
    def widget_with_state(self, qtbot):
        """DatasetStateManager 付きウィジェット"""
        widget = StagingWidget()
        qtbot.addWidget(widget)

        state_manager = DatasetStateManager()
        mock_images = [{"id": 1, "stored_image_path": "/path/to/image1.jpg"}]
        state_manager._all_images = mock_images

        widget.set_dataset_state_manager(state_manager)
        return widget

    @pytest.mark.gui
    def test_count_label_updates_on_add(self, qtbot, widget_with_state):
        """追加後にカウントラベルが更新されること"""
        widget = widget_with_state

        assert widget.ui.labelStagingCount.text() == f"0 / {widget.MAX_STAGING_IMAGES} 枚"

        widget.add_image_ids([1])

        assert widget.ui.labelStagingCount.text() == f"1 / {widget.MAX_STAGING_IMAGES} 枚"

    @pytest.mark.gui
    def test_count_label_updates_on_clear(self, qtbot, widget_with_state):
        """クリア後にカウントラベルがリセットされること"""
        widget = widget_with_state

        widget.add_image_ids([1])
        assert widget.ui.labelStagingCount.text() == f"1 / {widget.MAX_STAGING_IMAGES} 枚"

        widget.clear()

        assert widget.ui.labelStagingCount.text() == f"0 / {widget.MAX_STAGING_IMAGES} 枚"
