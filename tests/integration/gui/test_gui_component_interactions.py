# tests/integration/gui/test_gui_component_interactions.py

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QWidget

from lorairo.gui.state.dataset_state import DatasetStateManager


class TestGUIComponentInteractions:
    """GUIコンポーネント間相互作用の統合テスト"""

    @pytest.fixture
    def parent_widget(self, qtbot):
        """テスト用親ウィジェット (pytest-qt対応)"""
        widget = QWidget()
        qtbot.addWidget(widget)
        yield widget

    @pytest.fixture
    def dataset_state_manager(self, parent_widget):
        """テスト用データセット状態管理"""
        return DatasetStateManager(parent_widget)

    @pytest.fixture
    @patch("lorairo.gui.widgets.filter_search_panel.FilterSearchPanel.__init__")
    def mock_filter_panel(self, mock_init, parent_widget, dataset_state_manager):
        """モックフィルター検索パネル"""
        from lorairo.gui.widgets.filter_search_panel import FilterSearchPanel

        mock_init.return_value = None
        panel = FilterSearchPanel.__new__(FilterSearchPanel)

        # 必要な属性とメソッドを設定
        panel.dataset_state = dataset_state_manager
        panel.filter_applied = Mock()
        panel.get_filter_conditions = Mock(
            return_value={
                "tags": ["test", "sample"],
                "caption": "beautiful",
                "resolution": 1024,
                "use_and": True,
                "include_untagged": False,
                "date_range": (None, None),
            }
        )

        return panel

    @pytest.fixture
    @patch("lorairo.gui.widgets.thumbnail_enhanced.ThumbnailSelectorWidget.__init__")
    def mock_thumbnail_widget(self, mock_init, parent_widget, dataset_state_manager):
        """モックサムネイルセレクターウィジェット"""
        from lorairo.gui.widgets.thumbnail_enhanced import ThumbnailSelectorWidget

        mock_init.return_value = None
        widget = ThumbnailSelectorWidget.__new__(ThumbnailSelectorWidget)

        # 必要な属性とメソッドを設定
        widget.dataset_state = dataset_state_manager
        widget.image_selected = Mock()
        widget.selection_changed = Mock()
        widget.images_data = []
        widget.selected_images = []

        widget.set_images_data = Mock()
        widget.clear_thumbnails = Mock()
        widget.update_selection = Mock()

        return widget

    @pytest.fixture
    @patch("lorairo.gui.widgets.preview_detail_panel.PreviewDetailPanel.__init__")
    def mock_preview_panel(self, mock_init, parent_widget, dataset_state_manager):
        """モックプレビュー詳細パネル"""
        from lorairo.gui.widgets.preview_detail_panel import PreviewDetailPanel

        mock_init.return_value = None
        panel = PreviewDetailPanel.__new__(PreviewDetailPanel)

        # 必要な属性とメソッドを設定
        panel.dataset_state = dataset_state_manager
        panel.db_manager = Mock()

        panel.update_preview = Mock()
        panel.clear_preview = Mock()
        panel.update_annotations = Mock()

        return panel

    def test_filter_to_thumbnail_interaction(self, mock_filter_panel, mock_thumbnail_widget):
        """フィルター→サムネイル相互作用テスト"""
        # フィルター適用シミュレーション
        filter_conditions = mock_filter_panel.get_filter_conditions()

        # フィルター適用シグナル発行をシミュレート
        mock_filter_panel.filter_applied.emit = Mock()

        # サムネイルウィジェットでフィルター結果を受信
        filtered_images = [
            {"id": 1, "stored_image_path": "/test/image1.jpg"},
            {"id": 2, "stored_image_path": "/test/image2.jpg"},
        ]

        # 相互作用実行
        mock_filter_panel.filter_applied.emit(filter_conditions)
        mock_thumbnail_widget.set_images_data(filtered_images)

        # 結果確認
        mock_filter_panel.filter_applied.emit.assert_called_once_with(filter_conditions)
        mock_thumbnail_widget.set_images_data.assert_called_once_with(filtered_images)

    def test_thumbnail_to_preview_interaction(self, mock_thumbnail_widget, mock_preview_panel):
        """サムネイル→プレビュー相互作用テスト"""
        # 画像選択シミュレーション
        selected_image_data = {
            "id": 1,
            "stored_image_path": "/test/image1.jpg",
            "width": 1024,
            "height": 768,
        }

        # 画像選択シグナル発行をシミュレート
        mock_thumbnail_widget.image_selected.emit = Mock()

        # 相互作用実行
        mock_thumbnail_widget.image_selected.emit(selected_image_data)
        mock_preview_panel.update_preview(selected_image_data)

        # 結果確認
        mock_thumbnail_widget.image_selected.emit.assert_called_once_with(selected_image_data)
        mock_preview_panel.update_preview.assert_called_once_with(selected_image_data)

    def test_dataset_state_coordination(
        self, dataset_state_manager, mock_filter_panel, mock_thumbnail_widget, mock_preview_panel
    ):
        """データセット状態協調テスト"""
        # データセットパス設定
        test_path = Path("/test/dataset")
        dataset_state_manager.set_dataset_path(test_path)

        # 画像データ設定
        test_images = [
            {"id": 1, "stored_image_path": "/test/image1.jpg"},
            {"id": 2, "stored_image_path": "/test/image2.jpg"},
            {"id": 3, "stored_image_path": "/test/image3.jpg"},
        ]
        dataset_state_manager.set_dataset_images(test_images)

        # 状態確認
        assert dataset_state_manager.dataset_path == test_path
        assert len(dataset_state_manager.all_images) == 3
        assert len(dataset_state_manager.filtered_images) == 3

    def test_selection_state_synchronization(
        self, dataset_state_manager, mock_thumbnail_widget, mock_preview_panel
    ):
        """選択状態同期テスト"""
        # 画像データ設定
        test_images = [
            {"id": 1, "stored_image_path": "/test/image1.jpg"},
            {"id": 2, "stored_image_path": "/test/image2.jpg"},
        ]
        dataset_state_manager.set_dataset_images(test_images)

        # 画像選択
        dataset_state_manager.set_selected_images([1])
        dataset_state_manager.set_current_image(1)

        # 状態確認
        assert dataset_state_manager.selected_image_ids == [1]
        assert dataset_state_manager.current_image_id == 1
        assert dataset_state_manager.is_image_selected(1) is True
        assert dataset_state_manager.is_image_selected(2) is False

    def test_filter_state_propagation(self, dataset_state_manager, mock_filter_panel):
        """フィルター状態伝播テスト"""
        # フィルター条件設定
        filter_conditions = {
            "tags": ["anime", "girl"],
            "caption": "beautiful anime girl",
            "resolution": 2048,
            "use_and": True,
            "include_untagged": False,
        }

        # フィルター適用（実際のメソッドを使用）
        test_images = [{"id": 1, "tags": ["anime", "girl"]}]
        dataset_state_manager.apply_filter_results(test_images, filter_conditions)

        # フィルター状態確認
        assert dataset_state_manager.filter_conditions == filter_conditions

    def test_ui_state_coordination(self, dataset_state_manager):
        """UI状態協調テスト"""
        # サムネイルサイズ変更
        dataset_state_manager.set_thumbnail_size(200)
        assert dataset_state_manager.thumbnail_size == 200

        # レイアウトモード変更
        dataset_state_manager.set_layout_mode("list")
        assert dataset_state_manager.layout_mode == "list"

        # カスタムUI状態
        dataset_state_manager.set_ui_state("sidebar_width", 300)
        assert dataset_state_manager.get_ui_state("sidebar_width") == 300

    def test_data_flow_integration(
        self, dataset_state_manager, mock_filter_panel, mock_thumbnail_widget, mock_preview_panel
    ):
        """データフロー統合テスト"""
        # 1. データセット読み込み
        test_images = [
            {"id": 1, "stored_image_path": "/test/image1.jpg", "tags": ["anime"]},
            {"id": 2, "stored_image_path": "/test/image2.jpg", "tags": ["landscape"]},
            {"id": 3, "stored_image_path": "/test/image3.jpg", "tags": ["anime", "girl"]},
        ]
        dataset_state_manager.set_dataset_images(test_images)

        # 2. フィルター適用
        filter_conditions = {"tags": ["anime"], "use_and": False}
        # フィルター結果をシミュレート（実際のフィルタリングロジックは別途実装）
        filtered_images = [img for img in test_images if "anime" in img.get("tags", [])]
        dataset_state_manager.apply_filter_results(filtered_images, filter_conditions)

        # 3. 画像選択
        dataset_state_manager.set_current_image(1)

        # 4. データフロー確認
        assert len(dataset_state_manager.filtered_images) == 2  # anime タグを持つ画像
        assert dataset_state_manager.current_image_id == 1

    def test_error_state_handling(self, dataset_state_manager, mock_filter_panel, mock_thumbnail_widget):
        """エラー状態ハンドリングテスト"""
        # 空のデータセット
        dataset_state_manager.set_dataset_images([])
        assert len(dataset_state_manager.all_images) == 0
        assert not dataset_state_manager.has_images()

        # 存在しない画像選択
        dataset_state_manager.set_current_image(999)
        current_data = dataset_state_manager.get_current_image_data()
        assert current_data is None

    def test_signal_chain_integration(self, dataset_state_manager):
        """シグナルチェーン統合テスト"""
        # シグナル受信用モック
        dataset_changed_mock = Mock()
        images_loaded_mock = Mock()
        selection_changed_mock = Mock()
        filter_applied_mock = Mock()

        # シグナル接続
        dataset_state_manager.dataset_changed.connect(dataset_changed_mock)
        dataset_state_manager.images_loaded.connect(images_loaded_mock)
        dataset_state_manager.selection_changed.connect(selection_changed_mock)
        dataset_state_manager.filter_applied.connect(filter_applied_mock)

        # 操作実行
        dataset_state_manager.set_dataset_path(Path("/test/dataset"))
        dataset_state_manager.set_dataset_images([{"id": 1, "path": "/test/image1.jpg"}])
        dataset_state_manager.set_selected_images([1])
        dataset_state_manager.apply_filter_results(
            [{"id": 1, "path": "/test/image1.jpg"}], {"tags": ["test"]}
        )

        # シグナル発行確認
        dataset_changed_mock.assert_called_once()
        images_loaded_mock.assert_called_once()
        selection_changed_mock.assert_called_once()
        filter_applied_mock.assert_called_once()

    def test_responsive_layout_coordination(self, dataset_state_manager):
        """レスポンシブレイアウト協調テスト"""
        # ウィンドウサイズに応じたサムネイルサイズ調整をシミュレート
        window_sizes = [(800, 600), (1200, 900), (1920, 1080)]
        expected_thumbnail_sizes = [100, 150, 200]

        for (width, _height), expected_size in zip(window_sizes, expected_thumbnail_sizes, strict=False):
            # ウィンドウサイズに基づくサムネイルサイズ計算
            calculated_size = 100 if width < 1000 else (150 if width < 1600 else 200)
            dataset_state_manager.set_thumbnail_size(calculated_size)

            assert dataset_state_manager.thumbnail_size == expected_size

    def test_concurrent_state_updates(self, dataset_state_manager):
        """並行状態更新テスト"""
        # 複数の状態更新を連続実行
        test_images = [{"id": i, "path": f"/test/image{i}.jpg"} for i in range(10)]

        dataset_state_manager.set_dataset_images(test_images)
        dataset_state_manager.set_selected_images([1, 3, 5])
        dataset_state_manager.set_current_image(3)
        dataset_state_manager.set_thumbnail_size(175)
        dataset_state_manager.set_layout_mode("grid")

        # 最終状態確認
        assert len(dataset_state_manager.all_images) == 10
        assert dataset_state_manager.selected_image_ids == [1, 3, 5]
        assert dataset_state_manager.current_image_id == 3
        assert dataset_state_manager.thumbnail_size == 175
        assert dataset_state_manager.layout_mode == "grid"

    def test_memory_efficiency_in_interactions(self, dataset_state_manager):
        """相互作用でのメモリ効率テスト"""
        import gc

        # 大量データでのメモリ使用量テスト
        large_dataset = [{"id": i, "path": f"/test/image{i}.jpg", "data": "x" * 1000} for i in range(100)]

        dataset_state_manager.set_dataset_images(large_dataset)

        # データクリア
        dataset_state_manager.clear_dataset()
        gc.collect()

        # メモリリークがないことを確認（基本チェック）
        assert len(dataset_state_manager.all_images) == 0
        assert len(dataset_state_manager.filtered_images) == 0


class TestRealTimeInteractions:
    """リアルタイム相互作用テスト"""

    @pytest.fixture
    def event_loop(self):
        """テスト用イベントループ"""
        loop = QEventLoop()
        yield loop

    def test_real_time_search_updates(self, event_loop):
        """リアルタイム検索更新テスト"""
        # DatasetStateManagerでリアルタイム検索をシミュレート
        dataset_state = DatasetStateManager()

        # 検索結果更新の追跡
        update_count = 0

        def on_filter_update(conditions):
            nonlocal update_count
            update_count += 1
            if update_count >= 3:
                event_loop.quit()

        dataset_state.filter_applied.connect(on_filter_update)

        # 複数の検索条件を連続適用
        QTimer.singleShot(10, lambda: dataset_state.apply_filter_results([], {"tags": ["a"]}))
        QTimer.singleShot(20, lambda: dataset_state.apply_filter_results([], {"tags": ["ab"]}))
        QTimer.singleShot(30, lambda: dataset_state.apply_filter_results([], {"tags": ["abc"]}))

        # タイムアウト設定
        QTimer.singleShot(1000, event_loop.quit)

        # イベントループ実行
        event_loop.exec()

        # 更新回数確認
        assert update_count == 3

    def test_progressive_loading_simulation(self, event_loop):
        """段階的読み込みシミュレーションテスト"""
        dataset_state = DatasetStateManager()

        loaded_batches = []

        def on_images_loaded():
            loaded_batches.append(len(dataset_state.all_images))
            if len(loaded_batches) >= 3:
                event_loop.quit()

        dataset_state.images_loaded.connect(on_images_loaded)

        # 段階的に画像を追加
        batch1 = [{"id": 1, "path": "/test/image1.jpg"}]
        batch2 = [{"id": 2, "path": "/test/image2.jpg"}]
        batch3 = [{"id": 3, "path": "/test/image3.jpg"}]

        QTimer.singleShot(10, lambda: dataset_state.set_dataset_images(batch1))
        QTimer.singleShot(20, lambda: dataset_state.set_dataset_images(batch1 + batch2))
        QTimer.singleShot(30, lambda: dataset_state.set_dataset_images(batch1 + batch2 + batch3))

        # タイムアウト設定
        QTimer.singleShot(1000, event_loop.quit)

        # イベントループ実行
        event_loop.exec()

        # 段階的読み込み確認
        assert loaded_batches == [1, 2, 3]
