from __future__ import annotations

from collections import OrderedDict
from time import monotonic
from typing import Any

from ..utils.log import logger


class TagSuggestionService:
    """タグ入力オートコンプリート用サジェストサービス。"""

    def __init__(
        self,
        *,
        min_chars: int = 2,
        debounce_ms: int = 300,
        max_suggestions: int = 20,
        cache_size: int = 256,
        cache_ttl_seconds: float = 300.0,
    ) -> None:
        self.min_chars = min_chars
        self.debounce_ms = debounce_ms
        self.max_suggestions = max_suggestions
        self.cache_size = cache_size
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: OrderedDict[str, tuple[float, list[str]]] = OrderedDict()

    def get_suggestions(self, raw_query: str) -> list[str]:
        """入力文字列からタグ候補一覧を取得する。"""
        query = raw_query.strip()
        if len(query) < self.min_chars:
            return []

        cache_key = query.casefold()
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        suggestions = self._search_tags(query)
        self._set_cache(cache_key, suggestions)
        return suggestions

    def _search_tags(self, query: str) -> list[str]:
        try:
            from genai_tag_db_tools import search_tags

            try:
                records = search_tags(query=query, limit=self.max_suggestions)
            except TypeError:
                records = search_tags(query)
        except Exception as e:
            logger.warning("タグ候補取得に失敗: query='{}', error={}", query, e)
            return []

        return self._normalize_results(records)

    def _normalize_results(self, records: Any) -> list[str]:
        suggestions: list[str] = []
        seen: set[str] = set()

        if not isinstance(records, list):
            return []

        for record in records:
            tag_name = self._extract_tag_name(record)
            if not tag_name:
                continue

            normalized = tag_name.strip()
            key = normalized.casefold()
            if key in seen:
                continue

            seen.add(key)
            suggestions.append(normalized)

            if len(suggestions) >= self.max_suggestions:
                break

        return suggestions

    @staticmethod
    def _extract_tag_name(record: Any) -> str | None:
        if isinstance(record, str):
            return record

        if isinstance(record, dict):
            for key in ("tag", "name", "tag_name"):
                value = record.get(key)
                if isinstance(value, str):
                    return value
            return None

        for attr in ("tag", "name", "tag_name"):
            value = getattr(record, attr, None)
            if isinstance(value, str):
                return value

        return None

    def _get_cache(self, key: str) -> list[str] | None:
        if key not in self._cache:
            return None

        created_at, data = self._cache[key]
        now = monotonic()
        if now - created_at > self.cache_ttl_seconds:
            del self._cache[key]
            return None

        self._cache.move_to_end(key)
        return data

    def _set_cache(self, key: str, suggestions: list[str]) -> None:
        self._cache[key] = (monotonic(), suggestions)
        self._cache.move_to_end(key)

        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)
