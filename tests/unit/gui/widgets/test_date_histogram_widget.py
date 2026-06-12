from __future__ import annotations

import datetime

import pytest
from PySide6.QtCore import QPoint, Qt

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
        """update_histogram がビンデータを正しく設定することを確認する。"""
        widget = DateHistogramWidget()
        qtbot.addWidget(widget)
        now = datetime.datetime.now(datetime.UTC)
        bins = [(now, now + datetime.timedelta(days=1), 5)]
        widget.update_histogram(bins)
        assert widget._bins == bins

    def test_update_histogram_clears_selected_idx(self, qtbot: pytest.FixtureRequest) -> None:
        """update_histogram が選択インデックスをリセットすることを確認する。"""
        widget = DateHistogramWidget()
        qtbot.addWidget(widget)
        now = datetime.datetime.now(datetime.UTC)
        widget.update_histogram([(now, now, 1)])
        widget._selected_idx = 0
        widget.update_histogram([(now, now, 2)])
        assert widget._selected_idx is None

    def test_clear_resets_bins(self, qtbot: pytest.FixtureRequest) -> None:
        """clear() がビンをクリアすることを確認する。"""
        widget = DateHistogramWidget()
        qtbot.addWidget(widget)
        now = datetime.datetime.now(datetime.UTC)
        widget.update_histogram([(now, now, 1)])
        widget.clear()
        assert widget._bins == []

    def test_clear_resets_selected_idx(self, qtbot: pytest.FixtureRequest) -> None:
        """clear() が選択インデックスをリセットすることを確認する。"""
        widget = DateHistogramWidget()
        qtbot.addWidget(widget)
        now = datetime.datetime.now(datetime.UTC)
        widget.update_histogram([(now, now, 1)])
        widget._selected_idx = 0
        widget.clear()
        assert widget._selected_idx is None

    def test_range_selected_signal_emitted_on_click(self, qtbot: pytest.FixtureRequest) -> None:
        """クリック時に range_selected シグナルが発火することを確認する。"""
        widget = DateHistogramWidget()
        qtbot.addWidget(widget)
        widget.resize(300, 80)
        now = datetime.datetime.now(datetime.UTC)
        end = now + datetime.timedelta(days=1)
        widget.update_histogram([(now, end, 10)])

        with qtbot.waitSignal(widget.range_selected, timeout=3000) as blocker:
            qtbot.mouseClick(widget, Qt.MouseButton.LeftButton, pos=QPoint(10, 40))

        assert blocker.signal_triggered
        assert blocker.args[0] == now
        assert blocker.args[1] == end

    def test_click_sets_selected_idx(self, qtbot: pytest.FixtureRequest) -> None:
        """クリック後に選択インデックスが設定されることを確認する。"""
        widget = DateHistogramWidget()
        qtbot.addWidget(widget)
        widget.resize(300, 80)
        now = datetime.datetime.now(datetime.UTC)
        widget.update_histogram([(now, now, 3), (now, now, 5)])

        qtbot.mouseClick(widget, Qt.MouseButton.LeftButton, pos=QPoint(10, 40))
        assert widget._selected_idx == 0

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
