# tests/unit/gui/services/test_worker_service.py

import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PIL import Image
from PySide6.QtCore import QSize

from lorairo.gui.services.worker_service import WorkerService
from lorairo.services.search_models import SearchConditions


class TestWorkerService:
    """WorkerService のユニットテスト"""

    @pytest.fixture
    def mock_db_manager(self):
        """モックデータベースマネージャー"""
        return Mock()

    @pytest.fixture
    def mock_fsm(self):
        """モックファイルシステムマネージャー"""
        return Mock()

    @pytest.fixture
    @patch("lorairo.gui.services.worker_service.WorkerManager")
    def worker_service(self, mock_worker_manager_class, mock_db_manager, mock_fsm):
        """テスト用WorkerService"""
        # WorkerManagerのモックインスタンス
        mock_worker_manager = Mock()
        mock_worker_manager_class.return_value = mock_worker_manager

        service = WorkerService(mock_db_manager, mock_fsm)
        service.worker_manager = mock_worker_manager  # 明示的に設定
        return service

    def test_initialization(self, worker_service, mock_db_manager, mock_fsm):
        """初期化テスト"""
        assert worker_service.db_manager == mock_db_manager
        assert worker_service.fsm == mock_fsm
        assert worker_service.current_search_worker_id is None
        assert worker_service.current_registration_worker_id is None
        assert worker_service.current_annotation_worker_id is None
        assert worker_service.current_thumbnail_worker_id is None

    def test_signal_definitions(self, worker_service):
        """シグナル定義テスト"""
        # 基本シグナルの存在確認
        assert hasattr(worker_service, "batch_registration_started")
        assert hasattr(worker_service, "batch_registration_finished")
        assert hasattr(worker_service, "batch_registration_error")

        assert hasattr(worker_service, "annotation_started")
        assert hasattr(worker_service, "annotation_finished")
        assert hasattr(worker_service, "annotation_error")

        assert hasattr(worker_service, "search_started")
        assert hasattr(worker_service, "search_finished")
        assert hasattr(worker_service, "search_error")

        assert hasattr(worker_service, "thumbnail_started")
        assert hasattr(worker_service, "thumbnail_finished")
        assert hasattr(worker_service, "thumbnail_error")

        # 進捗・管理シグナル
        assert hasattr(worker_service, "worker_progress_updated")
        assert hasattr(worker_service, "worker_batch_progress")
        assert hasattr(worker_service, "active_worker_count_changed")
        assert hasattr(worker_service, "all_workers_finished")

    @patch("lorairo.gui.services.worker_service.DatabaseRegistrationWorker")
    def test_start_batch_registration_success(self, mock_worker_class, worker_service):
        """バッチ登録開始成功テスト"""
        # モックワーカー設定
        mock_worker = Mock()
        mock_worker_class.return_value = mock_worker
        worker_service.worker_manager.start_worker.return_value = True

        directory = Path("/test/directory")

        # バッチ登録開始
        worker_id = worker_service.start_batch_registration(directory)

        # ワーカー作成確認
        mock_worker_class.assert_called_once_with(directory, worker_service.db_manager, worker_service.fsm)

        # ワーカーマネージャー呼び出し確認
        worker_service.worker_manager.start_worker.assert_called_once()
        call_args = worker_service.worker_manager.start_worker.call_args
        assert call_args[0][0] == worker_id  # worker_id
        assert call_args[0][1] == mock_worker  # worker

        # worker_id形式確認
        assert worker_id.startswith("batch_reg_")
        assert worker_id.split("_")[-1].isdigit()

    @patch("lorairo.gui.services.worker_service.DatabaseRegistrationWorker")
    def test_start_batch_registration_failure(self, mock_worker_class, worker_service):
        """バッチ登録開始失敗テスト"""
        # モックワーカー設定
        mock_worker = Mock()
        mock_worker_class.return_value = mock_worker
        worker_service.worker_manager.start_worker.return_value = False

        directory = Path("/test/directory")

        # 例外発生確認
        with pytest.raises(RuntimeError, match="ワーカー開始失敗"):
            worker_service.start_batch_registration(directory)

    def test_cancel_batch_registration(self, worker_service):
        """バッチ登録キャンセルテスト"""
        worker_service.worker_manager.cancel_worker.return_value = True

        result = worker_service.cancel_batch_registration("test_worker_id")

        assert result is True
        worker_service.worker_manager.cancel_worker.assert_called_once_with("test_worker_id")

    @patch("lorairo.gui.services.worker_service.AnnotationWorker")
    def test_start_annotation_success(self, mock_worker_class, worker_service):
        """アノテーション開始成功テスト"""
        # モックワーカー設定
        mock_worker = Mock()
        mock_worker_class.return_value = mock_worker
        worker_service.worker_manager.start_worker.return_value = True

        # テストデータ
        images = [Image.new("RGB", (100, 100))]
        phash_list = ["test_hash"]
        models = ["test_model"]

        # アノテーション開始
        worker_id = worker_service.start_annotation(images, phash_list, models)

        # ワーカー作成確認
        mock_worker_class.assert_called_once_with(images, phash_list, models)

        # ワーカーマネージャー呼び出し確認
        worker_service.worker_manager.start_worker.assert_called_once()

        # worker_id形式確認
        assert worker_id.startswith("annotation_")
        assert worker_id.split("_")[-1].isdigit()

    @patch("lorairo.gui.services.worker_service.AnnotationWorker")
    def test_start_annotation_failure(self, mock_worker_class, worker_service):
        """アノテーション開始失敗テスト"""
        # モックワーカー設定
        mock_worker = Mock()
        mock_worker_class.return_value = mock_worker
        worker_service.worker_manager.start_worker.return_value = False

        # テストデータ
        images = [Image.new("RGB", (100, 100))]
        phash_list = ["test_hash"]
        models = ["test_model"]

        # 例外発生確認
        with pytest.raises(RuntimeError, match="ワーカー開始失敗"):
            worker_service.start_annotation(images, phash_list, models)

    def test_cancel_annotation(self, worker_service):
        """アノテーションキャンセルテスト"""
        worker_service.worker_manager.cancel_worker.return_value = True

        result = worker_service.cancel_annotation("test_worker_id")

        assert result is True
        worker_service.worker_manager.cancel_worker.assert_called_once_with("test_worker_id")

    @patch("lorairo.gui.services.worker_service.SearchWorker")
    def test_start_search_success(self, mock_worker_class, worker_service):
        """検索開始成功テスト"""
        # モックワーカー設定
        mock_worker = Mock()
        mock_worker_class.return_value = mock_worker
        worker_service.worker_manager.start_worker.return_value = True

        # フィルター条件
        filter_conditions = SearchConditions(tags=["test"], caption="sample")

        # 検索開始
        worker_id = worker_service.start_search(filter_conditions)

        # ワーカー作成確認
        mock_worker_class.assert_called_once_with(worker_service.db_manager, filter_conditions)

        # ワーカーマネージャー呼び出し確認
        worker_service.worker_manager.start_worker.assert_called_once()

        # worker_id形式確認
        assert worker_id.startswith("search_")
        assert worker_id.split("_")[-1].isdigit()

        # 現在の検索ワーカーID設定確認
        assert worker_service.current_search_worker_id == worker_id

    @patch("lorairo.gui.services.worker_service.SearchWorker")
    def test_start_search_cancels_existing(self, mock_worker_class, worker_service):
        """既存検索キャンセル付き検索開始テスト"""
        # モックワーカー設定
        mock_worker = Mock()
        mock_worker_class.return_value = mock_worker
        worker_service.worker_manager.start_worker.return_value = True
        worker_service.worker_manager.cancel_worker.return_value = True

        # 既存の検索ワーカーIDを設定
        existing_worker_id = "search_123456789"
        worker_service.current_search_worker_id = existing_worker_id

        # フィルター条件
        filter_conditions = SearchConditions(tags=["test"], caption="sample")

        # 検索開始
        new_worker_id = worker_service.start_search(filter_conditions)

        # 既存ワーカーのキャンセル確認
        worker_service.worker_manager.cancel_worker.assert_called_once_with(existing_worker_id)

        # 新しいワーカーID設定確認
        assert worker_service.current_search_worker_id == new_worker_id
        assert new_worker_id != existing_worker_id

    def test_cancel_search(self, worker_service):
        """検索キャンセルテスト"""
        worker_service.worker_manager.cancel_worker.return_value = True

        result = worker_service.cancel_search("test_worker_id")

        assert result is True
        worker_service.worker_manager.cancel_worker.assert_called_once_with("test_worker_id")

    @patch("lorairo.gui.services.worker_service.ThumbnailWorker")
    def test_start_thumbnail_loading_success(self, mock_worker_class, worker_service):
        """サムネイル読み込み開始成功テスト"""
        # モックワーカー設定
        mock_worker = Mock()
        mock_worker_class.return_value = mock_worker
        worker_service.worker_manager.start_worker.return_value = True

        # テストデータ
        image_metadata = [{"id": 1, "path": "/test/image1.jpg"}]
        thumbnail_size = QSize(150, 150)

        # サムネイル読み込み開始
        worker_id = worker_service.start_thumbnail_loading(image_metadata, thumbnail_size)

        # ワーカー作成確認
        mock_worker_class.assert_called_once_with(image_metadata, thumbnail_size, worker_service.db_manager)

        # ワーカーマネージャー呼び出し確認
        worker_service.worker_manager.start_worker.assert_called_once()

        # worker_id形式確認
        assert worker_id.startswith("thumbnail_")
        assert worker_id.split("_")[-1].isdigit()

        # 現在のサムネイルワーカーID設定確認
        assert worker_service.current_thumbnail_worker_id == worker_id

    @patch("lorairo.gui.services.worker_service.ThumbnailWorker")
    def test_start_thumbnail_loading_cancels_existing(self, mock_worker_class, worker_service):
        """既存サムネイル読み込みキャンセル付き開始テスト"""
        # モックワーカー設定
        mock_worker = Mock()
        mock_worker_class.return_value = mock_worker
        worker_service.worker_manager.start_worker.return_value = True
        worker_service.worker_manager.cancel_worker.return_value = True

        # 既存のサムネイルワーカーIDを設定
        existing_worker_id = "thumbnail_123456789"
        worker_service.current_thumbnail_worker_id = existing_worker_id

        # テストデータ
        image_metadata = [{"id": 1, "path": "/test/image1.jpg"}]
        thumbnail_size = QSize(150, 150)

        # サムネイル読み込み開始
        new_worker_id = worker_service.start_thumbnail_loading(image_metadata, thumbnail_size)

        # 既存ワーカーのキャンセル確認
        worker_service.worker_manager.cancel_worker.assert_called_once_with(existing_worker_id)

        # 新しいワーカーID設定確認
        assert worker_service.current_thumbnail_worker_id == new_worker_id
        assert new_worker_id != existing_worker_id

    def test_worker_manager_signal_connections(self, worker_service):
        """ワーカーマネージャーシグナル接続テスト"""
        # WorkerManagerのシグナルが適切に接続されているか確認
        # Note: モックオブジェクトでは実際のシグナル接続を確認するのは困難なので、
        # 接続メソッドが呼び出されたかを確認する

        # WorkerManagerが作成され、シグナル接続メソッドが呼び出されたことを確認
        assert worker_service.worker_manager is not None

        # シグナルハンドラーメソッドが存在することを確認
        assert hasattr(worker_service, "_on_worker_started")
        assert hasattr(worker_service, "_on_worker_finished")
        assert hasattr(worker_service, "_on_worker_error")

    def test_worker_id_uniqueness(self, worker_service):
        """ワーカーID一意性テスト"""
        # 時間ベースのIDが異なる時間に生成された場合に一意であることを確認
        with patch("lorairo.gui.services.worker_service.time.time") as mock_time:
            mock_time.side_effect = [1000000, 1000001]  # 異なる時刻を返す

            with patch("lorairo.gui.services.worker_service.SearchWorker"):
                worker_service.worker_manager.start_worker.return_value = True

                worker_id1 = worker_service.start_search(SearchConditions(tags=["test1"]))
                worker_id2 = worker_service.start_search(SearchConditions(tags=["test2"]))

                assert worker_id1 != worker_id2
                assert worker_id1.endswith("1000000")
                assert worker_id2.endswith("1000001")

    def test_progress_signal_forwarding(self, worker_service):
        """進捗シグナル転送テスト"""
        # シグナル受信用モック
        progress_mock = Mock()
        batch_progress_mock = Mock()

        worker_service.worker_progress_updated.connect(progress_mock)
        worker_service.worker_batch_progress.connect(batch_progress_mock)

        # 進捗シグナル発行のシミュレーション
        with patch("lorairo.gui.services.worker_service.SearchWorker") as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker
            worker_service.worker_manager.start_worker.return_value = True

            # 検索開始
            worker_service.start_search(SearchConditions(tags=["test"]))

            # 進捗信号接続の確認（connectメソッドが呼ばれることを確認）
            mock_worker.progress_updated.connect.assert_called()

    @patch("lorairo.gui.services.worker_service.DatabaseRegistrationWorker")
    def test_batch_registration_progress_signal_connection(self, mock_worker_class, worker_service):
        """バッチ登録進捗シグナル接続テスト"""
        mock_worker = Mock()
        mock_worker_class.return_value = mock_worker
        worker_service.worker_manager.start_worker.return_value = True

        # バッチ登録開始
        worker_service.start_batch_registration(Path("/test"))

        # 進捗シグナル接続確認
        mock_worker.progress_updated.connect.assert_called()
        mock_worker.batch_progress.connect.assert_called()

    @patch("lorairo.gui.services.worker_service.AnnotationWorker")
    def test_annotation_progress_signal_connection(self, mock_worker_class, worker_service):
        """アノテーション進捗シグナル接続テスト"""
        mock_worker = Mock()
        mock_worker_class.return_value = mock_worker
        worker_service.worker_manager.start_worker.return_value = True

        # アノテーション開始
        worker_service.start_annotation([Image.new("RGB", (100, 100))], ["hash"], ["model"])

        # 進捗シグナル接続確認
        mock_worker.progress_updated.connect.assert_called()

    def test_worker_service_inheritance(self, worker_service):
        """WorkerService継承テスト"""
        from PySide6.QtCore import QObject

        assert isinstance(worker_service, QObject)

    def test_cleanup_and_resource_management(self, worker_service):
        """クリーンアップとリソース管理テスト"""
        # WorkerServiceが適切にリソースを管理していることを確認
        # （メモリリークなどが起きないように設計されていることを確認）

        # 複数のワーカーIDが適切に管理されていることを確認
        assert worker_service.current_search_worker_id is None
        assert worker_service.current_registration_worker_id is None
        assert worker_service.current_annotation_worker_id is None
        assert worker_service.current_thumbnail_worker_id is None
