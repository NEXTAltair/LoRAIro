"""
Progress.Workerシステム統合テスト
実際のスレッド、シグナル、長時間処理との統合をテストする
"""

import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch
from threading import Event

import pytest
from PySide6.QtCore import QObject, QTimer, Signal, QEventLoop
from PySide6.QtWidgets import QApplication

from lorairo.gui.window.progress import Worker, Controller, ProgressWidget
from lorairo.services.batch_processor import process_directory_batch
from lorairo.services.annotation_service import AnnotationService, run_annotation_task

# QApplication の初期化（テスト実行時に必要）
if not QApplication.instance():
    app = QApplication([])


class TestWorkerSystemIntegration:
    """Progress.Workerシステムの統合テスト"""

    @pytest.fixture
    def mock_long_function(self):
        """長時間実行をシミュレートする関数"""
        def long_function(duration=0.1, progress_callback=None, status_callback=None, is_canceled=None):
            steps = 10
            step_duration = duration / steps
            
            for i in range(steps):
                if is_canceled and is_canceled():
                    if status_callback:
                        status_callback("処理がキャンセルされました")
                    return "canceled"
                
                if progress_callback:
                    progress_callback(int((i + 1) * 100 / steps))
                
                if status_callback:
                    status_callback(f"ステップ {i + 1}/{steps} 実行中")
                
                time.sleep(step_duration)
            
            return "completed"
        
        return long_function

    def test_worker_with_real_thread_execution(self, mock_long_function):
        """実際のスレッドでのWorker実行統合テスト"""
        # Arrange
        worker = Worker(mock_long_function, duration=0.2)
        
        # シグナル受信用のモック
        progress_signals = []
        status_signals = []
        finished_called = Event()
        
        def on_progress(value):
            progress_signals.append(value)
        
        def on_status(message):
            status_signals.append(message)
        
        def on_finished():
            finished_called.set()
        
        worker.progress_updated.connect(on_progress)
        worker.status_updated.connect(on_status)
        worker.finished.connect(on_finished)
        
        # Act
        worker.run()
        
        # 完了まで待機（最大3秒）
        assert finished_called.wait(timeout=3.0), "Workerが時間内に完了しませんでした"
        
        # Assert
        assert len(progress_signals) == 10  # 10ステップの進捗
        assert progress_signals == [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        assert len(status_signals) == 10   # 10ステップのステータス
        assert all("ステップ" in msg for msg in status_signals)

    def test_worker_cancellation_integration(self, mock_long_function):
        """Workerキャンセル機能の統合テスト"""
        # Arrange
        worker = Worker(mock_long_function, duration=1.0)  # 1秒の処理
        
        status_signals = []
        finished_called = Event()
        
        def on_status(message):
            status_signals.append(message)
        
        def on_finished():
            finished_called.set()
        
        worker.status_updated.connect(on_status)
        worker.finished.connect(on_finished)
        
        # 処理開始後すぐにキャンセル
        def cancel_after_delay():
            time.sleep(0.1)  # 少し待ってからキャンセル
            worker.cancel()
        
        import threading
        cancel_thread = threading.Thread(target=cancel_after_delay)
        cancel_thread.start()
        
        # Act
        worker.run()
        
        # 完了まで待機
        assert finished_called.wait(timeout=2.0), "Workerが時間内に完了しませんでした"
        cancel_thread.join()
        
        # Assert
        # キャンセルメッセージが送信されたことを確認
        assert any("キャンセル" in msg for msg in status_signals)

    def test_controller_with_real_worker_integration(self, mock_long_function):
        """ControllerとWorkerの統合テスト"""
        # Arrange
        progress_widget = ProgressWidget()
        controller = Controller(progress_widget)
        
        progress_values = []
        status_messages = []
        finished_called = Event()
        
        def track_progress(value):
            progress_values.append(value)
        
        def track_status(message):
            status_messages.append(message)
        
        def on_finished():
            finished_called.set()
        
        # シグナル接続のためのイベントループ
        loop = QEventLoop()
        
        # Controller開始
        controller.start_process(mock_long_function, duration=0.3)
        
        # Workerが作成されるまで少し待つ
        time.sleep(0.05)
        
        if controller.worker:
            controller.worker.progress_updated.connect(track_progress)
            controller.worker.status_updated.connect(track_status)
            controller.worker.finished.connect(on_finished)
            controller.worker.finished.connect(loop.quit)
        
        # Act
        # イベントループを実行して非同期処理を待つ
        QTimer.singleShot(1000, loop.quit)  # 最大1秒でタイムアウト
        loop.exec()
        
        # Assert
        assert len(progress_values) > 0, "進捗シグナルが受信されませんでした"
        assert len(status_messages) > 0, "ステータスシグナルが受信されませんでした"
        
        # プログレスウィジェットが非表示になったことを確認
        # (実際にはon_worker_finishedで非表示になる)
        
        # Cleanup
        controller.cleanup()
        progress_widget.close()

    def test_batch_processor_with_worker_integration(self, tmp_path):
        """BatchProcessorとWorkerシステムの統合テスト"""
        # Arrange
        from PIL import Image
        
        # テスト画像作成
        test_dir = tmp_path / "batch_test"
        test_dir.mkdir()
        
        for i in range(5):
            image_path = test_dir / f"test_{i}.jpg"
            image = Image.new('RGB', (20, 20), color=(i * 50, 0, 0))
            image.save(image_path, 'JPEG')
        
        # モックサービス
        config_service = Mock()
        fsm = Mock()
        fsm.get_image_files.return_value = list(test_dir.glob("*.jpg"))
        
        idm = Mock()
        idm.detect_duplicate_image.return_value = None
        idm.register_original_image.side_effect = lambda file, fs: (f"id_{file.stem}", {"metadata": "test"})
        
        # Progress tracking
        batch_progress_calls = []
        status_calls = []
        
        def track_batch_progress(current, total, filename):
            batch_progress_calls.append((current, total, filename))
        
        def track_status(message):
            status_calls.append(message)
        
        # WorkerでBatchProcessorを実行
        worker = Worker(
            process_directory_batch,
            test_dir,
            config_service,
            fsm,
            idm,
        )
        
        finished_called = Event()
        result_container = {}
        
        def capture_result():
            # Workerの実行結果をキャプチャする方法は限定的
            # 実際の使用ではシグナルで結果を受け取る
            finished_called.set()
        
        worker.finished.connect(capture_result)
        
        # Workerシステムで動的にコールバックが注入されることをテスト
        # この場合、batch_progress_callbackが自動的に注入される
        
        # Act
        worker.run()
        
        # 完了まで待機
        assert finished_called.wait(timeout=3.0), "バッチ処理が時間内に完了しませんでした"
        
        # Assert
        # idm.register_original_imageが各画像で呼ばれたことを確認
        assert idm.register_original_image.call_count == 5


class TestAnnotationServiceIntegration:
    """AnnotationServiceの統合テスト"""

    def test_annotation_service_with_worker_system(self):
        """AnnotationServiceとWorkerシステムの統合テスト"""
        # Arrange
        from PIL import Image
        
        # テスト画像作成
        test_images = []
        for i in range(2):
            image = Image.new('RGB', (30, 30), color=(i * 100, 0, 0))
            test_images.append(image)
        
        phash_list = [f"hash_{i}" for i in range(2)]
        models = ["test_model"]
        
        # AnnotationServiceの動作をモック
        with patch('lorairo.services.annotation_service.annotate') as mock_annotate:
            mock_result = {
                "hash_0": {"test_model": {"tags": ["tag1", "tag2"], "error": None}},
                "hash_1": {"test_model": {"tags": ["tag3", "tag4"], "error": None}}
            }
            mock_annotate.return_value = mock_result
            
            service = AnnotationService()
            
            # シグナル受信用
            result_received = Event()
            captured_result = {}
            
            def on_annotation_finished(result):
                captured_result['result'] = result
                result_received.set()
            
            def on_annotation_error(error):
                captured_result['error'] = error
                result_received.set()
            
            service.annotationFinished.connect(on_annotation_finished)
            service.annotationError.connect(on_annotation_error)
            
            # Act
            service.start_annotation(test_images, phash_list, models)
            
            # 結果まで待機
            assert result_received.wait(timeout=5.0), "アノテーション処理が時間内に完了しませんでした"
            
            # Assert
            assert 'result' in captured_result, f"エラーが発生しました: {captured_result.get('error')}"
            assert captured_result['result'] == mock_result
            mock_annotate.assert_called_once_with(test_images, models, phash_list)

    def test_annotation_task_function_integration(self):
        """run_annotation_task関数の統合テスト"""
        # Arrange
        from PIL import Image
        
        test_images = [Image.new('RGB', (25, 25), color='yellow')]
        phash_list = ["test_hash"]
        models = ["test_model"]
        
        progress_values = []
        status_messages = []
        
        def track_progress(value):
            progress_values.append(value)
        
        def track_status(message):
            status_messages.append(message)
        
        # Annotationライブラリをモック
        with patch('lorairo.services.annotation_service.annotate') as mock_annotate:
            mock_result = {"test_hash": {"test_model": {"tags": ["test_tag"], "error": None}}}
            mock_annotate.return_value = mock_result
            
            # Act
            result = run_annotation_task(
                test_images,
                phash_list,
                models,
                progress_callback=track_progress,
                status_callback=track_status
            )
            
            # Assert
            assert result == mock_result
            assert len(progress_values) >= 2  # 開始(10%)と完了(100%)
            assert 10 in progress_values  # 開始時の進捗
            assert 100 in progress_values  # 完了時の進捗
            assert len(status_messages) >= 2  # 開始と完了メッセージ
            assert any("開始" in msg for msg in status_messages)
            assert any("完了" in msg for msg in status_messages)


class TestWorkerSystemRobustness:
    """Workerシステムの堅牢性テスト"""

    def test_worker_exception_handling_integration(self):
        """Worker例外処理の統合テスト"""
        # Arrange
        def failing_function(progress_callback=None, status_callback=None):
            if progress_callback:
                progress_callback(50)
            if status_callback:
                status_callback("処理中にエラー発生")
            raise RuntimeError("テスト例外")
        
        worker = Worker(failing_function)
        
        error_called = Event()
        finished_called = Event()
        captured_error = {}
        
        def on_error(message):
            captured_error['message'] = message
            error_called.set()
        
        def on_finished():
            finished_called.set()
        
        worker.error_occurred.connect(on_error)
        worker.finished.connect(on_finished)
        
        # Act
        worker.run()
        
        # Assert
        assert error_called.wait(timeout=2.0), "エラーシグナルが発行されませんでした"
        assert finished_called.wait(timeout=2.0), "完了シグナルが発行されませんでした"
        assert "テスト例外" in captured_error['message']

    def test_multiple_workers_concurrent_execution(self):
        """複数Workerの同時実行テスト"""
        # Arrange
        def counting_function(worker_id, progress_callback=None):
            for i in range(5):
                if progress_callback:
                    progress_callback((i + 1) * 20)
                time.sleep(0.02)  # 短い待機
            return f"worker_{worker_id}_completed"
        
        workers = []
        finished_counts = []
        
        for i in range(3):
            worker = Worker(counting_function, worker_id=i)
            
            def make_finish_handler(worker_id):
                def on_finished():
                    finished_counts.append(worker_id)
                return on_finished
            
            worker.finished.connect(make_finish_handler(i))
            workers.append(worker)
        
        # Act
        for worker in workers:
            worker.run()  # 同期実行だが、各Workerは独立
        
        # Assert
        # すべてのWorkerが完了したことを確認
        assert len(finished_counts) == 3
        assert set(finished_counts) == {0, 1, 2}

    def test_worker_memory_cleanup(self, mock_long_function):
        """Workerのメモリクリーンアップテスト"""
        # Arrange
        import gc
        import weakref
        
        # 大量のデータを含む関数
        def memory_intensive_function(large_data, progress_callback=None):
            # 大きなデータを処理するシミュレーション
            result = sum(large_data)
            if progress_callback:
                progress_callback(100)
            return result
        
        large_data = list(range(10000))  # 大きなリスト
        
        # Workerの弱参照を作成
        worker = Worker(memory_intensive_function, large_data)
        worker_ref = weakref.ref(worker)
        
        finished_called = Event()
        worker.finished.connect(lambda: finished_called.set())
        
        # Act
        worker.run()
        assert finished_called.wait(timeout=2.0)
        
        # Workerの参照を削除
        del worker
        gc.collect()  # ガベージコレクション強制実行
        
        # Assert
        # Workerがガベージコレクションされたことを確認
        assert worker_ref() is None, "Workerのメモリリークが発生している可能性があります"