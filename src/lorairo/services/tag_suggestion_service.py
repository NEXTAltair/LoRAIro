# src/lorairo/services/tag_suggestion_service.py
# タグ入力オートコンプリート用サジェストサービス。
# genai-tag-db-tools の search_tags() API を使用してタグ候補を取得する。
# MergedTagReader を依存注入で受け取り、TTL + LRU キャッシュで候補を保持する。

from __future__ import annotations

import inspect
from collections import OrderedDict
from collections.abc import Mapping
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
        db_fetch_limit_factor: int = 4,
    ) -> None:
        """TagSuggestionService を初期化する。

        Args:
            merged_reader: genai-tag-db-tools の MergedTagReader インスタンス。
                None の場合は候補取得をスキップしてグレースフルデグラデーション。
            min_chars: 候補取得を開始する最小文字数。
            max_results: 取得する候補の最大件数。
            cache_size: LRU キャッシュの最大エントリ数。
            cache_ttl_seconds: キャッシュの有効期限（秒）。
            db_fetch_limit_factor: DB側 limit 指定時に max_results へ乗算する係数。
                重複・別名展開を見越して余剰件数を取得し、最終的に max_results へ整形する。
        """
        self._merged_reader = merged_reader
        self.min_chars = min_chars
        self.max_results = max_results
        self._db_fetch_limit = max_results * max(db_fetch_limit_factor, 1)
        self._cache_size = cache_size
        self._cache_ttl = cache_ttl_seconds
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

        suggestions = self._search_tags(normalized)
        self._set_cache(cache_key, suggestions)
        return suggestions

    def clear_cache(self) -> None:
        """キャッシュをクリアする。"""
        self._cache.clear()

    def _search_tags(self, query: str) -> list[str]:
        """genai-tag-db-tools で タグ検索を実行する。"""
        try:
            from genai_tag_db_tools import search_tags
            from genai_tag_db_tools.models import TagSearchRequest

            candidates: list[str] = []
            seen: set[str] = set()

            # 前方一致優先: "keyword*" で先に取得し、不足時のみ従来の部分一致へフォールバック
            prefix_query = query if query.endswith("*") else f"{query}*"
            for current_query in (prefix_query, query):
                request_kwargs = self._build_search_request_kwargs(TagSearchRequest, current_query)
                result = search_tags(self._merged_reader, TagSearchRequest(**request_kwargs))
                self._collect_candidates(result, seen, candidates)
                if len(candidates) >= self.max_results:
                    break

            return candidates

        except Exception as e:
            logger.warning("タグ候補取得に失敗: query='{}', error={}", query, e)
            return []

    def _build_search_request_kwargs(self, request_cls: type[Any], query: str) -> dict[str, Any]:
        """TagSearchRequest の互換性を保ちながら kwargs を構築する。"""
        kwargs = {
            "query": query,
            "partial": True,
            "resolve_preferred": False,
            "include_aliases": True,
            "include_deprecated": False,
        }
        accepted = self._accepted_request_fields(request_cls)
        if accepted is None or "limit" in accepted:
            kwargs["limit"] = self._db_fetch_limit
        return kwargs

    @staticmethod
    def _accepted_request_fields(request_cls: type[Any]) -> set[str] | None:
        """TagSearchRequest が受け取るフィールド名一覧を返す。

        Returns:
            set[str] | None:
                - フィールド一覧が分かる場合は set
                - 可変 kwargs のみで判定できない場合は None
        """
        model_fields = getattr(request_cls, "model_fields", None)
        if isinstance(model_fields, Mapping):
            return set(model_fields.keys())

        try:
            signature = inspect.signature(request_cls)
        except (TypeError, ValueError):
            return None

        accepted: set[str] = set()
        for name, param in signature.parameters.items():
            if param.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY):
                accepted.add(name)
            elif param.kind is inspect.Parameter.VAR_KEYWORD:
                return None
        return accepted

    def _collect_candidates(self, result: Any, seen: set[str], candidates: list[str]) -> None:
        """TagSearchResult から候補を重複排除しつつ収集する。"""
        for item in getattr(result, "items", []):
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
        self._cache[key] = (monotonic(), suggestions)
        self._cache.move_to_end(key)

        # LRU: サイズ超過時は最古のエントリを削除
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
