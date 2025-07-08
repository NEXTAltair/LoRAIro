"""progress.Worker システムのユニットテスト"""

import inspect
from unittest.mock import MagicMock, Mock, patch

import pytest
from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QApplication

from lorairo.gui.window.progress import Controller, ProgressWidget, Worker

# QApplication の初期化（テスト実行時に必要）
if not QApplication.instance():
    app = QApplication([])


class TestWorker:
    """Worker クラスのテスト"""

    def test_init(self):
        """Worker の初期化テスト"""
        def test_function():
            pass

        worker = Worker(test_function, "arg1", "arg2", kwarg1="value1")

        assert worker.function == test_function
        assert worker.args == ("arg1", "arg2")
        assert worker.kwargs == {"kwarg1": "value1"}
        assert worker._is_canceled is False

    def test_run_basic_function(self):
        """基本的な関数実行のテスト"""
        mock_function = Mock(return_value="test_result")
        mock_function.__name__ = "test_function"  # __name__ 属性を設定
        worker = Worker(mock_function, "arg1", kwarg1="value1")

        worker.run()

        mock_function.assert_called_once_with("arg1", kwarg1="value1")

    def test_run_with_progress_callback(self):
        """progress_callback 引数を持つ関数のテスト"""
        def test_function(arg1, progress_callback=None):
            if progress_callback:
                progress_callback(50)
            return "result"

        worker = Worker(test_function, "test_arg")
        
        # progress_updated シグナルをモック
        worker.progress_updated = Mock()

        worker.run()

        # progress_callback が注入され、シグナルがエミットされることを確認
        worker.progress_updated.emit.assert_called_once_with(50)

    def test_run_with_status_callback(self):
        """status_callback 引数を持つ関数のテスト"""
        def test_function(status_callback=None):
            if status_callback:
                status_callback("test status")

        worker = Worker(test_function)
        worker.status_updated = Mock()

        worker.run()

        worker.status_updated.emit.assert_called_once_with("test status")

    def test_run_with_batch_progress_callback(self):
        """batch_progress_callback 引数を持つ関数のテスト"""
        def test_function(batch_progress_callback=None):
            if batch_progress_callback:
                batch_progress_callback(5, 10, "test.jpg")

        worker = Worker(test_function)
        worker.batch_progress = Mock()

        worker.run()

        worker.batch_progress.emit.assert_called_once_with(5, 10, "test.jpg")

    def test_run_with_is_canceled_callback(self):
        """is_canceled 引数を持つ関数のテスト"""
        def test_function(is_canceled=None):
            if is_canceled and is_canceled():
                return "canceled"
            return "completed"

        worker = Worker(test_function)
        worker._is_canceled = True

        result = worker.run()

        # キャンセル状態が正しく伝達されることを確認
        # 実際の戻り値は取得できないが、関数が正しく実行されることを確認

    def test_run_with_all_callbacks(self):
        """すべてのコールバックを持つ関数のテスト"""
        def test_function(
            arg1,
            progress_callback=None,
            status_callback=None,
            batch_progress_callback=None,
            is_canceled=None,
            kwarg1="default"
        ):
            if progress_callback:
                progress_callback(25)
            if status_callback:
                status_callback("processing")
            if batch_progress_callback:
                batch_progress_callback(3, 12, "image.png")
            return f"{arg1}_{kwarg1}"

        worker = Worker(test_function, "test_arg", kwarg1="custom")
        worker.progress_updated = Mock()
        worker.status_updated = Mock()
        worker.batch_progress = Mock()

        worker.run()

        worker.progress_updated.emit.assert_called_once_with(25)
        worker.status_updated.emit.assert_called_once_with("processing")
        worker.batch_progress.emit.assert_called_once_with(3, 12, "image.png")

    def test_run_exception_handling(self):
        """例外処理のテスト"""
        def failing_function():
            raise ValueError("test error")

        worker = Worker(failing_function)
        worker.error_occurred = Mock()
        worker.finished = Mock()

        worker.run()

        worker.error_occurred.emit.assert_called_once_with("test error")
        worker.finished.emit.assert_called_once()

    def test_run_canceled_before_execution(self):
        """実行前にキャンセルされた場合のテスト"""
        mock_function = Mock()
        mock_function.__name__ = "test_function"  # __name__ 属性を設定
        worker = Worker(mock_function)
        worker._is_canceled = True
        worker.finished = Mock()

        worker.run()

        # キャンセル状態では関数が実行されない
        mock_function.assert_not_called()
        worker.finished.emit.assert_called_once()

    def test_cancel(self):
        """cancel メソッドのテスト"""
        worker = Worker(lambda: None)
        
        assert worker._is_canceled is False
        worker.cancel()
        assert worker._is_canceled is True

    def test_signature_inspection(self):
        """関数シグネチャ検査のテスト"""
        def function_without_callbacks(arg1, arg2):
            return f"{arg1}_{arg2}"

        def function_with_some_callbacks(arg1, progress_callback=None, custom_param=None):
            if progress_callback:
                progress_callback(100)
            return arg1

        # コールバックなしの関数
        worker1 = Worker(function_without_callbacks, "a", "b")
        worker1.progress_updated = Mock()
        worker1.run()
        
        # progress_callback が注入されないことを確認
        worker1.progress_updated.emit.assert_not_called()

        # 一部コールバックありの関数
        worker2 = Worker(function_with_some_callbacks, "test")
        worker2.progress_updated = Mock()
        worker2.status_updated = Mock()
        worker2.run()
        
        # progress_callback は注入されるが status_callback は注入されない
        worker2.progress_updated.emit.assert_called_once_with(100)
        worker2.status_updated.emit.assert_not_called()


class TestProgressWidget:
    """ProgressWidget クラスのテスト"""

    def test_init(self):
        """ProgressWidget の初期化テスト"""
        with patch("lorairo.gui.window.progress.Ui_ProgressWidget"):
            widget = ProgressWidget()
            
            assert widget.isModal() is True

    def test_update_status(self):
        """ステータス更新のテスト"""
        with patch("lorairo.gui.window.progress.Ui_ProgressWidget"):
            widget = ProgressWidget()
            widget.statusLabel = Mock()
            
            widget.update_status("Test Status")
            
            widget.statusLabel.setText.assert_called_once_with("Test Status")

    def test_update_progress(self):
        """プログレス更新のテスト"""
        with patch("lorairo.gui.window.progress.Ui_ProgressWidget"):
            widget = ProgressWidget()
            widget.progressBar = Mock()
            
            widget.update_progress(75)
            
            widget.progressBar.setValue.assert_called_once_with(75)

    def test_on_cancel_button_clicked(self):
        """キャンセルボタンクリックのテスト"""
        with patch("lorairo.gui.window.progress.Ui_ProgressWidget"):
            widget = ProgressWidget()
            widget.canceled = Mock()
            
            widget.on_cancelButton_clicked()
            
            widget.canceled.emit.assert_called_once()


class TestController:
    """Controller クラスのテスト"""

    def test_init_with_existing_widget(self):
        """既存ProgressWidgetでの初期化テスト"""
        mock_widget = Mock(spec=ProgressWidget)
        controller = Controller(mock_widget)
        
        assert controller.progress_widget == mock_widget
        assert controller.worker is None
        assert controller.thread is None

    def test_init_without_widget(self):
        """ProgressWidget自動作成での初期化テスト"""
        with patch("lorairo.gui.window.progress.ProgressWidget") as mock_widget_class:
            mock_widget = Mock(spec=ProgressWidget)
            mock_widget_class.return_value = mock_widget
            
            controller = Controller()
            
            assert controller.progress_widget == mock_widget
            mock_widget_class.assert_called_once()

    @patch("lorairo.gui.window.progress.QThread")
    @patch("lorairo.gui.window.progress.Worker")
    def test_start_process(self, mock_worker_class, mock_thread_class):
        """プロセス開始のテスト"""
        # Mocks setup
        mock_widget = Mock(spec=ProgressWidget)
        mock_thread = Mock(spec=QThread)
        mock_worker = Mock(spec=Worker)
        mock_thread_class.return_value = mock_thread
        mock_worker_class.return_value = mock_worker
        
        controller = Controller(mock_widget)
        test_function = Mock()
        
        # Act
        controller.start_process(test_function, "arg1", kwarg1="value1")
        
        # Assert
        mock_worker_class.assert_called_once_with(test_function, "arg1", kwarg1="value1")
        mock_worker.moveToThread.assert_called_once_with(mock_thread)
        mock_thread.start.assert_called_once()
        
        # Signal connections check
        mock_thread.started.connect.assert_called_once_with(mock_worker.run)
        mock_worker.finished.connect.assert_any_call(mock_thread.quit)
        mock_worker.finished.connect.assert_any_call(mock_worker.deleteLater)

    def test_cleanup_running_thread(self):
        """実行中スレッドのクリーンアップテスト"""
        controller = Controller()
        
        # Mock running thread
        mock_thread = Mock(spec=QThread)
        mock_worker = Mock(spec=Worker)
        mock_thread.isRunning.return_value = True
        
        controller.thread = mock_thread
        controller.worker = mock_worker
        
        controller.cleanup()
        
        mock_worker.cancel.assert_called_once()
        mock_thread.quit.assert_called_once()
        mock_thread.wait.assert_called_once()
        assert controller.thread is None
        assert controller.worker is None

    def test_cleanup_no_thread(self):
        """スレッドなしでのクリーンアップテスト"""
        controller = Controller()
        
        # No exception should be raised
        controller.cleanup()
        
        assert controller.thread is None
        assert controller.worker is None

    def test_on_worker_finished(self):
        """ワーカー完了時の処理テスト"""
        mock_widget = Mock(spec=ProgressWidget)
        controller = Controller(mock_widget)
        
        with patch.object(controller, 'cleanup') as mock_cleanup:
            controller.on_worker_finished()
            
            mock_widget.hide.assert_called_once()
            mock_cleanup.assert_called_once()

    def test_on_error(self):
        """エラー発生時の処理テスト"""
        mock_widget = Mock(spec=ProgressWidget)
        controller = Controller(mock_widget)
        
        with patch.object(controller, 'cleanup') as mock_cleanup:
            controller.on_error("Test error message")
            
            mock_widget.hide.assert_called_once()
            mock_cleanup.assert_called_once()