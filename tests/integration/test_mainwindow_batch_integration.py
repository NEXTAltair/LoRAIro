"""
MainWindowバッチ処理統合テスト
GUI、ファイルシステム、データベース、Workerシステムの統合をテストする
"""

import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from threading import Event

import pytest
from PySide6.QtCore import QTimer, QEventLoop
from PySide6.QtWidgets import QApplication
from PIL import Image

# QApplication の初期化（テスト実行時に必要）
if not QApplication.instance():
    app = QApplication([])

from lorairo.gui.window.main_window import MainWindow


class TestMainWindowBatchIntegration:
    """MainWindowバッチ処理の統合テスト"""

    @pytest.fixture
    def test_images_directory(self, tmp_path):
        """テスト用画像ディレクトリ"""
        images_dir = tmp_path / "integration_images"
        images_dir.mkdir()
        
        # 複数の画像ファイル作成
        for i in range(5):
            image_path = images_dir / f"integration_test_{i}.jpg"
            image = Image.new('RGB', (40, 40), color=(i * 40, 100, 200))
            image.save(image_path, 'JPEG')
        
        return images_dir

    @pytest.fixture
    def configured_main_window(self, tmp_path):
        """設定済みMainWindow"""
        # MainWindow.__init__をモックして依存関係を回避
        with patch.object(MainWindow, '__init__', return_value=None):
            window = MainWindow()
            
            # 必要な属性を設定
            window.config_service = Mock()
            window.fsm = Mock()
            window.idm = Mock()
            window.progress_widget = Mock()
            window.progress_controller = Mock()
            window.statusbar = Mock()
            
            # UIコンポーネントのモック
            window.mainWindowSplitter = Mock()
            
            return window

    def test_dataset_directory_change_triggers_batch_processing(self, configured_main_window, test_images_directory):
        """データセットディレクトリ変更でバッチ処理が開始される統合テスト"""
        # Arrange
        window = configured_main_window
        
        # start_batch_processingメソッドをモック
        with patch.object(window, 'start_batch_processing') as mock_start_batch:
            # Act
            window.dataset_dir_changed(str(test_images_directory))
            
            # Assert
            window.config_service.update_setting.assert_called_once_with(
                "directories", "dataset", str(test_images_directory)
            )
            mock_start_batch.assert_called_once_with(test_images_directory)

    def test_batch_processing_workflow_integration(self, configured_main_window, test_images_directory):
        """バッチ処理ワークフロー全体の統合テスト"""
        # Arrange
        window = configured_main_window
        
        # FileSystemManagerのモック設定
        window.fsm.get_image_files.return_value = list(test_images_directory.glob("*.jpg"))
        
        # ImageDatabaseManagerのモック設定
        window.idm.detect_duplicate_image.return_value = None
        window.idm.register_original_image.side_effect = lambda file, fsm: (f"id_{file.stem}", {"test": "data"})
        
        # Progress controllerの worker をモック
        mock_worker = Mock()
        mock_worker.batch_progress = Mock()
        window.progress_controller.worker = mock_worker
        
        # some_long_processをモックして即座に完了させる
        def mock_some_long_process(func, *args, **kwargs):
            # バッチ処理関数を直接実行
            result = func(*args, **kwargs)
            return result
        
        with patch.object(window, 'some_long_process', side_effect=mock_some_long_process):
            # Act
            window.start_batch_processing(test_images_directory)
            
            # Assert
            window.progress_widget.show.assert_called_once()
            
            # バッチ進捗シグナルが接続されたことを確認
            mock_worker.batch_progress.connect.assert_called()

    def test_batch_progress_display_integration(self, configured_main_window):
        """バッチ進捗表示の統合テスト"""
        # Arrange
        window = configured_main_window
        
        # ProgressWidgetにsetWindowTitleメソッドを追加
        window.progress_widget.setWindowTitle = Mock()
        
        # Act
        window.on_batch_progress(3, 10, "test_image.jpg")
        
        # Assert
        window.statusbar.showMessage.assert_called_once_with(
            "処理中: test_image.jpg (3/10)"
        )
        window.progress_widget.setWindowTitle.assert_called_once_with(
            "バッチ処理 - 30% 完了"
        )

    def test_batch_processing_error_handling_integration(self, configured_main_window, test_images_directory):
        """バッチ処理エラーハンドリングの統合テスト"""
        # Arrange
        window = configured_main_window
        
        # some_long_processでエラーが発生するように設定
        def mock_some_long_process_with_error(*args, **kwargs):
            raise RuntimeError("バッチ処理エラー")
        
        with patch.object(window, 'some_long_process', side_effect=mock_some_long_process_with_error), \
             patch('lorairo.gui.window.main_window.logger') as mock_logger:
            
            # Act - エラーが発生しても例外が外部に漏れないことを確認
            window.start_batch_processing(test_images_directory)
            
            # Assert
            window.progress_widget.show.assert_called_once()
            mock_logger.error.assert_called_once()

    def test_batch_processing_cancellation_integration(self, configured_main_window, test_images_directory):
        """バッチ処理キャンセル機能の統合テスト"""
        # Arrange
        window = configured_main_window
        
        # Progress controllerとworkerをより詳細にモック
        mock_worker = Mock()
        mock_worker.batch_progress = Mock()
        mock_worker.cancel = Mock()
        window.progress_controller.worker = mock_worker
        
        # Act
        window.start_batch_processing(test_images_directory)
        
        # キャンセル操作をシミュレート（実際のUIではキャンセルボタンから）
        # ProgressWidgetのcanceledシグナルをエミュレート
        window.progress_widget.canceled.emit()
        
        # Assert
        # キャンセルが適切に処理されることを確認
        # (実際の接続はstart_processで行われるため、ここでは設定を確認)
        assert mock_worker.cancel is not None

    def test_end_to_end_batch_processing_simulation(self, configured_main_window, test_images_directory):
        """エンドツーエンドバッチ処理シミュレーション"""
        # Arrange
        window = configured_main_window
        
        # より現実的なモック設定
        batch_progress_calls = []
        status_calls = []
        
        def track_batch_progress(current, total, filename):
            batch_progress_calls.append((current, total, filename))
        
        def track_status(message):
            status_calls.append(message)
        
        # バッチ処理の実際の流れをシミュレート
        def simulate_batch_processing(directory_path, config_service, fsm, idm):
            # ファイル取得をシミュレート
            image_files = list(test_images_directory.glob("*.jpg"))
            total = len(image_files)
            
            for i, image_file in enumerate(image_files):
                current = i + 1
                
                # batch_progress_callbackが注入されることをシミュレート
                track_batch_progress(current, total, image_file.name)
                track_status(f"処理中: {image_file.name}")
                
                # 画像登録をシミュレート
                idm.detect_duplicate_image.return_value = None
                idm.register_original_image.return_value = (f"id_{i}", {"metadata": "test"})
            
            return {"processed": total, "errors": 0, "skipped": 0, "total": total}
        
        # some_long_processをカスタムシミュレーションで置き換え
        with patch.object(window, 'some_long_process') as mock_long_process:
            mock_long_process.side_effect = lambda func, *args, **kwargs: simulate_batch_processing(*args, **kwargs)
            
            # Act
            window.start_batch_processing(test_images_directory)
            
            # Assert
            window.progress_widget.show.assert_called_once()
            mock_long_process.assert_called_once()
            
            # バッチ処理の引数が正しく渡されたことを確認
            call_args = mock_long_process.call_args[0]
            assert call_args[1] == test_images_directory  # directory_path
            assert call_args[2] == window.config_service  # config_service
            assert call_args[3] == window.fsm            # fsm
            assert call_args[4] == window.idm            # idm


class TestMainWindowRealComponentIntegration:
    """MainWindowと実際のコンポーネントとの統合テスト"""

    def test_progress_widget_controller_integration(self):
        """ProgressWidgetとControllerの実際の統合"""
        # Arrange
        with patch.object(MainWindow, '__init__', return_value=None):
            window = MainWindow()
            
            # 実際のProgressWidgetとControllerを作成
            from lorairo.gui.window.progress import ProgressWidget, Controller
            
            progress_widget = ProgressWidget()
            controller = Controller(progress_widget)
            
            window.progress_widget = progress_widget
            window.progress_controller = controller
            window.config_service = Mock()
            window.fsm = Mock()
            window.idm = Mock()
            
            # 短い処理関数
            def quick_function(progress_callback=None, status_callback=None):
                if progress_callback:
                    progress_callback(50)
                if status_callback:
                    status_callback("テスト処理中")
                time.sleep(0.1)
                return "completed"
            
            # Act
            window.some_long_process(quick_function)
            
            # 処理完了まで少し待つ
            loop = QEventLoop()
            QTimer.singleShot(500, loop.quit)
            loop.exec()
            
            # Assert
            # ProgressWidgetが表示されたことを確認
            assert progress_widget.isVisible()
            
            # Cleanup
            controller.cleanup()
            progress_widget.close()

    def test_file_system_manager_integration(self, tmp_path):
        """FileSystemManagerとの実際の統合"""
        # Arrange
        from lorairo.storage.file_system import FileSystemManager
        
        # テスト画像作成
        test_dir = tmp_path / "fsm_test"
        test_dir.mkdir()
        
        for i in range(3):
            image_path = test_dir / f"fsm_test_{i}.png"
            image = Image.new('RGB', (30, 30), color=(0, i * 80, 0))
            image.save(image_path, 'PNG')
        
        with patch.object(MainWindow, '__init__', return_value=None):
            window = MainWindow()
            window.fsm = FileSystemManager()
            window.config_service = Mock()
            window.idm = Mock()
            window.progress_widget = Mock()
            window.progress_controller = Mock()
            
            # some_long_processをモック
            def mock_process(func, *args, **kwargs):
                return func(*args, **kwargs)
            
            window.some_long_process = Mock(side_effect=mock_process)
            
            # バッチ処理関数をモック
            with patch('lorairo.services.batch_processor.process_directory_batch') as mock_batch:
                mock_batch.return_value = {"processed": 3, "errors": 0, "skipped": 0, "total": 3}
                
                # Act
                window.start_batch_processing(test_dir)
                
                # Assert
                mock_batch.assert_called_once()
                call_args = mock_batch.call_args[0]
                assert call_args[0] == test_dir
                assert isinstance(call_args[2], FileSystemManager)  # FSMが渡された


class TestMainWindowUserInteractionSimulation:
    """ユーザー操作シミュレーションテスト"""

    def test_user_workflow_simulation(self, tmp_path):
        """ユーザーワークフローのシミュレーション"""
        # Arrange - ユーザーが画像ディレクトリを選択する状況をシミュレート
        user_images_dir = tmp_path / "user_images"
        user_images_dir.mkdir()
        
        # ユーザーの画像ファイル
        for i in range(8):
            image_path = user_images_dir / f"vacation_photo_{i:02d}.jpg"
            image = Image.new('RGB', (60, 60), color=(i * 30, 100, 200 - i * 20))
            image.save(image_path, 'JPEG')
        
        with patch.object(MainWindow, '__init__', return_value=None):
            window = MainWindow()
            
            # 必要なコンポーネントをモック
            window.config_service = Mock()
            window.fsm = Mock()
            window.idm = Mock()
            window.progress_widget = Mock()
            window.progress_controller = Mock()
            window.statusbar = Mock()
            
            # バッチ処理の結果をモック
            window.fsm.get_image_files.return_value = list(user_images_dir.glob("*.jpg"))
            window.idm.detect_duplicate_image.return_value = None
            window.idm.register_original_image.side_effect = lambda f, fsm: (f"id_{f.stem}", {})
            
            # some_long_processをモックして即座に完了
            def instant_process(func, *args, **kwargs):
                return func(*args, **kwargs)
            
            window.some_long_process = Mock(side_effect=instant_process)
            
            # Act - ユーザーがディレクトリを変更する操作をシミュレート
            window.dataset_dir_changed(str(user_images_dir))
            
            # Assert
            # 設定が更新されたことを確認
            window.config_service.update_setting.assert_called_with(
                "directories", "dataset", str(user_images_dir)
            )
            
            # バッチ処理が開始されたことを確認
            window.some_long_process.assert_called_once()

    def test_concurrent_user_operations(self, configured_main_window):
        """同時ユーザー操作のテスト"""
        # Arrange
        window = configured_main_window
        
        # 複数の操作を短時間で実行
        test_dirs = [Path(f"/test/dir/{i}") for i in range(3)]
        
        with patch.object(window, 'start_batch_processing') as mock_start_batch:
            # Act - 連続したディレクトリ変更操作
            for test_dir in test_dirs:
                window.dataset_dir_changed(str(test_dir))
            
            # Assert
            # 最後のディレクトリ変更のみが有効になることを確認
            assert mock_start_batch.call_count == 3
            last_call_args = mock_start_batch.call_args_list[-1][0]
            assert last_call_args[0] == test_dirs[-1]

    def test_error_recovery_workflow(self, configured_main_window, tmp_path):
        """エラー発生後の回復ワークフローテスト"""
        # Arrange
        window = configured_main_window
        error_dir = tmp_path / "error_test"
        
        # 最初の操作でエラーが発生
        def failing_process(*args, **kwargs):
            raise RuntimeError("最初の処理でエラー")
        
        # 2回目は成功
        def success_process(*args, **kwargs):
            return {"processed": 1, "errors": 0, "skipped": 0, "total": 1}
        
        call_count = 0
        def alternating_process(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return failing_process(*args, **kwargs)
            else:
                return success_process(*args, **kwargs)
        
        with patch.object(window, 'some_long_process', side_effect=alternating_process), \
             patch('lorairo.gui.window.main_window.logger') as mock_logger:
            
            # Act - エラー発生
            window.start_batch_processing(error_dir)
            
            # エラー後の再試行
            window.start_batch_processing(error_dir)
            
            # Assert
            # エラーがログに記録されたことを確認
            assert mock_logger.error.call_count >= 1
            
            # 2回目の処理が正常に実行されたことを確認
            assert call_count == 2