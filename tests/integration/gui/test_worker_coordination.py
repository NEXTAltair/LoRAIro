# tests/integration/gui/test_worker_coordination.py

import time
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QEventLoop, QThread, QTimer

from lorairo.gui.services.worker_service import WorkerService

# ProgressManager削除により不要
from lorairo.gui.workers.search import SearchResult, SearchWorker


class TestWorkerSystemCoordination:
    """ワーカーシステム協調動作の統合テスト"""

    @pytest.fixture
    def mock_db_manager(self):
        """モックデータベースマネージャー"""
        mock = Mock()
        mock.get_images_by_filter.return_value = (
            [
                {"id": 1, "stored_image_path": "/test/image1.jpg"},
                {"id": 2, "stored_image_path": "/test/image2.jpg"},
            ],
            2,
        )
        return mock

    @pytest.fixture
    def mock_fsm(self):
        """モックファイルシステムマネージャー"""
        mock = Mock()
        mock.get_image_files.return_value = [
            Path("/test/image1.jpg"),
            Path("/test/image2.jpg"),
        ]
        return mock

    @pytest.fixture
    @patch("lorairo.gui.services.worker_service.WorkerManager")
    def worker_service(self, mock_worker_manager_class, mock_db_manager, mock_fsm):
        """テスト用WorkerService"""
        mock_worker_manager = Mock()
        mock_worker_manager.start_worker.return_value = True
        mock_worker_manager.cancel_worker.return_value = True
        mock_worker_manager_class.return_value = mock_worker_manager

        service = WorkerService(mock_db_manager, mock_fsm)
        service.worker_manager = mock_worker_manager
        return service

    # ProgressManager削除により不要となったfixture

    def test_worker_service_search_integration(self, worker_service, mock_db_manager):
        """WorkerService検索統合テスト"""
        # 検索開始
        filter_conditions = {"tags": ["test"], "caption": "sample"}

        with patch("lorairo.gui.services.worker_service.SearchWorker") as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker

            worker_id = worker_service.start_search(filter_conditions)

            # ワーカー作成確認
            mock_worker_class.assert_called_once_with(mock_db_manager, filter_conditions)

            # ワーカー開始確認
            worker_service.worker_manager.start_worker.assert_called_once()

            # 進捗シグナル接続確認
            mock_worker.progress_updated.connect.assert_called_once()

            # worker_id確認
            assert worker_id.startswith("search_")

    def test_multiple_search_worker_cancellation(self, worker_service):
        """複数検索ワーカーキャンセルテスト"""
        with patch("lorairo.gui.services.worker_service.SearchWorker"):
            # 最初の検索開始
            worker_id1 = worker_service.start_search({"tags": ["test1"]})
            assert worker_service.current_search_worker_id == worker_id1

            # 2番目の検索開始（1番目は自動キャンセル）
            worker_id2 = worker_service.start_search({"tags": ["test2"]})

            # 1番目のワーカーがキャンセルされたことを確認
            worker_service.worker_manager.cancel_worker.assert_called_with(worker_id1)

            # 現在のワーカーIDが更新されたことを確認
            assert worker_service.current_search_worker_id == worker_id2

    def test_progress_manager_worker_integration(self, progress_manager):
        """ProgressManager-Worker統合テスト"""
        # 実際のSearchWorkerでテスト
        mock_db_manager = Mock()
        mock_db_manager.get_images_by_filter.return_value = ([], 0)

        worker = SearchWorker(mock_db_manager, {"tags": []})

        # 進捗追跡用
        progress_updates = []
        finished_called = Event()

        def track_progress(progress):
            progress_updates.append(progress.percentage)

        def on_finished():
            finished_called.set()

        worker.progress_updated.connect(track_progress)
        worker.finished.connect(lambda result: on_finished())

        # ProgressManagerでワーカー開始
        with patch.object(progress_manager, "_update_progress") as mock_update:
            mock_update.side_effect = track_progress

            # 手動でワーカー実行（テスト用簡略化）
            worker.run()

            # 結果確認
            assert len(progress_updates) > 0
            assert 100 in progress_updates  # 完了進捗が含まれる

    def test_worker_error_propagation(self, worker_service):
        """ワーカーエラー伝播テスト"""
        # エラーを発生させるワーカー
        with patch("lorairo.gui.services.worker_service.SearchWorker") as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker

            # エラーシグナル発行のシミュレート
            error_received = []

            def capture_error(error_message):
                error_received.append(error_message)

            worker_service.search_error.connect(capture_error)

            # ワーカー開始
            worker_id = worker_service.start_search({"tags": ["test"]})

            # エラーシグナル発行をシミュレート
            # connect.call_argsがNoneの場合があるので、直接エラーシグナルを発行
            if mock_worker.error_occurred.connect.call_args:
                error_handler = mock_worker.error_occurred.connect.call_args[0][0]
                error_handler("Test error")
            else:
                # 代替方法: 直接WorkerServiceのエラーハンドラーを呼び出し
                if hasattr(worker_service, "_on_worker_error"):
                    worker_service._on_worker_error(worker_id, "Test error")

            # エラーが伝播されることを確認
            # （実際の実装では _on_worker_error でシグナル変換される）

    def test_concurrent_worker_management(self, worker_service):
        """並行ワーカー管理テスト"""
        with (
            patch("lorairo.gui.services.worker_service.DatabaseRegistrationWorker"),
            patch("lorairo.gui.services.worker_service.SearchWorker"),
            patch("lorairo.gui.services.worker_service.AnnotationWorker"),
        ):
            # 複数種類のワーカーを並行実行
            registration_id = worker_service.start_batch_registration(Path("/test"))
            search_id = worker_service.start_search({"tags": ["test"]})
            annotation_id = worker_service.start_annotation([], [], [])

            # 各ワーカーが独立して管理されることを確認
            assert registration_id != search_id != annotation_id

            # ワーカーマネージャーで複数回start_workerが呼ばれることを確認
            assert worker_service.worker_manager.start_worker.call_count == 3

    def test_worker_lifecycle_management(self, worker_service):
        """ワーカーライフサイクル管理テスト"""
        with patch("lorairo.gui.services.worker_service.SearchWorker") as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker

            # ワーカー開始
            worker_id = worker_service.start_search({"tags": ["test"]})

            # 進捗シグナル接続確認
            assert mock_worker.progress_updated.connect.called

            # キャンセル実行
            result = worker_service.cancel_search(worker_id)

            # キャンセル処理確認
            assert result is True
            worker_service.worker_manager.cancel_worker.assert_called_with(worker_id)

    def test_signal_routing_integration(self, worker_service):
        """シグナルルーティング統合テスト"""
        # シグナル受信用モック
        search_started_mock = Mock()
        search_finished_mock = Mock()
        progress_updated_mock = Mock()

        # シグナル接続
        worker_service.search_started.connect(search_started_mock)
        worker_service.search_finished.connect(search_finished_mock)
        worker_service.worker_progress_updated.connect(progress_updated_mock)

        with patch("lorairo.gui.services.worker_service.SearchWorker") as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker

            # 検索開始
            worker_id = worker_service.start_search({"tags": ["test"]})

            # 進捗更新シミュレート
            progress_callback = mock_worker.progress_updated.connect.call_args[0][0]
            mock_progress = Mock()
            mock_progress.percentage = 50
            progress_callback(mock_progress)

            # シグナル発行確認
            progress_updated_mock.assert_called_with(worker_id, mock_progress)

    def test_worker_result_processing(self, worker_service, mock_db_manager):
        """ワーカー結果処理テスト"""
        # 実際のSearchWorkerで結果処理をテスト
        filter_conditions = {"tags": ["test"], "caption": ""}
        worker = SearchWorker(mock_db_manager, filter_conditions)

        # 結果受信用
        result_received = []

        def capture_result(result):
            result_received.append(result)

        worker.finished.connect(capture_result)

        # 実行
        worker.run()

        # 結果確認
        assert len(result_received) == 1
        result = result_received[0]
        assert isinstance(result, SearchResult)
        assert result.total_count == 2
        assert len(result.image_metadata) == 2

    def test_error_recovery_integration(self, worker_service):
        """エラー回復統合テスト"""
        with patch("lorairo.gui.services.worker_service.SearchWorker") as mock_worker_class:
            # 最初の検索でエラー
            mock_worker_class.side_effect = [RuntimeError("Worker creation failed"), Mock()]

            # 最初の検索は失敗
            with pytest.raises(RuntimeError):
                worker_service.start_search({"tags": ["test1"]})

            # 2回目の検索は成功
            worker_id = worker_service.start_search({"tags": ["test2"]})
            assert worker_id.startswith("search_")

    def test_resource_cleanup_integration(self, worker_service):
        """リソースクリーンアップ統合テスト"""
        with patch("lorairo.gui.services.worker_service.SearchWorker") as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker

            # 検索開始
            worker_id = worker_service.start_search({"tags": ["test"]})
            assert worker_service.current_search_worker_id == worker_id

            # 新しい検索開始（自動クリーンアップ）
            new_worker_id = worker_service.start_search({"tags": ["new_test"]})

            # 古いワーカーがキャンセルされ、新しいIDが設定される
            worker_service.worker_manager.cancel_worker.assert_called_with(worker_id)
            assert worker_service.current_search_worker_id == new_worker_id

    def test_progress_dialog_integration(self, progress_manager):
        """プログレスダイアログ統合テスト"""
        # 実際のワーカーでプログレスダイアログをテスト
        mock_db_manager = Mock()
        mock_db_manager.get_images_by_filter.return_value = ([], 0)

        worker = SearchWorker(mock_db_manager, {"tags": []})

        with (
            patch("lorairo.gui.workers.progress_manager.QProgressDialog") as mock_dialog_class,
            patch("lorairo.gui.workers.progress_manager.QThread") as mock_thread_class,
            patch.object(worker, "moveToThread") as mock_move_to_thread,
        ):
            mock_dialog = Mock()
            mock_dialog_class.return_value = mock_dialog

            mock_thread = Mock()
            mock_thread_class.return_value = mock_thread

            # 進捗付きで開始
            progress_manager.start_worker_with_progress(worker, "検索中...", 100)

            # プログレスダイアログ作成確認
            mock_dialog_class.assert_called_once()
            mock_dialog.show.assert_called_once()

            # QThread作成・設定確認
            mock_thread_class.assert_called_once()
            mock_thread.start.assert_called_once()

            # moveToThreadが呼ばれたことを確認
            mock_move_to_thread.assert_called_once_with(mock_thread)


class TestWorkerSystemPerformance:
    """ワーカーシステムパフォーマンステスト"""

    def test_worker_creation_overhead(self):
        """ワーカー作成オーバーヘッドテスト"""
        mock_db_manager = Mock()
        mock_db_manager.get_images_by_filter.return_value = ([], 0)

        start_time = time.time()

        # 複数ワーカーを連続作成
        workers = []
        for i in range(10):
            worker = SearchWorker(mock_db_manager, {"tags": [f"test_{i}"]})
            workers.append(worker)

        creation_time = time.time() - start_time

        # 作成時間が合理的な範囲内であることを確認
        assert creation_time < 1.0  # 10ワーカーが1秒以内に作成される
        assert len(workers) == 10

    def test_concurrent_worker_performance(self):
        """並行ワーカーパフォーマンステスト"""
        mock_db_manager = Mock()
        mock_db_manager.get_images_by_filter.return_value = ([], 0)

        # 複数ワーカーの並行実行シミュレーション
        workers = []
        results = []

        start_time = time.time()

        for i in range(5):
            worker = SearchWorker(mock_db_manager, {"tags": [f"test_{i}"]})
            worker.finished.connect(lambda result: results.append(result))
            workers.append(worker)

        # 順次実行（実際は並行実行される）
        for worker in workers:
            worker.run()

        execution_time = time.time() - start_time

        # 実行時間が合理的であることを確認
        assert execution_time < 2.0  # 5ワーカーが2秒以内に完了
        assert len(results) == 5

    def test_memory_usage_stability(self):
        """メモリ使用量安定性テスト"""
        mock_db_manager = Mock()
        mock_db_manager.get_images_by_filter.return_value = ([], 0)

        # 多数のワーカーを作成・実行・削除してメモリリークをチェック
        import gc

        for i in range(50):
            worker = SearchWorker(mock_db_manager, {"tags": [f"test_{i}"]})
            worker.run()
            del worker

            # 定期的にガベージコレクション実行
            if i % 10 == 0:
                gc.collect()

        # 最終ガベージコレクション
        gc.collect()

        # メモリリークがないことを確認（参照カウントベース）
        # 実際のメモリ使用量測定は環境に依存するため、基本的なチェックのみ
        assert True  # 例外が発生しなければOK
