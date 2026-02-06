"""パイプライン制御サービス

Workerパイプライン（Search + Thumbnail）の完全な制御を担当。
- パイプライン連鎖（Search → Thumbnail）
- エラーハンドリング
- 進捗表示
- キャンセル制御

MainWindow.cancel_current_pipeline()から抽出。
"""

from typing import Any

from loguru import logger

from lorairo.gui.services.worker_service import WorkerService
from lorairo.gui.workers.database_worker import SearchResult


class PipelineControlService:
    """パイプライン制御サービス

    Search + Thumbnailワーカーのパイプライン制御を担当。
    MainWindowから分離し、パイプライン制御ロジックを集約。
    """

    def __init__(
        self,
        worker_service: WorkerService | None = None,
        thumbnail_selector: Any | None = None,
        filter_search_panel: Any | None = None,
    ):
        """初期化

        Args:
            worker_service: WorkerService
            thumbnail_selector: サムネイルセレクター（clear_thumbnails()メソッドを持つ）
            filter_search_panel: フィルター検索パネル（hide_progress_after_completion()メソッドを持つ）
        """
        self.worker_service = worker_service
        self.thumbnail_selector = thumbnail_selector
        self.filter_search_panel = filter_search_panel

    # ============================================================
    # パイプライン連鎖ロジック
    # ============================================================

    def on_search_completed(self, search_result: Any) -> None:
        """SearchWorker完了時にページネーション初期化を実行

        Args:
            search_result: SearchResultオブジェクトまたは辞書


        """
        if not self.worker_service:
            logger.error("WorkerService not initialized - cannot start thumbnail loading")
            return

        try:
            # SearchResultの検証
            if isinstance(search_result, SearchResult):
                if self.thumbnail_selector and hasattr(
                    self.thumbnail_selector, "initialize_pagination_search"
                ):
                    self.thumbnail_selector.initialize_pagination_search(
                        search_result=search_result,
                        worker_service=self.worker_service,
                    )
                    logger.info("Thumbnail pagination initialized after search completion")
                else:
                    logger.warning(
                        "ThumbnailSelectorWidget.initialize_pagination_search method not found"
                    )
            else:
                logger.warning(f"Invalid search_result type: {type(search_result)}")

        except Exception as e:
            logger.error(f"Failed to start thumbnail loading after search: {e}", exc_info=True)

    def on_thumbnail_completed(self, thumbnail_result: Any) -> None:
        """ThumbnailWorker完了時にThumbnailSelectorWidget更新

        Args:
            thumbnail_result: サムネイル生成結果


        """
        if not self.thumbnail_selector:
            logger.warning("ThumbnailSelectorWidget not available - thumbnail display update skipped")
            return

        try:
            if hasattr(self.thumbnail_selector, "handle_thumbnail_page_result"):
                self.thumbnail_selector.handle_thumbnail_page_result(thumbnail_result)
                logger.info("ThumbnailSelectorWidget handled paged thumbnail result")
            elif hasattr(self.thumbnail_selector, "load_thumbnails_from_result"):
                self.thumbnail_selector.load_thumbnails_from_result(thumbnail_result)
                logger.info("ThumbnailSelectorWidget updated with legacy thumbnail result")
            else:
                logger.warning("ThumbnailSelectorWidget result handler method not found")

            # パイプライン完了後にプログレスバーを非表示
            if self.filter_search_panel and hasattr(
                self.filter_search_panel, "hide_progress_after_completion"
            ):
                self.filter_search_panel.hide_progress_after_completion()

        except Exception as e:
            logger.error(f"Failed to update ThumbnailSelectorWidget: {e}", exc_info=True)

    # ============================================================
    # エラーハンドリング統合
    # ============================================================

    def on_search_error(self, error_message: str) -> None:
        """Pipeline検索エラー時の処理（検索結果破棄）

        Args:
            error_message: エラーメッセージ


        """
        logger.error(f"Pipeline search error: {error_message}")

        # FilterSearchPanelへのエラー通知
        if self.filter_search_panel and hasattr(self.filter_search_panel, "handle_pipeline_error"):
            self.filter_search_panel.handle_pipeline_error("search", {"message": error_message})

        # 検索結果破棄（要求仕様通り）
        if self.thumbnail_selector and hasattr(self.thumbnail_selector, "clear_thumbnails"):
            self.thumbnail_selector.clear_thumbnails()

    def on_thumbnail_error(self, error_message: str) -> None:
        """Pipelineサムネイル生成エラー時の処理（検索結果破棄）

        Args:
            error_message: エラーメッセージ


        """
        logger.error(f"Pipeline thumbnail error: {error_message}")

        # FilterSearchPanelへのエラー通知
        if self.filter_search_panel and hasattr(self.filter_search_panel, "handle_pipeline_error"):
            self.filter_search_panel.handle_pipeline_error("thumbnail", {"message": error_message})

        # 検索結果破棄（要求仕様通り）
        if self.thumbnail_selector and hasattr(self.thumbnail_selector, "clear_thumbnails"):
            self.thumbnail_selector.clear_thumbnails()

        # エラー時もプログレスバーを非表示
        if self.filter_search_panel and hasattr(self.filter_search_panel, "hide_progress_after_completion"):
            self.filter_search_panel.hide_progress_after_completion()

    # ============================================================
    # 進捗状態管理統合
    # ============================================================

    def on_search_started(self, _worker_id: str) -> None:
        """Pipeline検索フェーズ開始時の進捗表示

        Args:
            _worker_id: ワーカーID（未使用）


        """
        if self.filter_search_panel and hasattr(self.filter_search_panel, "update_pipeline_progress"):
            self.filter_search_panel.update_pipeline_progress("検索中...", 0.0, 0.3)

    def on_thumbnail_started(self, _worker_id: str) -> None:
        """Pipelineサムネイル生成フェーズ開始時の進捗表示

        Args:
            _worker_id: ワーカーID（未使用）


        """
        if self.filter_search_panel and hasattr(self.filter_search_panel, "update_pipeline_progress"):
            self.filter_search_panel.update_pipeline_progress("サムネイル読込中...", 0.3, 1.0)

    # ============================================================
    # キャンセル制御
    # ============================================================

    def cancel_current_pipeline(self) -> None:
        """現在のパイプライン全体をキャンセル

        SearchWorker + ThumbnailWorkerのcascade cancellationを実行し、
        関連UIのクリーンアップを行う。
        """
        if not self.worker_service:
            logger.warning("WorkerService not available - Pipeline cancellation skipped")
            return

        try:
            # SearchWorker + ThumbnailWorker の cascade cancellation
            if (
                hasattr(self.worker_service, "current_search_worker_id")
                and self.worker_service.current_search_worker_id
            ):
                self.worker_service.cancel_search(self.worker_service.current_search_worker_id)
                logger.info("Search worker cancelled in pipeline")

            if (
                hasattr(self.worker_service, "current_thumbnail_worker_id")
                and self.worker_service.current_thumbnail_worker_id
            ):
                self.worker_service.cancel_thumbnail_load(self.worker_service.current_thumbnail_worker_id)
                logger.info("Thumbnail worker cancelled in pipeline")

            # キャンセル時の結果破棄（要求仕様通り）
            if self.thumbnail_selector and hasattr(self.thumbnail_selector, "clear_thumbnails"):
                self.thumbnail_selector.clear_thumbnails()

            # キャンセル時もプログレスバーを非表示
            if self.filter_search_panel and hasattr(
                self.filter_search_panel, "hide_progress_after_completion"
            ):
                self.filter_search_panel.hide_progress_after_completion()

            logger.info("Pipeline cancellation completed")

        except Exception as e:
            logger.error(f"Pipeline cancellation failed: {e}", exc_info=True)
