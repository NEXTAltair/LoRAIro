"""StageModelPickerDialog 単体テスト (Issue #839: リッチモーダル化)。

旧 QListWidget 版から ``実行環境 × アノテーション種類 × provider`` 絞り込み +
モデル行のリッチモーダルへ刷新したことを検証する。公開 API
(コンストラクタの 4 キーワード / configure_key_requested / selected_model_ids /
refresh_key_status) の後方互換も併せて確認する。
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QDialogButtonBox, QLabel, QPushButton

from lorairo.gui.widgets.ds_segmented_control import DsSegmentedControl
from lorairo.gui.widgets.stage_model_picker_dialog import StageModelPickerDialog, _ModelRow
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
CLAUDE_TAGS = StageModelInfo(
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
AESTHETIC = StageModelInfo(
    litellm_model_id="aesthetic-v2",
    display_name="aesthetic-v2",
    provider=None,
    is_api=False,
    capabilities=frozenset({"scores"}),
)


def _rows(dialog: StageModelPickerDialog) -> list[_ModelRow]:
    return list(dialog._rows)


def _row_by_id(dialog: StageModelPickerDialog, model_id: str) -> _ModelRow:
    for row in dialog._rows:
        if row.info.litellm_model_id == model_id:
            return row
    raise AssertionError(f"row not found: {model_id}")


def _ok_button(dialog: StageModelPickerDialog):
    boxes = dialog.findChildren(QDialogButtonBox)
    assert len(boxes) == 1
    return boxes[0].button(QDialogButtonBox.StandardButton.Ok)


class TestRendering:
    def test_title_uses_uppercase_stage_value(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [GPT4O, WD_TAGGER])
        qtbot.addWidget(dialog)
        assert dialog.windowTitle() == "TAGS のモデルを選択"

    def test_one_row_per_candidate(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [GPT4O, WD_TAGGER, CLAUDE_TAGS])
        qtbot.addWidget(dialog)
        assert len(_rows(dialog)) == 3

    def test_multimodal_row_shows_fanout_note(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [GPT4O, WD_TAGGER])
        qtbot.addWidget(dialog)
        gpt_row = _row_by_id(dialog, "openai/gpt-4o")
        note_texts = [label.text() for label in gpt_row.findChildren(QLabel) if "1推論で" in label.text()]
        assert note_texts and "preflight" in note_texts[0]
        wd_row = _row_by_id(dialog, "wd-v1-4-tagger")
        assert all("1推論で" not in label.text() for label in wd_row.findChildren(QLabel))

    def test_per_image_cost_rendered(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [GPT4O, WD_TAGGER, CLAUDE_TAGS])
        qtbot.addWidget(dialog)
        gpt_texts = [label.text() for label in _row_by_id(dialog, "openai/gpt-4o").findChildren(QLabel)]
        # GPT4O per-image = 1500*2.5e-6 + 400*1e-5 = 0.00775 → $0.0077/img
        assert any("$0.0077/img" in t for t in gpt_texts)
        wd_texts = [label.text() for label in _row_by_id(dialog, "wd-v1-4-tagger").findChildren(QLabel)]
        assert any("ローカル（無料）" in t for t in wd_texts)
        claude_texts = [
            label.text() for label in _row_by_id(dialog, "anthropic/claude-x").findChildren(QLabel)
        ]
        assert any("—" in t for t in claude_texts)


class TestSelection:
    def test_no_selection_returns_empty(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [GPT4O, WD_TAGGER])
        qtbot.addWidget(dialog)
        assert dialog.selected_model_ids() == []

    def test_row_click_toggles_selection_in_candidate_order(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [GPT4O, WD_TAGGER])
        qtbot.addWidget(dialog)
        _row_by_id(dialog, "wd-v1-4-tagger").toggle_requested.emit()
        _row_by_id(dialog, "openai/gpt-4o").toggle_requested.emit()
        # 候補順 (GPT4O, WD) で返る
        assert dialog.selected_model_ids() == ["openai/gpt-4o", "wd-v1-4-tagger"]

    def test_row_click_twice_deselects(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [WD_TAGGER])
        qtbot.addWidget(dialog)
        row = _row_by_id(dialog, "wd-v1-4-tagger")
        row.toggle_requested.emit()
        assert dialog.selected_model_ids() == ["wd-v1-4-tagger"]
        row.toggle_requested.emit()
        assert dialog.selected_model_ids() == []

    def test_select_all_visible_selects_checkable(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [GPT4O, WD_TAGGER])
        qtbot.addWidget(dialog)
        dialog._select_all_visible()
        assert set(dialog.selected_model_ids()) == {"openai/gpt-4o", "wd-v1-4-tagger"}
        dialog._deselect_all_visible()
        assert dialog.selected_model_ids() == []

    def test_select_recommended_picks_local_and_multimodal(self, qtbot):
        # CLAUDE_TAGS は単機能 API → 推奨外。GPT4O(multimodal API) と WD(local) は推奨。
        dialog = StageModelPickerDialog(
            PipelineStage.TAGS,
            [GPT4O, WD_TAGGER, CLAUDE_TAGS],
            available_providers={"openai", "anthropic"},
        )
        qtbot.addWidget(dialog)
        dialog._select_recommended()
        assert set(dialog.selected_model_ids()) == {"openai/gpt-4o", "wd-v1-4-tagger"}


class TestFilters:
    def test_env_local_hides_api_rows(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [GPT4O, WD_TAGGER])
        qtbot.addWidget(dialog)
        dialog._set_env("local")
        assert _row_by_id(dialog, "openai/gpt-4o").isHidden()
        assert not _row_by_id(dialog, "wd-v1-4-tagger").isHidden()

    def test_env_change_resets_provider_to_all(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [GPT4O, WD_TAGGER])
        qtbot.addWidget(dialog)
        dialog._on_provider_toggled("openai", True)
        assert dialog._provider == "openai"
        dialog._set_env("local")
        assert dialog._provider == "all"

    def test_env_segment_is_ds_segmented_control_and_click_filters(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [GPT4O, WD_TAGGER])
        qtbot.addWidget(dialog)
        segment = dialog._env_segment
        assert isinstance(segment, DsSegmentedControl)
        assert segment.value() == "all"
        # ユーザークリック相当 (value_changed 経由) で環境フィルタが反映される
        segment._buttons["local"].click()
        assert dialog._env == "local"
        assert _row_by_id(dialog, "openai/gpt-4o").isHidden()

    def test_env_segment_follows_programmatic_env_change(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [GPT4O, WD_TAGGER])
        qtbot.addWidget(dialog)
        dialog._set_env("api")
        assert dialog._env_segment is not None
        assert dialog._env_segment.value() == "api"
        assert dialog._env_segment._buttons["api"].isChecked()

    def test_type_filter_narrows_to_matching_stage(self, qtbot):
        # SCORE ステージ: multimodal(GPT4O) と score-only(AESTHETIC) が候補。
        dialog = StageModelPickerDialog(PipelineStage.SCORE, [GPT4O, AESTHETIC])
        qtbot.addWidget(dialog)
        # atype=tags に絞ると tags を出せる GPT4O のみ表示、AESTHETIC は非表示
        dialog._on_type_toggled("tags", True)
        assert not _row_by_id(dialog, "openai/gpt-4o").isHidden()
        assert _row_by_id(dialog, "aesthetic-v2").isHidden()

    def test_no_match_label_visible_when_nothing_matches(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [WD_TAGGER])
        qtbot.addWidget(dialog)
        dialog._set_env("api")  # ローカルのみの候補が消える
        labels = dialog.findChildren(QLabel, "noMatchLabel")
        assert len(labels) == 1
        assert not labels[0].isHidden()


class TestEmptyCandidates:
    def test_empty_candidates_shows_label_and_disables_ok(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.RATING, [])
        qtbot.addWidget(dialog)
        labels = dialog.findChildren(QLabel, "emptyCandidatesLabel")
        assert len(labels) == 1
        assert "追加できる未選択モデルがありません" in labels[0].text()
        ok_button = _ok_button(dialog)
        assert ok_button is not None and not ok_button.isEnabled()
        assert dialog.selected_model_ids() == []


class TestKeyStatus:
    """Issue #755: ● installed / ● API ready / ○ needs key ステータス。"""

    def test_needs_key_row_not_selectable_and_emits_configure(self, qtbot):
        dialog = StageModelPickerDialog(
            PipelineStage.TAGS, [GPT4O, CLAUDE_TAGS], available_providers={"openai"}
        )
        qtbot.addWidget(dialog)
        claude_row = _row_by_id(dialog, "anthropic/claude-x")
        # needs key 行はトグルしても選択されない
        claude_row.toggle_requested.emit()
        assert "anthropic/claude-x" not in dialog.selected_model_ids()
        # クリックで configure_key_requested を emit
        with qtbot.waitSignal(dialog.configure_key_requested, timeout=1000) as blocker:
            claude_row.configure_requested.emit()
        assert blocker.args == ["anthropic"]

    def test_ready_row_does_not_emit_configure(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [GPT4O], available_providers={"openai"})
        qtbot.addWidget(dialog)
        emitted: list[str] = []
        dialog.configure_key_requested.connect(emitted.append)
        _row_by_id(dialog, "openai/gpt-4o").configure_requested.emit()
        assert emitted == []

    def test_default_none_available_providers_treats_all_ready(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [GPT4O, CLAUDE_TAGS])
        qtbot.addWidget(dialog)
        # available_providers 未指定 → needs key なし → 両方選択可
        _row_by_id(dialog, "anthropic/claude-x").toggle_requested.emit()
        assert "anthropic/claude-x" in dialog.selected_model_ids()

    def test_refresh_key_status_resolves_needs_key(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [CLAUDE_TAGS], available_providers=set())
        qtbot.addWidget(dialog)
        claude_row = _row_by_id(dialog, "anthropic/claude-x")
        claude_row.toggle_requested.emit()  # needs key 中は選択不可
        assert dialog.selected_model_ids() == []

        dialog.refresh_key_status({"anthropic"})

        claude_row.toggle_requested.emit()  # キー解消後は選択可
        assert dialog.selected_model_ids() == ["anthropic/claude-x"]


class TestBackwardCompatAndFooter:
    def test_constructor_matches_main_window_call_shape(self, qtbot):
        # main_window と同じ呼び出し形 (available_providers / parent はキーワード)
        dialog = StageModelPickerDialog(
            PipelineStage.TAGS,
            [GPT4O, WD_TAGGER],
            available_providers={"openai"},
            parent=None,
        )
        qtbot.addWidget(dialog)
        assert dialog.selected_model_ids() == []

    def test_staged_count_shows_jobs_in_footer(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [WD_TAGGER], staged_count=9)
        qtbot.addWidget(dialog)
        _row_by_id(dialog, "wd-v1-4-tagger").toggle_requested.emit()
        footer_texts = [label.text() for label in dialog.findChildren(QLabel)]
        assert any("1 × 9 = 9 jobs" in t for t in footer_texts)

    def test_no_staged_count_omits_jobs(self, qtbot):
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [WD_TAGGER])
        qtbot.addWidget(dialog)
        _row_by_id(dialog, "wd-v1-4-tagger").toggle_requested.emit()
        footer_texts = [label.text() for label in dialog.findChildren(QLabel)]
        assert any("1 モデル選択中" in t for t in footer_texts)
        assert all("jobs" not in t for t in footer_texts)


class TestSearchAndKeyboardAndQuickPresets:
    """Issue #1538: テキスト検索、キーボード操作、クイックプリセット差分の検証。"""

    def test_search_edit_filters_by_name_and_provider_case_insensitive(self, qtbot):
        dialog = StageModelPickerDialog(
            PipelineStage.TAGS,
            [GPT4O, CLAUDE_TAGS, WD_TAGGER],
            available_providers={"openai", "anthropic"},
        )
        qtbot.addWidget(dialog)
        assert dialog.search_edit.objectName() == "pickerSearchInput"

        # モデル名で絞り込み (大文字・小文字無視)
        dialog.search_edit.setText("WD-V1")
        visible_ids = [r.info.litellm_model_id for r in _rows(dialog) if not r.isHidden()]
        assert visible_ids == ["wd-v1-4-tagger"]

        # プロバイダ名で絞り込み
        dialog.search_edit.setText("anthropic")
        visible_ids = [r.info.litellm_model_id for r in _rows(dialog) if not r.isHidden()]
        assert visible_ids == ["anthropic/claude-x"]

        # 一致なし時は noMatchLabel を表示
        dialog.search_edit.setText("nonexistent-model-xyz")
        assert [r for r in _rows(dialog) if not r.isHidden()] == []
        assert dialog._no_match_label.isHidden() is False

        # クリアで全件復帰
        dialog.search_edit.clear()
        assert len([r for r in _rows(dialog) if not r.isHidden()]) == 3

    def test_model_row_keyboard_space_and_return_toggle_selection(self, qtbot):
        dialog = StageModelPickerDialog(
            PipelineStage.TAGS,
            [GPT4O, CLAUDE_TAGS],
            available_providers={"openai"},
        )
        qtbot.addWidget(dialog)
        gpt_row = _row_by_id(dialog, "openai/gpt-4o")
        claude_row = _row_by_id(dialog, "anthropic/claude-x")

        assert gpt_row.focusPolicy() == Qt.FocusPolicy.StrongFocus

        # Space キーで選択 ON
        space_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier)
        gpt_row.keyPressEvent(space_event)
        assert dialog.selected_model_ids() == ["openai/gpt-4o"]

        # Return キーで選択 OFF
        return_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
        gpt_row.keyPressEvent(return_event)
        assert dialog.selected_model_ids() == []

        # needs key 行で Space キーを押すと configure_key_requested が発火し選択はされない
        with qtbot.waitSignal(dialog.configure_key_requested, timeout=1000) as blocker:
            claude_row.keyPressEvent(space_event)
        assert blocker.args == ["anthropic"]
        assert dialog.selected_model_ids() == []

    def test_quick_presets_differentiate_all_installed_and_cheap_local(self, qtbot):
        dialog = StageModelPickerDialog(
            PipelineStage.TAGS,
            [GPT4O, WD_TAGGER],
            available_providers={"openai"},
        )
        qtbot.addWidget(dialog)
        preset_buttons = {btn.text(): btn for btn in dialog.findChildren(QPushButton, "pickerPresetChip")}

        # Cheap (local) はローカル表示へ絞り込むだけで選択状態は変えない
        preset_buttons["Cheap (local)"].click()
        visible_ids = [r.info.litellm_model_id for r in _rows(dialog) if not r.isHidden()]
        assert visible_ids == ["wd-v1-4-tagger"]
        assert dialog.selected_model_ids() == []

        # All installed はローカルモデルを表示しつつ一括選択する
        preset_buttons["All installed"].click()
        assert dialog.selected_model_ids() == ["wd-v1-4-tagger"]

    def test_refresh_models_button_emits_signal_and_set_candidates_rebuilds_rows(self, qtbot):
        """Issue #1570: モデル一覧を更新ボタンのシグナル発行と set_candidates 再構築。"""
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [WD_TAGGER])
        qtbot.addWidget(dialog)

        refresh_btn = dialog.findChild(QPushButton, "stagePickerRefreshModelsButton")
        assert refresh_btn is not None
        assert refresh_btn.text() == "モデル一覧を更新"
        assert refresh_btn.toolTip() == "プロバイダーとDBから最新のモデル一覧を再取得します"

        with qtbot.waitSignal(dialog.refresh_models_requested, timeout=1000):
            refresh_btn.click()

        dialog.set_candidates([GPT4O, WD_TAGGER])
        assert [r.info.litellm_model_id for r in _rows(dialog)] == [
            "openai/gpt-4o",
            "wd-v1-4-tagger",
        ]

    def test_empty_candidates_to_nonempty_set_candidates_builds_and_enables_rows(self, qtbot):
        """Issue #1570: 空候補で開いたピッカーに対して set_candidates で候補を追加すると行が構築され選択可能になる。"""
        dialog = StageModelPickerDialog(PipelineStage.TAGS, [])
        qtbot.addWidget(dialog)

        assert not dialog._empty_body.isHidden()
        assert dialog._main_area.isHidden()
        ok_button = _ok_button(dialog)
        assert ok_button is not None and not ok_button.isEnabled()

        dialog.set_candidates([WD_TAGGER])

        assert dialog._empty_body.isHidden()
        assert not dialog._main_area.isHidden()
        assert ok_button.isEnabled()
        assert [r.info.litellm_model_id for r in _rows(dialog)] == ["wd-v1-4-tagger"]

        _row_by_id(dialog, "wd-v1-4-tagger").toggle_requested.emit()
        assert dialog.selected_model_ids() == ["wd-v1-4-tagger"]
