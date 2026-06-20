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
