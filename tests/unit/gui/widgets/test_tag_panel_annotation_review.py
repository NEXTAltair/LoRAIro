"""Saved current annotation reviews decorate the existing editable tag chips."""

from __future__ import annotations

from dataclasses import replace

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QToolButton

from lorairo.gui import theme
from lorairo.gui.widgets.tag_panel_widget import TagPanelWidget
from lorairo.services.annotation_review_service import AnnotationReviewItem, AnnotationReviewResult

pytestmark = pytest.mark.gui


@pytest.fixture
def panel(qtbot):
    widget = TagPanelWidget()
    qtbot.addWidget(widget)
    widget.set_tags(
        [
            {"id": 7, "tag": "dog", "tag_id": 1},
            {"id": 8, "tag": "solo", "tag_id": 2},
        ],
        image_id=5,
        tag_types={"dog": "character", "solo": "general"},
    )
    return widget


@pytest.fixture
def review():
    return AnnotationReviewResult(
        5,
        "fingerprint",
        "clef-flash",
        (
            AnnotationReviewItem("tag_7", "tag", "dog", 0.125, "warning"),
            AnnotationReviewItem("tag_8", "tag", "solo", 0.875, "ok"),
            AnnotationReviewItem("suggestion_cat", "suggestion", "cat", 0.95, "suggestion"),
        ),
        "completed",
    )


def chips(panel):
    return {chip.canonical: chip for chip in panel._tag_chips}


def headers(panel):
    sections = panel._tags_chip_sections_layout
    return [
        sections.itemAt(index).widget().text()
        for index in range(sections.count())
        if isinstance(sections.itemAt(index).widget(), QLabel)
    ]


def test_review_decorates_only_current_existing_warning_tags(panel, review):
    before = chips(panel)["solo"].styleSheet()

    panel.set_annotation_review_result(review)

    dog, solo = chips(panel)["dog"], chips(panel)["solo"]
    assert dog.review_warning
    assert dog.text().endswith(" !")
    assert f"border: 1px solid {theme.WARN}" in dog.styleSheet()
    assert f"border-left: 4px solid {theme.TAG_TYPE_PALETTE['character'][1]}" in dog.styleSheet()
    assert "判定値 0.125" in dog.toolTip()
    assert "tag_7" in dog.toolTip()
    assert "判定対象: dog" in dog.toolTip()
    assert "clef-flash" in dog.toolTip()
    assert not solo.review_warning
    assert "!" not in solo.text()
    assert solo.styleSheet() == before
    assert "判定値 0.875" in solo.toolTip()
    assert "cat" not in chips(panel)


def test_review_group_moves_warning_tags_without_changing_native_type(panel, review):
    panel.set_annotation_review_result(review)
    panel._group_by_type_checkbox.setChecked(True)

    assert headers(panel) == ["要確認（1件）", "一般 (1)"]
    assert [chip.canonical for chip in panel._tag_chips] == ["dog", "solo"]
    assert panel._tag_types == {"dog": "character", "solo": "general"}
    assert chips(panel)["dog"].type_glyph == "C"
    assert "判定値 0.125" in chips(panel)["dog"].toolTip()


def test_single_native_type_can_group_and_flat_toggle_preserves_warning(panel, review):
    panel.apply_tag_metadata({}, {}, {"dog": "general", "solo": "general"})
    assert not panel._group_by_type_checkbox.isEnabled()

    panel.set_annotation_review_result(review)
    assert panel._group_by_type_checkbox.isEnabled()
    panel._group_by_type_checkbox.setChecked(True)
    assert headers(panel) == ["要確認（1件）", "一般 (1)"]

    panel._group_by_type_checkbox.setChecked(False)
    assert headers(panel) == []
    assert chips(panel)["dog"].review_warning
    assert "判定値 0.125" in chips(panel)["dog"].toolTip()


def test_every_tag_warning_has_only_one_group(panel, review):
    every_warning = replace(
        review, items=tuple(replace(item, status="warning", probability=0.1) for item in review.items[:2])
    )
    panel.set_annotation_review_result(every_warning)
    panel._group_by_type_checkbox.setChecked(True)

    assert headers(panel) == ["要確認（2件）"]
    assert len(panel._tag_chips) == 2


@pytest.mark.parametrize("status", ["stale", "failed", "unevaluated"])
def test_inactive_review_clears_warning_frame_group_and_score(panel, review, status):
    panel.set_annotation_review_result(review)
    panel._group_by_type_checkbox.setChecked(True)

    panel.set_annotation_review_result(replace(review, status=status))

    assert all(not chip.review_warning and "!" not in chip.text() for chip in panel._tag_chips)
    assert "要確認（1件）" not in headers(panel)
    assert "判定値" not in chips(panel)["dog"].toolTip()
    assert f"border: 1px solid {theme.WARN}" not in chips(panel)["dog"].styleSheet()


@pytest.mark.parametrize("status", ["partial", "cancelled"])
def test_partial_or_cancelled_review_keeps_only_evaluated_warnings(panel, review, status):
    panel.set_annotation_review_result(
        replace(
            review,
            status=status,
            items=(review.items[0], replace(review.items[1], status="unevaluated", probability=None)),
        )
    )
    panel._group_by_type_checkbox.setChecked(True)

    assert headers(panel) == ["要確認（1件）", "一般 (1)"]
    assert not chips(panel)["solo"].review_warning
    assert "未評価" in chips(panel)["solo"].toolTip()


@pytest.mark.parametrize(
    "item",
    [
        AnnotationReviewItem("tag_700", "tag", "dog", 0.1, "warning"),
        AnnotationReviewItem("tag_7", "tag", "cat", 0.1, "warning"),
        AnnotationReviewItem("tag_7", "caption", "dog", 0.1, "warning"),
        AnnotationReviewItem("tag_7", "tag", "dog", None, "unevaluated"),
        AnnotationReviewItem("tag_7", "tag", "dog", None, "failed"),
        AnnotationReviewItem("tag_7", "tag", "dog", float("nan"), "warning"),
    ],
)
def test_warning_requires_current_source_row_text_and_evaluated_tag(panel, review, item):
    panel.set_annotation_review_result(replace(review, items=(item,)))

    assert not any(chip.review_warning for chip in panel._tag_chips)
    assert "!" not in chips(panel)["dog"].text()


def test_rejected_row_with_same_text_cannot_warn_active_chip(panel, review):
    panel.set_tags(
        [
            {"id": 7, "tag": "dog", "rejected_at": "2026-10-09"},
            {"id": 70, "tag": "dog"},
        ],
        image_id=5,
    )
    panel.set_annotation_review_result(review)

    assert not chips(panel)["dog"].review_warning
    assert "tag_7" not in chips(panel)["dog"].toolTip()


def test_warning_selection_and_native_edit_actions_survive_group_rebuild(panel, review, qtbot):
    panel.set_tag_edit_enabled(True)
    panel.set_annotation_review_result(review)
    chips(panel)["dog"].ctrl_clicked.emit()
    panel._group_by_type_checkbox.setChecked(True)

    dog = chips(panel)["dog"]
    assert dog.selected
    assert f"background-color: {theme.ACCENT}" in dog.styleSheet()
    assert f"border: 1px solid {theme.WARN}" in dog.styleSheet()
    assert dog.text().endswith(" !")
    with qtbot.waitSignal(panel.tag_disable_requested) as emitted:
        dog.clicked.emit()
    assert emitted.args == ["dog"]
    with qtbot.waitSignal(panel.tag_restore_requested) as emitted:
        dog.clicked.emit()
    assert emitted.args == ["dog"]

    button = dog.parentWidget().findChild(QToolButton, "tagRejectButton")
    with qtbot.waitSignal(panel.tag_exclude_requested) as emitted:
        button.click()
    assert emitted.args == ["dog"]
    assert "dog" not in chips(panel)
    assert "要確認（1件）" not in headers(panel)


def test_selected_warning_copies_canonical_text_and_survives_new_result(panel, review):
    panel.set_annotation_review_result(review)
    chips(panel)["dog"].ctrl_clicked.emit()
    panel._group_by_type_checkbox.setChecked(True)

    assert panel.copy_selected_tags_to_clipboard()
    assert QApplication.clipboard().text() == "dog"
    panel.set_annotation_review_result(replace(review, items=()))
    assert chips(panel)["dog"].selected
    assert not chips(panel)["dog"].review_warning


def test_review_details_survive_metadata_and_refinement_rebuild(panel, review):
    panel.set_annotation_review_result(review)
    panel.apply_tag_metadata({1: {"ja": "犬"}}, {}, {"dog": "character", "solo": "general"})
    panel._refresh_tags_for_language("ja")
    panel.apply_refinements({})

    dog = chips(panel)["dog"]
    assert "犬" in dog.text()
    assert dog.review_warning
    assert "判定値 0.125" in dog.toolTip()
    assert dog.toolTip().count("判定値 0.125") == 1
    panel._refresh_tags_for_language("english")
    assert chips(panel)["dog"].toolTip().count("判定値 0.125") == 1


def test_new_result_and_image_reload_replace_warning_and_group_counts(panel, review):
    panel.set_annotation_review_result(review)
    panel._group_by_type_checkbox.setChecked(True)
    panel.set_annotation_review_result(
        replace(
            review, items=tuple(replace(item, status="ok", probability=0.9) for item in review.items[:2])
        )
    )
    assert "要確認（1件）" not in headers(panel)
    assert all(not chip.review_warning for chip in panel._tag_chips)

    panel.set_annotation_review_result(review)
    panel.set_tags([{"id": 7, "tag": "dog"}], image_id=6)
    panel.set_annotation_review_result(review)
    assert not chips(panel)["dog"].review_warning
    assert "判定値" not in chips(panel)["dog"].toolTip()


def test_tag_edit_reload_and_clear_invalidate_review(panel, review):
    panel.set_annotation_review_result(review)
    panel.set_tags([{"id": 7, "tag": "dog"}, {"id": 8, "tag": "cat"}], image_id=5)
    assert not any(chip.review_warning for chip in panel._tag_chips)

    panel.set_annotation_review_result(review)
    panel.set_annotation_review_result(None)
    assert not chips(panel)["dog"].review_warning
    panel.set_annotation_review_result(review)
    panel.clear()
    assert panel._review_warning_tags == set()
    assert panel._review_tooltips == {}
    assert panel._tag_chips == []


def test_duplicate_provenance_rows_share_one_chip_and_keep_each_score(panel, review):
    panel.set_tags([{"id": 7, "tag": "dog"}, {"id": 70, "tag": "dog"}], image_id=5)
    panel.set_annotation_review_result(
        replace(
            review,
            items=(review.items[0], AnnotationReviewItem("tag_70", "tag", "dog", 0.95, "ok")),
        )
    )
    panel._group_by_type_checkbox.setChecked(True)

    assert headers(panel) == ["要確認（1件）"]
    assert len(panel._tag_chips) == 1
    assert "tag_7: 判定値 0.125" in chips(panel)["dog"].toolTip()
    assert "tag_70: 判定値 0.950" in chips(panel)["dog"].toolTip()
