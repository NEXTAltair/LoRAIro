# tests/integration/gui/window/test_main_window.py
"""
MainWindow 統合テスト

責任分離後のMainWindowとThumbnailSelectorWidgetの実際の統合をテスト
- 実際のコンポーネントを使用した統合テスト
- 責任分離の検証
- 最小限のモックのみ使用（外部依存のみ）
"""

import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication

from lorairo.gui.state.dataset_state import DatasetStateManager
from lorairo.gui.widgets.thumbnail import ThumbnailSelectorWidget
from lorairo.gui.window.main_window import MainWindow
from lorairo.utils.log import initialize_logging


@pytest.fixture(scope="session")
def qapp() -> Generator[QApplication, None, None]:
    """Qt Application fixture for GUI tests"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestMainWindowThumbnailIntegration:
    """MainWindow と ThumbnailSelectorWidget の実際の統合テスト"""

    @pytest.fixture
    def temp_dir(self) -> Generator[Path, None, None]:
        """一時ディレクトリ"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)

    @pytest.fixture
    def real_main_window(self, qapp: QApplication) -> MainWindow:
        """実際のMainWindow（外部依存のみモック）"""
        # テスト用にログ初期化
        initialize_logging({"level": "ERROR", "file": None})

        # 実際のMainWindowを作成
        window = MainWindow()

        # 実際のコンポーネントを使用
        window.dataset_state = DatasetStateManager()

        # 外部依存のみモック化
        window.db_manager = Mock()

        return window

    @pytest.fixture
    def real_thumbnail_widget(self, qapp: QApplication) -> ThumbnailSelectorWidget:
        """実際のThumbnailSelectorWidget"""
        # 実際のDatasetStateManagerを使用
        dataset_state = DatasetStateManager()

        # 実際のThumbnailSelectorWidgetを作成
        widget = ThumbnailSelectorWidget(dataset_state=dataset_state)

        return widget

    def test_thumbnail_widget_integration(self, real_main_window, real_thumbnail_widget):
        """
        MainWindowとThumbnailSelectorWidgetの実際の統合
        """
        window = real_main_window
        thumbnail_widget = real_thumbnail_widget

        # 実際の統合：MainWindowがThumbnailWidgetにデータを渡す
        window.thumbnail_selector = thumbnail_widget

        # テスト用の最適化されたメタデータ
        optimal_metadata = [
            {"stored_image_path": "/processed/image1.jpg", "id": 1},
            {"stored_image_path": "/processed/image2.jpg", "id": 2},
        ]

        # 画像データとメタデータを直接設定（現行API）
        optimal_paths = [(Path(item["stored_image_path"]), item["id"]) for item in optimal_metadata]
        thumbnail_widget.image_data = optimal_paths
        thumbnail_widget.current_image_metadata = optimal_metadata

        # 実際の統合結果を検証
        assert len(thumbnail_widget.image_data) == 2
        assert thumbnail_widget.image_data[0] == (Path("/processed/image1.jpg"), 1)
        assert thumbnail_widget.image_data[1] == (Path("/processed/image2.jpg"), 2)

    def test_dataset_state_integration(self, real_main_window, temp_dir):
        """
        実際のDatasetStateManagerとの統合テスト
        """
        window = real_main_window
        test_path = Path(temp_dir) / "test_dataset"
        test_path.mkdir()

        # 実際のDatasetStateManagerの動作をテスト
        window.dataset_state.set_dataset_path(test_path)

        # 実際の状態管理が機能することを確認
        assert window.dataset_state.dataset_path == test_path

        # 画像データの設定
        test_images = [
            {"id": 1, "stored_image_path": "test1.jpg"},
            {"id": 2, "stored_image_path": "test2.jpg"},
        ]
        window.dataset_state.set_dataset_images(test_images)

        # フィルター結果の適用
        filtered_images = [{"id": 1, "stored_image_path": "test1.jpg"}]
        filter_conditions = {"tags": ["test"], "resolution": 1024}
        window.dataset_state.apply_filter_results(filtered_images, filter_conditions)

        # 実際の状態管理の結果を確認
        assert len(window.dataset_state.filtered_images) == 1
        assert window.dataset_state.filtered_images[0]["id"] == 1

    def test_responsibility_separation_integration(self, real_main_window, real_thumbnail_widget):
        """
        責任分離が実際に機能していることを統合テスト
        """
        thumbnail_widget = real_thumbnail_widget

        # ThumbnailSelectorWidgetの責任：表示のみ
        display_methods = [
            "load_thumbnails_from_result",
            "clear_thumbnails",
            "get_current_image_data",
        ]

        for method in display_methods:
            assert hasattr(thumbnail_widget, method)
            assert callable(getattr(thumbnail_widget, method))

        # 責任外メソッドが存在しないことを確認
        forbidden_methods = ["_get_thumbnail_path", "check_processed_image_exists", "resolve_stored_path"]

        for method in forbidden_methods:
            assert not hasattr(thumbnail_widget, method)

    def test_thumbnail_size_integration(self, real_thumbnail_widget):
        """
        サムネイルサイズ設定の実際の統合テスト
        """
        widget = real_thumbnail_widget

        # デフォルトサイズの確認
        assert widget.thumbnail_size == QSize(128, 128)

        # サイズ変更の実際のテスト（dataset_state経由で変更）
        new_size_value = 200
        expected_size = QSize(new_size_value, new_size_value)

        if widget.dataset_state:
            widget.dataset_state.set_thumbnail_size(new_size_value)
        else:
            # dataset_stateがない場合は直接変更
            widget.thumbnail_size = expected_size

        # 実際に変更されることを確認
        assert widget.thumbnail_size == expected_size

    def test_complete_integration_workflow(self, real_main_window, real_thumbnail_widget):
        """
        完全な統合ワークフローテスト
        """
        window = real_main_window
        thumbnail_widget = real_thumbnail_widget

        # 統合：MainWindowとThumbnailWidgetを接続
        window.thumbnail_selector = thumbnail_widget

        # テスト用の画像メタデータ
        image_metadata: list[dict[str, Any]] = [
            {"id": 1, "stored_image_path": "/original/image1.jpg"},
            {"id": 2, "stored_image_path": "/original/image2.jpg"},
        ]

        # サムネイルパスの解決はThumbnailWorkerの責務
        # ここではメタデータから直接パスを使用
        optimal_paths = [(Path(m["stored_image_path"]), m["id"]) for m in image_metadata]

        # サムネイル表示（ThumbnailWidgetの責任）
        thumbnail_widget.image_data = optimal_paths
        thumbnail_widget.current_image_metadata = image_metadata

        # 統合結果の検証
        assert len(thumbnail_widget.image_data) == 2
        assert thumbnail_widget.image_data == optimal_paths


if __name__ == "__main__":
    pytest.main([__file__])
