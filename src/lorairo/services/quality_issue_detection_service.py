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

from dataclasses import dataclass
from enum import Enum

from lorairo.domain.quality_tier import QualityTier


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

    @property
    def needs_review(self) -> bool:
        """構造的問題が 1 件以上あれば要レビュー。"""
        return len(self.issues) > 0


@dataclass(frozen=True)
class BatchTriageSummary:
    """バッチ全体のサマリ。"""

    batch_size: int
    needs_review_count: int
    clean_count: int
    issue_counts: dict[IssueType, int]  # issue 種別ごとの件数
    tier_distribution: dict[QualityTier, int]
    no_tier_count: int  # tier 算出不能 (no-score / unknown) の件数


class QualityIssueDetectionService:
    """ステージング集合のアノテーションを構造的品質問題に分類する (Qt-free)。"""

    def detect_image(self, image_id: int, image_meta: dict, annotations: dict) -> ImageTriageResult:
        """1 画像のアノテーションをトリアージする。

        Args:
            image_id: 画像 ID。
            image_meta: ``{"uuid": str|None, "width": int|None, "height": int|None}``。
            annotations: ``db_manager.get_image_annotations`` の戻り値
                (tags / captions / scores / score_labels / ratings)。

        Returns:
            1 画像分のトリアージ結果。
        """
        raise NotImplementedError

    def summarize(self, results: list[ImageTriageResult]) -> BatchTriageSummary:
        """画像別結果をバッチサマリに集約する。

        Args:
            results: ``detect_image`` の結果リスト。

        Returns:
            バッチ全体のサマリ。
        """
        raise NotImplementedError
