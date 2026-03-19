# src/lorairo/services/tag_suggestion_service.py
# タグ入力オートコンプリート用サジェストサービス。
# genai-tag-db-tools の search_tags() API を使用してタグ候補を取得する。
# MergedTagReader を依存注入で受け取り、TTL + LRU キャッシュで候補を保持する。

from __future__ import annotations

import inspect
from collections import OrderedDict
from threading import RLock
from time import monotonic
from typing import TYPE_CHECKING, Any

from ..utils.log import logger

if TYPE_CHECKING:
    from genai_tag_db_tools.db.reader import MergedTagReader


class TagSuggestionService:
    """タグ入力オートコンプリート用サジェストサービス。

    genai-tag-db-tools の search_tags() を使用してタグ候補を取得する。
    TTL + LRU キャッシュにより繰り返しクエリを効率化する。
    merged_reader が None の場合は空リストを返してグレースフルデグラデーション。
    """

    def __init__(
        self,
        merged_reader: MergedTagReader | None,
        *,
        min_chars: int = 2,
        max_results: int = 20,
        cache_size: int = 256,
        cache_ttl_seconds: float = 300.0,
    ) -> None:
        """TagSuggestionService を初期化する。

        Args:
            merged_reader: genai-tag-db-tools の MergedTagReader インスタンス。
                None の場合は候補取得をスキップしてグレースフルデグラデーション。
            min_chars: 候補取得を開始する最小文字数。
            max_results: 取得する候補の最大件数。
            cache_size: LRU キャッシュの最大エントリ数。
            cache_ttl_seconds: キャッシュの有効期限（秒）。
        """
        self._merged_reader = merged_reader
        self.min_chars = min_chars
        self.max_results = max_results
        self._cache_size = cache_size
        self._cache_ttl = cache_ttl_seconds
        self._cache_lock = RLock()
        # OrderedDict で LRU + TTL キャッシュを実装: key -> (timestamp, list[str])
        self._cache: OrderedDict[str, tuple[float, list[str]]] = OrderedDict()

    def get_suggestions(self, query: str) -> list[str]:
        """入力文字列からタグ候補一覧を取得する。

        Args:
            query: 検索クエリ（最後のトークンを渡すこと）。

        Returns:
            タグ名のリスト。min_chars 未満の場合や DB 未接続の場合は空リスト。
        """
        if self._merged_reader is None:
            return []

        normalized = query.strip()
        if len(normalized) < self.min_chars:
            return []

        cache_key = normalized.casefold()
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        subset = self._get_cached_subset(normalized)
        if subset is not None:
            self._set_cache(cache_key, subset)
            return subset

        suggestions = self._rank_candidates(normalized, self._search_tags(normalized))
        self._set_cache(cache_key, suggestions)
        return suggestions

    def clear_cache(self) -> None:
        """キャッシュをクリアする。"""
        with self._cache_lock:
            self._cache.clear()

    def get_cached_suggestions(self, query: str) -> list[str] | None:
        """キャッシュのみを利用して候補を返す（UIスレッド高速表示用）。"""
        if self._merged_reader is None:
            return []

        normalized = query.strip()
        if len(normalized) < self.min_chars:
            return []

        cache_key = normalized.casefold()
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        subset = self._get_cached_subset(normalized)
        if subset is not None:
            self._set_cache(cache_key, subset)
            return subset

        return None

    def _search_tags(self, query: str) -> list[str]:
        """genai-tag-db-tools で タグ検索を実行する。"""
        try:
            from genai_tag_db_tools import search_tags
            from genai_tag_db_tools.models import TagSearchRequest

            request_kwargs: dict[str, Any] = {
                "query": query,
                "partial": True,
                "resolve_preferred": False,
                "include_aliases": True,
                "include_deprecated": False,
            }
            if self._supports_limit_parameter(TagSearchRequest):
                request_kwargs["limit"] = self.max_results

            request = TagSearchRequest(**request_kwargs)
            result = search_tags(self._merged_reader, request)

            # TagSearchResult.items は list[TagRecordPublic]、各 item.tag がタグ文字列
            candidates: list[str] = []
            seen: set[str] = set()
            for item in result.items:
                tag_name = self._extract_tag_name(item)
                if not tag_name:
                    continue
                key = tag_name.casefold()
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(tag_name)
            return candidates

        except Exception as e:
            logger.warning("タグ候補取得に失敗: query='{}', error={}", query, e)
            return []

    @staticmethod
    def _supports_limit_parameter(tag_search_request_cls: type) -> bool:
        """TagSearchRequest が limit パラメータを受け付けるか判定する。"""
        model_fields = getattr(tag_search_request_cls, "model_fields", None)
        if isinstance(model_fields, dict):
            return "limit" in model_fields

        try:
            signature = inspect.signature(tag_search_request_cls)
        except (TypeError, ValueError):
            return False

        return "limit" in signature.parameters

    @staticmethod
    def _extract_tag_name(item: Any) -> str | None:
        """TagRecordPublic またはその他のオブジェクトからタグ名を抽出する。"""
        if isinstance(item, str):
            return item.strip() or None

        if isinstance(item, dict):
            for key in ("tag", "source_tag", "name"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            return None

        # TagRecordPublic オブジェクト (.tag フィールドが優先)
        for attr in ("tag", "source_tag", "name"):
            value = getattr(item, attr, None)
            if isinstance(value, str) and value.strip():
                return value.strip()

        return None

    def _get_cache(self, key: str) -> list[str] | None:
        """キャッシュからエントリを取得する（TTL チェック込み）。"""
        with self._cache_lock:
            if key not in self._cache:
                return None

            created_at, data = self._cache[key]
            if monotonic() - created_at > self._cache_ttl:
                del self._cache[key]
                return None

            # LRU: 最近アクセスしたエントリを末尾へ移動
            self._cache.move_to_end(key)
            return data

    def _set_cache(self, key: str, suggestions: list[str]) -> None:
        """キャッシュにエントリを追加する（LRU サイズ制限付き）。"""
        with self._cache_lock:
            self._cache[key] = (monotonic(), suggestions)
            self._cache.move_to_end(key)

            # LRU: サイズ超過時は最古のエントリを削除
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)

    def _get_cached_subset(self, query: str) -> list[str] | None:
        """既存キャッシュから query の部分集合候補を作成する。"""
        query_key = query.casefold()
        for length in range(len(query_key) - 1, self.min_chars - 1, -1):
            prefix_key = query_key[:length]
            if prefix_key == query_key:
                continue
            cached = self._get_cache(prefix_key)
            if cached is None:
                continue
            return self._rank_candidates(query, cached)
        return None

    def _rank_candidates(self, query: str, candidates: list[str]) -> list[str]:
        """候補を exact > prefix > contains の順で並べ替える。"""
        exact_matches: list[str] = []
        prefix_matches: list[str] = []
        contains_matches: list[str] = []
        query_key = query.casefold()
        seen: set[str] = set()

        for tag_name in candidates:
            key = tag_name.casefold()
            if key in seen or query_key not in key:
                continue
            seen.add(key)
            if key == query_key:
                exact_matches.append(tag_name)
            elif key.startswith(query_key):
                prefix_matches.append(tag_name)
            else:
                contains_matches.append(tag_name)

            if len(exact_matches) + len(prefix_matches) + len(contains_matches) >= self.max_results:
                break

        return (exact_matches + prefix_matches + contains_matches)[: self.max_results]
