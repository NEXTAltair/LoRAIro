"""データベース検索専用ワーカー"""

import traceback
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ...services.search_criteria_processor import SearchCriteriaProcessor
from ...services.search_review_status import apply_review_filter
from ...utils.log import logger
from .base import CancellationError, LoRAIroWorkerBase

if TYPE_CHECKING:
    from ...database.db_manager import ImageDatabaseManager
    from ...services.annotation_review_service import AnnotationReviewService
    from ...services.annotation_review_store import AnnotationReviewStore
    from ...services.search_models import SearchConditions


@dataclass
class SearchResult:
    """検索結果"""

    image_metadata: list[dict[str, Any]]
    total_count: int
    search_time: float
    filter_conditions: "SearchConditions"


class SearchWorker(LoRAIroWorkerBase[SearchResult]):
    """データベース検索専用ワーカー"""

    _OPERATION_TYPE = "search"

    def __init__(
        self,
        db_manager: "ImageDatabaseManager",
        search_conditions: "SearchConditions",
        *,
        review_service: "AnnotationReviewService | None" = None,
        review_store: "AnnotationReviewStore | None" = None,
    ):
        super().__init__(db_manager=db_manager)
        self.db_manager = db_manager
        self.criteria_processor = SearchCriteriaProcessor(db_manager)
        self.search_conditions = search_conditions
        self._review_service = review_service
        self._review_store = review_store

    def execute(self) -> SearchResult:
        """検索処理を実行"""
        import time

        try:
            start_time = time.time()

            # 検索開始
            self._report_progress(20, "データベース検索を開始...")

            # 検索実行
            self._report_progress(60, "フィルター条件を適用中...")

            # キャンセルチェック
            self._check_cancellation()

            image_metadata, total_count = self.criteria_processor.execute_search_with_filters(
                self.search_conditions
            )
            self._check_cancellation()

            if self._review_service is not None and self._review_store is not None:
                image_metadata = apply_review_filter(
                    image_metadata,
                    self._review_service,
                    self._review_store,
                    warnings_only=self.search_conditions.annotation_review_warnings_only,
                    check_cancellation=self._check_cancellation,
                )
                if self.search_conditions.annotation_review_warnings_only:
                    total_count = len(image_metadata)
            elif self.search_conditions.annotation_review_warnings_only:
                raise ValueError("Clef の設定を確認してから要確認フィルターを使用してください")

            search_time = time.time() - start_time

            # 完了
            self._report_progress(100, f"検索完了: {total_count}件の画像が見つかりました")

            result = SearchResult(
                image_metadata=image_metadata,
                total_count=total_count,
                search_time=search_time,
                filter_conditions=self.search_conditions,
            )

            logger.info(f"検索完了: {total_count}件, 処理時間={search_time:.3f}秒")

            return result

        except CancellationError:
            logger.debug("検索処理がキャンセルされました")
            raise

        except Exception as e:
            logger.opt(exception=True).error(f"検索処理エラー: {e}")

            # エラーレコード保存（二次エラー対策付き）
            try:
                self.db_manager.save_error_record(
                    operation_type="search",
                    error_type=type(e).__name__,
                    error_message=str(e),
                    image_id=None,  # 検索処理のため画像ID特定不可
                    stack_trace=traceback.format_exc(),
                    file_path=None,
                    model_name=None,
                )
            except Exception as save_error:
                logger.error(f"エラーレコード保存失敗（二次エラー）: {save_error}")

            self._error_already_recorded = True
            raise
