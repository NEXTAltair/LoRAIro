"""Tag suggestion service for search autocomplete."""

from collections.abc import Sequence

from genai_tag_db_tools import search_tags
from genai_tag_db_tools.db.repository import MergedTagReader
from genai_tag_db_tools.models import TagSearchRequest

from ..utils.log import logger


class TagSuggestionService:
    """Provide cached tag suggestions via genai-tag-db-tools search API."""

    def __init__(self, merged_reader: MergedTagReader | None, max_cache_size: int = 512) -> None:
        self.merged_reader = merged_reader
        self.max_cache_size = max_cache_size
        self._cache: dict[str, list[str]] = {}

    def get_suggestions(self, query: str, limit: int = 20) -> list[str]:
        """Fetch tag suggestions with in-memory cache.

        Args:
            query: Current token text.
            limit: Max number of candidates.

        Returns:
            List of suggested tags.
        """
        normalized_query = query.strip()
        if len(normalized_query) < 2:
            return []

        cache_key = normalized_query.lower()
        if cache_key in self._cache:
            return self._cache[cache_key]

        if self.merged_reader is None:
            logger.debug("TagSuggestionService skipped: merged_reader unavailable")
            return []

        try:
            request = TagSearchRequest(
                query=normalized_query,
                partial=True,
                resolve_preferred=False,
                include_aliases=True,
                include_deprecated=False,
                limit=limit,
            )
            result = search_tags(self.merged_reader, request)
            suggestions = self._extract_tag_names(result.items)
            self._put_cache(cache_key, suggestions)
            return suggestions
        except Exception as e:
            logger.warning("Failed to fetch tag suggestions for '{}': {}", normalized_query, e)
            return []

    def clear_cache(self) -> None:
        self._cache.clear()

    def _put_cache(self, key: str, value: list[str]) -> None:
        if len(self._cache) >= self.max_cache_size:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = value

    @staticmethod
    def _extract_tag_names(items: Sequence[object]) -> list[str]:
        names: list[str] = []
        for item in items:
            name = getattr(item, "tag", None) or getattr(item, "name", None)
            if isinstance(name, str) and name and name not in names:
                names.append(name)
        return names

