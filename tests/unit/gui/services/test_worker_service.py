# tests/unit/gui/services/test_worker_service.py

import re
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PIL import Image
from PySide6.QtCore import QSize

from lorairo.gui.services.operation_events import OperationOutcome, OperationType
from lorairo.gui.services.worker_service import WorkerService
from lorairo.gui.workers.search_worker import SearchResult
from lorairo.gui.workers.terminal import CancelReason, WorkerOutcome, WorkerTerminalEvent
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
        assert worker_service.current_batch_import_worker_id is None

    def test_signal_definitions(self, worker_service):
        """シグナル定義テスト"""
        # 基本シグナルの存在確認
        assert hasattr(worker_service, "batch_registration_started")
        assert hasattr(worker_service, "batch_registration_finished")
        assert hasattr(worker_service, "batch_registration_error")
        assert hasattr(worker_service, "batch_registration_canceled")

        assert hasattr(worker_service, "enhanced_annotation_started")
        assert hasattr(worker_service, "enhanced_annotation_finished")
        assert hasattr(worker_service, "enhanced_annotation_error")
        assert hasattr(worker_service, "enhanced_annotation_canceled")

        assert hasattr(worker_service, "search_started")
        assert hasattr(worker_service, "search_finished")
        assert hasattr(worker_service, "search_error")
        assert hasattr(worker_service, "search_canceled")

        assert hasattr(worker_service, "thumbnail_started")
        assert hasattr(worker_service, "thumbnail_finished")
        assert hasattr(worker_service, "thumbnail_error")
        assert hasattr(worker_service, "thumbnail_canceled")

        assert hasattr(worker_service, "batch_import_started")
        assert hasattr(worker_service, "batch_import_finished")
        assert hasattr(worker_service, "batch_import_error")
        assert hasattr(worker_service, "batch_import_canceled")

        # 進捗・管理シグナル
        assert hasattr(worker_service, "worker_progress_updated")
        assert hasattr(worker_service, "worker_batch_progress")
        assert hasattr(worker_service, "worker_terminal")
        assert hasattr(worker_service, "operation_event")
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

        # worker_id形式確認（UUID hex 8文字）
        assert worker_id.startswith("batch_reg_")
        suffix = worker_id.split("_")[-1]
        assert len(suffix) == 8 and bool(re.match(r"^[0-9a-f]{8}$", suffix))
        assert worker_service.current_registration_worker_id == worker_id

    @patch("lorairo.gui.services.worker_service.DatabaseRegistrationWorker")
    def test_start_batch_registration_failure(self, mock_worker_class, worker_service):
        """バッチ登録開始失敗テスト"""
        # モックワーカー設定
        mock_worker = Mock()
        mock_worker_class.return_value = mock_worker
        worker_service.worker_manager.start_worker.return_value = False
        worker_service.current_registration_worker_id = "batch_reg_existing"

        directory = Path("/test/directory")

        # 例外発生確認
        with pytest.raises(RuntimeError, match="ワーカー開始失敗"):
            worker_service.start_batch_registration(directory)

        assert worker_service.current_registration_worker_id == "batch_reg_existing"

    def test_cancel_batch_registration(self, worker_service):
        """バッチ登録キャンセルテスト"""
        worker_service.worker_manager.cancel_worker.return_value = True

        result = worker_service.cancel_batch_registration("test_worker_id")

        assert result is True
        worker_service.worker_manager.cancel_worker.assert_called_once_with("test_worker_id")

    # 注: 旧start_annotation()テストは削除済み（新API: start_enhanced_batch_annotation）

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
        filter_conditions = SearchConditions(search_type="tags", keywords=["test"], tag_logic="and")

        # 検索開始
        worker_id = worker_service.start_search(filter_conditions)

        # ワーカー作成確認
        mock_worker_class.assert_called_once_with(worker_service.db_manager, filter_conditions)

        # ワーカーマネージャー呼び出し確認
        worker_service.worker_manager.start_worker.assert_called_once()

        # worker_id形式確認（UUID hex 8文字）
        assert worker_id.startswith("search_")
        suffix = worker_id.split("_")[-1]
        assert len(suffix) == 8 and bool(re.match(r"^[0-9a-f]{8}$", suffix))

        # 現在の検索ワーカーID設定確認
        assert worker_service.current_search_worker_id == worker_id

    @patch("lorairo.gui.services.worker_service.SearchWorker")
    def test_start_search_marks_current_before_fast_terminal_event(self, mock_worker_class, worker_service):
        """start_worker 中に即完了しても operation event は current として扱う"""
        mock_worker_class.return_value = Mock()
        operation_mock = Mock()
        worker_service.operation_event.connect(operation_mock)

        def finish_during_start(worker_id, _worker):
            worker_service._on_worker_terminal(
                WorkerTerminalEvent(
                    worker_id=worker_id,
                    worker_type="search",
                    outcome=WorkerOutcome.SUCCEEDED,
                    result={"ok": True},
                )
            )
            return True

        worker_service.worker_manager.start_worker.side_effect = finish_during_start

        worker_id = worker_service.start_search(
            SearchConditions(search_type="tags", keywords=["test"], tag_logic="and")
        )

        operation_event = operation_mock.call_args.args[0]
        assert operation_event.worker_id == worker_id
        assert operation_event.operation_type is OperationType.SEARCH
        assert operation_event.outcome is OperationOutcome.SUCCEEDED
        assert operation_event.is_current is True
        assert worker_service.current_search_worker_id is None

    @patch("lorairo.gui.services.worker_service.SearchWorker")
    def test_start_search_failure_after_cancel_clears_current_worker_id(
        self, mock_worker_class, worker_service
    ):
        """既存検索キャンセル後の検索開始失敗時は stale id を残さない"""
        mock_worker_class.return_value = Mock()
        worker_service.worker_manager.start_worker.return_value = False
        worker_service.current_search_worker_id = "search_existing"

        with pytest.raises(RuntimeError, match="ワーカー開始失敗"):
            worker_service.start_search(
                SearchConditions(search_type="tags", keywords=["test"], tag_logic="and")
            )

        assert worker_service.current_search_worker_id is None

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
        filter_conditions = SearchConditions(search_type="tags", keywords=["test"], tag_logic="and")

        # 検索開始
        new_worker_id = worker_service.start_search(filter_conditions)

        # 既存ワーカーのキャンセル確認
        worker_service.worker_manager.cancel_worker.assert_called_once_with(
            existing_worker_id,
            reason=CancelReason.SEARCH_REPLACED,
        )

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
        search_result = SearchResult(
            image_metadata=[{"id": 1, "path": "/test/image1.jpg"}],
            total_count=1,
            search_time=0.1,
            filter_conditions=SearchConditions(search_type="tags", keywords=[], tag_logic="and"),
        )
        thumbnail_size = QSize(150, 150)

        # サムネイル読み込み開始
        worker_id = worker_service.start_thumbnail_load(search_result, thumbnail_size)

        # ワーカー作成確認
        mock_worker_class.assert_called_once_with(search_result, thumbnail_size, worker_service.db_manager)

        # ワーカーマネージャー呼び出し確認
        worker_service.worker_manager.start_worker.assert_called_once()

        # worker_id形式確認（UUID hex 8文字）
        assert worker_id.startswith("thumbnail_")
        suffix = worker_id.split("_")[-1]
        assert len(suffix) == 8 and bool(re.match(r"^[0-9a-f]{8}$", suffix))
        assert worker_service.current_thumbnail_worker_id == worker_id

    @patch("lorairo.gui.services.worker_service.ThumbnailWorker")
    def test_start_thumbnail_loading_marks_current_before_fast_terminal_event(
        self, mock_worker_class, worker_service
    ):
        """start_worker 中に即完了しても thumbnail operation event は current として扱う"""
        mock_worker_class.return_value = Mock()
        operation_mock = Mock()
        worker_service.operation_event.connect(operation_mock)
        search_result = SearchResult(
            image_metadata=[{"id": 1, "path": "/test/image1.jpg"}],
            total_count=1,
            search_time=0.1,
            filter_conditions=SearchConditions(search_type="tags", keywords=[], tag_logic="and"),
        )

        def finish_during_start(worker_id, _worker):
            worker_service._on_worker_terminal(
                WorkerTerminalEvent(
                    worker_id=worker_id,
                    worker_type="thumbnail",
                    outcome=WorkerOutcome.SUCCEEDED,
                    result={"page": 1},
                )
            )
            return True

        worker_service.worker_manager.start_worker.side_effect = finish_during_start

        worker_id = worker_service.start_thumbnail_load(search_result, QSize(150, 150))

        operation_event = operation_mock.call_args.args[0]
        assert operation_event.worker_id == worker_id
        assert operation_event.operation_type is OperationType.THUMBNAIL
        assert operation_event.outcome is OperationOutcome.SUCCEEDED
        assert operation_event.is_current is True
        assert worker_service.current_thumbnail_worker_id is None

    @patch("lorairo.gui.services.worker_service.ThumbnailWorker")
    def test_start_thumbnail_loading_returns_new_worker_id(self, mock_worker_class, worker_service):
        """複数回サムネイル読み込みで異なるworker_idが返されることをテスト"""
        # モックワーカー設定
        mock_worker = Mock()
        mock_worker_class.return_value = mock_worker
        worker_service.worker_manager.start_worker.return_value = True

        # テストデータ
        search_result = SearchResult(
            image_metadata=[{"id": 1, "path": "/test/image1.jpg"}],
            total_count=1,
            search_time=0.1,
            filter_conditions=SearchConditions(search_type="tags", keywords=[], tag_logic="and"),
        )
        thumbnail_size = QSize(150, 150)

        # 2回呼び出して異なるIDが返されることを確認
        worker_id_1 = worker_service.start_thumbnail_load(search_result, thumbnail_size)
        worker_id_2 = worker_service.start_thumbnail_load(search_result, thumbnail_size)

        assert worker_id_1 != worker_id_2
        assert worker_id_1.startswith("thumbnail_")
        assert worker_id_2.startswith("thumbnail_")

    @patch("lorairo.gui.services.worker_service.ThumbnailWorker")
    def test_start_thumbnail_loading_failure_keeps_current_worker_id(
        self, mock_worker_class, worker_service
    ):
        """サムネイル開始失敗時に current_thumbnail_worker_id を上書きしない"""
        mock_worker_class.return_value = Mock()
        worker_service.worker_manager.start_worker.return_value = False
        worker_service.current_thumbnail_worker_id = "thumbnail_existing"

        search_result = SearchResult(
            image_metadata=[{"id": 1, "path": "/test/image1.jpg"}],
            total_count=1,
            search_time=0.1,
            filter_conditions=SearchConditions(search_type="tags", keywords=[], tag_logic="and"),
        )

        with pytest.raises(RuntimeError, match="ワーカー開始失敗"):
            worker_service.start_thumbnail_load(search_result, QSize(128, 128))

        assert worker_service.current_thumbnail_worker_id == "thumbnail_existing"

    @patch("lorairo.gui.services.worker_service.ThumbnailWorker")
    def test_start_thumbnail_page_load_success(self, mock_worker_class, worker_service):
        """ページ単位サムネイル読み込み開始テスト"""
        mock_worker = Mock()
        mock_worker_class.return_value = mock_worker
        worker_service.worker_manager.start_worker.return_value = True

        search_result = SearchResult(
            image_metadata=[
                {"id": 1, "path": "/test/image1.jpg"},
                {"id": 2, "path": "/test/image2.jpg"},
            ],
            total_count=2,
            search_time=0.1,
            filter_conditions=SearchConditions(search_type="tags", keywords=[], tag_logic="and"),
        )

        worker_id = worker_service.start_thumbnail_page_load(
            search_result=search_result,
            thumbnail_size=QSize(128, 128),
            image_ids=[1, 2],
            page_num=1,
            request_id="req_001",
            cancel_previous=False,
        )

        mock_worker_class.assert_called_once_with(
            search_result=search_result,
            thumbnail_size=QSize(128, 128),
            db_manager=worker_service.db_manager,
            image_id_filter=[1, 2],
            request_id="req_001",
            page_num=1,
        )
        assert worker_id.startswith("thumbnail_")
        assert worker_service.current_thumbnail_worker_id == worker_id

    @patch("lorairo.gui.services.worker_service.ThumbnailWorker")
    def test_start_thumbnail_page_load_cancels_existing_worker(self, mock_worker_class, worker_service):
        """ページ単位読み込みで既存ワーカーをキャンセルできる"""
        mock_worker = Mock()
        mock_worker_class.return_value = mock_worker
        worker_service.worker_manager.start_worker.return_value = True
        worker_service.current_thumbnail_worker_id = "thumbnail_existing"

        search_result = SearchResult(
            image_metadata=[{"id": 1, "path": "/test/image1.jpg"}],
            total_count=1,
            search_time=0.1,
            filter_conditions=SearchConditions(search_type="tags", keywords=[], tag_logic="and"),
        )

        worker_service.start_thumbnail_page_load(
            search_result=search_result,
            thumbnail_size=QSize(128, 128),
            image_ids=[1],
            page_num=1,
            request_id="req_002",
            cancel_previous=True,
        )

        worker_service.worker_manager.cancel_worker.assert_called_with(
            "thumbnail_existing",
            reason=CancelReason.THUMBNAIL_REPLACED,
        )

    @patch("lorairo.gui.services.worker_service.ThumbnailWorker")
    def test_start_thumbnail_page_load_failure_keeps_current_worker_id(
        self, mock_worker_class, worker_service
    ):
        """ページ読み込み開始失敗時に current_thumbnail_worker_id を上書きしない"""
        mock_worker_class.return_value = Mock()
        worker_service.worker_manager.start_worker.return_value = False
        worker_service.current_thumbnail_worker_id = "thumbnail_existing"

        search_result = SearchResult(
            image_metadata=[{"id": 1, "path": "/test/image1.jpg"}],
            total_count=1,
            search_time=0.1,
            filter_conditions=SearchConditions(search_type="tags", keywords=[], tag_logic="and"),
        )

        with pytest.raises(RuntimeError, match="ワーカー開始失敗"):
            worker_service.start_thumbnail_page_load(
                search_result=search_result,
                thumbnail_size=QSize(128, 128),
                image_ids=[1],
                page_num=1,
                request_id="req_failure",
                cancel_previous=False,
            )

        assert worker_service.current_thumbnail_worker_id == "thumbnail_existing"

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
        assert hasattr(worker_service, "_on_worker_canceled")

    def test_on_worker_canceled_clears_current_id_and_finishes_progress(self, worker_service):
        """キャンセル完了時はエラーシグナルなしで進捗とcurrent idを片付ける"""
        worker_id = "search_cancelled"
        worker_service.current_search_worker_id = worker_id
        error_mock = Mock()
        canceled_mock = Mock()
        worker_service.search_error.connect(error_mock)
        worker_service.search_canceled.connect(canceled_mock)

        with patch.object(worker_service.progress_manager, "finish_worker_progress") as mock_finish:
            worker_service._on_worker_canceled(worker_id)

        mock_finish.assert_called_once_with(worker_id, success=False)
        assert worker_service.current_search_worker_id is None
        error_mock.assert_not_called()
        canceled_mock.assert_called_once_with(worker_id)

    def test_worker_terminal_emits_rich_event_and_dispatches_compat_signal(self, worker_service):
        worker_id = "search_cancelled"
        worker_service.current_search_worker_id = worker_id
        terminal_mock = Mock()
        canceled_mock = Mock()
        worker_service.worker_terminal.connect(terminal_mock)
        worker_service.search_canceled.connect(canceled_mock)
        event = WorkerTerminalEvent(
            worker_id=worker_id,
            worker_type="search",
            outcome=WorkerOutcome.CANCELED,
            cancel_reason=CancelReason.PIPELINE_CANCEL,
        )

        with patch.object(worker_service.progress_manager, "finish_worker_progress"):
            worker_service._on_worker_terminal(event)

        terminal_mock.assert_called_once_with(event)
        canceled_mock.assert_called_once_with(worker_id)
        assert worker_service.current_search_worker_id is None

    def test_worker_terminal_emits_current_operation_event(self, worker_service):
        worker_id = "search_current"
        worker_service.current_search_worker_id = worker_id
        worker_service._register_operation(worker_id, OperationType.SEARCH, generation=1)
        worker_service._search_generation = 1
        operation_mock = Mock()
        worker_service.operation_event.connect(operation_mock)
        event = WorkerTerminalEvent(
            worker_id=worker_id,
            worker_type="search",
            outcome=WorkerOutcome.SUCCEEDED,
            result={"ok": True},
        )

        with patch.object(worker_service.progress_manager, "finish_worker_progress"):
            worker_service._on_worker_terminal(event)

        operation_mock.assert_called_once()
        operation_event = operation_mock.call_args.args[0]
        assert operation_event.operation_type is OperationType.SEARCH
        assert operation_event.outcome is OperationOutcome.SUCCEEDED
        assert operation_event.is_current is True
        assert operation_event.result == {"ok": True}

    def test_worker_terminal_suppresses_replacement_canceled_compat_signal(self, worker_service):
        worker_id = "search_replaced"
        worker_service.current_search_worker_id = worker_id
        canceled_mock = Mock()
        worker_service.search_canceled.connect(canceled_mock)
        event = WorkerTerminalEvent(
            worker_id=worker_id,
            worker_type="search",
            outcome=WorkerOutcome.CANCELED,
            cancel_reason=CancelReason.SEARCH_REPLACED,
        )

        with patch.object(worker_service.progress_manager, "finish_worker_progress"):
            worker_service._on_worker_terminal(event)

        canceled_mock.assert_not_called()
        assert worker_service.current_search_worker_id is None

    def test_worker_terminal_replacement_canceled_emits_superseded_operation(self, worker_service):
        old_worker_id = "search_replaced"
        worker_service.current_search_worker_id = old_worker_id
        worker_service._register_operation(old_worker_id, OperationType.SEARCH, generation=1)
        worker_service._search_generation = 1
        operation_mock = Mock()
        worker_service.operation_event.connect(operation_mock)
        event = WorkerTerminalEvent(
            worker_id=old_worker_id,
            worker_type="search",
            outcome=WorkerOutcome.CANCELED,
            cancel_reason=CancelReason.SEARCH_REPLACED,
        )

        with patch.object(worker_service.progress_manager, "finish_worker_progress"):
            worker_service._on_worker_terminal(event)

        operation_event = operation_mock.call_args.args[0]
        assert operation_event.outcome is OperationOutcome.SUPERSEDED
        assert operation_event.is_current is False
        assert operation_event.cancel_reason is CancelReason.SEARCH_REPLACED

    def test_worker_terminal_abnormal_outcome_dispatches_error_not_canceled(self, worker_service):
        worker_id = "thumbnail_timeout"
        worker_service.current_thumbnail_worker_id = worker_id
        error_mock = Mock()
        canceled_mock = Mock()
        worker_service.thumbnail_error.connect(error_mock)
        worker_service.thumbnail_canceled.connect(canceled_mock)
        event = WorkerTerminalEvent(
            worker_id=worker_id,
            worker_type="thumbnail",
            outcome=WorkerOutcome.TERMINATED,
            error="terminated",
            cancel_reason=CancelReason.USER_REQUESTED,
        )

        worker_service._on_worker_terminal(event)

        error_mock.assert_called_once_with("terminated")
        canceled_mock.assert_not_called()
        assert worker_service.current_thumbnail_worker_id is None

    def test_worker_terminal_replacement_abnormal_suppresses_compat_error(self, worker_service):
        old_worker_id = "thumbnail_replaced"
        worker_service.current_thumbnail_worker_id = old_worker_id
        error_mock = Mock()
        worker_service.thumbnail_error.connect(error_mock)
        event = WorkerTerminalEvent(
            worker_id=old_worker_id,
            worker_type="thumbnail",
            outcome=WorkerOutcome.TERMINATED,
            error="terminated",
            cancel_reason=CancelReason.THUMBNAIL_REPLACED,
        )

        worker_service._on_worker_terminal(event)

        error_mock.assert_not_called()
        assert worker_service.current_thumbnail_worker_id is None

    def test_worker_terminal_replacement_abnormal_finishes_search_progress(self, worker_service):
        old_worker_id = "search_replaced"
        worker_service.current_search_worker_id = old_worker_id
        error_mock = Mock()
        worker_service.search_error.connect(error_mock)
        event = WorkerTerminalEvent(
            worker_id=old_worker_id,
            worker_type="search",
            outcome=WorkerOutcome.CANCEL_TIMEOUT,
            error="cancel timed out",
            cancel_reason=CancelReason.SEARCH_REPLACED,
        )

        with patch.object(worker_service.progress_manager, "finish_worker_progress") as mock_finish:
            worker_service._on_worker_terminal(event)

        mock_finish.assert_called_once_with(old_worker_id, success=False)
        error_mock.assert_not_called()
        assert worker_service.current_search_worker_id is None

    def test_worker_terminal_replacement_failed_emits_superseded_operation(self, worker_service):
        old_worker_id = "search_replaced"
        worker_service.current_search_worker_id = old_worker_id
        worker_service._register_operation(old_worker_id, OperationType.SEARCH, generation=1)
        worker_service._search_generation = 2
        operation_mock = Mock()
        worker_service.operation_event.connect(operation_mock)
        event = WorkerTerminalEvent(
            worker_id=old_worker_id,
            worker_type="search",
            outcome=WorkerOutcome.FAILED,
            error="superseded worker failed",
            cancel_reason=CancelReason.SEARCH_REPLACED,
        )

        with patch.object(worker_service.progress_manager, "finish_worker_progress"):
            worker_service._on_worker_terminal(event)

        operation_event = operation_mock.call_args.args[0]
        assert operation_event.outcome is OperationOutcome.SUPERSEDED
        assert operation_event.is_current is False
        assert operation_event.error == "superseded worker failed"

    def test_worker_terminal_replacement_failed_suppresses_compat_error(self, worker_service):
        old_worker_id = "search_replaced"
        worker_service.current_search_worker_id = old_worker_id
        error_mock = Mock()
        worker_service.search_error.connect(error_mock)
        event = WorkerTerminalEvent(
            worker_id=old_worker_id,
            worker_type="search",
            outcome=WorkerOutcome.FAILED,
            error="superseded worker failed",
            cancel_reason=CancelReason.SEARCH_REPLACED,
        )

        with patch.object(worker_service.progress_manager, "finish_worker_progress") as mock_finish:
            worker_service._on_worker_terminal(event)

        mock_finish.assert_called_once_with(old_worker_id, success=False)
        error_mock.assert_not_called()
        assert worker_service.current_search_worker_id is None

    def test_worker_id_uniqueness(self, worker_service):
        """ワーカーID一意性テスト"""
        with patch("lorairo.gui.services.worker_service.SearchWorker"):
            worker_service.worker_manager.start_worker.return_value = True

            worker_id1 = worker_service.start_search(
                SearchConditions(search_type="tags", keywords=["test1"], tag_logic="and")
            )
            worker_id2 = worker_service.start_search(
                SearchConditions(search_type="tags", keywords=["test2"], tag_logic="and")
            )

            # uuid ベースのため、異なるIDが生成されること
            assert worker_id1 != worker_id2
            assert worker_id1.startswith("search_")
            assert worker_id2.startswith("search_")

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
            worker_service.start_search(
                SearchConditions(search_type="tags", keywords=["test"], tag_logic="and")
            )

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

    # 注: test_annotation_progress_signal_connection は削除済み（旧APIテスト）

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
        assert worker_service.current_batch_import_worker_id is None

    @patch("lorairo.gui.services.worker_service.AnnotationWorker")
    @patch.object(WorkerService, "annotation_logic", create=True)
    def test_start_enhanced_batch_annotation_success(
        self, mock_annotation_logic, mock_worker_class, worker_service
    ):
        """バッチアノテーション開始成功テスト（新API）"""
        mock_worker = Mock()
        mock_worker_class.return_value = mock_worker
        worker_service.worker_manager.start_worker.return_value = True

        image_paths = ["/path/to/image1.jpg", "/path/to/image2.jpg"]
        models = ["gpt-4o-mini", "claude-3-haiku-20240307"]

        # バッチアノテーション開始
        worker_id = worker_service.start_enhanced_batch_annotation(
            image_paths=image_paths, litellm_model_ids=models
        )

        # AnnotationWorkerが新シグネチャで初期化されたことを確認 (Issue #225: model_registry 追加)
        mock_worker_class.assert_called_once()
        kwargs = mock_worker_class.call_args.kwargs
        assert kwargs["annotation_logic"] is worker_service.annotation_logic
        assert kwargs["image_paths"] == image_paths
        assert kwargs["litellm_model_ids"] == models
        assert kwargs["db_manager"] is worker_service.db_manager
        assert "model_registry" in kwargs

        # ワーカーマネージャーにワーカーが登録されたことを確認
        worker_service.worker_manager.start_worker.assert_called_once()

        # worker_idが正しい形式で返されることを確認
        assert worker_id.startswith("annotation_")
        suffix = worker_id.split("_")[-1]
        assert len(suffix) == 8 and bool(re.match(r"^[0-9a-f]{8}$", suffix))

        # 進捗シグナル接続確認
        mock_worker.progress_updated.connect.assert_called()
        assert worker_service.current_annotation_worker_id == worker_id

    @patch("lorairo.gui.services.worker_service.AnnotationWorker")
    @patch.object(WorkerService, "annotation_logic", create=True)
    def test_start_enhanced_batch_annotation_failure_keeps_current_worker_id(
        self, mock_annotation_logic, mock_worker_class, worker_service
    ):
        """アノテーション開始失敗時に current_annotation_worker_id を上書きしない"""
        mock_worker_class.return_value = Mock()
        worker_service.worker_manager.start_worker.return_value = False
        worker_service.current_annotation_worker_id = "annotation_existing"

        with pytest.raises(RuntimeError, match="アノテーションワーカー開始失敗"):
            worker_service.start_enhanced_batch_annotation(
                image_paths=["/path/to/image.jpg"], litellm_model_ids=["gpt-4o-mini"]
            )

        assert worker_service.current_annotation_worker_id == "annotation_existing"

    @patch("lorairo.gui.services.worker_service.get_service_container")
    @patch("lorairo.gui.workers.batch_import_worker.BatchImportWorker")
    def test_start_batch_import_success_sets_current_worker_id(
        self, mock_worker_class, mock_container, worker_service
    ):
        """バッチインポート開始成功時にcurrent worker idを設定する"""
        mock_container.return_value.image_repository = Mock()
        mock_worker = Mock()
        mock_worker_class.return_value = mock_worker
        worker_service.worker_manager.start_worker.return_value = True

        worker_id = worker_service.start_batch_import([Path("/tmp/test.jsonl")], dry_run=True)

        assert worker_id.startswith("batch_import_")
        assert worker_service.current_batch_import_worker_id == worker_id
        worker_service.worker_manager.start_worker.assert_called_once_with(worker_id, mock_worker)

    @patch("lorairo.gui.services.worker_service.get_service_container")
    @patch("lorairo.gui.workers.batch_import_worker.BatchImportWorker")
    def test_start_batch_import_failure_keeps_current_worker_id(
        self, mock_worker_class, mock_container, worker_service
    ):
        """バッチインポート開始失敗時に current_batch_import_worker_id を上書きしない"""
        mock_container.return_value.image_repository = Mock()
        mock_worker_class.return_value = Mock()
        worker_service.worker_manager.start_worker.return_value = False
        worker_service.current_batch_import_worker_id = "batch_import_existing"

        with pytest.raises(RuntimeError, match="ワーカー開始失敗"):
            worker_service.start_batch_import([Path("/tmp/test.jsonl")])

        assert worker_service.current_batch_import_worker_id == "batch_import_existing"

    @pytest.mark.parametrize(
        ("worker_id", "terminal", "signal_name", "current_attr", "payload"),
        [
            (
                "batch_reg_abc12345",
                "finished",
                "batch_registration_finished",
                "current_registration_worker_id",
                {"ok": True},
            ),
            (
                "batch_reg_abc12345",
                "error",
                "batch_registration_error",
                "current_registration_worker_id",
                "boom",
            ),
            (
                "batch_reg_abc12345",
                "canceled",
                "batch_registration_canceled",
                "current_registration_worker_id",
                None,
            ),
            (
                "batch_import_abc12345",
                "finished",
                "batch_import_finished",
                "current_batch_import_worker_id",
                {"ok": True},
            ),
            (
                "batch_import_abc12345",
                "error",
                "batch_import_error",
                "current_batch_import_worker_id",
                "boom",
            ),
            (
                "batch_import_abc12345",
                "canceled",
                "batch_import_canceled",
                "current_batch_import_worker_id",
                None,
            ),
            (
                "annotation_abc12345",
                "finished",
                "enhanced_annotation_finished",
                "current_annotation_worker_id",
                {"ok": True},
            ),
            (
                "annotation_abc12345",
                "error",
                "enhanced_annotation_error",
                "current_annotation_worker_id",
                "boom",
            ),
            (
                "annotation_abc12345",
                "canceled",
                "enhanced_annotation_canceled",
                "current_annotation_worker_id",
                None,
            ),
            ("search_abc12345", "finished", "search_finished", "current_search_worker_id", {"ok": True}),
            ("search_abc12345", "error", "search_error", "current_search_worker_id", "boom"),
            ("search_abc12345", "canceled", "search_canceled", "current_search_worker_id", None),
            (
                "thumbnail_abc12345",
                "finished",
                "thumbnail_finished",
                "current_thumbnail_worker_id",
                {"ok": True},
            ),
            ("thumbnail_abc12345", "error", "thumbnail_error", "current_thumbnail_worker_id", "boom"),
            ("thumbnail_abc12345", "canceled", "thumbnail_canceled", "current_thumbnail_worker_id", None),
        ],
    )
    def test_worker_terminal_dispatch_table(
        self, worker_service, worker_id, terminal, signal_name, current_attr, payload
    ):
        """全worker種別の終端signalとcurrent id cleanupを表で検証する"""
        setattr(worker_service, current_attr, worker_id)
        terminal_mock = Mock()
        getattr(worker_service, signal_name).connect(terminal_mock)

        with patch.object(worker_service.progress_manager, "finish_worker_progress") as mock_finish:
            if terminal == "finished":
                worker_service._on_worker_finished(worker_id, payload)
                terminal_mock.assert_called_once_with(payload)
            elif terminal == "error":
                worker_service._on_worker_error(worker_id, payload)
                terminal_mock.assert_called_once_with(payload)
            else:
                worker_service._on_worker_canceled(worker_id)
                terminal_mock.assert_called_once_with(worker_id)

        assert getattr(worker_service, current_attr) is None
        if not worker_id.startswith("thumbnail_"):
            mock_finish.assert_called_once()
        else:
            mock_finish.assert_not_called()

    def test_modern_progress_manager_integration(self, worker_service):
        """ModernProgressManager統合検証

        WorkerServiceがModernProgressManagerと正しく連携し、
        進捗更新・バッチ進捗更新・キャンセル要求が正しく処理されることを検証
        """
        from lorairo.gui.workers.base import WorkerProgress

        # 1. _on_progress_updated() の転送処理検証
        mock_progress = WorkerProgress(
            percentage=50, status_message="処理中...", processed_count=5, total_count=10
        )

        # ModernProgressManagerのupdate_worker_progressがモック化されていることを確認
        with patch.object(worker_service.progress_manager, "update_worker_progress") as mock_update:
            worker_service._on_progress_updated("test_worker_001", mock_progress)

            # ModernProgressManagerに転送されたことを確認
            mock_update.assert_called_once_with("test_worker_001", mock_progress)

        # 2. _on_batch_progress_updated() の転送処理検証
        with patch.object(worker_service.progress_manager, "update_batch_progress") as mock_batch_update:
            worker_service._on_batch_progress_updated(
                "test_worker_002", current=7, total=20, filename="test_image.jpg"
            )

            # ModernProgressManagerに転送されたことを確認
            mock_batch_update.assert_called_once_with("test_worker_002", 7, 20, "test_image.jpg")

        # 3. _on_progress_cancellation_requested() のキャンセル処理検証
        # WorkerManagerのcancel_workerをモック化
        worker_service.worker_manager.cancel_worker.return_value = True

        worker_service._on_progress_cancellation_requested("test_worker_003")

        # WorkerManagerにキャンセルが要求されたことを確認
        worker_service.worker_manager.cancel_worker.assert_called_with(
            "test_worker_003",
            reason=CancelReason.PROGRESS_DIALOG,
        )
