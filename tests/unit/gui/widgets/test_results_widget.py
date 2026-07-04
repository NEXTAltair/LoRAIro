"""ResultsWidget (Frame 5 · Results 読み取り専用トリアージ表示) のユニットテスト。

hand-built の契約 dataclass を直接渡すことで Track A の検出実装に依存しない。
"""

import time

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from lorairo.domain.quality_tier import QualityTier
from lorairo.gui.widgets.results_widget import (
    _MAX_TAG_CHIPS_PER_ROW,
    _VIRTUALIZE_THRESHOLD,
    ResultsWidget,
    _FlowChipRow,
    _RowThumbnail,
)
from lorairo.gui.widgets.tag_cloud_widget import FlowLayout
from lorairo.gui.widgets.tag_panel_widget import SelectableTagChip
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
    tags_row = next((r for r in rows if r._flow.count() > 10), None)
    assert tags_row is not None, "タグ chip 行の FlowChipRow が見つからない"
    assert isinstance(tags_row._flow, FlowLayout)


def test_flow_chip_row_wraps_at_narrow_width(qapp):
    """FlowLayout は狭幅で折り返して必要高さが増える (Issue #1105 項目4)。"""
    widget = ResultsWidget()
    widget.display(_summary(), [_result_with_tags(10, 30)])
    tags_row = next(r for r in widget.findChildren(_FlowChipRow) if r._flow.count() > 10)
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


# ─── #1104: 行内画像プレビュー ─────────────────────────────────────────


def test_row_has_thumbnail_widget(qapp):
    """各行に対象画像のサムネイルウィジェットが配置される (Issue #1104)。"""
    widget = ResultsWidget()
    widget.display(_summary(), [_result(10, [])], image_paths={10: "/tmp/none.png"})
    thumb = widget.findChild(_RowThumbnail, "resultsRowThumb_10")
    assert thumb is not None


def test_thumbnail_no_path_shows_placeholder(qapp):
    """パス未指定のサムネイルはプレースホルダ文言を出し、クラッシュしない。"""
    thumb = _RowThumbnail(10, None)
    thumb._load()
    assert thumb.text() == "no img"
    assert thumb.pixmap().isNull()


def test_thumbnail_missing_file_shows_placeholder(qapp):
    """存在しないパスのサムネイルはプレースホルダ文言を出し、クラッシュしない。"""
    thumb = _RowThumbnail(10, "/does/not/exist.png")
    thumb._load()
    assert thumb.text() == "欠落"
    assert thumb.pixmap().isNull()


def test_thumbnail_loads_valid_image(qapp, tmp_path):
    """有効な画像パスからは QPixmap が読み込まれる。"""
    img_path = tmp_path / "thumb.png"
    source = QPixmap(16, 16)
    source.fill(Qt.GlobalColor.white)
    assert source.save(str(img_path))
    thumb = _RowThumbnail(10, str(img_path))
    thumb._load()
    assert not thumb.pixmap().isNull()


def test_thumbnail_maybe_load_skips_when_not_visible(qapp, tmp_path):
    """未表示 (viewport 外) のサムネイルは maybe_load でデコードしない (Issue #1104 P2)。

    有効なパスでも viewport に見えるまでは同期デコードを走らせず、開いた瞬間に全行を
    デコードして固まるのを防ぐ。
    """
    img_path = tmp_path / "thumb.png"
    source = QPixmap(16, 16)
    source.fill(Qt.GlobalColor.white)
    assert source.save(str(img_path))
    thumb = _RowThumbnail(10, str(img_path))
    # 一度も show されていない → visibleRegion は空 → ロードされない。
    thumb.maybe_load()
    assert not thumb._loaded
    assert thumb.pixmap().isNull()


# ─── #1104: タグ chip の共通部品化 ────────────────────────────────────


def test_tag_chip_uses_selectable_tag_chip(qapp):
    """タグ chip は共通の SelectableTagChip を使う (Issue #1104 / ADR 0083)。"""
    widget = ResultsWidget()
    widget.display(_summary(), [_result(10, [])])
    chips = widget.findChildren(SelectableTagChip)
    assert chips, "SelectableTagChip が生成されていない"
    assert any(c.canonical == "dog" for c in chips)


def test_tag_chip_is_read_only_and_copies_canonical(qapp):
    """結果タブの chip は編集メニューを抑止し、Ctrl+クリックで canonical をコピーする。"""
    widget = ResultsWidget()
    widget.display(_summary(), [_result(10, [])])
    chip = next(c for c in widget.findChildren(SelectableTagChip) if c.canonical == "dog")
    # 編集系右クリックメニューは read-only View では抑止される。
    assert chip.contextMenuPolicy() == Qt.ContextMenuPolicy.PreventContextMenu
    # Ctrl+クリック相当で canonical がクリップボードへ入る。
    QApplication.clipboard().setText("")
    chip.ctrl_clicked.emit()
    assert QApplication.clipboard().text() == "dog"


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


# ─── #1140: 大規模バッチのフリーズ対策 (行チャンク構築 / chip上限 / 集約 degrade) ───


def _result_full(image_id: int, tag_count: int, issues: list[IssueType]) -> ImageTriageResult:
    """多数タグを持つ結果 (フリーズ対策の負荷検証用)。"""
    return ImageTriageResult(
        image_id=image_id,
        uuid=f"uuid{image_id:04d}",
        width=1024,
        height=1024,
        tags=[TagView(tag=f"tag{i}", confidence_score=0.9, model_id=1) for i in range(tag_count)],
        caption="a caption",
        caption_word_count=2,
        canonical_rating="PG",
        ratings=[RatingView(model="wd-rater", normalized_rating="PG", confidence_score=0.9)],
        canonical_tier=QualityTier.GOOD_QUALITY,
        scorers=[ScorerView(model="aesthetic_shadow_v2", label="aesthetic", tier=QualityTier.BEST_QUALITY)],
        issues=issues,
    )


def test_display_100_images_returns_quickly_and_builds_incrementally(qtbot):
    """100画像×50タグでも display() は即座に制御を返し、行はチャンク構築される (#1140)。"""
    widget = ResultsWidget()
    qtbot.addWidget(widget)
    results = [_result_full(i, 50, [IssueType.NO_SCORE]) for i in range(100)]

    start = time.perf_counter()
    widget.display(_summary(), results)
    elapsed = time.perf_counter() - start

    # (a) 呼び出しが一定時間内に UI へ制御を返す (旧実装は GUI スレッドを数分ブロックした)。
    assert elapsed < 2.0, f"display が {elapsed:.2f}s ブロックした"
    # 初回チャンクのみ即時構築 → 先頭行はあるが末尾行はまだ無い。
    assert widget.findChild(object, "resultsRow_0") is not None
    assert widget.findChild(object, "resultsRow_99") is None
    # 残チャンクはイベントループ復帰後に構築される。
    qtbot.waitUntil(lambda: widget.findChild(object, "resultsRow_99") is not None, timeout=5000)


def test_tag_chips_capped_per_row_with_overflow(qapp):
    """1行のタグ chip は上限で切られ、超過は「他 N件」ラベルへ畳まれる (#1140)。"""
    widget = ResultsWidget()
    widget.display(_summary(), [_result_full(10, 50, [IssueType.NO_SCORE])])
    chips = widget.findChildren(SelectableTagChip)
    assert len(chips) == _MAX_TAG_CHIPS_PER_ROW
    overflow = widget.findChild(object, "resultsTagsOverflow")
    assert overflow is not None
    assert str(50 - _MAX_TAG_CHIPS_PER_ROW) in overflow.text()


def test_large_set_degrades_to_aggregate(qapp):
    """閾値以上は per-row を諦め、集約ノーティスのみ表示する (#1140 / wireframes Results@500)。"""
    widget = ResultsWidget()
    results = [_result_full(i, 5, [IssueType.NO_SCORE]) for i in range(_VIRTUALIZE_THRESHOLD)]
    widget.display(_summary(), results)
    # per-row は描画しない (先頭行も無い)。
    assert widget.findChild(object, "resultsRow_0") is None
    # 集約ノーティスを出す。
    assert widget.findChild(object, "resultsScaleNotice") is not None


def test_redisplay_cancels_pending_chunk_build(qtbot):
    """再 display は前回の pending チャンク構築を無効化し、古い行を残さない (#1140)。"""
    widget = ResultsWidget()
    qtbot.addWidget(widget)
    widget.display(_summary(), [_result_full(i, 10, [IssueType.NO_SCORE]) for i in range(100)])
    # 直後に別集合で再描画 (前回の pending は世代トークンで破棄されるはず)。
    widget.display(_summary(), [_result_full(500, 10, [IssueType.NO_SCORE])])
    qtbot.waitUntil(lambda: widget.findChild(object, "resultsRow_500") is not None, timeout=5000)
    # 前回集合の行は残っていない。
    assert widget.findChild(object, "resultsRow_0") is None
    assert widget.findChild(object, "resultsRow_99") is None


def test_degrade_keeps_clean_audit_band(qapp):
    """degrade 域でも clean-audit の一括 accept 導線は残す (Codex #1143 P2-2)。"""
    widget = ResultsWidget()
    # 閾値件数すべて clean (issue 無し・未 reviewed) → degrade だが一括 accept 対象あり。
    results = [_result_full(i, 3, []) for i in range(_VIRTUALIZE_THRESHOLD)]
    widget.display(_summary(), results)
    # 集約ノーティスに加え、clean-audit バンドと「確認して accept」ボタンが残る。
    assert widget.findChild(object, "resultsScaleNotice") is not None
    assert widget.findChild(object, "resultsCleanAuditBand") is not None
    assert widget.findChild(object, "resultsAcceptCleanButton") is not None
