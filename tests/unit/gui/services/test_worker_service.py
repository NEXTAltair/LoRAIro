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
from lorairo.services.job_ledger_service import JobStatus
from lorairo.services.model_registry_protocol import ModelInfo
from lorairo.services.search_models import SearchConditions

# GPU 直列キューテスト用の registry モデル (ADR 0066 §6)
_LOCAL_MODEL_ID = "wd-v1-4-tagger"
_API_MODEL_ID = "openai/gpt-4o"


def _registry_model_infos() -> list[ModelInfo]:
    """ローカル ML / WebAPI 混在の ModelInfo リストを返すテストヘルパー。"""
    return [
        ModelInfo(
            name=_LOCAL_MODEL_ID,
            provider="local",
            capabilities=["tags"],
            litellm_model_id=None,
            requires_api_key=False,
            estimated_size_gb=1.2,
        ),
        ModelInfo(
            name=_API_MODEL_ID,
            provider="openai",
            capabilities=["caption", "tags"],
            litellm_model_id=_API_MODEL_ID,
            requires_api_key=True,
            estimated_size_gb=None,
        ),
    ]


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

    def test_worker_terminal_canceled_clears_current_id_and_finishes_progress(self, worker_service):
        """キャンセル終端時はエラーシグナルなしで進捗とcurrent idを片付ける"""
        worker_id = "search_cancelled"
        worker_service.current_search_worker_id = worker_id
        error_mock = Mock()
        canceled_mock = Mock()
        worker_service.search_error.connect(error_mock)
        worker_service.search_canceled.connect(canceled_mock)
        event = WorkerTerminalEvent(
            worker_id=worker_id,
            worker_type="search",
            outcome=WorkerOutcome.CANCELED,
            cancel_reason=CancelReason.USER_REQUESTED,
        )

        worker_service._on_worker_terminal(event)

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

        worker_service._on_worker_terminal(event)

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

        worker_service._on_worker_terminal(event)

        error_mock.assert_not_called()
        assert worker_service.current_search_worker_id is None

    def test_stale_search_replacement_failure_preserves_current_search_operation(self, worker_service):
        """古い search replacement failure は current search id を壊さず superseded operation になる"""
        old_worker_id = "search_old"
        current_worker_id = "search_current"
        worker_service.current_search_worker_id = current_worker_id
        worker_service._register_operation(old_worker_id, OperationType.SEARCH, generation=1)
        worker_service._register_operation(current_worker_id, OperationType.SEARCH, generation=2)
        worker_service._search_generation = 2
        operation_mock = Mock()
        error_mock = Mock()
        worker_service.operation_event.connect(operation_mock)
        worker_service.search_error.connect(error_mock)
        event = WorkerTerminalEvent(
            worker_id=old_worker_id,
            worker_type="search",
            outcome=WorkerOutcome.FAILED,
            error="old search failed after replacement",
            cancel_reason=CancelReason.SEARCH_REPLACED,
        )

        worker_service._on_worker_terminal(event)

        operation_event = operation_mock.call_args.args[0]
        assert operation_event.worker_id == old_worker_id
        assert operation_event.outcome is OperationOutcome.SUPERSEDED
        assert operation_event.is_current is False
        error_mock.assert_not_called()
        assert worker_service.current_search_worker_id == current_worker_id

    def test_stale_prefetch_replacement_failure_preserves_current_thumbnail_operation(self, worker_service):
        """prefetch replacement failure は current thumbnail id と表示要求を壊さない"""
        old_worker_id = "thumbnail_prefetch_old"
        current_worker_id = "thumbnail_current"
        worker_service.current_thumbnail_worker_id = current_worker_id
        worker_service._register_operation(
            old_worker_id,
            OperationType.THUMBNAIL,
            request_id="prefetch-old",
            generation=1,
        )
        worker_service._register_operation(
            current_worker_id,
            OperationType.THUMBNAIL,
            request_id="visible-current",
            generation=2,
        )
        worker_service._thumbnail_generation = 2
        operation_mock = Mock()
        error_mock = Mock()
        worker_service.operation_event.connect(operation_mock)
        worker_service.thumbnail_error.connect(error_mock)
        event = WorkerTerminalEvent(
            worker_id=old_worker_id,
            worker_type="thumbnail",
            outcome=WorkerOutcome.TERMINATED,
            error="old prefetch terminated",
            cancel_reason=CancelReason.PREFETCH_REPLACED,
        )

        worker_service._on_worker_terminal(event)

        operation_event = operation_mock.call_args.args[0]
        assert operation_event.worker_id == old_worker_id
        assert operation_event.request_id == "prefetch-old"
        assert operation_event.outcome is OperationOutcome.SUPERSEDED
        assert operation_event.is_current is False
        error_mock.assert_not_called()
        assert worker_service.current_thumbnail_worker_id == current_worker_id

    def test_non_replacement_search_failure_dispatches_error_once(self, worker_service):
        """通常 failure は compat error を一度だけ dispatch する"""
        worker_id = "search_failed"
        worker_service.current_search_worker_id = worker_id
        error_mock = Mock()
        canceled_mock = Mock()
        worker_service.search_error.connect(error_mock)
        worker_service.search_canceled.connect(canceled_mock)
        event = WorkerTerminalEvent(
            worker_id=worker_id,
            worker_type="search",
            outcome=WorkerOutcome.FAILED,
            error="search failed",
        )

        worker_service._on_worker_terminal(event)

        error_mock.assert_called_once_with("search failed")
        canceled_mock.assert_not_called()
        assert worker_service.current_search_worker_id is None

    # === Job Ledger (ADR 0066) ===

    def test_annotation_start_registers_job_ledger_entry(self, worker_service):
        """アノテーション開始で台帳に running 行が登録され変更通知が出る"""
        ledger_changed_mock = Mock()
        worker_service.job_ledger_changed.connect(ledger_changed_mock)

        worker_service._on_worker_started("annotation_abc12345")

        entry = worker_service.job_ledger.get("annotation_abc12345")
        assert entry is not None
        assert entry.job_type == "annotation"
        assert entry.title == "アノテーション処理"
        assert entry.status is JobStatus.RUNNING
        assert entry.finished_at is None
        ledger_changed_mock.assert_called_once()

    @pytest.mark.parametrize(
        ("outcome", "cancel_reason", "expected_status"),
        [
            (WorkerOutcome.SUCCEEDED, None, JobStatus.FINISHED),
            (WorkerOutcome.FAILED, None, JobStatus.FAILED),
            (WorkerOutcome.TERMINATED, None, JobStatus.FAILED),
            (WorkerOutcome.UNRESPONSIVE, None, JobStatus.FAILED),
            (WorkerOutcome.CANCELED, CancelReason.USER_REQUESTED, JobStatus.CANCELED),
        ],
    )
    def test_annotation_terminal_finishes_job_ledger_entry(
        self, worker_service, outcome, cancel_reason, expected_status
    ):
        """terminal outcome が台帳の終端状態へマップされ finished_at が確定する"""
        worker_id = "annotation_abc12345"
        worker_service._on_worker_started(worker_id)
        event = WorkerTerminalEvent(
            worker_id=worker_id,
            worker_type="annotation",
            outcome=outcome,
            result={"ok": True} if outcome is WorkerOutcome.SUCCEEDED else None,
            error="boom" if outcome is not WorkerOutcome.SUCCEEDED else None,
            cancel_reason=cancel_reason,
        )

        worker_service._on_worker_terminal(event)

        entry = worker_service.job_ledger.get(worker_id)
        assert entry is not None
        assert entry.status is expected_status
        assert entry.finished_at is not None
        if expected_status is JobStatus.FAILED:
            assert entry.summary == "boom"

    @pytest.mark.parametrize("worker_id", ["search_abc12345", "thumbnail_abc12345"])
    def test_job_ledger_excludes_search_and_thumbnail(self, worker_service, worker_id):
        """検索/サムネイル等のUI応答系workerは台帳に載せない (ADR 0066 §3)"""
        ledger_changed_mock = Mock()
        worker_service.job_ledger_changed.connect(ledger_changed_mock)

        worker_service._on_worker_started(worker_id)
        event = WorkerTerminalEvent(
            worker_id=worker_id,
            worker_type=worker_id.split("_")[0],
            outcome=WorkerOutcome.SUCCEEDED,
            result={"ok": True},
        )
        worker_service._on_worker_terminal(event)

        assert worker_service.job_ledger.get(worker_id) is None
        assert worker_service.job_ledger.list_entries() == []
        ledger_changed_mock.assert_not_called()

    def test_batch_registration_lifecycle_recorded_in_ledger(self, worker_service):
        """バッチ登録の開始→完了が台帳の running→finished に反映される"""
        worker_id = "batch_reg_abc12345"
        worker_service._on_worker_started(worker_id)
        assert worker_service.job_ledger.get(worker_id).status is JobStatus.RUNNING

        worker_service._on_worker_terminal(
            WorkerTerminalEvent(
                worker_id=worker_id,
                worker_type="batch_reg",
                outcome=WorkerOutcome.SUCCEEDED,
                result={"ok": True},
            )
        )

        entry = worker_service.job_ledger.get(worker_id)
        assert entry.status is JobStatus.FINISHED
        assert entry.finished_at is not None

    def test_cancel_job_delegates_to_worker_manager(self, worker_service):
        """Jobs 行のキャンセルは worker_manager.cancel_worker へ委譲される"""
        worker_service.worker_manager.cancel_worker.return_value = True

        assert worker_service.cancel_job("annotation_abc12345") is True
        worker_service.worker_manager.cancel_worker.assert_called_once_with("annotation_abc12345")

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

    @patch("lorairo.gui.services.worker_service.get_service_container")
    @patch("lorairo.gui.services.worker_service.AnnotationWorker")
    @patch.object(WorkerService, "annotation_logic", create=True)
    def test_start_enhanced_batch_annotation_success(
        self, mock_annotation_logic, mock_worker_class, mock_container, worker_service
    ):
        """バッチアノテーション開始成功テスト（新API）"""
        mock_container.return_value.model_registry.get_available_models.return_value = []
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

    @patch("lorairo.gui.services.worker_service.get_service_container")
    @patch("lorairo.gui.services.worker_service.AnnotationWorker")
    @patch.object(WorkerService, "annotation_logic", create=True)
    def test_start_enhanced_batch_annotation_failure_keeps_current_worker_id(
        self, mock_annotation_logic, mock_worker_class, mock_container, worker_service
    ):
        """アノテーション開始失敗時に current_annotation_worker_id を上書きしない"""
        mock_container.return_value.model_registry.get_available_models.return_value = []
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
        """全worker種別の互換終端signalとcurrent id cleanupを表で検証する"""
        setattr(worker_service, current_attr, worker_id)
        terminal_mock = Mock()
        getattr(worker_service, signal_name).connect(terminal_mock)

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


@patch("lorairo.gui.services.worker_service.get_service_container")
@patch("lorairo.gui.services.worker_service.AnnotationWorker")
@patch.object(WorkerService, "annotation_logic", create=True)
class TestGpuSerialQueue:
    """ローカル GPU 推論ジョブの直列キュー (ADR 0066 §6) のユニットテスト。

    ローカル ML (provider 空/"local") を含むアノテーションジョブは同時 1 件。
    実行中に投入されたジョブは queued で台帳に載り、前ジョブの終端で自動起動する。
    """

    @pytest.fixture
    @patch("lorairo.gui.services.worker_service.WorkerManager")
    def worker_service(self, mock_worker_manager_class):
        """テスト用WorkerService (WorkerManagerはモック)"""
        mock_worker_manager_class.return_value = Mock()
        service = WorkerService(Mock(), Mock())
        service.worker_manager = mock_worker_manager_class.return_value
        return service

    @staticmethod
    def _setup(mock_container, mock_worker_class, worker_service):
        """registry / worker / manager を直列キュー検証用に構成するヘルパー。

        start_worker は実 WorkerManager と同様に同期で worker_started 通知
        (= `_on_worker_started`) を発行し、起動順を `started_ids` に記録する。
        """
        registry = mock_container.return_value.model_registry
        registry.get_available_models.return_value = _registry_model_infos()
        # Issue #754: 既定はインストール済み (install ジョブの連結なし) として扱う
        adapter = mock_container.return_value.annotator_library
        adapter.get_missing_local_models.return_value = []
        mock_worker_class.side_effect = lambda **kwargs: Mock()

        started_ids: list[str] = []

        def start_and_notify(worker_id, _worker):
            started_ids.append(worker_id)
            worker_service._on_worker_started(worker_id)
            return True

        worker_service.worker_manager.start_worker.side_effect = start_and_notify
        return started_ids

    @staticmethod
    def _terminal_event(worker_id: str, outcome: WorkerOutcome, **kwargs) -> WorkerTerminalEvent:
        return WorkerTerminalEvent(
            worker_id=worker_id,
            worker_type="annotation",
            outcome=outcome,
            **kwargs,
        )

    def test_local_model_job_starts_immediately_when_gpu_idle(
        self, mock_annotation_logic, mock_worker_class, mock_container, worker_service
    ):
        """GPU アイドル時のローカル ML ジョブは即起動し GPU slot を占有する"""
        started_ids = self._setup(mock_container, mock_worker_class, worker_service)

        worker_id = worker_service.start_enhanced_batch_annotation(
            image_paths=["/img/a.jpg"], litellm_model_ids=[_LOCAL_MODEL_ID]
        )

        assert started_ids == [worker_id]
        assert worker_service._gpu_active_worker_id == worker_id
        assert worker_service.job_ledger.get(worker_id).status is JobStatus.RUNNING

    def test_second_local_job_queued_while_gpu_active(
        self, mock_annotation_logic, mock_worker_class, mock_container, worker_service
    ):
        """GPU ジョブ実行中の追加ローカル ML ジョブは queued で待機する"""
        started_ids = self._setup(mock_container, mock_worker_class, worker_service)
        ledger_changed_mock = Mock()

        first_id = worker_service.start_enhanced_batch_annotation(
            image_paths=["/img/a.jpg"], litellm_model_ids=[_LOCAL_MODEL_ID]
        )
        worker_service.job_ledger_changed.connect(ledger_changed_mock)
        second_id = worker_service.start_enhanced_batch_annotation(
            image_paths=["/img/b.jpg"], litellm_model_ids=[_LOCAL_MODEL_ID]
        )

        assert started_ids == [first_id]
        assert second_id.startswith("annotation_")
        entry = worker_service.job_ledger.get(second_id)
        assert entry is not None
        assert entry.status is JobStatus.QUEUED
        ledger_changed_mock.assert_called_once()
        assert [job.worker_id for job in worker_service._gpu_queue] == [second_id]

    def test_api_only_job_runs_parallel_while_gpu_active(
        self, mock_annotation_logic, mock_worker_class, mock_container, worker_service
    ):
        """API 系のみのジョブは GPU ジョブ実行中でも並列起動する (ADR 0066 §6)"""
        started_ids = self._setup(mock_container, mock_worker_class, worker_service)

        first_id = worker_service.start_enhanced_batch_annotation(
            image_paths=["/img/a.jpg"], litellm_model_ids=[_LOCAL_MODEL_ID]
        )
        second_id = worker_service.start_enhanced_batch_annotation(
            image_paths=["/img/b.jpg"], litellm_model_ids=[_API_MODEL_ID]
        )

        assert started_ids == [first_id, second_id]
        assert worker_service._gpu_queue == []
        assert worker_service._gpu_active_worker_id == first_id
        assert worker_service.job_ledger.get(second_id).status is JobStatus.RUNNING

    @pytest.mark.parametrize(
        ("outcome", "cancel_reason"),
        [
            (WorkerOutcome.SUCCEEDED, None),
            (WorkerOutcome.FAILED, None),
            (WorkerOutcome.CANCELED, CancelReason.USER_REQUESTED),
        ],
    )
    def test_queued_job_autostarts_after_active_terminal(
        self,
        mock_annotation_logic,
        mock_worker_class,
        mock_container,
        worker_service,
        outcome,
        cancel_reason,
    ):
        """前 GPU ジョブの終端 (成功/失敗/キャンセル) で待機ジョブが自動起動する"""
        started_ids = self._setup(mock_container, mock_worker_class, worker_service)
        first_id = worker_service.start_enhanced_batch_annotation(
            image_paths=["/img/a.jpg"], litellm_model_ids=[_LOCAL_MODEL_ID]
        )
        second_id = worker_service.start_enhanced_batch_annotation(
            image_paths=["/img/b.jpg"], litellm_model_ids=[_LOCAL_MODEL_ID]
        )

        worker_service._on_worker_terminal(
            self._terminal_event(
                first_id,
                outcome,
                error="boom" if outcome is WorkerOutcome.FAILED else None,
                cancel_reason=cancel_reason,
            )
        )

        assert started_ids == [first_id, second_id]
        assert worker_service._gpu_active_worker_id == second_id
        assert worker_service.current_annotation_worker_id == second_id
        assert worker_service._gpu_queue == []
        assert worker_service.job_ledger.get(second_id).status is JobStatus.RUNNING
        assert worker_service.job_ledger.get(first_id).status.is_terminal

    def test_cancel_queued_job_is_immediately_canceled(
        self, mock_annotation_logic, mock_worker_class, mock_container, worker_service
    ):
        """queued ジョブのキャンセルは実行前に即時 canceled で終端する"""
        started_ids = self._setup(mock_container, mock_worker_class, worker_service)
        canceled_mock = Mock()
        worker_service.enhanced_annotation_canceled.connect(canceled_mock)
        first_id = worker_service.start_enhanced_batch_annotation(
            image_paths=["/img/a.jpg"], litellm_model_ids=[_LOCAL_MODEL_ID]
        )
        second_id = worker_service.start_enhanced_batch_annotation(
            image_paths=["/img/b.jpg"], litellm_model_ids=[_LOCAL_MODEL_ID]
        )

        assert worker_service.cancel_annotation(second_id) is True

        worker_service.worker_manager.cancel_worker.assert_not_called()
        canceled_mock.assert_called_once_with(second_id)
        entry = worker_service.job_ledger.get(second_id)
        assert entry.status is JobStatus.CANCELED
        assert entry.finished_at is not None
        assert worker_service._gpu_queue == []

        # 前ジョブ終端後もキャンセル済みジョブは起動しない
        worker_service._on_worker_terminal(self._terminal_event(first_id, WorkerOutcome.SUCCEEDED))
        assert started_ids == [first_id]
        assert worker_service._gpu_active_worker_id is None

    def test_cancel_job_cancels_queued_entry(
        self, mock_annotation_logic, mock_worker_class, mock_container, worker_service
    ):
        """Jobs タブ行アクションの cancel_job でも queued ジョブを即時取り消せる"""
        self._setup(mock_container, mock_worker_class, worker_service)
        worker_service.start_enhanced_batch_annotation(
            image_paths=["/img/a.jpg"], litellm_model_ids=[_LOCAL_MODEL_ID]
        )
        second_id = worker_service.start_enhanced_batch_annotation(
            image_paths=["/img/b.jpg"], litellm_model_ids=[_LOCAL_MODEL_ID]
        )

        assert worker_service.cancel_job(second_id) is True
        assert worker_service.job_ledger.get(second_id).status is JobStatus.CANCELED
        worker_service.worker_manager.cancel_worker.assert_not_called()

    def test_cancel_all_workers_flushes_gpu_queue(
        self, mock_annotation_logic, mock_worker_class, mock_container, worker_service
    ):
        """cancel_all_workers は待機ジョブも SHUTDOWN 理由で取り消す"""
        self._setup(mock_container, mock_worker_class, worker_service)
        worker_service.start_enhanced_batch_annotation(
            image_paths=["/img/a.jpg"], litellm_model_ids=[_LOCAL_MODEL_ID]
        )
        second_id = worker_service.start_enhanced_batch_annotation(
            image_paths=["/img/b.jpg"], litellm_model_ids=[_LOCAL_MODEL_ID]
        )

        worker_service.cancel_all_workers()

        assert worker_service._gpu_queue == []
        assert worker_service.job_ledger.get(second_id).status is JobStatus.CANCELED
        worker_service.worker_manager.cancel_all_workers.assert_called_once_with(
            reason=CancelReason.SHUTDOWN
        )

    def test_gpu_slot_cleared_when_start_fails(
        self, mock_annotation_logic, mock_worker_class, mock_container, worker_service
    ):
        """GPU ジョブの起動失敗時は slot を解放して例外を伝播する"""
        self._setup(mock_container, mock_worker_class, worker_service)
        worker_service.worker_manager.start_worker.side_effect = None
        worker_service.worker_manager.start_worker.return_value = False

        with pytest.raises(RuntimeError, match="アノテーションワーカー開始失敗"):
            worker_service.start_enhanced_batch_annotation(
                image_paths=["/img/a.jpg"], litellm_model_ids=[_LOCAL_MODEL_ID]
            )

        assert worker_service._gpu_active_worker_id is None

    def test_queued_job_start_failure_marks_failed_and_starts_next(
        self, mock_annotation_logic, mock_worker_class, mock_container, worker_service
    ):
        """待機ジョブの起動失敗は台帳 failed で確定し、次の待機ジョブを起動する"""
        started_ids = self._setup(mock_container, mock_worker_class, worker_service)
        error_mock = Mock()
        worker_service.enhanced_annotation_error.connect(error_mock)
        first_id = worker_service.start_enhanced_batch_annotation(
            image_paths=["/img/a.jpg"], litellm_model_ids=[_LOCAL_MODEL_ID]
        )
        second_id = worker_service.start_enhanced_batch_annotation(
            image_paths=["/img/b.jpg"], litellm_model_ids=[_LOCAL_MODEL_ID]
        )
        third_id = worker_service.start_enhanced_batch_annotation(
            image_paths=["/img/c.jpg"], litellm_model_ids=[_LOCAL_MODEL_ID]
        )

        def start_second_fails(worker_id, _worker):
            if worker_id == second_id:
                return False
            started_ids.append(worker_id)
            worker_service._on_worker_started(worker_id)
            return True

        worker_service.worker_manager.start_worker.side_effect = start_second_fails
        worker_service._on_worker_terminal(self._terminal_event(first_id, WorkerOutcome.SUCCEEDED))

        assert started_ids == [first_id, third_id]
        second_entry = worker_service.job_ledger.get(second_id)
        assert second_entry.status is JobStatus.FAILED
        assert second_entry.summary == "ワーカー開始失敗"
        error_mock.assert_called_once()
        assert worker_service._gpu_active_worker_id == third_id
        assert worker_service.job_ledger.get(third_id).status is JobStatus.RUNNING

    def test_unresponsive_terminal_keeps_gpu_slot(
        self, mock_annotation_logic, mock_worker_class, mock_container, worker_service
    ):
        """UNRESPONSIVE 終端では VRAM 解放が未確認のため次ジョブを起動しない"""
        started_ids = self._setup(mock_container, mock_worker_class, worker_service)
        first_id = worker_service.start_enhanced_batch_annotation(
            image_paths=["/img/a.jpg"], litellm_model_ids=[_LOCAL_MODEL_ID]
        )
        second_id = worker_service.start_enhanced_batch_annotation(
            image_paths=["/img/b.jpg"], litellm_model_ids=[_LOCAL_MODEL_ID]
        )

        worker_service._on_worker_terminal(
            self._terminal_event(first_id, WorkerOutcome.UNRESPONSIVE, error="unresponsive")
        )

        assert started_ids == [first_id]
        assert worker_service._gpu_active_worker_id == first_id
        assert [job.worker_id for job in worker_service._gpu_queue] == [second_id]


@patch("lorairo.gui.services.worker_service.get_service_container")
@patch("lorairo.gui.services.worker_service.ModelInstallWorker")
@patch("lorairo.gui.services.worker_service.AnnotationWorker")
@patch.object(WorkerService, "annotation_logic", create=True)
class TestModelInstallChain:
    """model_install ジョブの前段連結 (Issue #754, ADR 0066 §5) のユニットテスト。

    未インストールのローカル ML モデルを含むアノテーション開始時、install ジョブが
    GPU 直列スロットで先行実行され、アノテーションは queued で待機する。
    install 成功 → アノテーション自動起動、失敗/キャンセル → アノテーション取り消し。
    """

    @pytest.fixture
    @patch("lorairo.gui.services.worker_service.WorkerManager")
    def worker_service(self, mock_worker_manager_class):
        """テスト用WorkerService (WorkerManagerはモック)"""
        mock_worker_manager_class.return_value = Mock()
        service = WorkerService(Mock(), Mock())
        service.worker_manager = mock_worker_manager_class.return_value
        return service

    @staticmethod
    def _setup(mock_container, mock_annotation_worker_class, mock_install_worker_class, worker_service):
        """未インストールモデルあり (install 連結発動) の構成ヘルパー。"""
        registry = mock_container.return_value.model_registry
        registry.get_available_models.return_value = _registry_model_infos()
        adapter = mock_container.return_value.annotator_library
        adapter.get_missing_local_models.return_value = [_LOCAL_MODEL_ID]
        mock_annotation_worker_class.side_effect = lambda **kwargs: Mock()
        mock_install_worker_class.side_effect = lambda *args, **kwargs: Mock()

        started_ids: list[str] = []

        def start_and_notify(worker_id, _worker):
            started_ids.append(worker_id)
            worker_service._on_worker_started(worker_id)
            return True

        worker_service.worker_manager.start_worker.side_effect = start_and_notify
        return started_ids

    @staticmethod
    def _terminal_event(worker_id: str, outcome: WorkerOutcome, **kwargs) -> WorkerTerminalEvent:
        return WorkerTerminalEvent(
            worker_id=worker_id,
            worker_type="model_install",
            outcome=outcome,
            **kwargs,
        )

    def test_missing_model_starts_install_first_and_queues_annotation(
        self,
        mock_annotation_logic,
        mock_annotation_worker_class,
        mock_install_worker_class,
        mock_container,
        worker_service,
    ):
        """未インストールモデル検出時は install が先行起動しアノテーションは queued"""
        started_ids = self._setup(
            mock_container, mock_annotation_worker_class, mock_install_worker_class, worker_service
        )

        annotation_id = worker_service.start_enhanced_batch_annotation(
            image_paths=["/img/a.jpg"], litellm_model_ids=[_LOCAL_MODEL_ID]
        )

        assert len(started_ids) == 1
        install_id = started_ids[0]
        assert install_id.startswith("model_install_")
        assert worker_service._gpu_active_worker_id == install_id
        assert worker_service._install_chained_annotation == {install_id: annotation_id}
        # install ワーカーには未インストールモデルのリストが渡される
        args = mock_install_worker_class.call_args.args
        assert args[1] == [_LOCAL_MODEL_ID]
        # 台帳: install=RUNNING (job_type=model_install)、annotation=QUEUED
        install_entry = worker_service.job_ledger.get(install_id)
        assert install_entry.status is JobStatus.RUNNING
        assert install_entry.job_type == "model_install"
        assert install_entry.title == "モデルインストール"
        assert worker_service.job_ledger.get(annotation_id).status is JobStatus.QUEUED

    def test_installed_models_skip_install_job(
        self,
        mock_annotation_logic,
        mock_annotation_worker_class,
        mock_install_worker_class,
        mock_container,
        worker_service,
    ):
        """全モデルインストール済みなら install ジョブは作られず従来どおり即起動"""
        started_ids = self._setup(
            mock_container, mock_annotation_worker_class, mock_install_worker_class, worker_service
        )
        mock_container.return_value.annotator_library.get_missing_local_models.return_value = []

        annotation_id = worker_service.start_enhanced_batch_annotation(
            image_paths=["/img/a.jpg"], litellm_model_ids=[_LOCAL_MODEL_ID]
        )

        assert started_ids == [annotation_id]
        mock_install_worker_class.assert_not_called()
        assert worker_service._install_chained_annotation == {}

    def test_api_only_selection_does_not_query_installer(
        self,
        mock_annotation_logic,
        mock_annotation_worker_class,
        mock_install_worker_class,
        mock_container,
        worker_service,
    ):
        """API モデルのみの選択では installer への問い合わせ自体を行わない"""
        self._setup(mock_container, mock_annotation_worker_class, mock_install_worker_class, worker_service)

        worker_service.start_enhanced_batch_annotation(
            image_paths=["/img/a.jpg"], litellm_model_ids=[_API_MODEL_ID]
        )

        mock_container.return_value.annotator_library.get_missing_local_models.assert_not_called()
        mock_install_worker_class.assert_not_called()

    def test_install_success_autostarts_chained_annotation(
        self,
        mock_annotation_logic,
        mock_annotation_worker_class,
        mock_install_worker_class,
        mock_container,
        worker_service,
    ):
        """install 成功終端で待機中のアノテーションが自動起動する"""
        started_ids = self._setup(
            mock_container, mock_annotation_worker_class, mock_install_worker_class, worker_service
        )
        annotation_id = worker_service.start_enhanced_batch_annotation(
            image_paths=["/img/a.jpg"], litellm_model_ids=[_LOCAL_MODEL_ID]
        )
        install_id = started_ids[0]

        worker_service._on_worker_terminal(self._terminal_event(install_id, WorkerOutcome.SUCCEEDED))

        assert started_ids == [install_id, annotation_id]
        assert worker_service._gpu_active_worker_id == annotation_id
        assert worker_service._install_chained_annotation == {}
        assert worker_service.job_ledger.get(install_id).status is JobStatus.FINISHED
        assert worker_service.job_ledger.get(annotation_id).status is JobStatus.RUNNING

    @pytest.mark.parametrize(
        ("outcome", "cancel_reason"),
        [
            (WorkerOutcome.FAILED, None),
            (WorkerOutcome.CANCELED, CancelReason.USER_REQUESTED),
        ],
    )
    def test_install_failure_or_cancel_cancels_chained_annotation(
        self,
        mock_annotation_logic,
        mock_annotation_worker_class,
        mock_install_worker_class,
        mock_container,
        worker_service,
        outcome,
        cancel_reason,
    ):
        """install の失敗/キャンセルで連結アノテーションも取り消される"""
        started_ids = self._setup(
            mock_container, mock_annotation_worker_class, mock_install_worker_class, worker_service
        )
        annotation_id = worker_service.start_enhanced_batch_annotation(
            image_paths=["/img/a.jpg"], litellm_model_ids=[_LOCAL_MODEL_ID]
        )
        install_id = started_ids[0]

        worker_service._on_worker_terminal(
            self._terminal_event(
                install_id,
                outcome,
                error="boom" if outcome is WorkerOutcome.FAILED else None,
                cancel_reason=cancel_reason,
            )
        )

        # アノテーションは起動されず canceled で終端
        assert started_ids == [install_id]
        assert worker_service.job_ledger.get(annotation_id).status is JobStatus.CANCELED
        assert worker_service.job_ledger.get(install_id).status.is_terminal
        assert worker_service._install_chained_annotation == {}
        assert worker_service._gpu_queue == []
        assert worker_service._gpu_active_worker_id is None

    def test_install_queued_behind_running_gpu_job(
        self,
        mock_annotation_logic,
        mock_annotation_worker_class,
        mock_install_worker_class,
        mock_container,
        worker_service,
    ):
        """GPU ジョブ実行中の install は queued で待機し、順に起動する"""
        started_ids = self._setup(
            mock_container, mock_annotation_worker_class, mock_install_worker_class, worker_service
        )
        # 先行: インストール済みモデルのアノテーションが GPU slot を占有
        mock_container.return_value.annotator_library.get_missing_local_models.return_value = []
        first_id = worker_service.start_enhanced_batch_annotation(
            image_paths=["/img/a.jpg"], litellm_model_ids=[_LOCAL_MODEL_ID]
        )
        # 後発: 未インストールモデルの選択 → install + annotation が queued
        mock_container.return_value.annotator_library.get_missing_local_models.return_value = [
            _LOCAL_MODEL_ID
        ]
        second_id = worker_service.start_enhanced_batch_annotation(
            image_paths=["/img/b.jpg"], litellm_model_ids=[_LOCAL_MODEL_ID]
        )

        queued_ids = [job.worker_id for job in worker_service._gpu_queue]
        assert len(queued_ids) == 2
        install_id = queued_ids[0]
        assert install_id.startswith("model_install_")
        assert queued_ids[1] == second_id
        assert worker_service.job_ledger.get(install_id).status is JobStatus.QUEUED

        # 先行ジョブ終端 → install が起動
        worker_service._on_worker_terminal(
            WorkerTerminalEvent(
                worker_id=first_id, worker_type="annotation", outcome=WorkerOutcome.SUCCEEDED
            )
        )
        assert started_ids == [first_id, install_id]
        assert worker_service.job_ledger.get(install_id).status is JobStatus.RUNNING

        # install 終端 → annotation が起動
        worker_service._on_worker_terminal(self._terminal_event(install_id, WorkerOutcome.SUCCEEDED))
        assert started_ids == [first_id, install_id, second_id]

    def test_install_progress_updates_ledger_summary(
        self,
        mock_annotation_logic,
        mock_annotation_worker_class,
        mock_install_worker_class,
        mock_container,
        worker_service,
    ):
        """install ワーカーの進捗が台帳サマリーへ反映される (Issue #754)"""
        self._setup(mock_container, mock_annotation_worker_class, mock_install_worker_class, worker_service)
        worker_service.start_enhanced_batch_annotation(
            image_paths=["/img/a.jpg"], litellm_model_ids=[_LOCAL_MODEL_ID]
        )
        install_id = worker_service._gpu_active_worker_id
        ledger_changed_mock = Mock()
        worker_service.job_ledger_changed.connect(ledger_changed_mock)

        from lorairo.gui.workers.base import WorkerProgress

        worker_service._on_model_install_progress(
            install_id,
            WorkerProgress(percentage=45, status_message="wd をダウンロード中 45% (350.0/780.0 MB)"),
        )

        entry = worker_service.job_ledger.get(install_id)
        assert entry.summary == "wd をダウンロード中 45% (350.0/780.0 MB)"
        ledger_changed_mock.assert_called_once()

    def test_user_cancel_of_running_install_via_cancel_job(
        self,
        mock_annotation_logic,
        mock_annotation_worker_class,
        mock_install_worker_class,
        mock_container,
        worker_service,
    ):
        """Jobs 行のキャンセルは実行中 install を manager 経由で取り消す"""
        started_ids = self._setup(
            mock_container, mock_annotation_worker_class, mock_install_worker_class, worker_service
        )
        worker_service.start_enhanced_batch_annotation(
            image_paths=["/img/a.jpg"], litellm_model_ids=[_LOCAL_MODEL_ID]
        )
        install_id = started_ids[0]
        worker_service.worker_manager.cancel_worker.return_value = True

        assert worker_service.cancel_job(install_id) is True
        worker_service.worker_manager.cancel_worker.assert_called_once_with(install_id)
