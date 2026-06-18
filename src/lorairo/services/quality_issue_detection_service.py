"""アノテーション品質の構造的問題検出サービス (Qt-free)。

Wireframes v11 Frame 5 (Results) の読み取り専用トリアージで使用する。
検出は**閾値を持たず**、DB にある構造的事実のみを 5 種に分類する:

- ``EMPTY_TAGS`` — 採用タグが 0 件
- ``NO_SCORE`` — scorer 出力 (score / score_label) が無い
- ``UNKNOWN_TIER`` — score_label の (model, label) が tier mapping に無い (ADR 0028)
- ``RATING_DISAGREEMENT`` — モデル間で ``normalized_rating`` が割れている
- ``SCORER_DISAGREEMENT`` — scorer 間で tier が割れている (is_unanimous=false 相当)

低信頼度タグ・短 caption は issue 化しない (行内にデータとして表示するのみ)。
"""

import math
import random
from dataclasses import dataclass
from enum import Enum
from typing import Any

from lorairo.domain.quality_tier import QualityTier, map_score_label_to_tier

# clean 抜き取り監査 (OK箱) の抽出枚数上限。母数が大きくても目視はこの枚数で頭打ち。
_CLEAN_SAMPLE_CAP = 30


def _recommended_clean_sample_size(clean_count: int) -> int:
    """clean 母数に応じた抜き取り推奨枚数を返す。

    母数連動: 20 以下は全数、500 以下は ceil(sqrt(n))、それ以上は ``_CLEAN_SAMPLE_CAP``。
    閾値ではなく「規模が上がるほど見る割合は下げるが上限を設ける」サンプリング方針。

    Args:
        clean_count: clean (issue 無し・未 accept) 画像の母数。

    Returns:
        推奨抜き取り枚数 (0 <= 戻り値 <= clean_count)。
    """
    if clean_count <= 20:
        return clean_count
    if clean_count <= 500:
        return math.ceil(math.sqrt(clean_count))
    return _CLEAN_SAMPLE_CAP


# Any 使用: image_meta / annotations は db_manager 由来の heterogeneous dict
# (uuid:str / width:int / list[_AnnotationRow] が混在) で具体型を 1 つに固定できない。
_AnnotationRow = dict[str, Any]

# normalized_rating の厳しさ順序 (値が大きいほど厳しい)。
_RATING_ORDER: dict[str, int] = {"PG": 0, "PG-13": 1, "R": 2, "X": 3, "XXX": 4}


class IssueType(Enum):
    """構造的品質問題の種別 (閾値非依存)。"""

    EMPTY_TAGS = "empty_tags"
    NO_SCORE = "no_score"
    UNKNOWN_TIER = "unknown_tier"
    RATING_DISAGREEMENT = "rating_disagreement"
    SCORER_DISAGREEMENT = "scorer_disagreement"


@dataclass(frozen=True)
class TagView:
    """行表示用のタグ (採用分のみ)。"""

    tag: str
    confidence_score: float | None
    model_id: int | None


@dataclass(frozen=True)
class RatingView:
    """モデル別 rating。"""

    model: str
    normalized_rating: str | None
    confidence_score: float | None


@dataclass(frozen=True)
class ScorerView:
    """モデル別 scorer 判定。"""

    model: str
    label: str | None
    tier: QualityTier | None  # mapping 不能なら None


@dataclass(frozen=True)
class ImageTriageResult:
    """1 画像分のトリアージ結果。"""

    image_id: int
    uuid: str | None
    width: int | None
    height: int | None
    tags: list[TagView]
    caption: str | None
    caption_word_count: int
    canonical_rating: str | None  # 最も厳しい normalized_rating
    ratings: list[RatingView]
    canonical_tier: QualityTier | None  # scorer tier の median 相当
    scorers: list[ScorerView]
    issues: list[IssueType]  # 検出された構造的問題 (空なら clean)
    reviewed: bool = False  # accept 済み (Image.reviewed_at が値あり) なら True

    @property
    def needs_review(self) -> bool:
        """構造的問題が 1 件以上あり、まだ accept されていなければ要レビュー。"""
        return len(self.issues) > 0 and not self.reviewed


@dataclass(frozen=True)
class BatchTriageSummary:
    """バッチ全体のサマリ。"""

    batch_size: int
    needs_review_count: int
    clean_count: int
    issue_counts: dict[IssueType, int]  # issue 種別ごとの件数
    tier_distribution: dict[QualityTier, int]
    no_tier_count: int  # tier 算出不能 (no-score / unknown) の件数
    accepted_count: int = 0  # accept 済み (reviewed) 画像の件数


@dataclass(frozen=True)
class CleanAuditPlan:
    """clean (issue 無し・未 accept) 集合の抜き取り監査プラン (OK箱)。

    「機械が clean と判定 → 人は見ずに一括 accept」の盲点を塞ぐため、一括 accept
    対象の母集団と、その目視確認用に無作為抽出した部分集合を返す。
    """

    clean_image_ids: list[int]  # 一括 accept 対象 (issue 無し かつ 未 reviewed)
    sample_image_ids: list[int]  # 目視確認のため抽出した部分集合 (clean_image_ids の順序を保持)


class QualityIssueDetectionService:
    """ステージング集合のアノテーションを構造的品質問題に分類する (Qt-free)。"""

    def detect_image(
        self, image_id: int, image_meta: _AnnotationRow, annotations: _AnnotationRow
    ) -> ImageTriageResult:
        """1 画像のアノテーションをトリアージする。

        Args:
            image_id: 画像 ID。
            image_meta: ``{"uuid", "width", "height", "reviewed_at"}`` を含む dict。
                ``reviewed_at`` が非 None なら accept 済みと判定する。
            annotations: ``db_manager.get_image_annotations`` の戻り値
                (tags / captions / scores / score_labels / ratings)。

        Returns:
            1 画像分のトリアージ結果。
        """
        tags_raw = annotations.get("tags", [])
        captions_raw = annotations.get("captions", [])
        scores_raw = annotations.get("scores", [])
        score_labels_raw = annotations.get("score_labels", [])
        ratings_raw = annotations.get("ratings", [])

        # 採用タグ (rejected_at is None) を confidence 降順で TagView 化する。
        accepted_tags = [t for t in tags_raw if t.get("rejected_at") is None]
        tag_views = self._build_tag_views(accepted_tags)

        # 採用 caption (最初の rejected_at is None) と語数。
        caption = self._first_accepted_caption(captions_raw)
        caption_word_count = len(caption.split()) if caption else 0

        # rating ビューと canonical (最も厳しい) rating。
        rating_views = self._build_rating_views(ratings_raw)
        canonical_rating = self._strictest_rating(rating_views)

        # scorer ビューと canonical tier (median, 偶数個は厳しい側)。
        scorer_views = self._build_scorer_views(score_labels_raw)
        canonical_tier = self._median_tier(scorer_views)

        issues = self._detect_issues(
            accepted_tags=accepted_tags,
            scores_raw=scores_raw,
            score_labels_raw=score_labels_raw,
            rating_views=rating_views,
            scorer_views=scorer_views,
        )

        return ImageTriageResult(
            image_id=image_id,
            uuid=image_meta.get("uuid"),
            width=image_meta.get("width"),
            height=image_meta.get("height"),
            tags=tag_views,
            caption=caption,
            caption_word_count=caption_word_count,
            canonical_rating=canonical_rating,
            ratings=rating_views,
            canonical_tier=canonical_tier,
            scorers=scorer_views,
            issues=issues,
            reviewed=image_meta.get("reviewed_at") is not None,
        )

    def summarize(self, results: list[ImageTriageResult]) -> BatchTriageSummary:
        """画像別結果をバッチサマリに集約する。

        Args:
            results: ``detect_image`` の結果リスト。

        Returns:
            バッチ全体のサマリ。
        """
        # needs_review = issue 有 かつ 未 accept。clean = issue 無し。accepted = reviewed。
        needs_review_count = sum(1 for r in results if r.needs_review)
        clean_count = sum(1 for r in results if not r.issues)
        accepted_count = sum(1 for r in results if r.reviewed)

        issue_counts: dict[IssueType, int] = dict.fromkeys(IssueType, 0)
        tier_distribution: dict[QualityTier, int] = {}
        no_tier_count = 0
        for result in results:
            for issue in result.issues:
                issue_counts[issue] += 1
            if result.canonical_tier is None:
                no_tier_count += 1
            else:
                tier_distribution[result.canonical_tier] = (
                    tier_distribution.get(result.canonical_tier, 0) + 1
                )

        return BatchTriageSummary(
            batch_size=len(results),
            needs_review_count=needs_review_count,
            clean_count=clean_count,
            issue_counts=issue_counts,
            tier_distribution=tier_distribution,
            no_tier_count=no_tier_count,
            accepted_count=accepted_count,
        )

    @staticmethod
    def build_clean_audit(
        results: list[ImageTriageResult],
        *,
        sample_size: int | None = None,
        rng: random.Random | None = None,
    ) -> CleanAuditPlan:
        """clean (issue 無し・未 accept) 集合と、その目視確認用の無作為抽出を算出する。

        「機械が clean と判定 → 無確認で一括 accept」の盲点を塞ぐための OK箱用プラン。
        抽出枚数は既定で母数連動 (``_recommended_clean_sample_size``)。``sample_size``
        を明示した場合はそれを ``[0, clean 母数]`` に丸める。

        Args:
            results: ``detect_image`` の結果リスト。
            sample_size: 抜き取り枚数の明示指定。None なら母数連動の推奨値。
            rng: 抽出に使う乱数生成器。None なら ``random.Random()`` を都度生成する
                (テストでは固定 seed の ``random.Random`` を渡して決定的にできる)。

        Returns:
            一括 accept 対象 (``clean_image_ids``) と目視抽出 (``sample_image_ids``)。
            clean が 0 件なら両方空。
        """
        clean_ids = [r.image_id for r in results if not r.issues and not r.reviewed]
        total = len(clean_ids)
        if total == 0:
            return CleanAuditPlan(clean_image_ids=[], sample_image_ids=[])

        target = sample_size if sample_size is not None else _recommended_clean_sample_size(total)
        target = max(0, min(target, total))
        if target == 0:
            return CleanAuditPlan(clean_image_ids=clean_ids, sample_image_ids=[])

        generator = rng if rng is not None else random.Random()
        chosen = set(generator.sample(clean_ids, target))
        # 表示の安定のため clean_ids の元順序で抽出分を返す。
        sample_ids = [image_id for image_id in clean_ids if image_id in chosen]
        return CleanAuditPlan(clean_image_ids=clean_ids, sample_image_ids=sample_ids)

    @staticmethod
    def _build_tag_views(accepted_tags: list[_AnnotationRow]) -> list[TagView]:
        """採用タグを confidence 降順の ``TagView`` リストに変換する。

        Args:
            accepted_tags: ``rejected_at is None`` のタグ dict のリスト。

        Returns:
            confidence_score 降順 (None は最下位) に並べた ``TagView`` リスト。
        """
        views = [
            TagView(
                tag=t.get("tag", ""),
                confidence_score=t.get("confidence_score"),
                model_id=t.get("model_id"),
            )
            for t in accepted_tags
        ]
        # confidence None は最下位に回す (降順なので -inf 相当)。
        views.sort(
            key=lambda v: v.confidence_score if v.confidence_score is not None else float("-inf"),
            reverse=True,
        )
        return views

    @staticmethod
    def _first_accepted_caption(captions_raw: list[_AnnotationRow]) -> str | None:
        """最初の採用 caption (``rejected_at is None``) を返す。無ければ ``None``。"""
        for c in captions_raw:
            if c.get("rejected_at") is None:
                return c.get("caption")
        return None

    @staticmethod
    def _build_rating_views(ratings_raw: list[_AnnotationRow]) -> list[RatingView]:
        """rating dict のリストを ``RatingView`` リストに変換する。"""
        return [
            RatingView(
                model=r.get("model", ""),
                normalized_rating=r.get("normalized_rating"),
                confidence_score=r.get("confidence_score"),
            )
            for r in ratings_raw
        ]

    @staticmethod
    def _strictest_rating(rating_views: list[RatingView]) -> str | None:
        """``normalized_rating`` のうち最も厳しい値を返す (``_RATING_ORDER`` 順)。

        ``_RATING_ORDER`` に無い値・``None`` は無視する。該当値が無ければ ``None``。
        """
        known = [
            v.normalized_rating
            for v in rating_views
            if v.normalized_rating is not None and v.normalized_rating in _RATING_ORDER
        ]
        if not known:
            return None
        return max(known, key=lambda rating: _RATING_ORDER[rating])

    @staticmethod
    def _build_scorer_views(score_labels_raw: list[_AnnotationRow]) -> list[ScorerView]:
        """score_label dict のリストを ``ScorerView`` リストに変換する。

        ``map_score_label_to_tier`` が ``None`` を返す場合は tier=None (mapping 不能)。
        """
        views: list[ScorerView] = []
        for sl in score_labels_raw:
            model = sl.get("model", "")
            label = sl.get("label")
            tier = map_score_label_to_tier(model, label) if label is not None else None
            views.append(ScorerView(model=model, label=label, tier=tier))
        return views

    @staticmethod
    def _median_tier(scorer_views: list[ScorerView]) -> QualityTier | None:
        """scorer tier (None 除く) の中央値を返す。

        偶数個に割れたときは厳しい側 (小さい ordinal) を採用する。
        ``QualityTier`` は値が大きいほど高品質なので、昇順 sort 後の左中央
        (``sorted[(len - 1) // 2]``) が小さい ordinal = 厳しい側になる。
        known tier が無ければ ``None``。
        """
        known = sorted(v.tier for v in scorer_views if v.tier is not None)
        if not known:
            return None
        return known[(len(known) - 1) // 2]

    @staticmethod
    def _detect_issues(
        *,
        accepted_tags: list[_AnnotationRow],
        scores_raw: list[_AnnotationRow],
        score_labels_raw: list[_AnnotationRow],
        rating_views: list[RatingView],
        scorer_views: list[ScorerView],
    ) -> list[IssueType]:
        """構造的品質問題 (閾値非依存) を検出する。

        Returns:
            検出された ``IssueType`` のリスト (定義順、空なら clean)。
        """
        issues: list[IssueType] = []

        if not accepted_tags:
            issues.append(IssueType.EMPTY_TAGS)

        if not scores_raw and not score_labels_raw:
            issues.append(IssueType.NO_SCORE)

        if any(v.tier is None for v in scorer_views):
            issues.append(IssueType.UNKNOWN_TIER)

        distinct_ratings = {v.normalized_rating for v in rating_views if v.normalized_rating is not None}
        if len(distinct_ratings) >= 2:
            issues.append(IssueType.RATING_DISAGREEMENT)

        distinct_tiers = {v.tier for v in scorer_views if v.tier is not None}
        if len(distinct_tiers) >= 2:
            issues.append(IssueType.SCORER_DISAGREEMENT)

        return issues
