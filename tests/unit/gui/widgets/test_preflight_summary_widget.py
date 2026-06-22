"""PreflightSummaryWidget 単体テスト (Issue #837)。"""

from __future__ import annotations

import pytest

from lorairo.gui.widgets.preflight_summary_widget import (
    PreflightSummaryWidget,
    classify_preflight_counts,
)

pytestmark = [pytest.mark.unit, pytest.mark.gui]


class TestClassifyPreflightCounts:
    def test_classifies_sendable_held_and_unrated(self):
        ratings = {1: "PG", 2: "PG-13", 3: "R", 4: "X", 5: "XXX", 6: None}
        # 7 は ratings に存在しない (rating 行なし) → 未判定
        summary = classify_preflight_counts(ratings, [1, 2, 3, 4, 5, 6, 7])
        assert summary.sendable == 3
        assert summary.held == 2
        assert summary.unrated == 2
        assert summary.total == 7

    def test_normalizes_case_and_whitespace(self):
        ratings = {1: " pg ", 2: "x"}
        summary = classify_preflight_counts(ratings, [1, 2])
        assert summary.sendable == 1
        assert summary.held == 1

    def test_unrated_label_and_empty_string_are_unrated(self):
        ratings = {1: "UNRATED", 2: "", 3: "unknown-scheme"}
        summary = classify_preflight_counts(ratings, [1, 2, 3])
        assert summary.sendable == 0
        assert summary.held == 0
        assert summary.unrated == 3

    def test_empty_staging_returns_zero(self):
        summary = classify_preflight_counts({}, [])
        assert summary.total == 0


@pytest.fixture
def widget(qtbot):
    w = PreflightSummaryWidget()
    qtbot.addWidget(w)
    return w


class TestPreflightSummaryWidgetDisplay:
    def test_display_sets_sendable_and_held_chip_text(self, widget):
        widget.display({1: "PG", 2: "R", 3: "X"}, [1, 2, 3])
        assert widget._sendable_chip.text() == "2 送信可 sendable"
        assert widget._held_chip.text() == "1 保留 held"
        assert not widget._sendable_chip.isHidden()
        assert not widget._held_chip.isHidden()
        assert not widget._badge.isHidden()
        assert widget._placeholder_label.isHidden()

    def test_unrated_chip_visible_only_when_present(self, widget):
        widget.display({1: "PG"}, [1, 2])
        assert widget._unrated_chip.text() == "1 未判定"
        assert not widget._unrated_chip.isHidden()

    def test_unrated_chip_hidden_when_zero(self, widget):
        widget.display({1: "PG", 2: "R"}, [1, 2])
        assert widget._unrated_chip.isHidden()

    def test_type_badge_shows_task_type(self, widget):
        widget.display({1: "PG"}, [1])
        assert widget._badge.text() == "task_type=rating_preflight"


class TestPreflightSummaryWidgetPlaceholder:
    def test_empty_staging_shows_placeholder(self, widget):
        widget.display({}, [])
        assert not widget._placeholder_label.isHidden()
        assert widget._sendable_chip.isHidden()
        assert widget._held_chip.isHidden()
        assert widget._badge.isHidden()

    def test_clear_resets_to_placeholder(self, widget):
        widget.display({1: "PG"}, [1])
        widget.clear()
        assert not widget._placeholder_label.isHidden()
        assert widget._sendable_chip.isHidden()
        assert widget._held_chip.isHidden()
        assert widget._unrated_chip.isHidden()
        assert widget._badge.isHidden()
