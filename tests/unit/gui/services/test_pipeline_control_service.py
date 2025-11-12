"""PipelineControlServiceの単体テスト

Phase 2.4 Stage 3で作成されたPipelineControlServiceのテスト。
"""

from unittest.mock import Mock

import pytest

from lorairo.gui.services.pipeline_control_service import PipelineControlService


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
        mock_worker_service.cancel_search.assert_called_once_with("search-123")
        mock_worker_service.cancel_thumbnail_load.assert_called_once_with("thumb-456")
        mock_thumbnail_selector.clear_thumbnails.assert_called_once()
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
