"""データベース検索専用ワーカー"""

import traceback
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ...utils.log import logger
from .base import LoRAIroWorkerBase

if TYPE_CHECKING:
    from ...database.db_manager import ImageDatabaseManager
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

    def __init__(self, db_manager: "ImageDatabaseManager", search_conditions: "SearchConditions"):
        super().__init__()
        self.db_manager = db_manager
        self.search_conditions = search_conditions

    def execute(self) -> SearchResult:
        """検索処理を実行"""
        import time

        try:
            start_time = time.time()

            # 検索開始
            self._report_progress(20, "データベース検索を開始...")

            # SearchConditionsから条件を抽出
            if self.search_conditions.search_type == "tags":
                tags = self.search_conditions.keywords
                caption = None
            elif self.search_conditions.search_type == "caption":
                tags = None
                caption = self.search_conditions.keywords[0] if self.search_conditions.keywords else ""
            else:
                tags = None
                caption = None

            # 解像度フィルター
            resolution = self.search_conditions._resolve_resolution()

            # タグロジック
            use_and = self.search_conditions.tag_logic == "and"

            # 日付範囲
            date_range_start = self.search_conditions.date_range_start
            date_range_end = self.search_conditions.date_range_end

            # その他のオプション
            include_untagged = self.search_conditions.only_untagged

            # 検索実行
            self._report_progress(60, "フィルター条件を適用中...")

            # キャンセルチェック
            self._check_cancellation()

            image_metadata, total_count = self.db_manager.get_images_by_filter(
                tags=tags,
                caption=caption,
                resolution=resolution,
                use_and=use_and,
                start_date=date_range_start.isoformat() if date_range_start else None,
                end_date=date_range_end.isoformat() if date_range_end else None,
                include_untagged=include_untagged,
            )

            # バッチ進捗報告（検索結果処理）
            if total_count > 0:
                # 検索結果を一件ずつ処理するバッチ進捗として報告
                batch_size = min(100, total_count)  # 100件ずつバッチ処理をシミュレート
                for i in range(0, total_count, batch_size):
                    self._check_cancellation()  # キャンセルチェック

                    current_batch = min(i + batch_size, total_count)
                    # ファイル名の代わりに件数情報を使用
                    self._report_batch_progress(
                        current_batch, total_count, f"search_batch_{i // batch_size + 1}"
                    )

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

        except Exception as e:
            logger.error(f"検索処理エラー: {e}", exc_info=True)

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

            raise
