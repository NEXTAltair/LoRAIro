# src/lorairo/services/tag_suggestion_service.py
# タグ入力オートコンプリート用サジェストサービス。
# genai-tag-db-tools の search_tags() API を使用してタグ候補を取得する。
# MergedTagReader を依存注入で受け取り、TTL + LRU キャッシュで候補を保持する。
# スレッドセーフ: ワーカースレッドからの並行アクセスに対応 (RLock)。

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
    連続入力時はキャッシュ部分集合の再利用で DB 検索を削減する。
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

        # 完全一致キャッシュ → 部分集合キャッシュ → DB検索 の順で取得
        cached = self.get_cached_suggestions(normalized)
        if cached is not None:
            return cached

        suggestions = self._rank_candidates(normalized, self._search_tags(normalized))
        self._set_cache(cache_key, suggestions)
        return suggestions

    def get_cached_suggestions(self, query: str) -> list[str] | None:
        """キャッシュのみを利用して候補を返す（UIスレッド高速表示用）。

        完全一致キャッシュと部分集合キャッシュの両方を確認する。
        DB検索は行わない。

        Args:
            query: 検索クエリ。

        Returns:
            キャッシュヒット時は候補一覧、未ヒット時は None。
        """
        if self._merged_reader is None:
            return []

        normalized = query.strip()
        if len(normalized) < self.min_chars:
            return []

        cache_key = normalized.casefold()

        with self._cache_lock:
            exact = self._get_cache_unlocked(cache_key)
            if exact is not None:
                return exact

            subset = self._get_cached_subset_unlocked(cache_key)
            if subset is not None:
                self._set_cache_unlocked(cache_key, subset)
                return subset

        return None

    def clear_cache(self) -> None:
        """キャッシュをクリアする。"""
        with self._cache_lock:
            self._cache.clear()

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
            sig = inspect.signature(tag_search_request_cls)
        except (TypeError, ValueError):
            return False

        return "limit" in sig.parameters

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

    def _rank_candidates(self, query: str, candidates: list[str]) -> list[str]:
        """候補を exact > prefix > contains の順で並べ替え、max_results に制限する。"""
        query_key = query.casefold()
        exact: list[str] = []
        prefix: list[str] = []
        contains: list[str] = []
        seen: set[str] = set()

        for tag_name in candidates:
            key = tag_name.casefold()
            if key in seen or query_key not in key:
                continue
            seen.add(key)
            if key == query_key:
                exact.append(tag_name)
            elif key.startswith(query_key):
                prefix.append(tag_name)
            else:
                contains.append(tag_name)

        return (exact + prefix + contains)[: self.max_results]

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
        """既存キャッシュから最長一致prefixの部分集合候補を取得する。

        "bl" のキャッシュがあるとき "blu" で呼ばれると、
        "bl" のキャッシュ結果から "blu" を含むものをフィルタして返す。
        最長一致を優先するため最も精度の高い部分集合が得られる。
        """
        for length in range(len(key) - 1, self.min_chars - 1, -1):
            prefix_key = key[:length]
            cached = self._get_cache_unlocked(prefix_key)
            if cached is None:
                continue
            return self._rank_candidates(key, cached)

        return None
