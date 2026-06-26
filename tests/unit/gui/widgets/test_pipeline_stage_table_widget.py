"""PipelineStageTableWidget 単体テスト"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel, QToolButton, QWidget

from lorairo.gui.widgets.ds_card import DsCard
from lorairo.gui.widgets.pipeline_stage_table_widget import (
    _BUILTIN_PRESETS,
    _DEFAULT_PRESET_ID,
    PipelineStageTableWidget,
)
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


class TestPipelineStageTableWidgetOperations:
    """Phase 6b: 「+ 追加」/ primary × の操作 Signal を検証する。"""

    def test_add_button_click_emits_stage_value(self, widget, qtbot):
        widget.display(_sample_rows())
        tags_row = widget.findChildren(QWidget, "stageRow_TAGS")[0]
        add_buttons = tags_row.findChildren(QToolButton, "stageAddModelButton")
        assert len(add_buttons) == 1
        with qtbot.waitSignal(widget.add_model_requested, timeout=1000) as blocker:
            add_buttons[0].click()
        assert blocker.args == ["tags"]

    def test_every_stage_row_has_add_button(self, widget):
        widget.display(_sample_rows())
        for stage in ("TAGS", "CAPTION", "SCORE", "RATING"):
            row = widget.findChildren(QWidget, f"stageRow_{stage}")[0]
            assert len(row.findChildren(QToolButton, "stageAddModelButton")) == 1

    def test_primary_chip_remove_click_emits_stage_and_model_id(self, widget, qtbot):
        widget.display(_sample_rows())
        tags_row = widget.findChildren(QWidget, "stageRow_TAGS")[0]
        remove_buttons = tags_row.findChildren(QToolButton, "primaryChipRemoveButton")
        assert len(remove_buttons) == 1
        with qtbot.waitSignal(widget.remove_model_requested, timeout=1000) as blocker:
            remove_buttons[0].click()
        assert blocker.args == ["tags", "wd-v1-4-tagger"]

    def test_remove_button_tooltip_warns_all_stages_removal(self, widget):
        widget.display(_sample_rows())
        remove_buttons = widget.findChildren(QToolButton, "primaryChipRemoveButton")
        assert remove_buttons != []
        assert all("全ステージ" in button.toolTip() for button in remove_buttons)

    def test_derived_chip_has_no_remove_button(self, widget):
        widget.display(_sample_rows())
        # SCORE 行は派生チップのみ → remove ボタンは存在しない
        score_row = widget.findChildren(QWidget, "stageRow_SCORE")[0]
        assert score_row.findChildren(QToolButton, "primaryChipRemoveButton") == []
        # remove ボタン総数 = primary チップ数 (派生には付かない)
        all_removes = widget.findChildren(QToolButton, "primaryChipRemoveButton")
        all_primaries = widget.findChildren(QLabel, "primaryChip")
        assert len(all_removes) == len(all_primaries) == 2

    def test_derived_chip_keeps_readonly_tooltip(self, widget):
        widget.display(_sample_rows())
        derived = widget.findChildren(QLabel, "derivedChip")
        assert derived != []
        assert all("外せません" in chip.toolTip() for chip in derived)


class TestPipelineStageTableWidgetPresetRow:
    """Issue #838: パイプライン上部の preset chip 行を検証する。"""

    def test_preset_row_renders_all_builtin_presets(self, widget):
        chips = widget.findChildren(QToolButton, "presetChip")
        assert len(chips) == len(_BUILTIN_PRESETS)
        texts = [chip.text() for chip in chips]
        assert texts == [f"{p.label} {p.model_count}" for p in _BUILTIN_PRESETS]

    def test_preset_row_has_save_button(self, widget):
        save_buttons = widget.findChildren(QToolButton, "savePresetButton")
        assert len(save_buttons) == 1
        assert "保存" in save_buttons[0].text()

    def test_default_preset_is_active_on_init(self, widget):
        chips = {
            chip.text().rsplit(" ", 1)[0]: chip for chip in widget.findChildren(QToolButton, "presetChip")
        }
        default_label = next(p.label for p in _BUILTIN_PRESETS if p.preset_id == _DEFAULT_PRESET_ID)
        assert chips[default_label].isChecked()
        # 他のプリセットは非アクティブ
        for label, chip in chips.items():
            assert chip.isChecked() == (label == default_label)

    def test_preset_click_emits_preset_id(self, widget, qtbot):
        chips = widget.findChildren(QToolButton, "presetChip")
        target = next(c for c in chips if c.text().startswith("Tags only"))
        with qtbot.waitSignal(widget.preset_selected, timeout=1000) as blocker:
            target.click()
        assert blocker.args == ["tags_only"]

    def test_preset_click_updates_active_highlight(self, widget):
        chips = {c.text().split(" ")[0]: c for c in widget.findChildren(QToolButton, "presetChip")}
        chips["Tags"].click()  # "Tags only N"
        assert chips["Tags"].isChecked()
        assert not chips["Default"].isChecked()

    def test_set_active_preset_does_not_emit(self, widget, qtbot):
        with qtbot.assertNotEmitted(widget.preset_selected):
            widget.set_active_preset("score_rate")
        chips = {c.text().split(" ")[0]: c for c in widget.findChildren(QToolButton, "presetChip")}
        assert chips["Score·rate"].isChecked()

    def test_set_active_preset_unknown_clears_all(self, widget):
        widget.set_active_preset("nonexistent")
        chips = widget.findChildren(QToolButton, "presetChip")
        assert all(not chip.isChecked() for chip in chips)

    def test_save_button_click_emits_save_request(self, widget, qtbot):
        save_button = widget.findChildren(QToolButton, "savePresetButton")[0]
        with qtbot.waitSignal(widget.save_preset_requested, timeout=1000):
            save_button.click()


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


class TestPipelineStageTableWidgetDsCardStructure:
    """#846/#847: DsCard 化による視覚構造テスト。"""

    def test_stage_rows_are_wrapped_in_ds_card(self, widget):
        """各ステージ行は DsCard で包まれている (#846)。"""
        widget.display(_sample_rows())
        for stage in ("TAGS", "CAPTION", "SCORE", "RATING"):
            rows = widget.findChildren(QWidget, f"stageRow_{stage}")
            assert len(rows) == 1
            assert isinstance(rows[0], DsCard), f"stageRow_{stage} は DsCard であるべき"

    def test_stage_rows_are_ds_card_after_clear(self, widget):
        """clear() 後も空ステージ行は DsCard で包まれている (#846)。"""
        widget.clear()
        for stage in ("TAGS", "CAPTION", "SCORE", "RATING"):
            rows = widget.findChildren(QWidget, f"stageRow_{stage}")
            assert len(rows) == 1
            assert isinstance(rows[0], DsCard)

    def test_preset_row_is_wrapped_in_ds_card(self, widget):
        """プリセット chip 行は DsCard で包まれている (#847)。"""
        preset_cards = widget.findChildren(DsCard, "presetRow")
        assert len(preset_cards) == 1

    def test_legend_is_inside_preset_card(self, widget):
        """凡例ラベルはプリセット DsCard 内に収まっている (#847)。"""
        preset_card = widget.findChildren(DsCard, "presetRow")[0]
        legends = preset_card.findChildren(QLabel, "pipelineLegendLabel")
        assert len(legends) == 1
        assert "↝" in legends[0].text()
        assert "MULTI" in legends[0].text()

    def test_preset_chips_are_inside_preset_card(self, widget):
        """preset chip ボタンはプリセット DsCard 内に収まっている (#847)。"""
        preset_card = widget.findChildren(DsCard, "presetRow")[0]
        chips = preset_card.findChildren(QToolButton, "presetChip")
        assert len(chips) == len(_BUILTIN_PRESETS)

    def test_stage_card_contains_count_and_chips(self, widget):
        """ステージ DsCard 内に count ラベルとチップが収まっている (#846)。"""
        widget.display(_sample_rows())
        tags_card = widget.findChildren(DsCard, "stageRow_TAGS")[0]
        # count ラベル
        assert len(tags_card.findChildren(QLabel, "stageCount_TAGS")) == 1
        # primary chip
        assert len(tags_card.findChildren(QLabel, "primaryChip")) >= 1
        # derived chip
        assert len(tags_card.findChildren(QLabel, "derivedChip")) >= 1

    def test_stage_card_contains_add_button(self, widget):
        """ステージ DsCard 内に「+ 追加」ボタンが収まっている (#846)。"""
        widget.display(_sample_rows())
        for stage in ("TAGS", "CAPTION", "SCORE", "RATING"):
            card = widget.findChildren(DsCard, f"stageRow_{stage}")[0]
            assert len(card.findChildren(QToolButton, "stageAddModelButton")) == 1
