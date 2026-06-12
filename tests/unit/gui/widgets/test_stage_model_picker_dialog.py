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


class TestStageModelPickerDialogKeyStatus:
    """Issue #755: ● installed / ● API ready / ○ needs key ステータス表示。"""

    def _texts(self, dialog: StageModelPickerDialog) -> list[str]:
        candidate_list = _candidate_list(dialog)
        return [candidate_list.item(i).text() for i in range(candidate_list.count())]

    def test_local_model_shows_installed_status(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [WD_TAGGER], available_providers=set())
        qtbot.addWidget(dialog)
        texts = self._texts(dialog)
        assert any("wd-v1-4-tagger" in t and "● installed" in t for t in texts)

    def test_api_model_with_key_shows_api_ready(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [GPT4O], available_providers={"openai"})
        qtbot.addWidget(dialog)
        texts = self._texts(dialog)
        assert any("gpt-4o" in t and "● API ready" in t for t in texts)

    def test_api_model_without_key_shows_needs_key_and_not_checkable(self, qtbot):
        dialog = StageModelPickerDialog(
            PipelineStage.TAGS, [GPT4O, NO_PRICE_API], available_providers={"openai"}
        )
        qtbot.addWidget(dialog)
        candidate_list = _candidate_list(dialog)
        texts = self._texts(dialog)
        assert any("claude-x" in t and "○ needs key" in t for t in texts)
        # needs key 行 (anthropic) はチェック不可、API ready 行 (openai) はチェック可
        for i in range(candidate_list.count()):
            item = candidate_list.item(i)
            if "claude-x" in item.text():
                assert not (item.flags() & Qt.ItemFlag.ItemIsUserCheckable)
            else:
                assert item.flags() & Qt.ItemFlag.ItemIsUserCheckable

    def test_default_none_available_providers_treats_all_api_ready(self, qtbot):
        """後方互換: available_providers 未指定では needs key を出さない。"""
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [GPT4O, NO_PRICE_API])
        qtbot.addWidget(dialog)
        texts = self._texts(dialog)
        assert all("○ needs key" not in t for t in texts)

    def test_needs_key_item_click_emits_configure_key_requested(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [NO_PRICE_API], available_providers=set())
        qtbot.addWidget(dialog)
        candidate_list = _candidate_list(dialog)
        item = candidate_list.item(0)
        with qtbot.waitSignal(dialog.configure_key_requested, timeout=1000) as blocker:
            candidate_list.itemClicked.emit(item)
        assert blocker.args == ["anthropic"]

    def test_ready_item_click_does_not_emit_signal(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [GPT4O], available_providers={"openai"})
        qtbot.addWidget(dialog)
        candidate_list = _candidate_list(dialog)
        emitted: list[str] = []
        dialog.configure_key_requested.connect(emitted.append)
        candidate_list.itemClicked.emit(candidate_list.item(0))
        assert emitted == []

    def test_refresh_key_status_resolves_needs_key_to_api_ready(self, qtbot):
        """キー保存後の refresh で ○ needs key → ● API ready に解消され、選択可能になる。"""
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [NO_PRICE_API], available_providers=set())
        qtbot.addWidget(dialog)
        candidate_list = _candidate_list(dialog)
        item = candidate_list.item(0)
        assert "○ needs key" in item.text()

        dialog.refresh_key_status({"anthropic"})

        assert "● API ready" in item.text()
        assert "○ needs key" not in item.text()
        assert item.flags() & Qt.ItemFlag.ItemIsUserCheckable
        item.setCheckState(Qt.CheckState.Checked)
        assert dialog.selected_model_ids() == ["anthropic/claude-x"]

    def test_refresh_key_status_preserves_checked_state(self, qtbot):
        """refresh はチェック済み行の選択状態を維持する。"""
        dialog = StageModelPickerDialog(
            PipelineStage.TAGS, [GPT4O, NO_PRICE_API], available_providers={"openai"}
        )
        qtbot.addWidget(dialog)
        candidate_list = _candidate_list(dialog)
        for i in range(candidate_list.count()):
            if "gpt-4o" in candidate_list.item(i).text():
                candidate_list.item(i).setCheckState(Qt.CheckState.Checked)

        dialog.refresh_key_status({"openai", "anthropic"})

        assert dialog.selected_model_ids() == ["openai/gpt-4o"]
