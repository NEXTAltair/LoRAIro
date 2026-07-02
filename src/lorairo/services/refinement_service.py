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

# tag1個を評価する callable のシグネチャ `(tag, *, repo, format_name)`。
# 本番では TagManagementService.recommend_with_translation_quality を注入する
# (manual refinement + 翻訳品質を統合した RefinementRecommendation を返す、#976)。
# ignore / フィルタは reason_code 単位で汎用的に効くため、reason の出自 (手動/翻訳) は問わない。
RecommendFn = Callable[..., RefinementRecommendation]

# タグ集合の翻訳を per-tag 評価の前に一括取得する callable のシグネチャ `(tags, *, repo)`。
# 本番では TagManagementService.prefetch_translations を注入し、per-tag の search_tags を
# N 回呼ぶ N+1 を解消する (#998)。未注入 (None) なら prefetch を行わず従来の per-tag fallback。
PrefetchFn = Callable[..., None]

# 候補タグ集合のサイト別使用カウントを一括解決する callable のシグネチャ `(tags, *, repo)`。
# 本番では TagManagementService.resolve_usage_counts_for_tags を注入する (#1052)。
CandidateCountsFn = Callable[..., dict[str, dict[str, int]]]


class RefinementIgnoreStore(Protocol):
    """ignore 永続化の最小インターフェイス (Repository / fake 双方を受ける)。"""

    def add_ignore(self, tag: str, reason_code: str) -> None: ...

    def is_ignored(self, tag: str, reason_code: str) -> bool: ...

    def list_ignored(self) -> set[tuple[str, str]]: ...


class RefinementService:
    """refinement リコメンドの取得と ignore 管理を担う Qt-free サービス。"""

    def __init__(
        self,
        recommend_fn: RecommendFn,
        ignore_repo: RefinementIgnoreStore,
        prefetch_fn: PrefetchFn | None = None,
        candidate_counts_fn: CandidateCountsFn | None = None,
    ) -> None:
        """RefinementService を初期化する。

        Args:
            recommend_fn: タグ1個を評価する callable。
                `(tag, *, repo=None, format_name="unknown") -> RefinementRecommendation` 互換。
                本番注入は manual refinement + 翻訳品質を統合した結果を返す (#976)。
            ignore_repo: ignore 設定の永続化ストア。
            prefetch_fn: タグ集合の翻訳を一括取得する callable `(tags, *, repo)` (#998)。
                None なら prefetch せず per-tag fallback のまま動く (後方互換)。
        """
        self._recommend_fn = recommend_fn
        self._ignore_repo = ignore_repo
        self._prefetch_fn = prefetch_fn
        self._candidate_counts_fn = candidate_counts_fn
        # キー = (tag, format_name, reader 識別子)。reader 違いで結果が変わるため含める。
        self._cache: dict[tuple[str, str, int], RefinementRecommendation] = {}

    def resolve_candidate_counts(
        self,
        recommendations: Mapping[str, RefinementRecommendation],
        *,
        repo: object | None = None,
    ) -> dict[str, dict[str, int]]:
        """リコメンド中の候補タグ全件のサイト別使用カウントを一括解決する (#1052)。

        候補名の羅列だけでは選べないため、ツールチップ/置換メニューに counts を
        併記する。評価時にまとめて解決し、表示のたびに DB を叩かない。

        Returns:
            ``{候補タグ: {format_name: usage_count}}``。fn 未注入なら空 dict。
        """
        if self._candidate_counts_fn is None:
            return {}
        candidates = [
            suggestion.tag
            for recommendation in recommendations.values()
            for suggestion in recommendation.suggestions
            if suggestion.tag
        ]
        if not candidates:
            return {}
        return self._candidate_counts_fn(candidates, repo=repo)

    def recommend_for_tags(
        self,
        tags: Iterable[str],
        format_map: Mapping[str, str] | None = None,
        repo: object | None = None,
        cancel_check: Callable[[], None] | None = None,
    ) -> dict[str, RefinementRecommendation]:
        """タグ集合を評価し、表示すべきリコメンドを tag ごとに返す。

        ignore された (tag, reason_code) は reasons から除外し、残り reason が無ければ
        そのタグは結果から落とす。同一 (tag, format_name) はキャッシュする。

        Args:
            tags: 評価対象のタグ文字列。
            format_map: タグ→format_name のマップ。未指定タグは "unknown"。
            repo: lib に渡す DB リーダー (エイリアス/タイポ候補の参照に使う)。
            cancel_check: 中断要求を確認する callable (#1024)。中断すべきときに例外を
                送出する契約 (例外型は呼び出し元が決め、本サービスは素通しする)。
                DB 往復 (prefetch / per-tag 評価) の合間に呼び、DB 呼び出し中に殺せない
                ワーカーへ協調キャンセルを効かせるチェックポイント。None なら無効。

        Returns:
            needs_refinement=True のタグだけを含む {tag: RefinementRecommendation}。
        """
        # list_ignored() も DB 読み取りのため、最初の往復前にもチェックする (Codex P2)。
        if cancel_check is not None:
            cancel_check()
        ignored = self._ignore_repo.list_ignored()
        fmap = format_map or {}
        # reader (repo) が違うと DB 由来の alias/typo 候補が変わるためキー要素に含める。
        repo_key = id(repo) if repo is not None else 0
        tags_list = list(tags)
        # 未キャッシュのタグだけ翻訳を一括 prefetch し、per-tag の search_tags N+1 を解消する
        # (#998)。prefetch_fn は失敗時も例外を伝播させず per-tag fallback に委ねる契約。
        if self._prefetch_fn is not None:
            uncached = [
                tag
                for tag in dict.fromkeys(tags_list)
                if (tag, fmap.get(tag, "unknown"), repo_key) not in self._cache
            ]
            if uncached:
                if cancel_check is not None:
                    cancel_check()
                self._prefetch_fn(uncached, repo=repo)
        result: dict[str, RefinementRecommendation] = {}
        total = 0
        evaluated = 0
        for tag in tags_list:
            total += 1
            format_name = fmap.get(tag, "unknown")
            key = (tag, format_name, repo_key)
            rec = self._cache.get(key)
            if rec is None:
                # DB 往復を伴う評価の直前だけチェックする (キャッシュヒット時は呼ばない)。
                if cancel_check is not None:
                    cancel_check()
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

        除外で reason が空になったら needs_refinement を False にする。除外が無ければ
        元オブジェクトをそのまま返す。

        ignore された reason 由来の修正候補が UI (tooltip) に漏れないよう、部分 ignore 時は:
        - proposals: `reason_codes` が残存 reason に紐づくものだけ残す (DbFeedbackProposal は
          reason_codes でひも付くため厳密に除外できる)。
        - suggestions: モデル上 reason との明示的ひも付けが無いため、どの reason 由来か特定できない。
          ignore 済み reason の修正が残るのを防ぐ保守側に倒し、部分 ignore 時はクリアする
          (残存 reason の message は引き続き表示されるので「見直すべき」ことは伝わる)。
        """
        kept = [r for r in rec.reasons if (rec.source_tag, r.code) not in ignored]
        if len(kept) == len(rec.reasons):
            return rec
        needs = rec.needs_refinement and len(kept) > 0
        kept_codes = {r.code for r in kept}
        kept_proposals = [
            p for p in rec.proposals if not p.reason_codes or (set(p.reason_codes) & kept_codes)
        ]
        return rec.model_copy(
            update={
                "reasons": kept,
                "needs_refinement": needs,
                "suggestions": [],
                "proposals": kept_proposals,
            }
        )

    def ignore(self, tag: str, reason_code: str) -> None:
        """タグの特定 reason のリコメンドを以後抑制する (永続化)。"""
        self._ignore_repo.add_ignore(tag, reason_code)
        # 当該タグのキャッシュを無効化 (format 問わず)
        self._cache = {k: v for k, v in self._cache.items() if k[0] != tag}
        logger.debug(f"refinement ignore 追加: tag='{tag}', reason_code='{reason_code}'")

    def clear_cache(self) -> None:
        """評価キャッシュを全消去する (#931)。

        tagdb のメタデータ (alias/type 等) が同一セッション中に編集された場合
        (例: TagManagementWidget の type 更新)、キャッシュ済みリコメンドが stale になるため、
        編集フロー側から本メソッドを呼んで無効化する。
        """
        self._cache.clear()
        logger.debug("refinement キャッシュをクリア")

    def is_ignored(self, tag: str, reason_code: str) -> bool:
        """(tag, reason_code) が ignore 済みか返す。"""
        return self._ignore_repo.is_ignored(tag, reason_code)

    def list_ignored(self) -> set[tuple[str, str]]:
        """ignore 済みの (tag, reason_code) 集合を返す。"""
        return self._ignore_repo.list_ignored()
