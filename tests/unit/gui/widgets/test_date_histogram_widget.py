from __future__ import annotations

import datetime

import pytest
from PySide6.QtCore import QPoint, Qt

from lorairo.domain.registration_date_range import LocalDayRange
from lorairo.gui.widgets.date_histogram_widget import DateHistogramWidget


@pytest.mark.unit
@pytest.mark.gui
class TestDateHistogramWidget:
    def test_initial_state_is_empty(self, qtbot: pytest.FixtureRequest) -> None:
        """初期状態でビンが空であることを確認する。"""
        widget = DateHistogramWidget()
        qtbot.addWidget(widget)
        assert widget._bins == []

    def test_update_histogram_sets_bins(self, qtbot: pytest.FixtureRequest) -> None:
        """update_histogram が暦日ビンを設定する。"""
        widget = DateHistogramWidget()
        qtbot.addWidget(widget)
        bins = [(datetime.date(2026, 11, 7), datetime.date(2026, 11, 7), 5)]
        widget.update_histogram(bins)
        assert widget._bins == bins

    def test_clear_resets_bins_and_selection(self, qtbot: pytest.FixtureRequest) -> None:
        """clear() がビンと強調表示をクリアする。"""
        widget = DateHistogramWidget()
        qtbot.addWidget(widget)
        day = datetime.date(2026, 11, 7)
        widget.update_histogram([(day, day, 1)])
        widget.set_selected_range(LocalDayRange(day, day))
        widget.clear()
        assert widget._bins == []
        assert widget.selected_index() is None

    def test_range_selected_signal_emits_bin_days(self, qtbot: pytest.FixtureRequest) -> None:
        """クリックでそのビンの暦日範囲 (開始日, 終了日) が通知される。"""
        widget = DateHistogramWidget()
        qtbot.addWidget(widget)
        widget.resize(300, 80)
        start, end = datetime.date(2026, 11, 1), datetime.date(2026, 11, 3)
        widget.update_histogram(
            [(start, end, 10), (datetime.date(2026, 11, 4), datetime.date(2026, 11, 6), 2)]
        )

        with qtbot.waitSignal(widget.range_selected, timeout=3000) as blocker:
            qtbot.mouseClick(widget, Qt.MouseButton.LeftButton, pos=QPoint(10, 40))

        assert blocker.args == [start, end]

    def test_click_does_not_hold_selection_by_itself(self, qtbot: pytest.FixtureRequest) -> None:
        """クリックだけでは強調表示は変わらない (選択状態はスライダー側が持つ, ADR 0100)。"""
        widget = DateHistogramWidget()
        qtbot.addWidget(widget)
        widget.resize(300, 80)
        day = datetime.date(2026, 11, 7)
        widget.update_histogram([(day, day, 3)])
        qtbot.mouseClick(widget, Qt.MouseButton.LeftButton, pos=QPoint(10, 40))
        assert widget.selected_index() is None

    def test_selected_index_follows_selected_range(self, qtbot: pytest.FixtureRequest) -> None:
        """強調表示は設定された範囲と完全一致するビンだけ。"""
        widget = DateHistogramWidget()
        qtbot.addWidget(widget)
        d1, d2 = datetime.date(2026, 11, 1), datetime.date(2026, 11, 2)
        widget.update_histogram([(d1, d1, 3), (d2, d2, 5)])
        widget.set_selected_range(LocalDayRange(d2, d2))
        assert widget.selected_index() == 1
        widget.set_selected_range(LocalDayRange(d1, d2))
        assert widget.selected_index() is None

    def test_no_signal_when_bins_empty_on_click(self, qtbot: pytest.FixtureRequest) -> None:
        """ビンが空のときにクリックしてもシグナルが発火しないことを確認する。"""
        widget = DateHistogramWidget()
        qtbot.addWidget(widget)
        widget.resize(300, 80)

        signal_fired = []
        widget.range_selected.connect(lambda s, e: signal_fired.append((s, e)))
        qtbot.mouseClick(widget, Qt.MouseButton.LeftButton, pos=QPoint(10, 40))

        assert signal_fired == []

    def test_size_hint(self, qtbot: pytest.FixtureRequest) -> None:
        """sizeHint が (300, 80) を返すことを確認する。"""
        widget = DateHistogramWidget()
        qtbot.addWidget(widget)
        hint = widget.sizeHint()
        assert hint.width() == 300
        assert hint.height() == 80
