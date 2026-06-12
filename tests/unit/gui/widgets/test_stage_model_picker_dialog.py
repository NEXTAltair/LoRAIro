"""StageModelPickerDialog 単体テスト (Phase 6b)"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialogButtonBox, QLabel, QListWidget

from lorairo.gui.widgets.stage_model_picker_dialog import StageModelPickerDialog
from lorairo.services.pipeline_composition import PipelineStage, StageModelInfo

pytestmark = [pytest.mark.unit, pytest.mark.gui]

GPT4O = StageModelInfo(
    litellm_model_id="openai/gpt-4o",
    display_name="gpt-4o",
    provider="openai",
    is_api=True,
    capabilities=frozenset({"multimodal", "caption", "tags", "scores"}),
    input_cost_per_token=2.5e-06,
    output_cost_per_token=1.0e-05,
)
NO_PRICE_API = StageModelInfo(
    litellm_model_id="anthropic/claude-x",
    display_name="claude-x",
    provider="anthropic",
    is_api=True,
    capabilities=frozenset({"tags"}),
)
WD_TAGGER = StageModelInfo(
    litellm_model_id="wd-v1-4-tagger",
    display_name="wd-v1-4-tagger",
    provider=None,
    is_api=False,
    capabilities=frozenset({"tags"}),
)


def _candidate_list(dialog: StageModelPickerDialog) -> QListWidget:
    lists = dialog.findChildren(QListWidget, "stageModelCandidateList")
    assert len(lists) == 1
    return lists[0]


def _ok_button(dialog: StageModelPickerDialog):
    boxes = dialog.findChildren(QDialogButtonBox)
    assert len(boxes) == 1
    return boxes[0].button(QDialogButtonBox.StandardButton.Ok)


class TestStageModelPickerDialogRendering:
    def test_title_uses_uppercase_stage_value(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [GPT4O, WD_TAGGER])
        qtbot.addWidget(dialog)
        assert dialog.windowTitle() == "TAGS のモデルを選択"

    def test_candidates_rendered_with_provider_origin(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [GPT4O, WD_TAGGER])
        qtbot.addWidget(dialog)
        candidate_list = _candidate_list(dialog)
        assert candidate_list.count() == 2
        texts = [candidate_list.item(i).text() for i in range(candidate_list.count())]
        assert any("gpt-4o" in text and "API: openai" in text for text in texts)
        assert any("wd-v1-4-tagger" in text and "ローカル" in text for text in texts)

    def test_multimodal_row_shows_fanout_note(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [GPT4O, WD_TAGGER])
        qtbot.addWidget(dialog)
        candidate_list = _candidate_list(dialog)
        texts = [candidate_list.item(i).text() for i in range(candidate_list.count())]
        multimodal_texts = [text for text in texts if "gpt-4o" in text]
        assert len(multimodal_texts) == 1
        assert "1推論で T C S" in multimodal_texts[0]
        assert "preflight" in multimodal_texts[0]
        local_texts = [text for text in texts if "wd-v1-4-tagger" in text]
        assert "1推論で" not in local_texts[0]

    def test_candidate_cards_show_per_image_cost(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [GPT4O, WD_TAGGER, NO_PRICE_API])
        qtbot.addWidget(dialog)
        candidate_list = _candidate_list(dialog)
        texts = [candidate_list.item(i).text() for i in range(candidate_list.count())]
        # GPT4O per-image = 1500*2.5e-6 + 400*1e-5 = 0.00775 → $0.0077/img (.4f 丸め)
        assert any("gpt-4o" in t and "$0.0077/img" in t for t in texts)
        # ローカルは無料表記
        assert any("wd-v1-4-tagger" in t and "ローカル（無料）" in t for t in texts)
        # pricing 未取得の API モデルは "—"
        assert any("claude-x" in t and "—" in t for t in texts)

    def test_items_are_user_checkable_and_initially_unchecked(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [GPT4O, WD_TAGGER])
        qtbot.addWidget(dialog)
        candidate_list = _candidate_list(dialog)
        for i in range(candidate_list.count()):
            item = candidate_list.item(i)
            assert item.flags() & Qt.ItemFlag.ItemIsUserCheckable
            assert item.checkState() == Qt.CheckState.Unchecked


class TestStageModelPickerDialogSelection:
    def test_no_check_returns_empty(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [GPT4O, WD_TAGGER])
        qtbot.addWidget(dialog)
        assert dialog.selected_model_ids() == []

    def test_checked_items_return_litellm_model_ids(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [GPT4O, WD_TAGGER])
        qtbot.addWidget(dialog)
        candidate_list = _candidate_list(dialog)
        candidate_list.item(0).setCheckState(Qt.CheckState.Checked)
        candidate_list.item(1).setCheckState(Qt.CheckState.Checked)
        assert dialog.selected_model_ids() == ["openai/gpt-4o", "wd-v1-4-tagger"]

    def test_partial_check_returns_only_checked(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [GPT4O, WD_TAGGER])
        qtbot.addWidget(dialog)
        candidate_list = _candidate_list(dialog)
        candidate_list.item(1).setCheckState(Qt.CheckState.Checked)
        assert dialog.selected_model_ids() == ["wd-v1-4-tagger"]


class TestStageModelPickerDialogEmptyCandidates:
    def test_empty_candidates_shows_label_and_disables_ok(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.RATING, [])
        qtbot.addWidget(dialog)
        labels = dialog.findChildren(QLabel, "emptyCandidatesLabel")
        assert len(labels) == 1
        assert "追加できる未選択モデルがありません" in labels[0].text()
        ok_button = _ok_button(dialog)
        assert ok_button is not None
        assert not ok_button.isEnabled()
        assert dialog.selected_model_ids() == []
