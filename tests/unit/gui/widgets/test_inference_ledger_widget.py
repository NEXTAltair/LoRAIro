"""InferenceLedgerWidget 単体テスト"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel

from lorairo.gui.widgets.inference_ledger_widget import InferenceLedgerWidget
from lorairo.services.pipeline_composition import (
    InferenceLedger,
    LedgerEntry,
    StageModelInfo,
)

pytestmark = [pytest.mark.unit, pytest.mark.gui]

GPT4O = StageModelInfo(
    litellm_model_id="openai/gpt-4o",
    display_name="gpt-4o",
    provider="openai",
    is_api=True,
    capabilities=frozenset({"multimodal", "caption", "tags", "scores"}),
)


def _local_model(name: str, capability: str) -> StageModelInfo:
    return StageModelInfo(
        litellm_model_id=name,
        display_name=name,
        provider=None,
        is_api=False,
        capabilities=frozenset({capability}),
    )


def _sample_ledger() -> InferenceLedger:
    """local 5 + API 1 (multimodal 3 枠) × 9 枚 = 54 推論ジョブ。"""
    entries = (
        LedgerEntry(model=GPT4O, stage_count=3),
        LedgerEntry(model=_local_model("wd-v1-4-tagger", "tags"), stage_count=1),
        LedgerEntry(model=_local_model("blip2-caption", "caption"), stage_count=1),
        LedgerEntry(model=_local_model("aesthetic-scorer", "scores"), stage_count=1),
        LedgerEntry(model=_local_model("cafe-aesthetic", "scores"), stage_count=1),
        LedgerEntry(model=_local_model("nsfw-rater", "ratings"), stage_count=1),
    )
    return InferenceLedger(entries=entries, staged_count=9)


@pytest.fixture
def widget(qtbot):
    w = InferenceLedgerWidget()
    qtbot.addWidget(w)
    return w


class TestInferenceLedgerWidgetFormula:
    def test_formula_shows_unique_staged_and_total(self, widget):
        widget.display(_sample_ledger())
        formula = widget._formula_label.text()
        assert "6 ユニークモデル" in formula
        assert "9 枚" in formula
        assert "54 推論ジョブ" in formula

    def test_formula_shows_local_api_breakdown(self, widget):
        widget.display(_sample_ledger())
        formula = widget._formula_label.text()
        assert "local 5" in formula
        assert "API 1" in formula


class TestInferenceLedgerWidgetChips:
    def test_one_chip_per_unique_model_with_staged_count(self, widget):
        widget.display(_sample_ledger())
        chips = widget.findChildren(QLabel, "ledgerChip")
        assert len(chips) == 6
        chip_texts = [chip.text() for chip in chips]
        assert any("gpt-4o" in text and "×9枚" in text for text in chip_texts)
        assert any("wd-v1-4-tagger" in text and "×9枚" in text for text in chip_texts)

    def test_multimodal_entry_has_frame_to_inference_badge(self, widget):
        widget.display(_sample_ledger())
        badges = widget.findChildren(QLabel, "ledgerMultiBadge")
        assert len(badges) == 1
        assert badges[0].text() == "3枠 → 1推論"

    def test_display_twice_does_not_duplicate_chips(self, widget):
        widget.display(_sample_ledger())
        widget.display(_sample_ledger())
        assert len(widget.findChildren(QLabel, "ledgerChip")) == 6
        assert len(widget.findChildren(QLabel, "ledgerMultiBadge")) == 1


class TestInferenceLedgerWidgetPlaceholder:
    def test_empty_entries_shows_placeholder(self, widget):
        widget.display(InferenceLedger(entries=(), staged_count=9))
        assert widget._placeholder_label.text() == "モデル未選択"
        assert widget._formula_label.text() == ""
        assert widget.findChildren(QLabel, "ledgerChip") == []

    def test_zero_staged_count_shows_placeholder(self, widget):
        ledger = InferenceLedger(entries=_sample_ledger().entries, staged_count=0)
        widget.display(ledger)
        assert widget._placeholder_label.text() == "モデル未選択"
        assert widget.findChildren(QLabel, "ledgerChip") == []

    def test_clear_resets_to_placeholder(self, widget):
        widget.display(_sample_ledger())
        widget.clear()
        assert widget._placeholder_label.text() == "モデル未選択"
        assert widget._formula_label.text() == ""
        assert widget.findChildren(QLabel, "ledgerChip") == []
        assert widget.findChildren(QLabel, "ledgerMultiBadge") == []
