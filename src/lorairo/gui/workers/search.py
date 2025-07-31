# src/lorairo/gui/workers/search.py

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ...utils.log import logger
from .base import LoRAIroWorkerBase

if TYPE_CHECKING:
    from ...database.db_manager import ImageDatabaseManager


@dataclass
class SearchResult:
    """検索結果"""

    image_metadata: list[dict[str, Any]]
    total_count: int
    search_time: float
    filter_conditions: dict[str, Any]


class SearchWorker(LoRAIroWorkerBase[SearchResult]):
    """
    データベース検索専用ワーカー（簡素化版）

    従来の複雑な実装から PySide6 標準機能ベースに移行。
    """

    def __init__(self, db_manager: "ImageDatabaseManager", filter_conditions: dict[str, Any]) -> None:
        super().__init__()
        self.db_manager = db_manager
        self.filter_conditions = filter_conditions
        logger.debug(f"SearchWorker初期化: {filter_conditions}")

    def execute(self) -> SearchResult:
        """検索処理を実行"""
        start_time = time.time()

        # 検索開始
        self._report_progress(10, "データベース検索を開始...")

        # フィルター条件の解析
        tags = self.filter_conditions.get("tags", [])
        caption = self.filter_conditions.get("caption", "")
        resolution = self.filter_conditions.get("resolution", 0)
        use_and = self.filter_conditions.get("use_and", True)
        date_range = self.filter_conditions.get("date_range", (None, None))
        include_untagged = self.filter_conditions.get("include_untagged", False)

        # 進捗報告
        self._report_progress(30, "フィルター条件を解析中...")

        # キャンセルチェック
        if self.cancellation.is_canceled():
            logger.info("検索がキャンセルされました")
            return SearchResult([], 0, 0.0, self.filter_conditions)

        # 検索実行
        self._report_progress(60, "データベース検索を実行中...")

        try:
            image_metadata, total_count = self.db_manager.get_images_by_filter(
                tags=tags,
                caption=caption,
                resolution=resolution,
                use_and=use_and,
                start_date=date_range[0],
                end_date=date_range[1],
                include_untagged=include_untagged,
            )

            search_time = time.time() - start_time

            # 完了
            self._report_progress(
                100,
                f"検索完了: {total_count}件の画像が見つかりました",
                processed_count=total_count,
                total_count=total_count,
            )

            result = SearchResult(
                image_metadata=image_metadata,
                total_count=total_count,
                search_time=search_time,
                filter_conditions=self.filter_conditions,
            )

            logger.info(f"検索完了: {total_count}件, 処理時間={search_time:.3f}秒")
            return result

        except Exception as e:
            logger.error(f"検索処理エラー: {e}", exc_info=True)
            raise
