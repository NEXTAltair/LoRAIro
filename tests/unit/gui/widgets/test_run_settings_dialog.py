"""RunSettingsDialog / SegmentedControl 単体テスト (Issue #789)。"""

from __future__ import annotations

import pytest

from lorairo.gui.widgets.run_settings_dialog import (
    RunOptions,
    RunSettingsDialog,
    SegmentedControl,
)

pytestmark = [pytest.mark.unit, pytest.mark.gui]


@pytest.fixture
def dialog(qtbot):
    d = RunSettingsDialog(staged_count=9)
    qtbot.addWidget(d)
    return d


class TestSegmentedControl:
    def test_initial_value_is_selected(self, qtbot):
        sc = SegmentedControl([("a", "A"), ("b", "B")], value="b")
        qtbot.addWidget(sc)
        assert sc.value() == "b"
        assert sc._buttons["b"].isChecked()
        assert not sc._buttons["a"].isChecked()

    def test_click_changes_value(self, qtbot):
        sc = SegmentedControl([("a", "A"), ("b", "B")], value="a")
        qtbot.addWidget(sc)
        sc._buttons["b"].click()
        assert sc.value() == "b"


class TestRunSettingsDialogDefaults:
    def test_default_run_options_match_ds(self, dialog):
        opts = dialog.run_options()
        assert opts == RunOptions(
            concurrency=4,
            retries=2,
            on_fail="skip",
            rating_gate=True,
            overwrite=False,
            dedupe=True,
            dry_run=False,
            dispatch_mode="sync",
        )

    def test_header_shows_staged_count(self, dialog):
        from PySide6.QtWidgets import QLabel

        headers = dialog.findChildren(QLabel, "runSettingsHeader")
        assert len(headers) == 1
        assert "9 枚" in headers[0].text()


class TestRunSettingsDialogEnabledControls:
    def test_dry_run_toggle_reflected(self, dialog):
        dialog._dry_run.setChecked(True)
        assert dialog.run_options().dry_run is True

    def test_rating_gate_toggle_reflected(self, dialog):
        dialog._rating_gate._buttons["off"].click()
        assert dialog.run_options().rating_gate is False

    def test_rating_gate_and_dry_run_are_enabled(self, dialog):
        assert dialog._rating_gate.isEnabled()
        assert dialog._dry_run.isEnabled()


class TestRunSettingsDialogDispatchMode:
    def test_dispatch_mode_defaults_to_sync(self, dialog):
        assert dialog.run_options().dispatch_mode == "sync"

    def test_dispatch_mode_control_is_enabled(self, dialog):
        # Phase 2c で Batch API 経路を配線済みのため操作可能。
        assert dialog._dispatch_mode.isEnabled()
        assert dialog._dispatch_mode.toolTip() != ""

    def test_dispatch_mode_value_reflected_in_run_options(self, dialog):
        # control を操作すると run_options に載る。
        dialog._dispatch_mode.set_value("batch_api")
        assert dialog.run_options().dispatch_mode == "batch_api"


class TestRunSettingsDialogPromptMetadata:
    """prompt_profile / description 入力 (#902, ADR 0076 §1)。"""

    def test_prompt_profile_defaults_to_default(self, dialog):
        assert dialog.run_options().prompt_profile == "default"

    def test_description_defaults_to_none(self, dialog):
        assert dialog.run_options().description is None

    def test_prompt_profile_value_reflected(self, dialog):
        dialog._prompt_profile.setText("photoreal-v2")
        assert dialog.run_options().prompt_profile == "photoreal-v2"

    def test_blank_prompt_profile_falls_back_to_default(self, dialog):
        # 空入力は "default" に正規化する (射影は非空 prompt_profile を要求)。
        dialog._prompt_profile.setText("   ")
        assert dialog.run_options().prompt_profile == "default"

    def test_description_value_reflected(self, dialog):
        dialog._description.setText("monthly audit run")
        assert dialog.run_options().description == "monthly audit run"

    def test_blank_description_normalized_to_none(self, dialog):
        dialog._description.setText("   ")
        assert dialog.run_options().description is None

    def test_prompt_metadata_inputs_are_enabled(self, dialog):
        assert dialog._prompt_profile.isEnabled()
        assert dialog._description.isEnabled()


class TestRunSettingsDialogSeedFromCurrent:
    """再オープン時に現在の RunOptions を seed する (#902 Codex P2)。"""

    def test_seeds_prompt_metadata_from_current(self, qtbot):
        current = RunOptions(prompt_profile="photoreal-v2", description="audit run")
        d = RunSettingsDialog(staged_count=3, current=current)
        qtbot.addWidget(d)
        opts = d.run_options()
        assert opts.prompt_profile == "photoreal-v2"
        assert opts.description == "audit run"

    def test_seeds_enabled_controls_from_current(self, qtbot):
        current = RunOptions(dispatch_mode="batch_api", rating_gate=False, dry_run=True)
        d = RunSettingsDialog(staged_count=3, current=current)
        qtbot.addWidget(d)
        opts = d.run_options()
        assert opts.dispatch_mode == "batch_api"
        assert opts.rating_gate is False
        assert opts.dry_run is True

    def test_full_round_trip_preserves_run_options(self, qtbot):
        current = RunOptions(
            dispatch_mode="batch_api",
            rating_gate=False,
            dry_run=True,
            prompt_profile="custom",
            description="note",
        )
        d = RunSettingsDialog(staged_count=3, current=current)
        qtbot.addWidget(d)
        assert d.run_options() == current

    def test_none_current_uses_defaults(self, qtbot):
        d = RunSettingsDialog(staged_count=3, current=None)
        qtbot.addWidget(d)
        assert d.run_options() == RunOptions()


class TestRunSettingsDialogDisabledControls:
    def test_unimplemented_controls_are_disabled(self, dialog):
        for control in (
            dialog._concurrency,
            dialog._retries,
            dialog._on_fail,
            dialog._overwrite,
            dialog._dedupe,
        ):
            assert not control.isEnabled()

    def test_disabled_controls_have_tooltip(self, dialog):
        assert dialog._concurrency.toolTip() != ""
        assert dialog._dedupe.toolTip() != ""
