"""ResultsWidget (Frame 5 · Results 読み取り専用トリアージ表示) のユニットテスト。

hand-built の契約 dataclass を直接渡すことで Track A の検出実装に依存しない。
"""

import pytest

from lorairo.domain.quality_tier import QualityTier
from lorairo.gui.widgets.results_widget import ResultsWidget, _FlowChipRow
from lorairo.gui.widgets.tag_cloud_widget import FlowLayout
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


def test_review_button_removed(qapp):
    """▸ レビューボタンは撤去済み (Issue #1106): 行ヘッダに存在しない。"""
    widget = ResultsWidget()
    widget.display(_summary(), [_result(10, [IssueType.EMPTY_TAGS])])
    assert widget.findChild(object, "resultsReviewButton_10") is None


def _result_with_tags(image_id: int, tag_count: int) -> ImageTriageResult:
    """多数タグを持つ結果 (折り返し検証用)。"""
    return ImageTriageResult(
        image_id=image_id,
        uuid="abcd1234",
        width=1024,
        height=1024,
        tags=[TagView(tag=f"tag{i}", confidence_score=0.9, model_id=1) for i in range(tag_count)],
        caption="a dog on grass",
        caption_word_count=4,
        canonical_rating="PG",
        ratings=[RatingView(model="wd-rater", normalized_rating="PG", confidence_score=0.9)],
        canonical_tier=QualityTier.GOOD_QUALITY,
        scorers=[ScorerView(model="aesthetic_shadow_v2", label="aesthetic", tier=QualityTier.BEST_QUALITY)],
        issues=[],
    )


def test_tags_line_uses_flow_layout(qapp):
    """タグ chip 行は FlowLayout を採用している (Issue #1105 項目4)。"""
    widget = ResultsWidget()
    widget.display(_summary(), [_result_with_tags(10, 30)])
    rows = widget.findChildren(_FlowChipRow)
    # サマリ band・タグ行など複数の FlowChipRow が生成される。
    assert rows, "FlowChipRow が生成されていない"
    tags_row = next((r for r in rows if r._flow.count() > 25), None)
    assert tags_row is not None, "タグ chip 行の FlowChipRow が見つからない"
    assert isinstance(tags_row._flow, FlowLayout)


def test_flow_chip_row_wraps_at_narrow_width(qapp):
    """FlowLayout は狭幅で折り返して必要高さが増える (Issue #1105 項目4)。"""
    widget = ResultsWidget()
    widget.display(_summary(), [_result_with_tags(10, 30)])
    tags_row = next(r for r in widget.findChildren(_FlowChipRow) if r._flow.count() > 25)
    narrow = tags_row._flow.heightForWidth(120)
    wide = tags_row._flow.heightForWidth(4000)
    # 狭幅では複数行に折り返すため wide より高くなる。
    assert narrow > wide


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


def _reviewed_result(image_id: int, issues: list[IssueType], reviewed: bool) -> ImageTriageResult:
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
        reviewed=reviewed,
    )


def test_accept_button_emitted_for_unreviewed(qapp, qtbot):
    widget = ResultsWidget()
    widget.display(_summary(), [_reviewed_result(10, [IssueType.EMPTY_TAGS], reviewed=False)])
    button = widget.findChild(object, "resultsAcceptButton_10")
    assert button is not None
    with qtbot.waitSignal(widget.accept_requested, timeout=1000) as blocker:
        button.click()
    assert blocker.args == [10]


def test_reviewed_row_shows_undo_not_accept(qapp):
    widget = ResultsWidget()
    widget.display(_summary(), [_reviewed_result(10, [IssueType.EMPTY_TAGS], reviewed=True)])
    assert widget.findChild(object, "resultsUnacceptButton_10") is not None
    assert widget.findChild(object, "resultsAcceptButton_10") is None


def test_unaccept_button_emits_signal(qapp, qtbot):
    widget = ResultsWidget()
    widget.display(_summary(), [_reviewed_result(10, [IssueType.EMPTY_TAGS], reviewed=True)])
    button = widget.findChild(object, "resultsUnacceptButton_10")
    with qtbot.waitSignal(widget.unaccept_requested, timeout=1000) as blocker:
        button.click()
    assert blocker.args == [10]


def test_bulk_accept_clean_emits_clean_ids(qapp, qtbot):
    widget = ResultsWidget()
    # clean かつ未 reviewed の #11 のみ一括対象、#10 は issue 有で対象外。
    results = [
        _reviewed_result(10, [IssueType.EMPTY_TAGS], reviewed=False),
        _reviewed_result(11, [], reviewed=False),
    ]
    widget.display(_summary(), results)
    button = widget.findChild(object, "resultsAcceptCleanButton")
    assert button is not None
    with qtbot.waitSignal(widget.accept_clean_requested, timeout=1000) as blocker:
        button.click()
    assert blocker.args == [[11]]


def test_no_bulk_footer_when_no_clean_unreviewed(qapp):
    widget = ResultsWidget()
    # 全て issue 有 → 一括対象なし → フッタ無し。
    widget.display(_summary(), [_reviewed_result(10, [IssueType.EMPTY_TAGS], reviewed=False)])
    assert widget.findChild(object, "resultsAcceptCleanButton") is None


def test_clean_audit_band_shows_resample_and_accept(qapp):
    """CLEAN 監査バンドに引き直しボタンと accept ボタンが出る。"""
    widget = ResultsWidget()
    # #11 が clean 未 accept、#10 は issue 有。
    results = [_result(10, [IssueType.EMPTY_TAGS]), _result(11, [])]
    widget.display(_summary(), results)
    assert widget.findChild(object, "resultsCleanAuditBand") is not None
    assert widget.findChild(object, "resultsResampleButton") is not None
    assert widget.findChild(object, "resultsAcceptCleanButton") is not None


def test_resample_keeps_clean_audit_band(qapp):
    """引き直し後もバンド・accept ボタンが残る (再描画されても消えない)。"""
    widget = ResultsWidget()
    results = [_result(11, []), _result(12, [])]
    widget.display(_summary(), results)
    button = widget.findChild(object, "resultsResampleButton")
    assert button is not None
    button.click()
    assert widget.findChild(object, "resultsCleanAuditBand") is not None
    assert widget.findChild(object, "resultsAcceptCleanButton") is not None


def test_clean_audit_accept_emits_all_clean_ids(qapp, qtbot):
    """accept は抽出枚数に関係なく clean 全件 id を emit する。"""
    results = [_result(11, []), _result(12, [])]
    widget = ResultsWidget()
    widget.display(_summary(), results)
    button = widget.findChild(object, "resultsAcceptCleanButton")
    with qtbot.waitSignal(widget.accept_clean_requested, timeout=1000) as blocker:
        button.click()
    assert sorted(blocker.args[0]) == [11, 12]


def test_no_clean_audit_band_when_no_clean(qapp):
    """clean が無ければバンドも accept ボタンも出ない。"""
    widget = ResultsWidget()
    widget.display(_summary(), [_result(10, [IssueType.EMPTY_TAGS])])
    assert widget.findChild(object, "resultsCleanAuditBand") is None
    assert widget.findChild(object, "resultsAcceptCleanButton") is None
