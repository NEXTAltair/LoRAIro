"""タグ refinement リコメンドサービス (#931, Qt-free)。

genai-tag-db-tools の refinement 判定 (`recommend_manual_refinement`) を呼び、
ローカル ignore (tag + reason_code 単位) を除外した「表示すべきリコメンド」を返す。
同一 (tag, format_name) はプロセス内キャッシュで再評価を避ける。

判定ロジック・承認反映・base DB 提案は genai-tag-db-tools 側の責務。
本サービスは「表示すべきものを決める」ことに専念する。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Protocol

from genai_tag_db_tools.models import RefinementRecommendation

from ..utils.log import logger

# recommend_manual_refinement 互換のシグネチャ。
# 本番では TagManagementService.recommend_manual_refinement を注入する。
RecommendFn = Callable[..., RefinementRecommendation]


class RefinementIgnoreStore(Protocol):
    """ignore 永続化の最小インターフェイス (Repository / fake 双方を受ける)。"""

    def add_ignore(self, tag: str, reason_code: str) -> None: ...

    def is_ignored(self, tag: str, reason_code: str) -> bool: ...

    def list_ignored(self) -> set[tuple[str, str]]: ...


class RefinementService:
    """refinement リコメンドの取得と ignore 管理を担う Qt-free サービス。"""

    def __init__(self, recommend_fn: RecommendFn, ignore_repo: RefinementIgnoreStore) -> None:
        """RefinementService を初期化する。

        Args:
            recommend_fn: タグ1個を評価する callable。
                `recommend_manual_refinement(tag, *, repo=None, format_name="unknown")` 互換。
            ignore_repo: ignore 設定の永続化ストア。
        """
        self._recommend_fn = recommend_fn
        self._ignore_repo = ignore_repo
        self._cache: dict[tuple[str, str], RefinementRecommendation] = {}

    def recommend_for_tags(
        self,
        tags: Iterable[str],
        format_map: Mapping[str, str] | None = None,
        repo: object | None = None,
    ) -> dict[str, RefinementRecommendation]:
        """タグ集合を評価し、表示すべきリコメンドを tag ごとに返す。

        ignore された (tag, reason_code) は reasons から除外し、残り reason が無ければ
        そのタグは結果から落とす。同一 (tag, format_name) はキャッシュする。

        Args:
            tags: 評価対象のタグ文字列。
            format_map: タグ→format_name のマップ。未指定タグは "unknown"。
            repo: lib に渡す DB リーダー (エイリアス/タイポ候補の参照に使う)。

        Returns:
            needs_refinement=True のタグだけを含む {tag: RefinementRecommendation}。
        """
        ignored = self._ignore_repo.list_ignored()
        fmap = format_map or {}
        result: dict[str, RefinementRecommendation] = {}
        total = 0
        evaluated = 0
        for tag in tags:
            total += 1
            format_name = fmap.get(tag, "unknown")
            key = (tag, format_name)
            rec = self._cache.get(key)
            if rec is None:
                rec = self._recommend_fn(tag, repo=repo, format_name=format_name)
                self._cache[key] = rec
                evaluated += 1
            filtered = self._apply_ignores(rec, ignored)
            if filtered.needs_refinement:
                result[tag] = filtered
        logger.debug(f"refinement 評価: 対象={total}, 新規評価={evaluated}, 表示={len(result)}")
        return result

    def _apply_ignores(
        self, rec: RefinementRecommendation, ignored: set[tuple[str, str]]
    ) -> RefinementRecommendation:
        """ignore された reason を除外したリコメンドを返す。

        除外で reason が空になったら needs_refinement を False にする。
        除外が無ければ元オブジェクトをそのまま返す。
        """
        kept = [r for r in rec.reasons if (rec.source_tag, r.code) not in ignored]
        if len(kept) == len(rec.reasons):
            return rec
        needs = rec.needs_refinement and len(kept) > 0
        return rec.model_copy(update={"reasons": kept, "needs_refinement": needs})

    def ignore(self, tag: str, reason_code: str) -> None:
        """タグの特定 reason のリコメンドを以後抑制する (永続化)。"""
        self._ignore_repo.add_ignore(tag, reason_code)
        # 当該タグのキャッシュを無効化 (format 問わず)
        self._cache = {k: v for k, v in self._cache.items() if k[0] != tag}
        logger.debug(f"refinement ignore 追加: tag='{tag}', reason_code='{reason_code}'")

    def is_ignored(self, tag: str, reason_code: str) -> bool:
        """(tag, reason_code) が ignore 済みか返す。"""
        return self._ignore_repo.is_ignored(tag, reason_code)

    def list_ignored(self) -> set[tuple[str, str]]:
        """ignore 済みの (tag, reason_code) 集合を返す。"""
        return self._ignore_repo.list_ignored()
