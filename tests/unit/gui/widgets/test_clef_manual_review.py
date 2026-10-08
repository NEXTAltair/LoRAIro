"""Row-specific highlights, caption correction, and separate proposal adoption."""

from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton

from lorairo.gui.widgets.annotation_data_display_widget import AnnotationData, AnnotationDataDisplayWidget
from lorairo.gui.widgets.annotation_review_widget import AnnotationReviewWidget
from lorairo.gui.widgets.caption_review_panel import CaptionReviewPanel
from lorairo.services.annotation_review_service import AnnotationReviewItem, AnnotationReviewResult
from lorairo.services.annotation_review_store import StoredReviewResult

pytestmark = pytest.mark.gui


def test_caption_panel_highlights_and_edits_the_source_row(qtbot):
    panel = CaptionReviewPanel()
    qtbot.addWidget(panel)
    panel.set_editable(True)
    panel.set_rows([{"id": 1, "caption": "A dog."}, {"id": 2, "caption": "A cat."}])
    panel.set_warning_ids({1})
    panel.show()
    button = panel.findChild(QPushButton, "editCaption1")
    with qtbot.waitSignal(panel.edit_requested) as emitted:
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    assert emitted.args == [1, "A dog."]
    assert "要確認" in panel.findChild(QLabel, "captionRow1").text()


def test_tag_warning_survives_refinement_and_translation_rebuild(qtbot):
    display = AnnotationDataDisplayWidget()
    qtbot.addWidget(display)
    display.update_data(
        AnnotationData(
            tags=[{"id": 7, "tag": "dog", "tag_id": None}], captions=[{"id": 3, "caption": "A dog."}]
        ),
        image_id=5,
    )
    display.set_review_warnings({7}, {3})
    chip = display._tag_chips[0]
    assert chip.review_warning
    assert "⚠" in chip.text()
    display.apply_refinements([])
    display._tag_panel._refresh_tags_for_language("english")
    assert display._tag_chips[0].review_warning
    assert "Clef" in display._tag_chips[0].toolTip()
    display.set_review_warnings(set(), set())
    assert not display._tag_chips[0].review_warning


def test_addition_proposals_are_separate_and_require_manual_adoption(qtbot):
    widget = AnnotationReviewWidget()
    qtbot.addWidget(widget)
    review = AnnotationReviewResult(
        5,
        "fp",
        "clef-flash",
        (
            AnnotationReviewItem("tag_7", "tag", "dog", 0.1, "warning"),
            AnnotationReviewItem("suggestion_cat", "suggestion", "cat", 0.9, "suggestion"),
        ),
        "completed",
    )
    saved = StoredReviewResult(review, 0.2, datetime.now(UTC))
    widget._image_id = 5
    widget._saved = saved
    adoption = Mock()
    adoption.adopt.return_value = True
    widget.set_adoption_service(adoption)
    widget._display_result(review)
    assert widget.results_table.rowCount() == 1
    assert widget.suggestions_table.rowCount() == 1
    assert "要確認 1 件" in widget.status_label.text()
    adoption.adopt.assert_not_called()
    with qtbot.waitSignal(widget.annotations_changed) as emitted:
        qtbot.mouseClick(widget.suggestions_table.cellWidget(0, 3), Qt.MouseButton.LeftButton)
    assert emitted.args == [5]
    adoption.adopt.assert_called_once_with(5, "suggestion_cat", saved.checked_at)
    widget._display_result(AnnotationReviewResult(5, "fp", "clef-flash", review.items, "stale"))
    assert widget.suggestions_table.isHidden()
    assert widget.results_table.rowCount() == 0
