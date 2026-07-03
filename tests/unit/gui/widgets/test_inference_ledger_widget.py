"""InferenceLedgerWidget 単体テスト (Card化 #848)。

DsCard + DsSummaryStat グリッド化後のテスト。
推論ジョブ合計・コスト・ブレークダウンは各 DsSummaryStat の
_value_widget / _sub_widget で検証する。
"""

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
    input_cost_per_token=2.5e-06,
    output_cost_per_token=1.0e-05,
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


class TestInferenceLedgerWidgetStats:
    """DsSummaryStat グリッドの値検証。"""

    def test_stats_show_unique_staged_and_total(self, widget):
        widget.display(_sample_ledger())
        # ユニークモデル数 / staged / total をそれぞれ stat value で確認
        assert widget._stat_unique_models._value_widget.text() == "6"
        assert widget._stat_staged._value_widget.text() == "9"
        assert widget._stat_total_jobs._value_widget.text() == "54"

    def test_stats_show_local_api_breakdown_in_sub(self, widget):
        widget.display(_sample_ledger())
        # local/API 内訳は total_jobs stat の sub に表示される
        sub_text = widget._stat_total_jobs._sub_widget.text()
        assert "local 5" in sub_text
        assert "API 1" in sub_text

    def test_stats_visible_after_display(self, widget):
        widget.display(_sample_ledger())
        assert not widget._stats_widget.isHidden()

    def test_stats_hidden_when_placeholder(self, widget):
        widget.display(InferenceLedger(entries=(), staged_count=9))
        assert widget._stats_widget.isHidden()


class TestInferenceLedgerWidgetChips:
    def test_one_chip_per_unique_model_with_staged_count(self, widget):
        widget.display(_sample_ledger())
        chips = widget.findChildren(QLabel, "ledgerChip")
        assert len(chips) == 6
        chip_texts = [chip.text() for chip in chips]
        assert any("gpt-4o" in text and "×9枚" in text for text in chip_texts)
        assert any("wd-v1-4-tagger" in text and "×9枚" in text for text in chip_texts)

    def test_one_route_badge_per_entry_with_local_api_text(self, widget):
        # #884 Phase 4a: 各エントリに local/api route バッジを付与する。
        widget.display(_sample_ledger())
        badges = widget.findChildren(QLabel, "ledgerRouteBadge")
        assert len(badges) == 6
        texts = [b.text() for b in badges]
        assert texts.count("api") == 1  # GPT4O のみ API
        assert texts.count("local") == 5

    def test_route_badge_local_only_ledger(self, widget):
        ledger = InferenceLedger(
            entries=(LedgerEntry(model=_local_model("wd-tagger", "tags"), stage_count=1),),
            staged_count=3,
        )
        widget.display(ledger)
        badges = widget.findChildren(QLabel, "ledgerRouteBadge")
        assert len(badges) == 1
        assert badges[0].text() == "local"

    def test_route_badges_not_duplicated_on_redisplay(self, widget):
        widget.display(_sample_ledger())
        widget.display(_sample_ledger())
        assert len(widget.findChildren(QLabel, "ledgerRouteBadge")) == 6

    def test_route_badges_cleared_to_placeholder(self, widget):
        widget.display(_sample_ledger())
        widget.clear()
        assert widget.findChildren(QLabel, "ledgerRouteBadge") == []

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

    def test_multimodal_dedupe_note_shown_when_multimodal_present(self, widget):
        widget.display(_sample_ledger())
        # GPT4O は multimodal → 注記ラベルが表示される
        assert not widget._multi_note_label.isHidden()

    def test_multimodal_dedupe_note_hidden_when_no_multimodal(self, widget):
        ledger = InferenceLedger(
            entries=(LedgerEntry(model=_local_model("wd-tagger", "tags"), stage_count=1),),
            staged_count=3,
        )
        widget.display(ledger)
        assert widget._multi_note_label.isHidden()


class TestInferenceLedgerWidgetBands:
    """#884 Phase 4b: SYNC / PROVIDER BATCH 2バンド分割。"""

    @staticmethod
    def _batch_ledger() -> InferenceLedger:
        """local 2 (sync) + API 1 (batch route) × 9 枚。"""
        entries = (
            LedgerEntry(model=GPT4O, stage_count=3, route="batch"),
            LedgerEntry(model=_local_model("wd-tagger", "tags"), stage_count=1, route="sync"),
            LedgerEntry(model=_local_model("aesthetic", "scores"), stage_count=1, route="sync"),
        )
        return InferenceLedger(entries=entries, staged_count=9)

    def test_batch_band_hidden_when_no_batch_entries(self, widget):
        widget.display(_sample_ledger())  # 全 sync (default route)
        assert widget._batch_band.isHidden()

    def test_batch_band_shown_when_batch_entries_present(self, widget):
        widget.display(self._batch_ledger())
        assert not widget._batch_band.isHidden()

    def test_batch_entry_has_batch_route_badge(self, widget):
        widget.display(self._batch_ledger())
        badges = [b.text() for b in widget.findChildren(QLabel, "ledgerRouteBadge")]
        assert "batch·api" in badges
        assert badges.count("local") == 2

    def test_batch_chip_rendered(self, widget):
        widget.display(self._batch_ledger())
        chips = [c.text() for c in widget.findChildren(QLabel, "ledgerChip")]
        assert any("gpt-4o" in t and "×9枚" in t for t in chips)
        assert len(chips) == 3  # sync 2 + batch 1

    def test_redisplay_sync_only_hides_batch_band_again(self, widget):
        widget.display(self._batch_ledger())
        widget.display(_sample_ledger())
        assert widget._batch_band.isHidden()
        assert "batch·api" not in [b.text() for b in widget.findChildren(QLabel, "ledgerRouteBadge")]

    def test_clear_hides_batch_band(self, widget):
        widget.display(self._batch_ledger())
        widget.clear()
        assert widget._batch_band.isHidden()


class TestInferenceLedgerWidgetFlow:
    """#1100: entries は FlowLayout で折り返し、狭幅で縦長崩れしない。"""

    def test_entries_use_flow_layout(self, widget):
        from lorairo.gui.widgets.tag_cloud_widget import FlowLayout

        assert isinstance(widget._sync_entries_layout, FlowLayout)
        assert isinstance(widget._batch_entries_layout, FlowLayout)

    def test_entries_wrap_when_width_is_narrow(self, widget):
        # 多数エントリを並べ、狭幅では heightForWidth が増える (=折り返す) ことを確認。
        entries = tuple(
            LedgerEntry(model=_local_model(f"model-{i}", "tags"), stage_count=1) for i in range(12)
        )
        widget.display(InferenceLedger(entries=entries, staged_count=3))
        flow = widget._sync_entries_layout
        wide = flow.heightForWidth(2000)  # 全チップ 1 行に収まる
        narrow = flow.heightForWidth(120)  # 1 行に 1〜2 個 → 複数行に折り返す
        assert narrow > wide, f"折り返しが効いていない (narrow={narrow}, wide={wide})"

    def test_container_min_height_stays_bounded(self, widget):
        # FlowLayout の minimumSize は「単一エントリ幅」で、全チップ縦積みには
        # ならない。widgetResizable スクロール内で最小高さが暴れない回帰防止。
        entries = tuple(
            LedgerEntry(model=_local_model(f"model-{i}", "tags"), stage_count=1) for i in range(12)
        )
        widget.display(InferenceLedger(entries=entries, staged_count=3))
        container = widget._sync_entries_layout.parentWidget()
        # 12 エントリでも最小高さは 1〜2 行相当 (≪ 全縦積み) に収まる
        assert container.minimumSizeHint().height() < 80


class TestInferenceLedgerWidgetEstimate:
    """DsSummaryStat 推定 stat の値検証。"""

    def test_estimate_stat_shows_amount_and_duration(self, widget):
        widget.display(_sample_ledger())
        est_val = widget._stat_estimate._value_widget.text()
        # GPT4O per-image = 1500*2.5e-6 + 400*1e-5 = 0.00775、×9枚 ≈ $0.07
        assert "$0.07" in est_val
        # 54 ジョブ × 3.0s = 162s = 2m42s
        assert "2m42s" in est_val
        assert not widget._stats_widget.isHidden()

    def test_estimate_stat_flags_unknown_when_pricing_missing(self, widget):
        no_price_api = StageModelInfo(
            litellm_model_id="anthropic/claude-x",
            display_name="claude-x",
            provider="anthropic",
            is_api=True,
            capabilities=frozenset({"tags"}),
        )
        ledger = InferenceLedger(entries=(LedgerEntry(model=no_price_api, stage_count=1),), staged_count=4)
        widget.display(ledger)
        est_val = widget._stat_estimate._value_widget.text()
        assert "$0.00+" in est_val
        # 料金不明注記は sub に入る
        sub_text = widget._stat_estimate._sub_widget.text()
        assert "料金不明" in sub_text

    def test_local_only_ledger_shows_zero_cost(self, widget):
        ledger = InferenceLedger(
            entries=(LedgerEntry(model=_local_model("wd-tagger", "tags"), stage_count=1),),
            staged_count=5,
        )
        widget.display(ledger)
        est_val = widget._stat_estimate._value_widget.text()
        assert "$0.00" in est_val
        # 料金不明注記なし (sub は空文字/非表示)
        assert widget._stat_estimate._sub_widget.isHidden()


class TestInferenceLedgerWidgetPlaceholder:
    def test_empty_entries_shows_placeholder(self, widget):
        widget.display(InferenceLedger(entries=(), staged_count=9))
        assert widget._placeholder_label.text() == "モデル未選択"
        assert widget._stats_widget.isHidden()
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
        assert widget._stats_widget.isHidden()
        assert widget.findChildren(QLabel, "ledgerChip") == []
        assert widget.findChildren(QLabel, "ledgerMultiBadge") == []


def _badge_declarations(qss: str) -> dict[str, str]:
    """QLabel QSS の { ... } 本文を property:value の dict に正規化する (順不同比較用)。"""
    body = qss[qss.index("{") + 1 : qss.rindex("}")].strip()
    result: dict[str, str] = {}
    for part in body.split(";"):
        part = part.strip()
        if not part:
            continue
        key, value = part.split(":", 1)
        result[key.strip()] = value.strip()
    return result


class TestLedgerBadgeStyleVisualParity:
    """#1105: 手書きバッジ定数を theme.chip_qss へ置換しても見た目不変であること。"""

    def test_entry_chip_style_unchanged(self):
        from lorairo.gui import theme
        from lorairo.gui.widgets import inference_ledger_widget as mod

        baseline = (
            f"QLabel {{ font-family: {theme.FONT_MONO_CSS}; background-color: {theme.PAPER_SHADE};"
            f" color: {theme.INK_SOFT}; border: {theme.BORDER_WIDTH}px solid {theme.LINE};"
            f" border-radius: {theme.RADIUS_BADGE}px; padding: 1px 6px;"
            f" font-size: {theme.FONT_SIZE_META}px; }}"
        )
        assert _badge_declarations(mod._ENTRY_CHIP_STYLE) == _badge_declarations(baseline)

    def test_multi_badge_style_unchanged(self):
        from lorairo.gui import theme
        from lorairo.gui.widgets import inference_ledger_widget as mod

        baseline = (
            f"QLabel {{ font-family: {theme.FONT_MONO_CSS}; background-color: {theme.ACCENT_SOFT};"
            f" color: {theme.ACCENT_HOVER}; border: {theme.BORDER_WIDTH}px solid {theme.ACCENT_BORDER};"
            f" border-radius: {theme.RADIUS_BADGE}px; padding: 1px 6px;"
            f" font-size: {theme.FONT_SIZE_META}px; font-weight: {theme.FONT_WEIGHT_SEMIBOLD}; }}"
        )
        assert _badge_declarations(mod._MULTI_BADGE_STYLE) == _badge_declarations(baseline)

    def test_route_local_badge_style_unchanged(self):
        from lorairo.gui import theme
        from lorairo.gui.widgets import inference_ledger_widget as mod

        baseline = (
            f"QLabel {{ font-family: {theme.FONT_MONO_CSS}; background-color: {theme.PAPER_SHADE};"
            f" color: {theme.INK_FAINT}; border: {theme.BORDER_WIDTH}px solid {theme.LINE};"
            f" border-radius: {theme.RADIUS_BADGE}px; padding: 1px 6px;"
            f" font-size: {theme.FONT_SIZE_META}px; }}"
        )
        assert _badge_declarations(mod._ROUTE_BADGE_STYLE_LOCAL) == _badge_declarations(baseline)

    def test_route_api_badge_style_unchanged(self):
        from lorairo.gui import theme
        from lorairo.gui.widgets import inference_ledger_widget as mod

        baseline = (
            f"QLabel {{ font-family: {theme.FONT_MONO_CSS}; background-color: {theme.ACCENT_SOFT};"
            f" color: {theme.ACCENT_HOVER}; border: {theme.BORDER_WIDTH}px solid {theme.ACCENT_BORDER};"
            f" border-radius: {theme.RADIUS_BADGE}px; padding: 1px 6px;"
            f" font-size: {theme.FONT_SIZE_META}px; }}"
        )
        assert _badge_declarations(mod._ROUTE_BADGE_STYLE_API) == _badge_declarations(baseline)
