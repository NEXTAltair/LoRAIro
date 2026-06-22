"""ErrorsTabWidget の GUI テスト (Epic #867 / #871)。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from lorairo.gui.tab.errors_tab import ErrorsTabWidget
from lorairo.gui.widgets.errors_triage_widget import ErrorsTriageWidget


def _db_with_no_errors() -> MagicMock:
    db = MagicMock()
    db.error_record_repo.get_error_records.return_value = []
    return db


@pytest.mark.gui
def test_errors_tab_hosts_triage_widget(qtbot) -> None:
    widget = ErrorsTabWidget(db_manager=_db_with_no_errors())
    qtbot.addWidget(widget)

    assert isinstance(widget.triage_widget, ErrorsTriageWidget)
    assert widget.triage_widget.parent() is widget


@pytest.mark.gui
def test_resolve_marks_resolved_and_emits(qtbot) -> None:
    db = _db_with_no_errors()
    db.mark_errors_resolved_batch.return_value = (True, 1)
    widget = ErrorsTabWidget(db_manager=db)
    qtbot.addWidget(widget)

    with qtbot.waitSignal(widget.errors_resolved, timeout=1000):
        widget.triage_widget.resolve_requested.emit(7)

    db.mark_errors_resolved_batch.assert_called_once_with([7])


@pytest.mark.gui
def test_resolve_group_marks_all(qtbot) -> None:
    db = _db_with_no_errors()
    db.mark_errors_resolved_batch.return_value = (True, 3)
    widget = ErrorsTabWidget(db_manager=db)
    qtbot.addWidget(widget)

    widget.triage_widget.resolve_group_requested.emit([1, 2, 3])

    db.mark_errors_resolved_batch.assert_called_once_with([1, 2, 3])


@pytest.mark.gui
def test_refresh_without_db_does_not_crash(qtbot) -> None:
    widget = ErrorsTabWidget(db_manager=None)
    qtbot.addWidget(widget)

    widget.refresh()  # 例外なし
