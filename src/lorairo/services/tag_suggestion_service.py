from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Any

from ..utils.log import logger


@dataclass
class _CacheEntry:
    suggestions: list[str]
    expires_at: float


class TagSuggestionService:
    """タグ補完候補を取得するサービス。

    - genai-tag-db-tools の search_tags() を利用
    - クエリ単位でTTLキャッシュ
    """

    def __init__(
        self, merged_reader: Any, *, cache_ttl_seconds: float = 300.0, max_results: int = 20
    ) -> None:
        self._merged_reader = merged_reader
        self._cache_ttl_seconds = cache_ttl_seconds
        self._max_results = max_results
        self._cache: dict[str, _CacheEntry] = {}

    def suggest_tags(self, query: str, *, min_length: int = 2) -> list[str]:
        normalized_query = query.strip().lower()
        if len(normalized_query) < min_length:
            return []

        now = monotonic()
        cached = self._cache.get(normalized_query)
        if cached and cached.expires_at > now:
            return cached.suggestions

        suggestions = self._query_tags(normalized_query)
        self._cache[normalized_query] = _CacheEntry(
            suggestions=suggestions,
            expires_at=now + self._cache_ttl_seconds,
        )
        return suggestions

    def clear_cache(self) -> None:
        self._cache.clear()

    def _query_tags(self, query: str) -> list[str]:
        if self._merged_reader is None:
            return []

        try:
            from genai_tag_db_tools import search_tags
            from genai_tag_db_tools.models import TagSearchRequest

            request = TagSearchRequest(
                query=query,
                partial=True,
                resolve_preferred=False,
                include_aliases=True,
                include_deprecated=False,
            )
            result = search_tags(self._merged_reader, request)

            candidates: list[str] = []
            for item in getattr(result, "items", []):
                tag_name = self._extract_tag_name(item)
                if tag_name:
                    candidates.append(tag_name)

            unique_candidates = list(dict.fromkeys(candidates))
            return unique_candidates[: self._max_results]
        except Exception as e:
            logger.warning("Failed to fetch tag suggestions for '{}': {}", query, e)
            return []

    @staticmethod
    def _extract_tag_name(item: Any) -> str | None:
        if item is None:
            return None

        for key in ("tag", "source_tag", "name"):
            value = getattr(item, key, None)
            if isinstance(value, str) and value.strip():
                return value.strip()

        if isinstance(item, dict):
            for key in ("tag", "source_tag", "name"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        return None
