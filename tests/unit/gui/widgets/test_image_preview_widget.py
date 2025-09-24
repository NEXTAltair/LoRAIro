# tests/unit/gui/widgets/test_image_preview_widget.py

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtGui import QPixmap

from lorairo.gui.widgets.image_preview import ImagePreviewWidget


class TestImagePreviewWidget:
    """ImagePreviewWidget単体テスト（Phase 3実装: DatasetStateManagerキャッシュ機能削除対応）"""

    @pytest.fixture
    def widget(self, qtbot):
        """テスト用ImagePreviewWidget"""
        widget = ImagePreviewWidget()
        qtbot.addWidget(widget)
        return widget

    @pytest.fixture
    def mock_state_manager(self):
        """テスト用モックDatasetStateManager (Phase 3実装: キャッシュ機能削除対応)"""
        mock_manager = Mock()
        mock_manager.current_image_id = None
        mock_manager.current_image_changed = Mock()
        mock_manager.current_image_changed.connect = Mock()
        mock_manager.current_image_changed.disconnect = Mock()
        # Phase 3実装: データキャッシュ機能削除により、get_image_by_id()削除
        return mock_manager

    @pytest.fixture
    def sample_image_data(self):
        """テスト用画像データ"""
        from pathlib import Path

        return {
            "id": 123,
            "stored_image_path": str(Path("/test/dataset/sample.jpg")),
            "width": 1024,
            "height": 768,
            "file_size": 2048000,
        }

    def test_initialization(self, widget):
        """初期化テスト（Phase 3.3パターン）"""
        assert widget.state_manager is None
        assert widget._current_image_id is None
        assert widget._image_data is None

    def test_connect_to_data_signals(self, widget, mock_state_manager):
        """DatasetStateManagerシグナル接続テスト"""
        widget.connect_to_data_signals(mock_state_manager)

        assert widget.state_manager is mock_state_manager
        mock_state_manager.current_image_changed.connect.assert_called_once()

    @patch("lorairo.gui.widgets.image_preview.resolve_stored_path")
    def test_load_image_success(self, mock_resolve, widget):
        """画像読み込み成功テスト（Phase 3実装: 直接パス指定版）"""
        # Phase 3実装: 直接画像パスを指定してテスト
        test_image_path = Path("/test/dataset/sample.jpg")
        mock_resolve.return_value = test_image_path

        with patch.object(test_image_path, "exists", return_value=True):
            with patch("lorairo.gui.widgets.image_preview.QPixmap") as mock_pixmap:
                mock_pixmap_instance = Mock(spec=QPixmap)
                mock_pixmap_instance.isNull.return_value = False
                mock_pixmap.return_value = mock_pixmap_instance

                widget.load_image(str(test_image_path))

                assert widget.current_image_path == test_image_path
                mock_pixmap.assert_called_once_with(str(test_image_path))

    @patch("lorairo.gui.widgets.image_preview.resolve_stored_path")
    def test_load_image_with_metadata(self, mock_resolve, widget, sample_image_data):
        """メタデータ付き画像読み込みテスト（Phase 3実装: 直接データ渡し版）"""
        # Phase 3実装: メタデータを直接渡すテスト
        test_image_path = Path(sample_image_data["stored_image_path"])
        mock_resolve.return_value = test_image_path

        with patch.object(test_image_path, "exists", return_value=True):
            with patch("lorairo.gui.widgets.image_preview.QPixmap") as mock_pixmap:
                mock_pixmap_instance = Mock(spec=QPixmap)
                mock_pixmap_instance.isNull.return_value = False
                mock_pixmap.return_value = mock_pixmap_instance

                # 直接メタデータを渡して読み込み
                widget.load_image_with_metadata(sample_image_data)

                assert widget.current_image_path == test_image_path
                assert widget._image_data == sample_image_data

    def test_load_image_file_not_found(self, widget):
        """画像ファイルが見つからない場合のテスト"""
        with patch("lorairo.gui.widgets.image_preview.resolve_stored_path") as mock_resolve:
            test_path = Path("/nonexistent/image.jpg")
            mock_resolve.return_value = test_path

            with patch.object(test_path, "exists", return_value=False):
                widget.load_image(str(test_path))

                # ファイルが存在しない場合、クリア処理が実行される
                assert widget.current_image_path is None

    def test_load_image_invalid_path(self, widget):
        """無効なパスでの画像読み込みテスト"""
        # Phase 3実装: データキャッシュ機能削除により、直接パスエラーテスト
        invalid_path = None
        widget.load_image(invalid_path)

        # 無効なパスの場合、クリア処理が実行される
        assert widget.current_image_path is None

    def test_load_image_database_error_handling(self, widget):
        """データベースエラー時の処理テスト（Phase 3実装: エラーハンドリング簡素化）"""
        # Phase 3実装: データベース依存を削除したため、ファイルシステムエラーのみテスト
        with patch("lorairo.gui.widgets.image_preview.resolve_stored_path") as mock_resolve:
            mock_resolve.side_effect = Exception("Path resolution error")

            widget.load_image("some/path.jpg")

            # エラー時はクリア処理が実行される
            assert widget.current_image_path is None

    def test_clear_image(self, widget):
        """画像クリアテスト"""
        # 初期状態設定
        widget.current_image_path = Path("/test/sample.jpg")
        widget._image_data = {"id": 123}

        widget.clear_image()

        assert widget.current_image_path is None
        assert widget._image_data is None

    def test_get_current_image_info(self, widget, sample_image_data):
        """現在の画像情報取得テスト"""
        widget._image_data = sample_image_data
        widget.current_image_path = Path(sample_image_data["stored_image_path"])

        info = widget.get_current_image_info()

        assert info["id"] == sample_image_data["id"]
        assert info["path"] == widget.current_image_path
        assert info["width"] == sample_image_data["width"]
        assert info["height"] == sample_image_data["height"]

    def test_get_current_image_info_no_data(self, widget):
        """データなし時の画像情報取得テスト"""
        info = widget.get_current_image_info()

        assert info["id"] is None
        assert info["path"] is None
        assert info["width"] is None
        assert info["height"] is None

    def test_on_current_image_changed(self, widget):
        """Phase 3実装: current_image_changed処理テスト（簡素化版）"""
        # Phase 3実装では、データ取得はThumbnailSelectorWidgetから直接行うため、
        # ImagePreviewWidgetの処理は簡素化されています

        test_image_id = 456

        # シグナル処理の内部メソッドを直接テスト
        widget._on_current_image_changed(test_image_id)

        # Phase 3実装では、IDのみ保存され、実際のデータ取得は他のコンポーネントが担当
        assert widget._current_image_id == test_image_id


class TestImagePreviewWidgetIntegration:
    """ImagePreviewWidget統合テスト（Phase 3実装対応）"""

    @pytest.fixture
    def widget_with_mock_manager(self, qtbot):
        """モックマネージャー付きwidget"""
        widget = ImagePreviewWidget()
        qtbot.addWidget(widget)

        mock_manager = Mock()
        mock_manager.current_image_id = None
        mock_manager.current_image_changed = Mock()
        mock_manager.current_image_changed.connect = Mock()
        mock_manager.current_image_changed.disconnect = Mock()

        widget.connect_to_data_signals(mock_manager)

        return widget

    def test_widget_cleanup(self, widget_with_mock_manager):
        """ウィジェットクリーンアップテスト"""
        widget = widget_with_mock_manager

        # クリーンアップ実行
        widget.clear_image()

        assert widget.current_image_path is None
        assert widget._image_data is None
        assert widget._current_image_id is None

    @patch("lorairo.gui.widgets.image_preview.resolve_stored_path")
    def test_async_image_loading(self, mock_resolve, widget_with_mock_manager):
        """Phase 3実装: 非同期画像読み込みテスト（簡素化版）"""
        widget = widget_with_mock_manager
        test_path = Path("/test/async_image.jpg")
        mock_resolve.return_value = test_path

        with patch.object(test_path, "exists", return_value=True):
            with patch("lorairo.gui.widgets.image_preview.QPixmap") as mock_pixmap:
                mock_pixmap_instance = Mock(spec=QPixmap)
                mock_pixmap_instance.isNull.return_value = False
                mock_pixmap.return_value = mock_pixmap_instance

                widget.load_image(str(test_path))

                # 非同期処理完了確認
                assert widget.current_image_path == test_path