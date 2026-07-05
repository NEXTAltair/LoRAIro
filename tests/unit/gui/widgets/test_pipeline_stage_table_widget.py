"""PipelineStageTableWidget 単体テスト"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel, QToolButton, QWidget

from lorairo.gui.widgets.ds_card import DsCard
from lorairo.gui.widgets.pipeline_stage_table_widget import (
    _BUILTIN_PRESETS,
    _DEFAULT_PRESET_ID,
    PipelinePreset,
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


class TestPipelineStageTableWidgetCustomPresets:
    """Issue #1186: 保存済みカスタムプリセット chip の検証。"""

    def test_set_custom_presets_adds_chips_after_builtins(self, widget):
        widget.set_custom_presets([PipelinePreset("custom:mine", "mine", 2)])

        chips = widget.findChildren(QToolButton, "presetChip")
        assert len(chips) == len(_BUILTIN_PRESETS) + 1
        assert chips[-1].text() == "mine 2"

    def test_custom_chip_click_emits_custom_preset_id(self, widget, qtbot):
        widget.set_custom_presets([PipelinePreset("custom:mine", "mine", 1)])
        chip = next(c for c in widget.findChildren(QToolButton, "presetChip") if c.text() == "mine 1")

        with qtbot.waitSignal(widget.preset_selected, timeout=1000) as blocker:
            chip.click()

        assert blocker.args == ["custom:mine"]

    def test_set_custom_presets_is_idempotent(self, widget):
        widget.set_custom_presets([PipelinePreset("custom:a", "a", 1)])
        widget.set_custom_presets([PipelinePreset("custom:b", "b", 1)])

        texts = [c.text() for c in widget.findChildren(QToolButton, "presetChip")]
        assert "a 1" not in texts
        assert texts.count("b 1") == 1
        assert len(texts) == len(_BUILTIN_PRESETS) + 1

    def test_save_button_stays_last_in_layout(self, widget):
        widget.set_custom_presets([PipelinePreset("custom:mine", "mine", 1)])

        layout = widget._preset_row_layout
        last_widget = layout.itemAt(layout.count() - 1).widget()
        assert last_widget.objectName() == "savePresetButton"

    def test_set_active_preset_works_for_custom_chip(self, widget):
        widget.set_custom_presets([PipelinePreset("custom:mine", "mine", 1)])
        widget.set_active_preset("custom:mine")

        chip = next(c for c in widget.findChildren(QToolButton, "presetChip") if c.text() == "mine 1")
        assert chip.isChecked()

    def test_rebuild_preserves_active_builtin(self, widget):
        widget.set_active_preset("tags_only")
        widget.set_custom_presets([PipelinePreset("custom:mine", "mine", 1)])

        chips = {c.text(): c for c in widget.findChildren(QToolButton, "presetChip")}
        active = [t for t, c in chips.items() if c.isChecked()]
        assert active == [
            next(f"{p.label} {p.model_count}" for p in _BUILTIN_PRESETS if p.preset_id == "tags_only")
        ]


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


def _chip_declarations(qss: str) -> dict[str, str]:
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


class TestChipStyleVisualParity:
    """#1105: 手書き chip 定数を theme.chip_qss へ置換しても見た目不変であること。

    置換前の QSS 文字列 (frozen baseline) と現行モジュール定数の宣言セットが
    一致することを assert する (QSS は宣言順に非依存なので順不同 dict で比較)。
    """

    def test_primary_chip_style_unchanged(self):
        from lorairo.gui import theme
        from lorairo.gui.widgets import pipeline_stage_table_widget as mod

        baseline = (
            f"QLabel {{ font-family: {theme.FONT_MONO_CSS}; background-color: {theme.CARD};"
            f" border: {theme.BORDER_WIDTH}px solid {theme.LINE_STRONG};"
            f" border-radius: {theme.RADIUS_CHIP}px; padding: 1px 9px;"
            f" color: {theme.INK}; font-size: {theme.FONT_SIZE_SMALL}px; }}"
        )
        assert _chip_declarations(mod._PRIMARY_CHIP_STYLE) == _chip_declarations(baseline)

    def test_multi_chip_style_unchanged(self):
        from lorairo.gui import theme
        from lorairo.gui.widgets import pipeline_stage_table_widget as mod

        baseline = (
            f"QLabel {{ font-family: {theme.FONT_MONO_CSS}; background-color: {theme.CARD};"
            f" border: {theme.BORDER_WIDTH}px solid {theme.ACCENT_BORDER};"
            f" border-radius: {theme.RADIUS_CHIP}px; padding: 1px 9px;"
            f" color: {theme.ACCENT_HOVER}; font-size: {theme.FONT_SIZE_SMALL}px;"
            f" font-weight: {theme.FONT_WEIGHT_SEMIBOLD}; }}"
        )
        assert _chip_declarations(mod._MULTI_CHIP_STYLE) == _chip_declarations(baseline)

    def test_derived_chip_style_unchanged(self):
        from lorairo.gui import theme
        from lorairo.gui.widgets import pipeline_stage_table_widget as mod

        baseline = (
            f"QLabel {{ font-family: {theme.FONT_MONO_CSS};"
            f" border: {theme.BORDER_WIDTH}px dashed {theme.LINE_STRONG};"
            f" border-radius: {theme.RADIUS_CHIP}px; padding: 1px 9px;"
            f" color: {theme.INK_SOFT}; font-style: italic; font-size: {theme.FONT_SIZE_SMALL}px; }}"
        )
        assert _chip_declarations(mod._DERIVED_CHIP_STYLE) == _chip_declarations(baseline)


def _many_rating_models(count: int) -> tuple[StageModelInfo, ...]:
    return tuple(
        StageModelInfo(
            litellm_model_id=f"rating-model-{i:02d}",
            display_name=f"rating-model-{i:02d}",
            provider=None,
            is_api=False,
            capabilities=frozenset({"ratings"}),
        )
        for i in range(count)
    )


def _chip_rows(chips_container: QWidget) -> int:
    """FlowLayout 内チップの distinct y (= 行数) を返す。"""
    layout = chips_container.layout()
    ys = set()
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item is not None and item.widget() is not None:
            ys.add(item.widget().y())
    return len(ys)


class TestStageRowChipWrap:
    """#1100 再オープン: ステージ行チップが折り返し、横スクロールを起こさない runtime 検証。"""

    @pytest.mark.parametrize("window_width", [800, 500])
    def test_content_fits_viewport_and_chips_wrap(self, qtbot, window_width):
        from PySide6.QtWidgets import QScrollArea

        widget = PipelineStageTableWidget()
        widget.display(
            [StageRow(stage=PipelineStage.RATING, primary_models=_many_rating_models(14), derived_chips=())]
        )
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        qtbot.addWidget(scroll)
        scroll.resize(window_width, 600)
        scroll.show()
        qtbot.waitExposed(scroll)

        viewport_width = scroll.viewport().width()
        # (a) コンテンツ実幅がビューポート幅以下 (横スクロール不要)
        assert widget.width() <= viewport_width
        assert widget.minimumSizeHint().width() <= viewport_width
        # (b) ステージ行チップが複数行に折り返されている
        chips = widget.findChild(QWidget, "stageChips_RATING")
        assert chips is not None
        assert _chip_rows(chips) >= 2

    def test_narrower_window_wraps_more_rows(self, qtbot):
        from PySide6.QtWidgets import QScrollArea

        def rows_at(width: int) -> int:
            widget = PipelineStageTableWidget()
            widget.display(
                [
                    StageRow(
                        stage=PipelineStage.RATING, primary_models=_many_rating_models(14), derived_chips=()
                    )
                ]
            )
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(widget)
            qtbot.addWidget(scroll)
            scroll.resize(width, 600)
            scroll.show()
            qtbot.waitExposed(scroll)
            return _chip_rows(widget.findChild(QWidget, "stageChips_RATING"))

        assert rows_at(400) > rows_at(900)

    def test_stage_chips_use_flow_layout(self, qtbot):
        from lorairo.gui.widgets.tag_cloud_widget import FlowLayout

        widget = PipelineStageTableWidget()
        widget.display(
            [StageRow(stage=PipelineStage.RATING, primary_models=_many_rating_models(6), derived_chips=())]
        )
        qtbot.addWidget(widget)
        chips = widget.findChild(QWidget, "stageChips_RATING")
        assert isinstance(chips.layout(), FlowLayout)

    def test_preset_row_uses_flow_layout(self, qtbot):
        from lorairo.gui.widgets.tag_cloud_widget import FlowLayout

        widget = PipelineStageTableWidget()
        qtbot.addWidget(widget)
        preset_row = widget.findChild(QWidget, "presetChipRow")
        assert isinstance(preset_row.layout(), FlowLayout)

    def test_legend_wraps(self, qtbot):
        widget = PipelineStageTableWidget()
        qtbot.addWidget(widget)
        legend = widget.findChild(QLabel, "pipelineLegendLabel")
        assert legend.wordWrap() is True
