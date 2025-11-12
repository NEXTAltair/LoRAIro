"""パイプライン制御サービス

Workerパイプライン（Search + Thumbnail）のキャンセル制御を担当。
MainWindow.cancel_current_pipeline()から抽出（Phase 2.4 Stage 3）。
"""

from typing import Any

from loguru import logger

from lorairo.gui.services.worker_service import WorkerService


class PipelineControlService:
    """パイプライン制御サービス

    Search + Thumbnailワーカーのパイプライン制御を担当。
    MainWindowから分離し、パイプライン制御ロジックを集約。

    Phase 2.4 Stage 3で作成。
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
