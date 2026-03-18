# src/lorairo/services/tag_suggestion_service.py
# タグ入力オートコンプリート用サジェストサービス。
# genai-tag-db-tools の search_tags() API を使用してタグ候補を取得する。
# MergedTagReader を依存注入で受け取り、TTL + LRU キャッシュで候補を保持する。

from __future__ import annotations

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
        cached = self.get_cached_suggestions(normalized)
        if cached is not None:
            return cached

        cached_subset = self.get_cached_subset(normalized)
        if cached_subset is not None:
            self._set_cache(cache_key, cached_subset)
            return cached_subset

        suggestions = self._search_tags(normalized)
        self._set_cache(cache_key, suggestions)
        return suggestions

    def clear_cache(self) -> None:
        """キャッシュをクリアする。"""
        with self._cache_lock:
            self._cache.clear()

    def get_cached_suggestions(self, query: str) -> list[str] | None:
        """完全一致キーでキャッシュ済み候補を取得する。"""
        normalized = query.strip()
        if len(normalized) < self.min_chars:
            return None
        return self._get_cache(normalized.casefold())

    def get_cached_subset(self, query: str) -> list[str] | None:
        """既存キャッシュの部分集合から候補を再利用する。"""
        normalized = query.strip()
        if len(normalized) < self.min_chars:
            return None

        target = normalized.casefold()
        with self._cache_lock:
            now = monotonic()
            best_key: str | None = None
            best_data: list[str] | None = None

            for key, (created_at, data) in list(self._cache.items()):
                if now - created_at > self._cache_ttl:
                    del self._cache[key]
                    continue
                if not target.startswith(key):
                    continue
                if best_key is None or len(key) > len(best_key):
                    best_key = key
                    best_data = data

            if best_key is None or best_data is None:
                return None

            self._cache.move_to_end(best_key)

        return self._filter_and_rank(target, best_data)

    def _search_tags(self, query: str) -> list[str]:
        """genai-tag-db-tools で タグ検索を実行する。"""
        try:
            from genai_tag_db_tools import search_tags
            from genai_tag_db_tools.models import TagSearchRequest

            request_kwargs = {
                "query": query,
                "partial": True,
                "resolve_preferred": False,
                "include_aliases": True,
                "include_deprecated": False,
                "limit": self.max_results,
            }
            try:
                request = TagSearchRequest(**request_kwargs)
            except TypeError:
                # 古い API では limit を受け付けないためフォールバックする
                request_kwargs.pop("limit", None)
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
                if len(candidates) >= self.max_results:
                    break

            return self._filter_and_rank(query.casefold(), candidates)

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

    def _filter_and_rank(self, query_key: str, candidates: list[str]) -> list[str]:
        """候補をクエリ関連度でソートし、max_results に制限する。"""
        if not query_key:
            return candidates[: self.max_results]

        def _rank(tag: str) -> tuple[int, str]:
            key = tag.casefold()
            if key == query_key:
                return (0, key)
            if key.startswith(query_key):
                return (1, key)
            if query_key in key:
                return (2, key)
            return (3, key)

        filtered = [tag for tag in candidates if query_key in tag.casefold()]
        filtered.sort(key=_rank)
        return filtered[: self.max_results]
