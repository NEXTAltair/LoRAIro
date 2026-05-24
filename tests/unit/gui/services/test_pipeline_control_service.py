"""PipelineControlServiceの単体テスト

Phase 2.4 Stage 3で作成されたPipelineControlServiceのテスト。
"""

from unittest.mock import Mock

import pytest

from lorairo.gui.services.pipeline_control_service import PipelineControlService
from lorairo.gui.workers.search_worker import SearchResult
from lorairo.gui.workers.terminal import CancelReason, WorkerOutcome, WorkerTerminalEvent
from lorairo.services.search_models import SearchConditions


@pytest.fixture
def mock_worker_service():
    """WorkerServiceのモック"""
    service = Mock()
    service.current_search_worker_id = "search-123"
    service.current_thumbnail_worker_id = "thumb-456"
    service.cancel_search = Mock()
    service.cancel_thumbnail_load = Mock()
    return service


@pytest.fixture
def mock_thumbnail_selector():
    """サムネイルセレクターのモック"""
    selector = Mock()
    selector.clear_thumbnails = Mock()
    return selector


@pytest.fixture
def mock_filter_panel():
    """フィルターパネルのモック"""
    panel = Mock()
    panel.hide_progress_after_completion = Mock()
    panel.clear_pipeline_results = Mock()
    return panel


@pytest.fixture
def service(mock_worker_service, mock_thumbnail_selector, mock_filter_panel):
    """PipelineControlServiceインスタンス"""
    return PipelineControlService(
        worker_service=mock_worker_service,
        thumbnail_selector=mock_thumbnail_selector,
        filter_search_panel=mock_filter_panel,
    )


@pytest.mark.gui
class TestPipelineControlServiceInit:
    """初期化テスト"""

    def test_init_with_all_params(self, mock_worker_service, mock_thumbnail_selector, mock_filter_panel):
        """全パラメータ有り"""
        service = PipelineControlService(
            worker_service=mock_worker_service,
            thumbnail_selector=mock_thumbnail_selector,
            filter_search_panel=mock_filter_panel,
        )
        assert service.worker_service is mock_worker_service
        assert service.thumbnail_selector is mock_thumbnail_selector
        assert service.filter_search_panel is mock_filter_panel

    def test_init_without_params(self):
        """パラメータ無し"""
        service = PipelineControlService()
        assert service.worker_service is None
        assert service.thumbnail_selector is None
        assert service.filter_search_panel is None


@pytest.mark.gui
class TestCancelCurrentPipeline:
    """cancel_current_pipeline()テスト"""

    def test_cancel_pipeline_success(
        self, service, mock_worker_service, mock_thumbnail_selector, mock_filter_panel
    ):
        """正常なパイプラインキャンセル"""
        # Execute
        service.cancel_current_pipeline()

        # Assert
        mock_worker_service.cancel_search.assert_called_once_with(
            "search-123",
            reason=CancelReason.PIPELINE_CANCEL,
        )
        mock_worker_service.cancel_thumbnail_load.assert_called_once_with(
            "thumb-456",
            reason=CancelReason.PIPELINE_CANCEL,
        )
        mock_thumbnail_selector.clear_thumbnails.assert_called_once()
        mock_filter_panel.clear_pipeline_results.assert_called_once()
        mock_filter_panel.hide_progress_after_completion.assert_called_once()

    def test_cancel_pipeline_without_worker_service(self, mock_thumbnail_selector, mock_filter_panel):
        """WorkerService無し"""
        service = PipelineControlService(
            worker_service=None,
            thumbnail_selector=mock_thumbnail_selector,
            filter_search_panel=mock_filter_panel,
        )

        # Execute
        service.cancel_current_pipeline()

        # Assert - WorkerServiceないので何もキャンセルされない
        mock_thumbnail_selector.clear_thumbnails.assert_not_called()

    def test_cancel_pipeline_no_active_workers(
        self, mock_worker_service, mock_thumbnail_selector, mock_filter_panel
    ):
        """アクティブなワーカーなし"""
        # Setup - ワーカーIDなし
        mock_worker_service.current_search_worker_id = None
        mock_worker_service.current_thumbnail_worker_id = None
        service = PipelineControlService(
            worker_service=mock_worker_service,
            thumbnail_selector=mock_thumbnail_selector,
            filter_search_panel=mock_filter_panel,
        )

        # Execute
        service.cancel_current_pipeline()

        # Assert - キャンセルは呼ばれないが、UIクリアは実行
        mock_worker_service.cancel_search.assert_not_called()
        mock_worker_service.cancel_thumbnail_load.assert_not_called()
        mock_thumbnail_selector.clear_thumbnails.assert_called_once()
        mock_filter_panel.clear_pipeline_results.assert_called_once()

    def test_cancel_pipeline_without_thumbnail_selector(self, mock_worker_service, mock_filter_panel):
        """サムネイルセレクター無し"""
        service = PipelineControlService(
            worker_service=mock_worker_service,
            thumbnail_selector=None,
            filter_search_panel=mock_filter_panel,
        )

        # Execute
        service.cancel_current_pipeline()

        # Assert - ワーカーキャンセルは実行
        mock_worker_service.cancel_search.assert_called_once()
        mock_worker_service.cancel_thumbnail_load.assert_called_once()

    def test_cancel_pipeline_with_error(
        self, mock_worker_service, mock_thumbnail_selector, mock_filter_panel
    ):
        """キャンセル中のエラー"""
        # Setup - cancel_searchでエラー
        mock_worker_service.cancel_search.side_effect = RuntimeError("Cancel failed")
        service = PipelineControlService(
            worker_service=mock_worker_service,
            thumbnail_selector=mock_thumbnail_selector,
            filter_search_panel=mock_filter_panel,
        )

        # Execute - エラーログ出力されるが、クラッシュしない
        service.cancel_current_pipeline()


@pytest.mark.gui
class TestPipelineFlow:
    """検索完了・サムネイル完了のフローテスト"""

    def test_on_search_completed_initializes_pagination(
        self, service, mock_worker_service, mock_thumbnail_selector
    ):
        search_result = SearchResult(
            image_metadata=[{"id": 1, "stored_image_path": "/tmp/1.png"}],
            total_count=1,
            search_time=0.1,
            filter_conditions=SearchConditions(search_type="tags", keywords=[], tag_logic="and"),
        )

        service.on_search_completed(search_result)

        mock_thumbnail_selector.initialize_pagination_search.assert_called_once_with(
            search_result=search_result,
            worker_service=mock_worker_service,
        )

    def test_on_thumbnail_completed_forwards_to_paged_handler(
        self, service, mock_thumbnail_selector, mock_filter_panel
    ):
        thumbnail_result = Mock()

        service.on_thumbnail_completed(thumbnail_result)

        mock_thumbnail_selector.handle_thumbnail_page_result.assert_called_once_with(thumbnail_result)
        mock_filter_panel.hide_progress_after_completion.assert_called_once()

    def test_on_search_canceled_clears_results_without_error(
        self, service, mock_thumbnail_selector, mock_filter_panel
    ):
        service.on_search_canceled("search-123")

        mock_thumbnail_selector.clear_thumbnails.assert_called_once()
        mock_filter_panel.clear_pipeline_results.assert_called_once()
        mock_filter_panel.hide_progress_after_completion.assert_called_once()

    def test_on_search_replaced_canceled_keeps_current_results(
        self, service, mock_thumbnail_selector, mock_filter_panel
    ):
        event = WorkerTerminalEvent(
            worker_id="search-123",
            worker_type="search",
            outcome=WorkerOutcome.CANCELED,
            cancel_reason=CancelReason.SEARCH_REPLACED,
        )

        service.on_search_canceled(event)

        mock_thumbnail_selector.clear_thumbnails.assert_not_called()
        mock_filter_panel.clear_pipeline_results.assert_not_called()
        mock_filter_panel.hide_progress_after_completion.assert_called_once()

    def test_on_thumbnail_canceled_keeps_pipeline_results_without_error(
        self, service, mock_thumbnail_selector, mock_filter_panel
    ):
        service.on_thumbnail_canceled("thumbnail-123")

        mock_thumbnail_selector.clear_thumbnails.assert_not_called()
        mock_filter_panel.clear_pipeline_results.assert_not_called()

    def test_on_search_completed_invalid_type_logs_warning(self, service):
        """SearchResult 以外の型が渡されたとき warning ログを出力し例外を起こさない"""
        service.on_search_completed("not_a_search_result")
        # 例外が起きないことを確認（暗黙に assert）

    def test_on_search_completed_thumbnail_selector_none(self, mock_worker_service, mock_filter_panel):
        """thumbnail_selector=None のとき SearchResult でも例外なし（警告のみ）"""
        service = PipelineControlService(
            worker_service=mock_worker_service,
            thumbnail_selector=None,
            filter_search_panel=mock_filter_panel,
        )
        search_result = SearchResult(
            image_metadata=[],
            total_count=0,
            search_time=0.0,
            filter_conditions=SearchConditions(search_type="tags", keywords=[], tag_logic="and"),
        )
        service.on_search_completed(search_result)
        # 例外なし

    def test_on_search_completed_no_worker_service_logs_error(
        self, mock_thumbnail_selector, mock_filter_panel
    ):
        """worker_service が None のとき error ログを出力して早期リターン"""
        service = PipelineControlService(
            worker_service=None,
            thumbnail_selector=mock_thumbnail_selector,
            filter_search_panel=mock_filter_panel,
        )
        search_result = SearchResult(
            image_metadata=[],
            total_count=0,
            search_time=0.0,
            filter_conditions=SearchConditions(search_type="tags", keywords=[], tag_logic="and"),
        )
        service.on_search_completed(search_result)
        mock_thumbnail_selector.initialize_pagination_search.assert_not_called()

    def test_on_thumbnail_completed_uses_legacy_handler(self, mock_worker_service, mock_filter_panel):
        """handle_thumbnail_page_result がなく load_thumbnails_from_result があるとき legacy を使う"""
        selector = Mock(spec=["load_thumbnails_from_result"])
        # spec により handle_thumbnail_page_result は hasattr で False になる
        service = PipelineControlService(
            worker_service=mock_worker_service,
            thumbnail_selector=selector,
            filter_search_panel=mock_filter_panel,
        )
        thumbnail_result = Mock()
        service.on_thumbnail_completed(thumbnail_result)
        selector.load_thumbnails_from_result.assert_called_once_with(thumbnail_result)
        mock_filter_panel.hide_progress_after_completion.assert_called_once()

    def test_on_thumbnail_completed_no_handler_logs_warning(self, mock_worker_service, mock_filter_panel):
        """どちらのメソッドもないとき warning ログを出して例外なし"""
        selector = Mock(spec=[])  # メソッドなし
        service = PipelineControlService(
            worker_service=mock_worker_service,
            thumbnail_selector=selector,
            filter_search_panel=mock_filter_panel,
        )
        service.on_thumbnail_completed(Mock())
        # 例外なし、hide_progress_after_completion は呼ばれない（handler なし→ウォーニングのみ）

    def test_on_thumbnail_completed_filter_panel_none(self, service, mock_thumbnail_selector):
        """filter_search_panel=None のとき hide_progress が呼ばれず例外もなし"""
        service.filter_search_panel = None
        service.on_thumbnail_completed(Mock())
        # hide_progress_after_completion は None なので呼ばれない → 例外なし

    def test_on_thumbnail_completed_thumbnail_selector_none(self, mock_worker_service, mock_filter_panel):
        """thumbnail_selector=None のとき early return し例外なし"""
        service = PipelineControlService(
            worker_service=mock_worker_service,
            thumbnail_selector=None,
            filter_search_panel=mock_filter_panel,
        )
        service.on_thumbnail_completed(Mock())
        mock_filter_panel.hide_progress_after_completion.assert_not_called()

    def test_on_search_started_filter_panel_none(self, mock_worker_service, mock_thumbnail_selector):
        """filter_search_panel=None のとき例外なし"""
        service = PipelineControlService(
            worker_service=mock_worker_service,
            thumbnail_selector=mock_thumbnail_selector,
            filter_search_panel=None,
        )
        service.on_search_started("worker-id-001")
        # 例外なし

    def test_on_search_started_calls_update_progress(self, service, mock_filter_panel):
        """filter_search_panel がある場合 update_pipeline_progress が呼ばれる"""
        service.on_search_started("worker-id-001")
        mock_filter_panel.update_pipeline_progress.assert_called_once_with("検索中...", 0.0, 0.3)

    def test_on_thumbnail_started_filter_panel_none(self, mock_worker_service, mock_thumbnail_selector):
        """filter_search_panel=None のとき例外なし"""
        service = PipelineControlService(
            worker_service=mock_worker_service,
            thumbnail_selector=mock_thumbnail_selector,
            filter_search_panel=None,
        )
        service.on_thumbnail_started("worker-id-002")
        # 例外なし

    def test_on_thumbnail_started_calls_update_progress(self, service, mock_filter_panel):
        """filter_search_panel がある場合 update_pipeline_progress が呼ばれる"""
        service.on_thumbnail_started("worker-id-002")
        mock_filter_panel.update_pipeline_progress.assert_called_once_with("サムネイル読込中...", 0.3, 1.0)

    def test_on_search_error_filter_panel_none(self, mock_worker_service, mock_thumbnail_selector):
        """filter_search_panel=None のとき例外なし"""
        service = PipelineControlService(
            worker_service=mock_worker_service,
            thumbnail_selector=mock_thumbnail_selector,
            filter_search_panel=None,
        )
        service.on_search_error("search failed")
        mock_thumbnail_selector.clear_thumbnails.assert_called_once()

    def test_on_search_error_thumbnail_selector_none(self, mock_worker_service, mock_filter_panel):
        """thumbnail_selector=None のとき clear_thumbnails が呼ばれず例外なし"""
        service = PipelineControlService(
            worker_service=mock_worker_service,
            thumbnail_selector=None,
            filter_search_panel=mock_filter_panel,
        )
        service.on_search_error("search failed")
        mock_filter_panel.handle_pipeline_error.assert_called_once_with(
            "search", {"message": "search failed"}
        )

    def test_on_thumbnail_error_filter_panel_none(self, mock_worker_service, mock_thumbnail_selector):
        """filter_search_panel=None のとき例外なし"""
        service = PipelineControlService(
            worker_service=mock_worker_service,
            thumbnail_selector=mock_thumbnail_selector,
            filter_search_panel=None,
        )
        service.on_thumbnail_error("thumbnail failed")
        mock_thumbnail_selector.clear_thumbnails.assert_called_once()

    def test_on_thumbnail_error_thumbnail_selector_none(self, mock_worker_service, mock_filter_panel):
        """thumbnail_selector=None のとき clear_thumbnails が呼ばれず例外なし"""
        service = PipelineControlService(
            worker_service=mock_worker_service,
            thumbnail_selector=None,
            filter_search_panel=mock_filter_panel,
        )
        service.on_thumbnail_error("thumbnail failed")
        mock_filter_panel.handle_pipeline_error.assert_called_once_with(
            "thumbnail", {"message": "thumbnail failed"}
        )
        mock_filter_panel.hide_progress_after_completion.assert_called_once()

    def test_on_search_error_notifies_panel_and_clears_thumbnails(
        self, service, mock_filter_panel, mock_thumbnail_selector
    ):
        """filter_search_panel と thumbnail_selector の両方がある場合の正常フロー"""
        service.on_search_error("error msg")
        mock_filter_panel.handle_pipeline_error.assert_called_once_with("search", {"message": "error msg"})
        mock_thumbnail_selector.clear_thumbnails.assert_called_once()

    def test_on_thumbnail_error_notifies_panel_and_clears_thumbnails(
        self, service, mock_filter_panel, mock_thumbnail_selector
    ):
        """filter_search_panel と thumbnail_selector の両方がある場合の正常フロー"""
        service.on_thumbnail_error("thumb error")
        mock_filter_panel.handle_pipeline_error.assert_called_once_with(
            "thumbnail", {"message": "thumb error"}
        )
        mock_thumbnail_selector.clear_thumbnails.assert_called_once()
        mock_filter_panel.hide_progress_after_completion.assert_called_once()

    def test_on_worker_terminal_abnormal_thumbnail_defers_cleanup_to_compat_error(
        self, service, mock_thumbnail_selector, mock_filter_panel
    ):
        event = WorkerTerminalEvent(
            worker_id="thumbnail-123",
            worker_type="thumbnail",
            outcome=WorkerOutcome.TERMINATED,
            error="terminated",
            cancel_reason=CancelReason.USER_REQUESTED,
        )

        service.on_worker_terminal(event)

        mock_thumbnail_selector.clear_thumbnails.assert_not_called()
        mock_filter_panel.clear_pipeline_results.assert_not_called()
        mock_filter_panel.hide_progress_after_completion.assert_not_called()

    def test_on_worker_terminal_replacement_abnormal_keeps_results(
        self, service, mock_thumbnail_selector, mock_filter_panel
    ):
        event = WorkerTerminalEvent(
            worker_id="thumbnail-123",
            worker_type="thumbnail",
            outcome=WorkerOutcome.TERMINATED,
            error="terminated",
            cancel_reason=CancelReason.THUMBNAIL_REPLACED,
        )

        service.on_worker_terminal(event)

        mock_thumbnail_selector.clear_thumbnails.assert_not_called()
        mock_filter_panel.clear_pipeline_results.assert_not_called()
        mock_filter_panel.hide_progress_after_completion.assert_not_called()
