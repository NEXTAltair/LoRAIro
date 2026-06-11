"""ErrorsTriageWidget 単体テスト。

Track A の ``ErrorTriageService`` 実装には依存せず、hand-built の
dataclass (``ErrorTriageSummary`` / ``ErrorGroup`` / ``ErrorRow``) を渡して
View の描画・シグナル発火・フィルタ状態のみを検証する。

QT_QPA_PLATFORM=offscreen ヘッドレス。signal 検証は qtbot.waitSignal。
"""

import pytest
from PySide6.QtWidgets import QPushButton

from lorairo.gui.widgets.errors_triage_widget import ErrorsTriageWidget
from lorairo.services.error_triage_service import (
    ErrorGroup,
    ErrorRow,
    ErrorStatusFilter,
    ErrorTriageSummary,
)


@pytest.fixture
def summary() -> ErrorTriageSummary:
    return ErrorTriageSummary(
        total=5,
        unresolved=3,
        resolved=2,
        last_24h=1,
        by_error_type={"TimeoutError": 2, "ValueError": 1},
    )


@pytest.fixture
def groups() -> list[ErrorGroup]:
    return [
        ErrorGroup(
            operation_type="annotation",
            error_type="TimeoutError",
            model_name="gpt-4o",
            count=2,
            unresolved_count=2,
            sample_message="request timed out",
            image_ids=[10, 11],
            error_ids=[1, 2],
            unresolved_error_ids=[1, 2],
        ),
        ErrorGroup(
            operation_type="upscale",
            error_type="ValueError",
            model_name=None,
            count=1,
            unresolved_count=1,
            sample_message="invalid scale",
            image_ids=[12],
            error_ids=[3],
            unresolved_error_ids=[3],
        ),
    ]


@pytest.fixture
def rows() -> list[ErrorRow]:
    return [
        ErrorRow(
            error_id=1,
            image_id=10,
            operation_type="annotation",
            error_type="TimeoutError",
            error_message="request timed out",
            model_name="gpt-4o",
            resolved=False,
            created_at=None,
        ),
        ErrorRow(
            error_id=2,
            image_id=11,
            operation_type="annotation",
            error_type="TimeoutError",
            error_message="request timed out again",
            model_name="gpt-4o",
            resolved=True,
            created_at=None,
        ),
        ErrorRow(
            error_id=3,
            image_id=12,
            operation_type="upscale",
            error_type="ValueError",
            error_message="invalid scale",
            model_name=None,
            resolved=False,
            created_at=None,
        ),
    ]


@pytest.fixture
def widget(qtbot) -> ErrorsTriageWidget:
    w = ErrorsTriageWidget()
    qtbot.addWidget(w)
    return w


def _resolve_buttons(widget: ErrorsTriageWidget) -> list[QPushButton]:
    """objectName が errorRowResolveButton_ で始まるボタンを集める。"""
    return [
        btn
        for btn in widget.findChildren(QPushButton)
        if btn.objectName().startswith("errorRowResolveButton_")
    ]


class TestGroupDisplay:
    def test_group_mode_renders_all_groups(self, widget, summary, groups, rows):
        widget.display(summary, groups, rows)

        assert widget.is_grouped() is True
        keys = widget._group_keys()
        assert keys == [
            ("annotation", "TimeoutError", "gpt-4o"),
            ("upscale", "ValueError", None),
        ]

    def test_group_resolve_emits_unresolved_error_ids(self, widget, qtbot, summary, groups, rows):
        widget.display(summary, groups, rows)

        # 各グループカード内の resolve ボタン
        group_buttons = [
            btn for btn in widget.findChildren(QPushButton) if btn.objectName() == "errorGroupResolveButton"
        ]
        assert len(group_buttons) == 2

        with qtbot.waitSignal(widget.resolve_group_requested, timeout=1000) as blocker:
            group_buttons[0].click()
        assert blocker.args == [[1, 2]]


class TestRowDisplay:
    def test_row_mode_renders_unresolved_resolve_buttons(self, widget, summary, groups, rows):
        widget.display(summary, groups, rows)
        widget.toggle_grouped(False)
        widget.display(summary, groups, rows)

        assert widget.is_grouped() is False
        buttons = _resolve_buttons(widget)
        # resolved 済み (error_id=2) は resolve ボタンを持たない
        names = {btn.objectName() for btn in buttons}
        assert names == {"errorRowResolveButton_1", "errorRowResolveButton_3"}

    def test_single_resolve_emits_error_id(self, widget, qtbot, summary, groups, rows):
        widget.toggle_grouped(False)
        widget.display(summary, groups, rows)

        target = next(
            btn for btn in _resolve_buttons(widget) if btn.objectName() == "errorRowResolveButton_3"
        )
        with qtbot.waitSignal(widget.resolve_requested, timeout=1000) as blocker:
            target.click()
        assert blocker.args == [3]


class TestBulkResolve:
    def test_bulk_resolve_aggregates_all_unresolved_ids(self, widget, qtbot, summary, groups, rows):
        widget.display(summary, groups, rows)

        bulk = next(
            btn for btn in widget.findChildren(QPushButton) if btn.objectName() == "errorsBulkResolveButton"
        )
        with qtbot.waitSignal(widget.resolve_group_requested, timeout=1000) as blocker:
            bulk.click()
        assert blocker.args == [[1, 2, 3]]


class TestFilterChanged:
    def test_status_segment_emits_filter_changed(self, widget, qtbot, summary, groups, rows):
        widget.set_filter_options(["annotation", "upscale"], ["TimeoutError", "ValueError"], ["gpt-4o"])
        widget.display(summary, groups, rows)

        with qtbot.waitSignal(widget.filter_changed, timeout=1000):
            widget.toggle_grouped(False)

    def test_get_filter_reflects_status_selection(self, widget, summary, groups, rows):
        widget.set_filter_options(["annotation"], ["TimeoutError"], ["gpt-4o"])
        widget.display(summary, groups, rows)

        result = widget.get_filter()
        assert result.status == ErrorStatusFilter.UNRESOLVED


class TestEmptyState:
    def test_empty_state_shown_when_no_data(self, widget):
        empty_summary = ErrorTriageSummary(total=0, unresolved=0, resolved=0, last_24h=0, by_error_type={})
        widget.display(empty_summary, [], [])

        empty = next(
            (
                child
                for child in widget.findChildren(object)
                if hasattr(child, "objectName") and child.objectName() == "errorsEmptyState"
            ),
            None,
        )
        assert empty is not None
        assert empty.isVisible() or not empty.isHidden()
