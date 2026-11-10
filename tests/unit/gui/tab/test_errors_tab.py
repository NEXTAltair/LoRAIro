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


@pytest.mark.gui
def test_combo_filter_selection_preserved_and_filters_on_refresh(qtbot) -> None:
    """combo 変更で refresh() が走っても選択がリセットされず絞り込みが効く (#1536)。"""
    r1 = MagicMock()
    r1.id = 1
    r1.image_id = 10
    r1.operation_type = "annotation"
    r1.error_type = "TimeoutError"
    r1.error_message = "timeout"
    r1.model_name = "gpt-4o"
    r1.resolved_at = None
    r1.created_at = None

    r2 = MagicMock()
    r2.id = 2
    r2.image_id = 11
    r2.operation_type = "upscale"
    r2.error_type = "ValueError"
    r2.error_message = "bad scale"
    r2.model_name = "realesrgan"
    r2.resolved_at = None
    r2.created_at = None

    db = MagicMock()
    db.error_record_repo.get_error_records.return_value = [r1, r2]

    widget = ErrorsTabWidget(db_manager=db)
    qtbot.addWidget(widget)
    widget.refresh()

    triage = widget.triage_widget
    assert len(triage._group_keys()) == 2

    # 操作種別 combo で "upscale" を選択 → filter_changed → refresh() が走る
    idx = triage._operation_combo.findData("upscale")
    assert idx > 0
    triage._operation_combo.setCurrentIndex(idx)

    # 選択が "すべて" に戻らず "upscale" のまま維持され、描画グループも 1 件に絞られる
    assert triage._operation_combo.currentData() == "upscale"
    assert triage.get_filter().operation_type == "upscale"
    assert triage._group_keys() == [("upscale", "ValueError", "realesrgan")]
