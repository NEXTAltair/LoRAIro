"""MainWindow ユニットテスト

責任分離後のMainWindowのビジネスロジックをテスト
- データベースアクセスロジック
- エラーハンドリング
- サービス統合

Note: これらのテストはGUIコンポーネントを実際に作成せず、
ビジネスロジックのみをテストします。
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest


class TestMainWindowPhase3Integration:
    """MainWindow Phase 3統合機能テスト（サービス統合）"""

    @pytest.fixture
    def mock_dependencies(self):
        """MainWindow依存関係のモック"""
        mocks = {
            "config_service": Mock(),
            "fsm": Mock(),
            "db_manager": Mock(),
            "worker_service": Mock(),
            "dataset_state": Mock(),
        }

        # ConfigurationServiceのモック
        mocks["config_service"].get_setting.return_value = ""
        mocks["config_service"].get_database_directory.return_value = Path("test_db")

        # ImageDatabaseManagerのモック
        mocks["db_manager"].repository = Mock()

        return mocks

    def test_setup_image_db_write_service(self, mock_dependencies):
        """ImageDBWriteService統合テスト: シグナル接続パターン"""
        from lorairo.gui.window.main_window import MainWindow

        method = MainWindow._setup_image_db_write_service

        # モックオブジェクト作成（シグナル属性を持つウィジェット）
        mock_window = Mock()
        mock_window.db_manager = mock_dependencies["db_manager"]
        mock_widget = Mock()
        mock_widget.rating_updated = Mock()
        mock_widget.score_updated = Mock()
        mock_widget.save_requested = Mock()
        mock_window.selected_image_details_widget = mock_widget

        with patch("lorairo.gui.window.main_window.ImageDBWriteService") as mock_service_class:
            with patch("lorairo.gui.window.main_window.logger") as mock_logger:
                mock_service_instance = Mock()
                mock_service_class.return_value = mock_service_instance

                # メソッド実行
                method(mock_window)

                # ImageDBWriteServiceが正しく初期化される
                mock_service_class.assert_called_once_with(mock_dependencies["db_manager"])

                # サービスがインスタンス変数に設定される
                assert mock_window.image_db_write_service == mock_service_instance

                # シグナルが接続される
                mock_widget.rating_updated.connect.assert_called_once()
                mock_widget.score_updated.connect.assert_called_once()
                mock_widget.save_requested.connect.assert_called_once()

                # ログが出力される
                mock_logger.info.assert_called_with(
                    "ImageDBWriteService created and signals connected"
                )

    def test_setup_image_db_write_service_view_only(self, mock_dependencies):
        """ImageDBWriteService: 閲覧専用ウィジェット（シグナルなし）"""
        from lorairo.gui.window.main_window import MainWindow

        method = MainWindow._setup_image_db_write_service

        mock_window = Mock()
        mock_window.db_manager = mock_dependencies["db_manager"]
        # hasattr が False を返すようにspec設定
        mock_widget = Mock(spec=[])
        mock_window.selected_image_details_widget = mock_widget

        with patch("lorairo.gui.window.main_window.ImageDBWriteService") as mock_service_class:
            with patch("lorairo.gui.window.main_window.logger") as mock_logger:
                mock_service_instance = Mock()
                mock_service_class.return_value = mock_service_instance

                method(mock_window)

                # サービスは作成される
                mock_service_class.assert_called_once_with(mock_dependencies["db_manager"])
                assert mock_window.image_db_write_service == mock_service_instance

                # シグナル接続はスキップされる
                mock_logger.info.assert_called_with(
                    "SelectedImageDetailsWidget is view-only; edit signals not connected"
                )

    def test_setup_image_db_write_service_missing_deps(self, mock_dependencies):
        """ImageDBWriteService: 依存関係なし時の警告"""
        from lorairo.gui.window.main_window import MainWindow

        method = MainWindow._setup_image_db_write_service

        mock_window = Mock()
        mock_window.db_manager = None
        mock_window.selected_image_details_widget = Mock()

        with patch("lorairo.gui.window.main_window.logger") as mock_logger:
            method(mock_window)

            mock_logger.warning.assert_called_once()

    def test_state_manager_connection_validation(self, mock_dependencies):
        """DatasetStateManager接続検証テスト"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.dataset_state = mock_dependencies["dataset_state"]

        # image_previewがNoneの場合
        mock_window.image_preview = None

        with pytest.raises(AttributeError):
            MainWindow._setup_state_integration(mock_window)


if __name__ == "__main__":
    pytest.main([__file__])
