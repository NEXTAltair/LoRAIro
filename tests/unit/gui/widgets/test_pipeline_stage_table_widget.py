"""PipelineStageTableWidget 単体テスト"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel, QWidget

from lorairo.gui.widgets.pipeline_stage_table_widget import PipelineStageTableWidget
from lorairo.services.pipeline_composition import (
    DerivedChip,
    PipelineStage,
    StageModelInfo,
    StageRow,
)

pytestmark = [pytest.mark.unit, pytest.mark.gui]

GPT4O = StageModelInfo(
    litellm_model_id="openai/gpt-4o",
    display_name="gpt-4o",
    provider="openai",
    is_api=True,
    capabilities=frozenset({"multimodal", "caption", "tags", "scores"}),
)
WD_TAGGER = StageModelInfo(
    litellm_model_id="wd-v1-4-tagger",
    display_name="wd-v1-4-tagger",
    provider=None,
    is_api=False,
    capabilities=frozenset({"tags"}),
)


@pytest.fixture
def widget(qtbot):
    w = PipelineStageTableWidget()
    qtbot.addWidget(w)
    return w


def _sample_rows() -> list[StageRow]:
    """CAPTION に multimodal 明示割当、TAGS に local 明示 + 派生、の典型構成。"""
    return [
        StageRow(
            stage=PipelineStage.TAGS,
            primary_models=(WD_TAGGER,),
            derived_chips=(DerivedChip(model=GPT4O, origin_stage=PipelineStage.CAPTION),),
        ),
        StageRow(
            stage=PipelineStage.CAPTION,
            primary_models=(GPT4O,),
            derived_chips=(),
        ),
        StageRow(
            stage=PipelineStage.SCORE,
            primary_models=(),
            derived_chips=(DerivedChip(model=GPT4O, origin_stage=PipelineStage.CAPTION),),
        ),
        StageRow(stage=PipelineStage.RATING, primary_models=(), derived_chips=()),
    ]


def _label_texts(widget: QWidget, object_name: str) -> list[str]:
    return [label.text() for label in widget.findChildren(QLabel, object_name)]


class TestPipelineStageTableWidgetStructure:
    def test_empty_display_renders_four_stage_rows_and_legend(self, widget):
        widget.display([])
        for stage in ("TAGS", "CAPTION", "SCORE", "RATING"):
            assert len(widget.findChildren(QWidget, f"stageRow_{stage}")) == 1
        legends = widget.findChildren(QLabel, "pipelineLegendLabel")
        assert len(legends) == 1
        assert "↝" in legends[0].text()
        assert "MULTI" in legends[0].text()

    def test_clear_renders_four_empty_rows(self, widget):
        widget.display(_sample_rows())
        widget.clear()
        for stage in ("TAGS", "CAPTION", "SCORE", "RATING"):
            assert len(widget.findChildren(QWidget, f"stageRow_{stage}")) == 1
        assert widget.findChildren(QLabel, "primaryChip") == []
        assert widget.findChildren(QLabel, "derivedChip") == []


class TestPipelineStageTableWidgetChips:
    def test_primary_chip_shows_display_name(self, widget):
        widget.display(_sample_rows())
        primary_texts = _label_texts(widget, "primaryChip")
        assert any("wd-v1-4-tagger" in text for text in primary_texts)

    def test_derived_chip_shows_arrow_and_origin_stage(self, widget):
        widget.display(_sample_rows())
        derived_texts = _label_texts(widget, "derivedChip")
        assert len(derived_texts) == 2
        assert all(text.startswith("↝") for text in derived_texts)
        assert all("from CAPTION" in text for text in derived_texts)
        assert all("gpt-4o" in text for text in derived_texts)

    def test_multimodal_primary_chip_has_multi_badge(self, widget):
        widget.display(_sample_rows())
        primary_texts = _label_texts(widget, "primaryChip")
        multi_texts = [text for text in primary_texts if "MULTI" in text]
        assert len(multi_texts) == 1
        assert "gpt-4o" in multi_texts[0]
        # CAPTION 割当の multimodal は TAGS / SCORE へファンアウトする注記を持つ
        assert "派生" in multi_texts[0]
        assert "T" in multi_texts[0]
        assert "S" in multi_texts[0]

    def test_count_label_shows_primary_and_derived_counts(self, widget):
        widget.display(_sample_rows())
        assert _label_texts(widget, "stageCount_TAGS") == ["1 + ↝1"]
        assert _label_texts(widget, "stageCount_CAPTION") == ["1"]
        assert _label_texts(widget, "stageCount_SCORE") == ["0 + ↝1"]
        assert _label_texts(widget, "stageCount_RATING") == ["0"]


class TestPipelineStageTableWidgetRatingNote:
    def test_rating_row_has_no_derived_note(self, widget):
        widget.display(_sample_rows())
        notes = widget.findChildren(QLabel, "ratingNoDerivedNote")
        assert len(notes) == 1
        assert "multimodal 派生なし" in notes[0].text()
        assert notes[0].toolTip() != ""

    def test_derived_chip_has_readonly_tooltip(self, widget):
        widget.display(_sample_rows())
        derived = widget.findChildren(QLabel, "derivedChip")
        assert all("Results" in chip.toolTip() for chip in derived)


class TestPipelineStageTableWidgetRedisplay:
    def test_display_twice_does_not_duplicate_chips(self, widget):
        widget.display(_sample_rows())
        first_primary = len(widget.findChildren(QLabel, "primaryChip"))
        first_derived = len(widget.findChildren(QLabel, "derivedChip"))
        widget.display(_sample_rows())
        assert len(widget.findChildren(QLabel, "primaryChip")) == first_primary
        assert len(widget.findChildren(QLabel, "derivedChip")) == first_derived
        for stage in ("TAGS", "CAPTION", "SCORE", "RATING"):
            assert len(widget.findChildren(QWidget, f"stageRow_{stage}")) == 1
