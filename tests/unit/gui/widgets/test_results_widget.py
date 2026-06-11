"""ResultsWidget (Frame 5 · Results 読み取り専用トリアージ表示) のユニットテスト。

hand-built の契約 dataclass を直接渡すことで Track A の検出実装に依存しない。
"""

import pytest

from lorairo.domain.quality_tier import QualityTier
from lorairo.gui.widgets.results_widget import ResultsWidget
from lorairo.services.quality_issue_detection_service import (
    BatchTriageSummary,
    ImageTriageResult,
    IssueType,
    RatingView,
    ScorerView,
    TagView,
)

pytestmark = pytest.mark.gui


def _result(image_id: int, issues: list[IssueType]) -> ImageTriageResult:
    return ImageTriageResult(
        image_id=image_id,
        uuid="abcd1234",
        width=1024,
        height=1024,
        tags=[TagView(tag="dog", confidence_score=0.9, model_id=1)],
        caption="a dog on grass",
        caption_word_count=4,
        canonical_rating="PG",
        ratings=[RatingView(model="wd-rater", normalized_rating="PG", confidence_score=0.9)],
        canonical_tier=QualityTier.GOOD_QUALITY,
        scorers=[ScorerView(model="aesthetic_shadow_v2", label="aesthetic", tier=QualityTier.BEST_QUALITY)],
        issues=issues,
    )


def _summary() -> BatchTriageSummary:
    return BatchTriageSummary(
        batch_size=2,
        needs_review_count=1,
        clean_count=1,
        issue_counts={IssueType.EMPTY_TAGS: 1},
        tier_distribution={QualityTier.GOOD_QUALITY: 1},
        no_tier_count=1,
    )


def test_display_renders_rows(qapp):
    widget = ResultsWidget()
    results = [_result(10, [IssueType.EMPTY_TAGS]), _result(11, [])]
    widget.display(_summary(), results)
    # 行が image_id 分描画される
    assert widget.findChild(object, "resultsRow_10") is not None
    assert widget.findChild(object, "resultsRow_11") is not None


def test_review_requested_signal_emitted(qapp, qtbot):
    widget = ResultsWidget()
    widget.display(_summary(), [_result(10, [IssueType.EMPTY_TAGS])])
    button = widget.findChild(object, "resultsReviewButton_10")
    assert button is not None
    with qtbot.waitSignal(widget.review_requested, timeout=1000) as blocker:
        button.click()
    assert blocker.args == [10]


def test_needs_review_sorted_first(qapp):
    widget = ResultsWidget()
    clean = _result(11, [])
    bad = _result(10, [IssueType.EMPTY_TAGS])
    widget.display(_summary(), [clean, bad])
    order = widget._row_order()  # 実装が提供する内部順序アクセサ（list[int]）
    assert order.index(10) < order.index(11)


def test_clear_shows_empty_state(qapp):
    widget = ResultsWidget()
    widget.display(_summary(), [_result(10, [])])
    widget.clear()
    assert widget.findChild(object, "resultsRow_10") is None
    assert widget.findChild(object, "resultsEmptyState") is not None


def test_display_after_display_clears_previous_rows(qapp):
    """再描画は前回行を消してから再構築する。"""
    widget = ResultsWidget()
    widget.display(_summary(), [_result(10, [IssueType.EMPTY_TAGS]), _result(11, [])])
    widget.display(_summary(), [_result(20, [])])
    assert widget.findChild(object, "resultsRow_10") is None
    assert widget.findChild(object, "resultsRow_11") is None
    assert widget.findChild(object, "resultsRow_20") is not None
