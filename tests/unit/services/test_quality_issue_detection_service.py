"""QualityIssueDetectionService の構造的品質問題検出テスト (Refs #726)。

検出は閾値非依存・構造的事実 5 種 (EMPTY_TAGS / NO_SCORE / UNKNOWN_TIER /
RATING_DISAGREEMENT / SCORER_DISAGREEMENT) と集約 (canonical_rating /
canonical_tier / caption_word_count / tags) を検証する。
"""

import pytest

from lorairo.domain.quality_tier import QualityTier
from lorairo.services.quality_issue_detection_service import (
    IssueType,
    QualityIssueDetectionService,
)

pytestmark = pytest.mark.unit

META = {"uuid": "abcd", "width": 1024, "height": 1024}


@pytest.fixture
def service() -> QualityIssueDetectionService:
    return QualityIssueDetectionService()


def _ann(*, tags=None, captions=None, scores=None, score_labels=None, ratings=None) -> dict:
    return {
        "tags": tags or [],
        "captions": captions or [],
        "scores": scores or [],
        "score_labels": score_labels or [],
        "ratings": ratings or [],
    }


def test_empty_tags_detected(service):
    result = service.detect_image(
        1,
        META,
        _ann(tags=[], score_labels=[{"model": "aesthetic_shadow_v2", "label": "aesthetic"}]),
    )
    assert IssueType.EMPTY_TAGS in result.issues


def test_all_rejected_tags_count_as_empty(service):
    rejected = [{"tag": "x", "confidence_score": 0.9, "model_id": 1, "rejected_at": "2026-01-01"}]
    result = service.detect_image(1, META, _ann(tags=rejected))
    assert IssueType.EMPTY_TAGS in result.issues


def test_no_score_detected(service):
    result = service.detect_image(
        1,
        META,
        _ann(tags=[{"tag": "a", "confidence_score": 0.9, "model_id": 1, "rejected_at": None}]),
    )
    assert IssueType.NO_SCORE in result.issues


def test_unknown_tier_detected(service):
    sl = [{"model": "waifu_aesthetic", "label": "tier_2"}]
    result = service.detect_image(
        1,
        META,
        _ann(
            tags=[{"tag": "a", "confidence_score": 0.9, "model_id": 1, "rejected_at": None}],
            score_labels=sl,
        ),
    )
    assert IssueType.UNKNOWN_TIER in result.issues


def test_rating_disagreement_detected(service):
    ratings = [
        {"model": "wd-rater", "normalized_rating": "R", "confidence_score": 0.7},
        {"model": "gpt-4o", "normalized_rating": "PG", "confidence_score": 0.6},
    ]
    result = service.detect_image(
        1,
        META,
        _ann(
            tags=[{"tag": "a", "confidence_score": 0.9, "model_id": 1, "rejected_at": None}],
            score_labels=[{"model": "aesthetic_shadow_v2", "label": "aesthetic"}],
            ratings=ratings,
        ),
    )
    assert IssueType.RATING_DISAGREEMENT in result.issues
    assert result.canonical_rating == "R"  # 厳しい方


def test_scorer_disagreement_detected(service):
    sl = [
        {"model": "aesthetic_shadow_v2", "label": "aesthetic"},  # BEST_QUALITY
        {"model": "aesthetic_shadow_v2", "label": "displeasing"},  # LOW_QUALITY
    ]
    result = service.detect_image(
        1,
        META,
        _ann(
            tags=[{"tag": "a", "confidence_score": 0.9, "model_id": 1, "rejected_at": None}],
            score_labels=sl,
        ),
    )
    assert IssueType.SCORER_DISAGREEMENT in result.issues


def test_clean_image_has_no_issues(service):
    ann = _ann(
        tags=[{"tag": "a", "confidence_score": 0.9, "model_id": 1, "rejected_at": None}],
        captions=[{"caption": "a young woman walking a dog in the city", "rejected_at": None}],
        score_labels=[{"model": "aesthetic_shadow_v2", "label": "aesthetic"}],
        ratings=[{"model": "wd-rater", "normalized_rating": "PG", "confidence_score": 0.9}],
    )
    result = service.detect_image(1, META, ann)
    assert result.issues == []
    assert result.needs_review is False
    # "a young woman walking a dog in the city" = 9 語 (空白 split)。
    # 計画の例示値 8 は数え間違い。集約ルール (空白 split 語数) に従い 9 を検証する。
    assert result.caption_word_count == 9
    assert result.canonical_tier == QualityTier.BEST_QUALITY


def test_summarize_counts(service):
    clean = service.detect_image(
        1,
        META,
        _ann(
            tags=[{"tag": "a", "confidence_score": 0.9, "model_id": 1, "rejected_at": None}],
            score_labels=[{"model": "aesthetic_shadow_v2", "label": "aesthetic"}],
            ratings=[{"model": "wd-rater", "normalized_rating": "PG", "confidence_score": 0.9}],
        ),
    )
    bad = service.detect_image(2, META, _ann())  # empty everything → EMPTY_TAGS + NO_SCORE
    summary = service.summarize([clean, bad])
    assert summary.batch_size == 2
    assert summary.needs_review_count == 1
    assert summary.clean_count == 1
    assert summary.issue_counts[IssueType.EMPTY_TAGS] == 1
    assert summary.issue_counts[IssueType.NO_SCORE] == 1


def test_canonical_tier_even_count_picks_stricter_side(service):
    """tier が偶数個に割れたら厳しい側 (小さい ordinal) を採用する。"""
    sl = [
        {"model": "aesthetic_shadow_v2", "label": "aesthetic"},  # BEST_QUALITY (5)
        {"model": "cafe_aesthetic", "label": "aesthetic"},  # GOOD_QUALITY (4)
    ]
    result = service.detect_image(
        1,
        META,
        _ann(
            tags=[{"tag": "a", "confidence_score": 0.9, "model_id": 1, "rejected_at": None}],
            score_labels=sl,
        ),
    )
    # 2 件は scorer 不一致でもある
    assert IssueType.SCORER_DISAGREEMENT in result.issues
    # 偶数個 → 厳しい側 = 小さい ordinal = GOOD_QUALITY
    assert result.canonical_tier == QualityTier.GOOD_QUALITY


def test_tags_sorted_by_confidence_descending(service):
    tags = [
        {"tag": "low", "confidence_score": 0.2, "model_id": 1, "rejected_at": None},
        {"tag": "high", "confidence_score": 0.95, "model_id": 1, "rejected_at": None},
        {"tag": "mid", "confidence_score": 0.5, "model_id": 1, "rejected_at": None},
        {"tag": "rejected", "confidence_score": 0.99, "model_id": 1, "rejected_at": "2026-01-01"},
    ]
    result = service.detect_image(
        1,
        META,
        _ann(
            tags=tags,
            score_labels=[{"model": "aesthetic_shadow_v2", "label": "aesthetic"}],
        ),
    )
    assert [t.tag for t in result.tags] == ["high", "mid", "low"]


def test_no_caption_word_count_is_zero(service):
    result = service.detect_image(
        1,
        META,
        _ann(
            tags=[{"tag": "a", "confidence_score": 0.9, "model_id": 1, "rejected_at": None}],
            score_labels=[{"model": "aesthetic_shadow_v2", "label": "aesthetic"}],
        ),
    )
    assert result.caption_word_count == 0
    assert result.caption is None


def test_canonical_rating_orders_xxx_strictest(service):
    """rating 順序 PG < PG-13 < R < X < XXX。最も厳しい値を採用する。"""
    ratings = [
        {"model": "a", "normalized_rating": "PG-13", "confidence_score": 0.7},
        {"model": "b", "normalized_rating": "XXX", "confidence_score": 0.6},
        {"model": "c", "normalized_rating": "X", "confidence_score": 0.5},
    ]
    result = service.detect_image(
        1,
        META,
        _ann(
            tags=[{"tag": "a", "confidence_score": 0.9, "model_id": 1, "rejected_at": None}],
            score_labels=[{"model": "aesthetic_shadow_v2", "label": "aesthetic"}],
            ratings=ratings,
        ),
    )
    assert result.canonical_rating == "XXX"
    assert IssueType.RATING_DISAGREEMENT in result.issues


def test_reviewed_image_is_not_needs_review(service):
    """reviewed_at が値ありなら issue があっても needs_review にならない。"""
    meta = {**META, "reviewed_at": "2026-06-11T00:00:00Z"}
    result = service.detect_image(1, meta, _ann())  # 空 = EMPTY_TAGS + NO_SCORE
    assert result.reviewed is True
    assert result.issues  # issue 自体は検出される
    assert result.needs_review is False


def test_unreviewed_image_with_issue_needs_review(service):
    """reviewed_at が None なら issue 有で needs_review。"""
    meta = {**META, "reviewed_at": None}
    result = service.detect_image(1, meta, _ann())
    assert result.reviewed is False
    assert result.needs_review is True


def test_summarize_counts_accepted(service):
    """summarize が accepted_count を集計する。"""
    accepted = service.detect_image(
        1,
        {**META, "reviewed_at": "2026-06-11T00:00:00Z"},
        _ann(
            tags=[{"tag": "a", "confidence_score": 0.9, "model_id": 1, "rejected_at": None}],
            score_labels=[{"model": "aesthetic_shadow_v2", "label": "aesthetic"}],
            ratings=[{"model": "wd-rater", "normalized_rating": "PG", "confidence_score": 0.9}],
        ),
    )
    unreviewed = service.detect_image(2, {**META, "reviewed_at": None}, _ann())
    summary = service.summarize([accepted, unreviewed])
    assert summary.accepted_count == 1
