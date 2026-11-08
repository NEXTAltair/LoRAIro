"""登録日フィルタの UI 相互作用テスト (#1440 / #1457, ADR 0100)。

状態は「有効か」と「スライダーの暦日範囲」だけで、クイック選択チップとヒストグラムは
スライダーの値を書き換えるだけであることを、実 widget で確認する。
(QMessageBox は tests/unit/gui/conftest.py の autouse fixture でモック済み)
"""

from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt

from lorairo.domain.registration_date_range import (
    PRESET_ALL,
    PRESET_CUSTOM,
    PRESET_LAST_7_DAYS,
    PRESET_TODAY,
    PRESET_YESTERDAY,
    LocalDayRange,
    preset_day_range,
    to_utc_bounds,
)
from lorairo.gui.widgets.filter_search_panel import FilterSearchPanel

pytestmark = [pytest.mark.unit, pytest.mark.gui]


@pytest.fixture()
def panel(qtbot):
    widget = FilterSearchPanel()
    qtbot.addWidget(widget)
    return widget


def _click_chip(qtbot, panel: FilterSearchPanel, preset: str) -> None:
    qtbot.mouseClick(panel._date_preset_control._buttons[preset], Qt.MouseButton.LeftButton)


def _today() -> dt.date:
    return dt.date.today()


def _slider_visible(panel: FilterSearchPanel) -> bool:
    return not panel.ui.frameDateRange.isHidden()


class TestQuickSelectChips:
    def test_initial_state_is_all_and_no_bounds(self, panel):
        assert panel._date_preset_control.value() == PRESET_ALL
        assert not _slider_visible(panel)
        assert panel.get_date_range_from_slider() == (None, None)

    @pytest.mark.parametrize("preset", [PRESET_TODAY, PRESET_YESTERDAY, PRESET_LAST_7_DAYS])
    def test_preset_writes_slider_and_bounds(self, qtbot, panel, preset):
        _click_chip(qtbot, panel, preset)

        expected = preset_day_range(preset, _today())
        qtbot.waitUntil(lambda: panel._date_preset_control.value() == preset, timeout=3000)
        assert panel.date_range_slider.get_day_range() == expected
        # 検索の境界はスライダーの値から 1 箇所の関数で作る
        assert panel.get_date_range_from_slider() == to_utc_bounds(expected)
        # プリセット選択中はスライダーを隠す (カスタム時のみ表示)
        assert not _slider_visible(panel)

    def test_custom_chip_shows_slider_and_keeps_range(self, qtbot, panel):
        _click_chip(qtbot, panel, PRESET_TODAY)
        _click_chip(qtbot, panel, PRESET_CUSTOM)

        qtbot.waitUntil(lambda: _slider_visible(panel), timeout=3000)
        assert panel._date_filter_enabled is True
        assert panel.date_range_slider.get_day_range() == preset_day_range(PRESET_TODAY, _today())

    def test_manual_slider_move_switches_to_custom(self, qtbot, panel):
        _click_chip(qtbot, panel, PRESET_LAST_7_DAYS)
        start = _today() - dt.timedelta(days=3)
        panel.date_range_slider.slider.setValue((start.toordinal(), _today().toordinal()))

        qtbot.waitUntil(lambda: panel._date_preset_control.value() == PRESET_CUSTOM, timeout=3000)
        assert _slider_visible(panel)
        assert panel.date_range_slider.get_day_range() == LocalDayRange(start, _today())

    def test_all_chip_disables_filter(self, qtbot, panel):
        _click_chip(qtbot, panel, PRESET_TODAY)
        _click_chip(qtbot, panel, PRESET_ALL)

        qtbot.waitUntil(lambda: panel._date_filter_enabled is False, timeout=3000)
        assert panel.get_date_range_from_slider() == (None, None)
        assert not _slider_visible(panel)
        assert panel._search_facets_sidebar._histogram._selected_range is None


class TestHistogramWritesSlider:
    def test_bar_selection_sets_slider_and_highlight_without_second_condition(self, qtbot, panel):
        start, end = dt.date(2026, 10, 1), dt.date(2026, 10, 3)
        panel._search_facets_sidebar.update_histogram([(start, end, 4), (dt.date(2026, 10, 4), end, 1)])
        panel._on_search_requested = MagicMock()

        panel._search_facets_sidebar._histogram.range_selected.emit(start, end)

        qtbot.waitUntil(lambda: panel._date_preset_control.value() == PRESET_CUSTOM, timeout=3000)
        assert panel.date_range_slider.get_day_range() == LocalDayRange(start, end)
        assert panel.get_date_range_from_slider() == to_utc_bounds(LocalDayRange(start, end))
        assert panel._search_facets_sidebar._histogram.selected_index() == 0
        # ヒストグラムの選択は facet 値として持たず、再検索もしない (スライダーを書き換えるだけ)
        assert "created_at_range" not in panel._facet_values
        panel._on_search_requested.assert_not_called()

    def test_moving_slider_off_bin_removes_highlight(self, qtbot, panel):
        start = dt.date(2026, 10, 1)
        panel._search_facets_sidebar.update_histogram([(start, start, 4)])
        panel._search_facets_sidebar._histogram.range_selected.emit(start, start)
        panel.date_range_slider.slider.setValue((start.toordinal(), start.toordinal() + 1))

        qtbot.waitUntil(
            lambda: panel._search_facets_sidebar._histogram.selected_index() is None, timeout=3000
        )

    def test_bar_before_slider_minimum_extends_slider(self, qtbot, panel):
        old = dt.date(2022, 6, 1)
        panel._search_facets_sidebar._histogram.range_selected.emit(old, old)
        qtbot.waitUntil(
            lambda: panel.date_range_slider.get_day_range() == LocalDayRange(old, old), timeout=3000
        )


class TestSavedFilterRoundTrip:
    def test_custom_range_round_trip(self, qtbot, panel):
        day_range = LocalDayRange(dt.date(2026, 9, 1), dt.date(2026, 9, 15))
        panel._search_facets_sidebar._histogram.range_selected.emit(day_range.start, day_range.end)
        saved = panel.get_current_conditions()
        assert saved["date_filter_enabled"] is True
        assert saved["date_range"] == ["2026-09-01", "2026-09-15"]

        panel._clear_all_inputs()
        assert panel._date_filter_enabled is False
        panel.apply_conditions(saved)

        assert panel.get_current_conditions() == saved
        assert panel.get_date_range_from_slider() == to_utc_bounds(day_range)
        assert panel._date_preset_control.value() == PRESET_CUSTOM
        assert _slider_visible(panel)

    def test_restore_derives_preset_chip(self, qtbot, panel):
        _click_chip(qtbot, panel, PRESET_LAST_7_DAYS)
        saved = panel.get_current_conditions()
        panel._clear_all_inputs()

        panel.apply_conditions(saved)

        assert panel._date_preset_control.value() == PRESET_LAST_7_DAYS
        assert not _slider_visible(panel)

    def test_favorite_without_date_filter_clears_previous_selection(self, qtbot, panel):
        _click_chip(qtbot, panel, PRESET_TODAY)
        conditions = panel.get_current_conditions()
        conditions["date_filter_enabled"] = False
        conditions.pop("date_range")

        panel.apply_conditions(conditions)

        assert panel._date_filter_enabled is False
        assert panel.date_range_slider.is_full_range()
        assert panel._date_preset_control.value() == PRESET_ALL

    def test_legacy_epoch_seconds_are_restored_as_local_days(self, qtbot, panel):
        start = dt.datetime(2026, 9, 1, 12).astimezone()
        end = dt.datetime(2026, 9, 3, 12).astimezone()
        conditions = panel.get_current_conditions()
        conditions["date_filter_enabled"] = True
        conditions["date_range"] = [int(start.timestamp()), int(end.timestamp())]

        panel.apply_conditions(conditions)

        assert panel.date_range_slider.get_day_range() == LocalDayRange(
            dt.date(2026, 9, 1), dt.date(2026, 9, 3)
        )


class TestSearchConditionsUseSliderOnly:
    def test_date_filter_alone_builds_half_open_bounds(self, qtbot, panel):
        service = MagicMock()
        service.parse_search_input.return_value = ([], [])
        panel.search_filter_service = service
        panel.ui.lineEditSearch.setText("")
        _click_chip(qtbot, panel, PRESET_YESTERDAY)

        panel._build_search_conditions_from_ui(show_status=False)

        kwargs = service.create_search_conditions.call_args.kwargs
        expected = to_utc_bounds(preset_day_range(PRESET_YESTERDAY, _today()))
        assert kwargs["date_filter_enabled"] is True
        assert (kwargs["date_range_start"], kwargs["date_range_end"]) == expected
