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

        cached = self.get_cached_suggestions(normalized)
        if cached is not None:
            return cached

        suggestions = self._search_tags(normalized)
        cache_key = normalized.casefold()
        self._set_cache(cache_key, suggestions)
        return suggestions

    def get_cached_suggestions(self, query: str) -> list[str] | None:
        """キャッシュから候補を取得する（DB検索は行わない）。

        完全一致キャッシュがない場合は、より短いクエリのキャッシュ部分集合を再利用する。

        Args:
            query: 検索クエリ。

        Returns:
            キャッシュヒット時は候補一覧、未ヒット時は None。
        """
        normalized = query.strip()
        if len(normalized) < self.min_chars:
            return []

        cache_key = normalized.casefold()

        with self._cache_lock:
            exact = self._get_cache_unlocked(cache_key)
            if exact is not None:
                return exact

            subset = self._get_cached_subset_unlocked(cache_key)
            if subset is None:
                return None

            self._set_cache_unlocked(cache_key, subset)
            return subset

    def clear_cache(self) -> None:
        """キャッシュをクリアする。"""
        with self._cache_lock:
            self._cache.clear()

    def _search_tags(self, query: str) -> list[str]:
        """genai-tag-db-tools で タグ検索を実行する。"""
        try:
            from genai_tag_db_tools import search_tags
            from genai_tag_db_tools.models import TagSearchRequest

            request = TagSearchRequest(
                query=query,
                partial=True,
                resolve_preferred=False,
                include_aliases=True,
                include_deprecated=False,
                limit=self.max_results,
            )
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

            return self._rank_candidates(candidates, query)

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

    @staticmethod
    def _rank_candidates(candidates: list[str], query: str) -> list[str]:
        """候補を優先度順に並び替える（exact > prefix > contains）。"""
        needle = query.casefold()

        def _score(tag: str) -> tuple[int, str]:
            folded = tag.casefold()
            if folded == needle:
                return (0, folded)
            if folded.startswith(needle):
                return (1, folded)
            return (2, folded)

        return sorted(candidates, key=_score)

    def _get_cache(self, key: str) -> list[str] | None:
        """キャッシュからエントリを取得する（TTL チェック込み）。"""
        with self._cache_lock:
            return self._get_cache_unlocked(key)

    def _get_cache_unlocked(self, key: str) -> list[str] | None:
        """ロック取得済み前提のキャッシュ読み出し。"""
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
            self._set_cache_unlocked(key, suggestions)

    def _set_cache_unlocked(self, key: str, suggestions: list[str]) -> None:
        """ロック取得済み前提のキャッシュ更新。"""
        self._cache[key] = (monotonic(), suggestions)
        self._cache.move_to_end(key)

        # LRU: サイズ超過時は最古のエントリを削除
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    def _get_cached_subset_unlocked(self, key: str) -> list[str] | None:
        """ロック取得済み前提でキャッシュ部分集合を取得する。"""
        best_source: list[str] | None = None
        best_len = -1

        for candidate_key in list(self._cache.keys()):
            if not key.startswith(candidate_key) or len(candidate_key) >= len(key):
                continue

            cached_values = self._get_cache_unlocked(candidate_key)
            if cached_values is None:
                continue

            if len(candidate_key) > best_len:
                best_len = len(candidate_key)
                best_source = cached_values

        if best_source is None:
            return None

        filtered = [tag for tag in best_source if key in tag.casefold()]
        if not filtered:
            return []

        ranked = self._rank_candidates(filtered, key)
        return ranked[: self.max_results]
