# tests/unit/gui/state/test_dataset_state.py

from pathlib import Path
from unittest.mock import Mock

import pytest

from src.lorairo.gui.state.dataset_state import DatasetStateManager


class TestDatasetStateManager:
    """DatasetStateManager のユニットテスト"""

    @pytest.fixture
    def state_manager(self):
        """テスト用のDatasetStateManagerを作成"""
        return DatasetStateManager()

    @pytest.fixture
    def sample_image_metadata(self):
        """サンプル画像メタデータ"""
        return [
            {"id": 1, "stored_image_path": "/test/image1.jpg", "width": 1024, "height": 768},
            {"id": 2, "stored_image_path": "/test/image2.jpg", "width": 800, "height": 600},
            {"id": 3, "stored_image_path": "/test/image3.jpg", "width": 1200, "height": 900},
        ]

    def test_initialization(self, state_manager):
        """初期化テスト"""
        assert state_manager.dataset_path is None
        assert len(state_manager.all_images) == 0
        assert len(state_manager.filtered_images) == 0
        assert len(state_manager.selected_image_ids) == 0
        assert state_manager.current_image_id is None
        assert state_manager.thumbnail_size == 150
        assert state_manager.layout_mode == "grid"

    def test_set_dataset_path(self, state_manager):
        """データセットパス設定テスト"""
        test_path = Path("/test/dataset")

        # シグナル発行確認用のモック
        signal_mock = Mock()
        state_manager.dataset_changed.connect(signal_mock)

        state_manager.set_dataset_path(test_path)

        assert state_manager.dataset_path == test_path
        signal_mock.assert_called_once_with(str(test_path))

    def test_set_dataset_images(self, state_manager, sample_image_metadata):
        """データセット画像設定テスト"""
        # シグナル発行確認用のモック
        images_loaded_mock = Mock()
        images_filtered_mock = Mock()
        dataset_loaded_mock = Mock()

        state_manager.images_loaded.connect(images_loaded_mock)
        state_manager.images_filtered.connect(images_filtered_mock)
        state_manager.dataset_loaded.connect(dataset_loaded_mock)

        state_manager.set_dataset_images(sample_image_metadata)

        assert len(state_manager.all_images) == 3
        assert len(state_manager.filtered_images) == 3
        assert state_manager.selected_image_ids == []

        images_loaded_mock.assert_called_once()
        images_filtered_mock.assert_called_once()
        dataset_loaded_mock.assert_called_once_with(3)

    def test_selection_management(self, state_manager, sample_image_metadata):
        """選択管理テスト"""
        state_manager.set_dataset_images(sample_image_metadata)

        # 単一選択
        selection_mock = Mock()
        state_manager.selection_changed.connect(selection_mock)

        state_manager.set_selected_images([1])
        assert state_manager.selected_image_ids == [1]
        selection_mock.assert_called_with([1])

        # 複数選択
        state_manager.set_selected_images([1, 2])
        assert state_manager.selected_image_ids == [1, 2]

        # 選択追加
        state_manager.add_to_selection(3)
        assert state_manager.selected_image_ids == [1, 2, 3]

        # 選択削除
        state_manager.remove_from_selection(2)
        assert state_manager.selected_image_ids == [1, 3]

        # トグル選択
        state_manager.toggle_selection(2)  # 追加
        assert 2 in state_manager.selected_image_ids
        state_manager.toggle_selection(2)  # 削除
        assert 2 not in state_manager.selected_image_ids

    def test_current_image_management(self, state_manager):
        """現在画像管理テスト"""
        current_changed_mock = Mock()
        current_cleared_mock = Mock()

        state_manager.current_image_changed.connect(current_changed_mock)
        state_manager.current_image_cleared.connect(current_cleared_mock)

        # 現在画像設定
        state_manager.set_current_image(1)
        assert state_manager.current_image_id == 1
        current_changed_mock.assert_called_once_with(1)

        # 現在画像クリア
        state_manager.clear_current_image()
        assert state_manager.current_image_id is None
        current_cleared_mock.assert_called_once()

    def test_filter_management(self, state_manager, sample_image_metadata):
        """フィルター管理テスト"""
        state_manager.set_dataset_images(sample_image_metadata)

        filter_applied_mock = Mock()
        state_manager.filter_applied.connect(filter_applied_mock)

        # フィルター適用
        filter_conditions = {"tags": ["test"], "caption": "sample"}
        state_manager.apply_filter(filter_conditions)

        assert state_manager.filter_conditions == filter_conditions
        filter_applied_mock.assert_called_once_with(filter_conditions)

    def test_ui_state_management(self, state_manager):
        """UI状態管理テスト"""
        thumbnail_size_mock = Mock()
        layout_mode_mock = Mock()
        ui_state_mock = Mock()

        state_manager.thumbnail_size_changed.connect(thumbnail_size_mock)
        state_manager.layout_mode_changed.connect(layout_mode_mock)
        state_manager.ui_state_changed.connect(ui_state_mock)

        # サムネイルサイズ変更
        state_manager.set_thumbnail_size(200)
        assert state_manager.thumbnail_size == 200
        thumbnail_size_mock.assert_called_once_with(200)

        # レイアウトモード変更
        state_manager.set_layout_mode("list")
        assert state_manager.layout_mode == "list"
        layout_mode_mock.assert_called_once_with("list")

        # 任意UI状態
        state_manager.set_ui_state("test_key", "test_value")
        assert state_manager.get_ui_state("test_key") == "test_value"
        ui_state_mock.assert_called_once_with("test_key", "test_value")

    def test_utility_methods(self, state_manager, sample_image_metadata):
        """ユーティリティメソッドテスト"""
        state_manager.set_dataset_images(sample_image_metadata)

        # 画像検索
        image_data = state_manager.get_image_by_id(1)
        assert image_data["id"] == 1
        assert image_data["stored_image_path"] == "/test/image1.jpg"

        # 存在チェック
        assert state_manager.has_images() is True
        assert state_manager.has_filtered_images() is True

        # 選択状態チェック
        state_manager.set_selected_images([1, 2])
        assert state_manager.is_image_selected(1) is True
        assert state_manager.is_image_selected(3) is False

        # 現在画像データ取得
        state_manager.set_current_image(2)
        current_data = state_manager.get_current_image_data()
        assert current_data["id"] == 2

    def test_state_summary(self, state_manager, sample_image_metadata):
        """状態サマリーテスト"""
        state_manager.set_dataset_path(Path("/test/dataset"))
        state_manager.set_dataset_images(sample_image_metadata)
        state_manager.set_selected_images([1, 2])
        state_manager.set_current_image(1)

        summary = state_manager.get_state_summary()

        assert summary["dataset_path"] == "/test/dataset"
        assert summary["total_images"] == 3
        assert summary["filtered_images"] == 3
        assert summary["selected_images"] == 2
        assert summary["current_image_id"] == 1
        assert summary["thumbnail_size"] == 150
        assert summary["layout_mode"] == "grid"

    def test_clear_dataset(self, state_manager, sample_image_metadata):
        """データセットクリアテスト"""
        # データ設定
        state_manager.set_dataset_path(Path("/test/dataset"))
        state_manager.set_dataset_images(sample_image_metadata)
        state_manager.set_selected_images([1])
        state_manager.set_current_image(1)

        # クリア実行
        filter_cleared_mock = Mock()
        state_manager.filter_cleared.connect(filter_cleared_mock)

        state_manager.clear_dataset()

        # 状態確認
        assert state_manager.dataset_path is None
        assert len(state_manager.all_images) == 0
        assert len(state_manager.filtered_images) == 0
        assert state_manager.selected_image_ids == []
        assert state_manager.current_image_id is None

        filter_cleared_mock.assert_called_once()
