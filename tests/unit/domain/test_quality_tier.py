"""Unit tests for ``lorairo.domain.quality_tier`` (ADR 0029)。"""

from __future__ import annotations

import pytest

from lorairo.domain.quality_tier import (
    MANUAL_MODEL_NAME,
    MAPPING_VERSION,
    NO_SCORE,
    UNKNOWN,
    QualityTier,
    compute_quality_summary,
    map_manual_score_to_tier,
    map_score_label_to_tier,
    tier_label_to_value,
)

pytestmark = pytest.mark.unit


class TestQualityTierEnum:
    def test_ordinal_ordering(self) -> None:
        assert QualityTier.MASTERPIECE > QualityTier.BEST_QUALITY
        assert QualityTier.BEST_QUALITY > QualityTier.GOOD_QUALITY
        assert QualityTier.GOOD_QUALITY > QualityTier.NORMAL_QUALITY
        assert QualityTier.NORMAL_QUALITY > QualityTier.LOW_QUALITY
        assert QualityTier.LOW_QUALITY > QualityTier.WORST_QUALITY

    def test_label_property(self) -> None:
        assert QualityTier.MASTERPIECE.label == "masterpiece"
        assert QualityTier.BEST_QUALITY.label == "best quality"
        assert QualityTier.GOOD_QUALITY.label == "good quality"
        assert QualityTier.NORMAL_QUALITY.label == "normal quality"
        assert QualityTier.LOW_QUALITY.label == "low quality"
        assert QualityTier.WORST_QUALITY.label == "worst quality"


class TestScoreLabelMapping:
    @pytest.mark.parametrize(
        ("model", "label", "expected"),
        [
            ("aesthetic_shadow_v1", "very aesthetic", QualityTier.MASTERPIECE),
            ("aesthetic_shadow_v1", "aesthetic", QualityTier.BEST_QUALITY),
            ("aesthetic_shadow_v1", "displeasing", QualityTier.LOW_QUALITY),
            ("aesthetic_shadow_v1", "very displeasing", QualityTier.WORST_QUALITY),
            ("aesthetic_shadow_v2", "very aesthetic", QualityTier.MASTERPIECE),
            ("aesthetic_shadow_v2", "aesthetic", QualityTier.BEST_QUALITY),
            ("aesthetic_shadow_v2", "displeasing", QualityTier.LOW_QUALITY),
            ("aesthetic_shadow_v2", "very displeasing", QualityTier.WORST_QUALITY),
            ("cafe_aesthetic", "aesthetic", QualityTier.GOOD_QUALITY),
            ("cafe_aesthetic", "not_aesthetic", QualityTier.LOW_QUALITY),
        ],
    )
    def test_known_mappings(self, model: str, label: str, expected: QualityTier) -> None:
        assert map_score_label_to_tier(model, label) == expected

    def test_unknown_model(self) -> None:
        assert map_score_label_to_tier("waifu_aesthetic", "very aesthetic") is None

    def test_unknown_label(self) -> None:
        assert map_score_label_to_tier("aesthetic_shadow_v1", "mediocre") is None


class TestManualScoreMapping:
    @pytest.mark.parametrize(
        ("score", "expected"),
        [
            (10.0, QualityTier.MASTERPIECE),
            (9.0, QualityTier.MASTERPIECE),
            (8.99, QualityTier.BEST_QUALITY),
            (8.0, QualityTier.BEST_QUALITY),
            (7.99, QualityTier.GOOD_QUALITY),
            (6.0, QualityTier.GOOD_QUALITY),
            (5.99, QualityTier.NORMAL_QUALITY),
            (5.0, QualityTier.NORMAL_QUALITY),
            (4.99, QualityTier.LOW_QUALITY),
            (3.0, QualityTier.LOW_QUALITY),
            (2.99, QualityTier.WORST_QUALITY),
            (0.0, QualityTier.WORST_QUALITY),
        ],
    )
    def test_known_ranges(self, score: float, expected: QualityTier) -> None:
        assert map_manual_score_to_tier(score) == expected

    @pytest.mark.parametrize("score", [-0.1, 10.01, -100.0, 100.0])
    def test_out_of_range_returns_none(self, score: float) -> None:
        assert map_manual_score_to_tier(score) is None


class TestTierLabelToValue:
    def test_known_labels(self) -> None:
        assert tier_label_to_value("best quality") == QualityTier.BEST_QUALITY
        assert tier_label_to_value("worst quality") == QualityTier.WORST_QUALITY

    def test_sentinel_returns_none(self) -> None:
        assert tier_label_to_value(NO_SCORE) is None
        assert tier_label_to_value(UNKNOWN) is None

    def test_unknown_label_returns_none(self) -> None:
        assert tier_label_to_value("EXCELLENT") is None


class TestComputeQualitySummary:
    def test_empty_inputs_returns_no_score(self) -> None:
        result = compute_quality_summary([], [])
        assert result["tier"] == NO_SCORE
        assert result["no_score"] is True
        assert result["is_unanimous"] is False
        assert result["known_count"] == 0
        assert result["unknown_count"] == 0
        assert result["votes"] == []
        assert result["mapping_version"] == MAPPING_VERSION

    def test_only_unknown_labels_returns_unknown_tier(self) -> None:
        score_labels = [{"model": "waifu_aesthetic", "label": "very aesthetic"}]
        result = compute_quality_summary(score_labels, [])
        assert result["tier"] == UNKNOWN
        assert result["no_score"] is False
        assert result["is_unanimous"] is False
        assert result["known_count"] == 0
        assert result["unknown_count"] == 1
        assert len(result["votes"]) == 1
        assert result["votes"][0]["quality_tier"] == UNKNOWN

    def test_single_known_label(self) -> None:
        score_labels = [{"model": "aesthetic_shadow_v2", "label": "aesthetic"}]
        result = compute_quality_summary(score_labels, [])
        assert result["tier"] == "best quality"
        assert result["is_unanimous"] is True
        assert result["known_count"] == 1
        assert result["unknown_count"] == 0

    def test_unanimous_high_quality(self) -> None:
        score_labels = [
            {"model": "aesthetic_shadow_v1", "label": "aesthetic"},
            {"model": "aesthetic_shadow_v2", "label": "aesthetic"},
        ]
        result = compute_quality_summary(score_labels, [])
        assert result["tier"] == "best quality"
        assert result["is_unanimous"] is True
        assert result["known_count"] == 2

    def test_median_odd_n(self) -> None:
        # [best, best, good] -> sorted [good, best, best] -> index 1 -> best
        score_labels = [
            {"model": "aesthetic_shadow_v1", "label": "aesthetic"},  # best
            {"model": "aesthetic_shadow_v2", "label": "aesthetic"},  # best
            {"model": "cafe_aesthetic", "label": "aesthetic"},  # good
        ]
        result = compute_quality_summary(score_labels, [])
        assert result["tier"] == "best quality"
        assert result["is_unanimous"] is False
        assert result["known_count"] == 3

    def test_median_disagreement(self) -> None:
        # [best, good, low] -> sorted [low, good, best] -> index 1 -> good
        score_labels = [
            {"model": "aesthetic_shadow_v1", "label": "aesthetic"},  # best
            {"model": "cafe_aesthetic", "label": "aesthetic"},  # good
            {"model": "aesthetic_shadow_v2", "label": "displeasing"},  # low
        ]
        result = compute_quality_summary(score_labels, [])
        assert result["tier"] == "good quality"
        assert result["is_unanimous"] is False

    def test_median_even_n_higher_priority(self) -> None:
        # [best, good] -> sorted [good, best] -> n//2 = 1 -> best (higher 寄り)
        score_labels = [
            {"model": "aesthetic_shadow_v1", "label": "aesthetic"},  # best
            {"model": "cafe_aesthetic", "label": "aesthetic"},  # good
        ]
        result = compute_quality_summary(score_labels, [])
        assert result["tier"] == "best quality"
        assert result["is_unanimous"] is False

    def test_unanimous_false_when_unknown_present(self) -> None:
        score_labels = [
            {"model": "aesthetic_shadow_v1", "label": "aesthetic"},  # best
            {"model": "aesthetic_shadow_v2", "label": "aesthetic"},  # best
            {"model": "waifu_aesthetic", "label": "very aesthetic"},  # unknown
        ]
        result = compute_quality_summary(score_labels, [])
        assert result["tier"] == "best quality"
        assert result["is_unanimous"] is False
        assert result["known_count"] == 2
        assert result["unknown_count"] == 1

    def test_manual_score_contributes(self) -> None:
        # score_labels: [best], scores: manual 9.5 (-> masterpiece)
        # known votes: [best, masterpiece] -> sorted [best, masterpiece]
        # n//2 = 1 -> masterpiece
        score_labels = [{"model": "aesthetic_shadow_v2", "label": "aesthetic"}]  # best
        scores = [{"score": 9.5, "is_edited_manually": True}]
        result = compute_quality_summary(score_labels, scores)
        assert result["tier"] == "masterpiece"
        assert result["known_count"] == 2
        manual_votes = [v for v in result["votes"] if v["source"] == "manual_score"]
        assert len(manual_votes) == 1
        assert manual_votes[0]["model"] == MANUAL_MODEL_NAME
        assert manual_votes[0]["raw_score"] == 9.5
        assert manual_votes[0]["quality_tier"] == "masterpiece"

    def test_ai_scorer_numeric_score_excluded(self) -> None:
        # is_edited_manually=False scores are AI scorer outputs, NOT counted.
        score_labels = [{"model": "aesthetic_shadow_v2", "label": "aesthetic"}]
        scores = [
            {"score": 0.92, "is_edited_manually": False},  # AI scorer, excluded
            {"score": 0.08, "is_edited_manually": False},  # AI scorer, excluded
        ]
        result = compute_quality_summary(score_labels, scores)
        # only score_labels vote counted
        assert result["known_count"] == 1
        assert result["tier"] == "best quality"
        manual_votes = [v for v in result["votes"] if v["source"] == "manual_score"]
        assert len(manual_votes) == 0

    def test_manual_score_out_of_range_becomes_unknown(self) -> None:
        scores = [{"score": 99.9, "is_edited_manually": True}]
        result = compute_quality_summary([], scores)
        assert result["tier"] == UNKNOWN
        assert result["known_count"] == 0
        assert result["unknown_count"] == 1
        assert result["votes"][0]["quality_tier"] == UNKNOWN

    def test_manual_score_missing_value_skipped(self) -> None:
        scores = [
            {"score": None, "is_edited_manually": True},
            {"is_edited_manually": True},
        ]
        result = compute_quality_summary([], scores)
        assert result["tier"] == NO_SCORE
        assert result["no_score"] is True

    def test_vote_shape_for_score_label(self) -> None:
        score_labels = [{"model": "cafe_aesthetic", "label": "not_aesthetic"}]
        result = compute_quality_summary(score_labels, [])
        vote = result["votes"][0]
        assert vote["model"] == "cafe_aesthetic"
        assert vote["source"] == "score_label"
        assert vote["raw_label"] == "not_aesthetic"
        assert vote["quality_tier"] == "low quality"
        assert "raw_score" not in vote

    def test_vote_shape_for_manual_score(self) -> None:
        scores = [{"score": 7.5, "is_edited_manually": True}]
        result = compute_quality_summary([], scores)
        vote = result["votes"][0]
        assert vote["model"] == MANUAL_MODEL_NAME
        assert vote["source"] == "manual_score"
        assert vote["raw_score"] == 7.5
        assert vote["quality_tier"] == "good quality"
        assert "raw_label" not in vote
