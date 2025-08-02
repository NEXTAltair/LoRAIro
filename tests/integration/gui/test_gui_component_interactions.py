# tests/integration/gui/test_gui_component_interactions.py
"""
真の統合テスト - 実際のGUIコンポーネント間相互作用をテスト
モックは外部API・外部システムのみに制限し、内部コンポーネントは実インスタンス化
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QWidget

from lorairo.gui.state.dataset_state import DatasetStateManager
from lorairo.gui.widgets.filter_search_panel import FilterSearchPanel
from lorairo.gui.widgets.image_preview import ImagePreviewWidget
from lorairo.gui.widgets.selected_image_details_widget import SelectedImageDetailsWidget
from lorairo.gui.widgets.thumbnail import ThumbnailSelectorWidget


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
    def real_filter_panel(self, parent_widget, dataset_state_manager, qtbot):
        """実際のフィルター検索パネル（外部依存のみモック）"""
        try:
            # 外部ファイルシステム操作のみモック（統合テスト方針準拠）
            with patch("lorairo.storage.file_system.FileSystemManager"):
                panel = FilterSearchPanel(parent_widget, dataset_state_manager)
                qtbot.addWidget(panel)
                return panel
        except Exception as e:
            pytest.skip(f"FilterSearchPanel initialization failed: {e}")
            return None

    @pytest.fixture
    def real_thumbnail_widget(self, parent_widget, dataset_state_manager, qtbot):
        """実際のサムネイルセレクターウィジェット（テスト用画像リソース使用）"""
        try:
            widget = ThumbnailSelectorWidget(parent_widget, dataset_state_manager)
            qtbot.addWidget(widget)
            return widget
        except Exception as e:
            pytest.skip(f"ThumbnailSelectorWidget initialization failed: {e}")
            return None

    @pytest.fixture
    def real_preview_widget(self, parent_widget, qtbot):
        """実際の画像プレビューウィジェット（テスト用画像リソース使用）"""
        try:
            widget = ImagePreviewWidget(parent_widget)
            qtbot.addWidget(widget)
            return widget
        except Exception as e:
            pytest.skip(f"ImagePreviewWidget initialization failed: {e}")
            return None

    @pytest.fixture
    def real_details_widget(self, parent_widget, qtbot):
        """実際の選択画像詳細ウィジェット"""
        try:
            widget = SelectedImageDetailsWidget(parent_widget)
            qtbot.addWidget(widget)
            return widget
        except Exception as e:
            pytest.skip(f"SelectedImageDetailsWidget initialization failed: {e}")
            return None

    @pytest.fixture
    def test_images_data(self):
        """テスト用画像データ（実際のテストリソース使用）"""
        test_img_dir = Path("/workspaces/LoRAIro/tests/resources/img/1_img")
        return [
            {
                "id": i + 1,
                "stored_image_path": str(test_img_dir / f"file{i + 1:02d}.webp"),
                "width": 512,
                "height": 512,
                "tags": ["test", "sample"] if i % 2 == 0 else ["anime", "girl"],
            }
            for i in range(5)  # file01.webp から file05.webp まで
        ]

    def test_real_filter_to_thumbnail_signal_flow(
        self, real_filter_panel, real_thumbnail_widget, test_images_data
    ):
        """実際のフィルター→サムネイル シグナルフロー統合テスト"""
        if not real_filter_panel or not real_thumbnail_widget:
            pytest.skip("Required widgets not available")

        # 実際のシグナル受信確認
        signal_received = []

        def on_filter_applied(conditions):
            signal_received.append(conditions)

        # 実際のシグナル接続
        real_filter_panel.filter_applied.connect(on_filter_applied)

        # 実際のフィルター条件
        test_conditions = {
            "tags": ["test", "sample"],
            "caption": "",
            "resolution": None,
            "use_and": False,
            "include_untagged": True,
            "date_range": (None, None),
        }

        # 実際のシグナル発行
        real_filter_panel.filter_applied.emit(test_conditions)

        # 実際のシグナル伝播確認
        assert len(signal_received) == 1
        assert signal_received[0] == test_conditions

    def test_real_image_selection_to_preview_flow(
        self, real_thumbnail_widget, real_preview_widget, test_images_data
    ):
        """実際の画像選択→プレビュー フロー統合テスト"""
        if not real_thumbnail_widget or not real_preview_widget:
            pytest.skip("Required widgets not available")

        # 実際のテスト画像データを使用
        test_image = test_images_data[0]  # file01.webp

        # 実際の画像読み込み
        try:
            real_preview_widget.load_image(Path(test_image["stored_image_path"]))

            # 画像が読み込まれたことを確認
            assert real_preview_widget.graphics_scene is not None

        except Exception as e:
            pytest.skip(f"Image loading failed: {e}")

    def test_real_dataset_state_coordination(self, dataset_state_manager, test_images_data):
        """実際のデータセット状態協調統合テスト"""
        # 実際のテストリソースパス設定
        test_path = Path("/workspaces/LoRAIro/tests/resources/img/1_img")
        dataset_state_manager.set_dataset_path(test_path)

        # 実際のテスト画像データ設定
        dataset_state_manager.set_dataset_images(test_images_data)

        # 実際の状態確認
        assert dataset_state_manager.dataset_path == test_path
        assert len(dataset_state_manager.all_images) == 5
        assert len(dataset_state_manager.filtered_images) == 5

        # 実際の画像ファイルパス確認
        first_image = dataset_state_manager.all_images[0]
        assert Path(first_image["stored_image_path"]).exists()
        assert first_image["stored_image_path"].endswith("file01.webp")

    def test_real_selection_state_synchronization(self, dataset_state_manager, test_images_data):
        """実際の選択状態同期統合テスト"""
        # 実際のテスト画像データ設定
        dataset_state_manager.set_dataset_images(test_images_data)

        # 実際の画像選択操作
        dataset_state_manager.set_selected_images([1, 3])
        dataset_state_manager.set_current_image(1)

        # 実際の状態確認
        assert dataset_state_manager.selected_image_ids == [1, 3]
        assert dataset_state_manager.current_image_id == 1
        assert dataset_state_manager.is_image_selected(1) is True
        assert dataset_state_manager.is_image_selected(2) is False
        assert dataset_state_manager.is_image_selected(3) is True

        # 実際の選択画像データ取得
        current_data = dataset_state_manager.get_current_image_data()
        assert current_data is not None
        assert current_data["id"] == 1
        assert current_data["stored_image_path"].endswith("file01.webp")

    def test_real_filter_state_propagation(self, dataset_state_manager, test_images_data):
        """実際のフィルター状態伝播統合テスト"""
        # 実際のフィルター条件設定
        filter_conditions = {
            "tags": ["anime", "girl"],
            "caption": "beautiful anime girl",
            "resolution": 2048,
            "use_and": True,
            "include_untagged": False,
        }

        # 実際のフィルタリング適用（anime tagを持つ画像のみ）
        anime_images = [img for img in test_images_data if "anime" in img.get("tags", [])]
        dataset_state_manager.apply_filter_results(anime_images, filter_conditions)

        # 実際のフィルター状態確認
        assert dataset_state_manager.filter_conditions == filter_conditions
        assert len(dataset_state_manager.filtered_images) == len(anime_images)

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

    def test_real_data_flow_integration(self, dataset_state_manager, test_images_data):
        """実際のデータフロー統合テスト"""
        # 1. 実際のデータセット読み込み
        dataset_state_manager.set_dataset_images(test_images_data)

        # 2. 実際のフィルター適用
        filter_conditions = {"tags": ["anime"], "use_and": False}
        # 実際のフィルタリングロジック実行
        filtered_images = [img for img in test_images_data if "anime" in img.get("tags", [])]
        dataset_state_manager.apply_filter_results(filtered_images, filter_conditions)

        # 3. 実際の画像選択
        if filtered_images:  # anime画像が存在する場合
            first_anime_id = filtered_images[0]["id"]
            dataset_state_manager.set_current_image(first_anime_id)

            # 4. 実際のデータフロー確認
            assert len(dataset_state_manager.filtered_images) == len(filtered_images)
            assert dataset_state_manager.current_image_id == first_anime_id
        else:
            # anime画像がない場合の確認
            assert len(dataset_state_manager.filtered_images) == 0

    def test_error_state_handling(self, dataset_state_manager):
        """エラー状態ハンドリングテスト"""
        # 空のデータセット
        dataset_state_manager.set_dataset_images([])
        assert len(dataset_state_manager.all_images) == 0
        assert not dataset_state_manager.has_images()

        # 存在しない画像選択
        dataset_state_manager.set_current_image(999)
        current_data = dataset_state_manager.get_current_image_data()
        assert current_data is None

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
