# src/lorairo/gui/workers/search_facets_worker.py
"""検索ファセット (最近使ったモデル / 作成日ヒストグラム) を背景で取得する worker (#1438)。

従来は ``FilterSearchPanel.set_search_filter_service`` が GUI スレッドで DB を同期クエリし、
キャッシュが冷えていると最長 35 秒ほど起動がブロックされていた。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from .base import LoRAIroWorkerBase


class _FacetsSource(Protocol):
    """ファセット取得元 (SearchFilterService 互換)。"""

    def get_recently_used_model_ids(self, limit: int = 10) -> list[str]: ...

    def get_created_at_histogram(self, bins: int = 20) -> list[tuple[datetime, datetime, int]]: ...


@dataclass
class SearchFacetsResult:
    """ファセット取得結果。取得元が対応していない項目は None。"""

    model_ids: list[str] | None = None
    histogram_bins: list[tuple[datetime, datetime, int]] | None = field(default=None)


class SearchFacetsWorker(LoRAIroWorkerBase[SearchFacetsResult]):
    """モデル候補と作成日ヒストグラムを取得する。"""

    _OPERATION_TYPE = "search_facets"

    def __init__(self, source: _FacetsSource) -> None:
        """Worker を初期化する。

        Args:
            source: ``get_recently_used_model_ids`` / ``get_created_at_histogram`` を持つサービス。
        """
        super().__init__()
        self._source = source

    def execute(self) -> SearchFacetsResult:
        """ファセットを取得する (対応メソッドの無い取得元は該当項目を None のままにする)。"""
        result = SearchFacetsResult()
        if hasattr(self._source, "get_recently_used_model_ids"):
            result.model_ids = self._source.get_recently_used_model_ids()
            self._check_cancellation()
        if hasattr(self._source, "get_created_at_histogram"):
            result.histogram_bins = self._source.get_created_at_histogram()
        return result
