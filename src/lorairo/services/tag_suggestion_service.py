# src/lorairo/services/tag_suggestion_service.py
# タグ入力オートコンプリート用サジェストサービス。
# genai-tag-db-tools の search_tags() API を使用してタグ候補を取得する。
# MergedTagReader を依存注入で受け取り、TTL + LRU キャッシュで候補を保持する。

from __future__ import annotations

from collections import OrderedDict
from inspect import Parameter, signature
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
        # OrderedDict で LRU + TTL キャッシュを実装: key -> (timestamp, list[str])
        self._cache: OrderedDict[str, tuple[float, list[str]]] = OrderedDict()
        self._cache_lock = RLock()

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

        suggestions = self._search_tags(normalized)
        self._set_cache(cache_key, suggestions)
        return suggestions

    def clear_cache(self) -> None:
        """キャッシュをクリアする。"""
        with self._cache_lock:
            self._cache.clear()

    def _search_tags(self, query: str) -> list[str]:
        """genai-tag-db-tools で タグ検索を実行する。"""
        try:
            from genai_tag_db_tools import search_tags
            from genai_tag_db_tools.models import TagSearchRequest

            request = self._build_search_request(TagSearchRequest, query)
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
                if len(candidates) >= self.max_results:
                    break

            return self._sort_candidates(candidates, query)

        except Exception as e:
            logger.warning("タグ候補取得に失敗: query='{}', error={}", query, e)
            return []

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

    def _build_search_request(self, request_cls: Any, query: str) -> Any:
        """TagSearchRequest を互換性を保ちながら組み立てる。"""
        kwargs: dict[str, Any] = {
            "query": query,
            "partial": True,
            "resolve_preferred": False,
            "include_aliases": True,
            "include_deprecated": False,
        }
        if self._supports_request_field(request_cls, "limit"):
            kwargs["limit"] = self.max_results
        return request_cls(**kwargs)

    @staticmethod
    def _supports_request_field(request_cls: Any, field_name: str) -> bool:
        """TagSearchRequest が指定フィールドを受け付けるかを判定する。"""
        model_fields = getattr(request_cls, "model_fields", None)
        if isinstance(model_fields, dict):
            return field_name in model_fields

        try:
            sig = signature(request_cls)
        except (TypeError, ValueError):
            return False

        if field_name in sig.parameters:
            return True

        return any(param.kind == Parameter.VAR_KEYWORD for param in sig.parameters.values())

    @staticmethod
    def _sort_candidates(candidates: list[str], query: str) -> list[str]:
        """前方一致を優先しつつ候補を安定ソートする。"""
        lowered_query = query.casefold()

        def sort_key(tag: str) -> tuple[int, int, str]:
            lowered_tag = tag.casefold()
            if lowered_tag == lowered_query:
                return (0, 0, lowered_tag)
            if lowered_tag.startswith(lowered_query):
                return (0, 1, lowered_tag)
            contains_index = lowered_tag.find(lowered_query)
            if contains_index >= 0:
                return (1, contains_index, lowered_tag)
            return (2, 9999, lowered_tag)

        return sorted(candidates, key=sort_key)
