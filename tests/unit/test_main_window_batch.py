"""MainWindow のバッチ処理機能のユニットテスト（簡略版）"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from PySide6.QtWidgets import QApplication, QStatusBar

# QApplication の初期化（テスト実行時に必要）
if not QApplication.instance():
    app = QApplication([])

from lorairo.gui.window.main_window import MainWindow


class TestMainWindowBatch:
    """MainWindow のバッチ処理機能のテスト"""

    @patch("lorairo.gui.window.main_window.ConfigurationService")
    def test_dataset_dir_changed_calls_batch_processing(self, mock_config_service):
        """dataset_dir_changed がバッチ処理を呼び出すテスト"""
        # Arrange
        mock_config_instance = Mock()
        mock_config_service.return_value = mock_config_instance
        mock_config_instance.get_setting.return_value = ""

        # Mock MainWindow.__init__ to avoid UI dependencies
        with patch.object(MainWindow, "__init__", return_value=None):
            window = MainWindow()
            window.config_service = mock_config_instance

            # Mock the batch processing method
            with patch.object(window, "start_batch_processing") as mock_start_batch:
                # Act
                window.dataset_dir_changed("/test/path")

                # Assert
                mock_config_instance.update_setting.assert_called_once_with(
                    "directories", "dataset", "/test/path"
                )
                mock_start_batch.assert_called_once_with(Path("/test/path"))

    def test_on_batch_progress(self):
        """on_batch_progress メソッドのテスト"""
        # Mock MainWindow.__init__ to avoid UI dependencies
        with patch.object(MainWindow, "__init__", return_value=None):
            window = MainWindow()

            # Mock statusbar
            mock_statusbar = Mock(spec=QStatusBar)
            window.statusbar = mock_statusbar

            # Mock progress widget
            mock_progress_widget = Mock()
            mock_progress_widget.setWindowTitle = Mock()
            window.progress_widget = mock_progress_widget

            # Act
            window.on_batch_progress(5, 10, "test_image.jpg")

            # Assert
            mock_statusbar.showMessage.assert_called_once_with("処理中: test_image.jpg (5/10)")
            mock_progress_widget.setWindowTitle.assert_called_once_with("バッチ処理 - 50% 完了")

    def test_on_batch_progress_division_by_zero(self):
        """total が 0 の場合の除算エラー回避テスト"""
        # Mock MainWindow.__init__ to avoid UI dependencies
        with patch.object(MainWindow, "__init__", return_value=None):
            window = MainWindow()

            # Mock statusbar
            mock_statusbar = Mock(spec=QStatusBar)
            window.statusbar = mock_statusbar

            # Mock progress widget
            mock_progress_widget = Mock()
            mock_progress_widget.setWindowTitle = Mock()
            window.progress_widget = mock_progress_widget

            # Act - total が 0 の場合
            window.on_batch_progress(1, 0, "test_image.jpg")

            # Assert - 例外が発生せず、パーセンテージは 0 になる
            mock_statusbar.showMessage.assert_called_once_with("処理中: test_image.jpg (1/0)")
            mock_progress_widget.setWindowTitle.assert_called_once_with("バッチ処理 - 0% 完了")

    def test_some_long_process_with_batch_parameters(self):
        """some_long_process でバッチ処理関数を呼び出すテスト"""
        # Mock MainWindow.__init__ to avoid UI dependencies
        with patch.object(MainWindow, "__init__", return_value=None):
            window = MainWindow()

            # Mock required attributes
            window.config_service = Mock()
            window.fsm = Mock()
            window.idm = Mock()

            # Mock progress components
            mock_progress_widget = Mock()
            mock_progress_controller = Mock()
            window.progress_widget = mock_progress_widget
            window.progress_controller = mock_progress_controller

            # Mock batch function
            mock_batch_function = Mock()
            test_path = Path("/test/path")

            # Act
            window.some_long_process(
                mock_batch_function, test_path, window.config_service, window.fsm, window.idm
            )

            # Assert
            mock_progress_widget.show.assert_called_once()
            mock_progress_controller.start_process.assert_called_once_with(
                mock_batch_function, test_path, window.config_service, window.fsm, window.idm
            )

    @patch("lorairo.gui.window.main_window.logger")
    def test_some_long_process_exception_handling(self, mock_logger):
        """some_long_process の例外処理テスト"""
        # Mock MainWindow.__init__ to avoid UI dependencies
        with patch.object(MainWindow, "__init__", return_value=None):
            window = MainWindow()

            # Mock progress components
            mock_progress_widget = Mock()
            mock_progress_controller = Mock()
            mock_progress_controller.start_process.side_effect = RuntimeError("Test error")
            window.progress_widget = mock_progress_widget
            window.progress_controller = mock_progress_controller

            mock_function = Mock()

            # Act - 例外が発生しても外部に伝播しないことを確認
            window.some_long_process(mock_function)

            # Assert - エラーがログに記録される
            mock_logger.error.assert_called_once()
            assert "ProgressWidgetを使用した処理中にエラーが発生しました" in str(
                mock_logger.error.call_args
            )

    def test_start_batch_processing_with_fsm_initialization(self):
        """start_batch_processing での FileSystemManager 初期化テスト"""
        # Mock MainWindow.__init__ to avoid UI dependencies
        with patch.object(MainWindow, "__init__", return_value=None):
            window = MainWindow()

            # Mock required attributes
            mock_config_service = Mock()
            mock_config_service.get_database_directory.return_value = Path("/test/database")
            mock_fsm = Mock()
            window.config_service = mock_config_service
            window.fsm = mock_fsm
            window.idm = Mock()
            window.progress_widget = Mock()
            window.progress_controller = Mock()

            # Mock worker for signal connection
            mock_worker = Mock()
            mock_worker.batch_progress = Mock()
            window.progress_controller.worker = mock_worker

            # Mock some_long_process method
            with patch.object(window, "some_long_process") as mock_long_process:
                test_path = Path("/test/batch/path")

                # Act
                window.start_batch_processing(test_path)

                # Assert
                # FileSystemManagerが初期化されることを確認
                mock_fsm.initialize.assert_called_once_with(Path("/test/database"))
                window.progress_widget.show.assert_called_once()
                mock_long_process.assert_called_once()
                # バッチ進捗シグナルが接続されることを確認
                mock_worker.batch_progress.connect.assert_called()

    def test_start_batch_processing_auto_project_creation(self):
        """データベースディレクトリ未設定時の自動プロジェクト作成テスト"""
        # Mock MainWindow.__init__ to avoid UI dependencies
        with patch.object(MainWindow, "__init__", return_value=None):
            window = MainWindow()

            # Mock required attributes - データベースディレクトリが未設定
            mock_config_service = Mock()
            mock_config_service.get_database_directory.return_value = Path("database")  # デフォルト値
            mock_config_service.get_setting.return_value = "lorairo_data"
            mock_fsm = Mock()
            window.config_service = mock_config_service
            window.fsm = mock_fsm
            window.idm = Mock()
            window.progress_widget = Mock()
            window.progress_controller = Mock()

            # Mock worker
            mock_worker = Mock()
            mock_worker.batch_progress = Mock()
            window.progress_controller.worker = mock_worker

            with (
                patch.object(window, "some_long_process") as mock_long_process,
                patch("datetime.datetime") as mock_datetime,
            ):
                # 固定の日時を設定
                mock_datetime.now.return_value.strftime.return_value = "20250708_123000"

                test_path = Path("/test/batch/path")

                # Act
                window.start_batch_processing(test_path)

                # Assert
                # プロジェクトディレクトリが自動生成されることを確認
                expected_project_dir = Path("lorairo_data") / "batch_project_20250708_123000"
                mock_config_service.update_setting.assert_called_with(
                    "directories", "database_dir", str(expected_project_dir)
                )
                mock_fsm.initialize.assert_called_once_with(expected_project_dir)
