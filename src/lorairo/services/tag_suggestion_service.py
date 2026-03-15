"""Tag suggestion service for search auto-complete."""

from __future__ import annotations

from time import monotonic

from genai_tag_db_tools import search_tags
from genai_tag_db_tools.db.repository import MergedTagReader, get_default_reader
from genai_tag_db_tools.models import TagSearchRequest

from ..utils.log import logger


class TagSuggestionService:
    """タグ候補のサジェストを提供するサービス。"""

    def __init__(
        self,
        reader: MergedTagReader | None = None,
        *,
        min_query_length: int = 2,
        max_results: int = 20,
        cache_ttl_seconds: int = 300,
    ) -> None:
        self.reader = reader if reader is not None else get_default_reader()
        self.min_query_length = min_query_length
        self.max_results = max_results
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[str, tuple[float, list[str]]] = {}

    def get_suggestions(self, query: str) -> list[str]:
        """queryに対するタグ候補を返す。"""
        normalized_query = query.strip()
        if len(normalized_query) < self.min_query_length:
            return []

        cache_key = normalized_query.casefold()
        now = monotonic()
        cached = self._cache.get(cache_key)
        if cached and (now - cached[0]) < self.cache_ttl_seconds:
            return cached[1]

        request = TagSearchRequest(
            query=normalized_query,
            partial=True,
            resolve_preferred=True,
            include_aliases=False,
            include_deprecated=False,
        )

        try:
            result = search_tags(self.reader, request)
            suggestions = [item.tag for item in result.items[: self.max_results]]
        except Exception as e:
            logger.warning("Failed to fetch tag suggestions for '{}': {}", normalized_query, e)
            return []

        self._cache[cache_key] = (now, suggestions)
        return suggestions

