"""ErrorsTabWidget の GUI テスト (Epic #867 / #871)。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QVBoxLayout, QWidget

from lorairo.gui.state.staging_state import StagingStateManager
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


@pytest.mark.gui
def test_error_record_to_row_populates_file_path_and_stack_trace() -> None:
    record = SimpleNamespace(
        id=11,
        image_id=22,
        operation_type="annotation",
        error_type="RuntimeError",
        error_message="failed",
        model_name="gpt-4o",
        resolved_at=None,
        created_at=None,
        file_path="/tmp/test.png",
        stack_trace="Traceback: line 1",
    )
    row = ErrorsTabWidget._error_record_to_row(record)
    assert row.file_path == "/tmp/test.png"
    assert row.stack_trace == "Traceback: line 1"


@pytest.mark.gui
def test_image_link_clicked_opens_annotation_review_image(qtbot) -> None:
    host = QWidget()
    host._open_annotation_review_image = MagicMock()  # type: ignore[attr-defined]
    layout = QVBoxLayout(host)
    widget = ErrorsTabWidget(db_manager=_db_with_no_errors(), parent=host)
    layout.addWidget(widget)
    qtbot.addWidget(host)

    widget.triage_widget.image_link_clicked.emit(77)

    host._open_annotation_review_image.assert_called_once_with(77)  # type: ignore[attr-defined]


@pytest.mark.gui
def test_restage_images_requested_adds_images_to_staging_state_manager(qtbot) -> None:
    host = QWidget()
    host.staging_state_manager = MagicMock()  # type: ignore[attr-defined]
    layout = QVBoxLayout(host)
    widget = ErrorsTabWidget(db_manager=_db_with_no_errors(), parent=host)
    layout.addWidget(widget)
    qtbot.addWidget(host)

    widget.triage_widget.restage_images_requested.emit([10, 12])

    host.staging_state_manager.add_images.assert_called_once_with([10, 12])  # type: ignore[attr-defined]


@pytest.mark.gui
def test_restage_resolves_missing_image_ids_from_db_to_dataset_state(qtbot) -> None:
    db = _db_with_no_errors()
    db.get_image_metadata.return_value = {
        "id": 99,
        "stored_image_path": "/path/to/img99.jpg",
    }
    host = QWidget()
    staging_mgr = MagicMock(spec=StagingStateManager)
    dataset_mgr = MagicMock()
    # Image 99 is missing from current search results cache
    dataset_mgr.get_image_by_id.return_value = None
    staging_mgr._dataset_state_manager = dataset_mgr

    host.staging_state_manager = staging_mgr  # type: ignore[attr-defined]
    layout = QVBoxLayout(host)
    widget = ErrorsTabWidget(db_manager=db, parent=host)
    layout.addWidget(widget)
    qtbot.addWidget(host)

    widget.triage_widget.restage_images_requested.emit([99])

    db.get_image_metadata.assert_called_once_with(99)
    dataset_mgr.cache_external_image_metadata.assert_called_once_with(
        {
            "id": 99,
            "stored_image_path": "/path/to/img99.jpg",
        }
    )
    staging_mgr.add_image_ids.assert_called_once_with([99])


@pytest.mark.gui
def test_refresh_sets_truncated_when_records_reach_limit(qtbot) -> None:
    db = MagicMock()
    db.error_record_repo.get_error_records.return_value = [
        SimpleNamespace(
            id=i,
            image_id=i,
            operation_type="annotation",
            error_type="TimeoutError",
            error_message="timeout",
            model_name="gpt-4o",
            resolved_at=None,
            created_at=None,
            file_path=None,
            stack_trace=None,
        )
        for i in range(1, 501)
    ]
    widget = ErrorsTabWidget(db_manager=db)
    qtbot.addWidget(widget)

    widget.refresh()

    assert "最新500件を表示中" in widget.triage_widget._summary_label.text()
    assert not widget.triage_widget._truncation_label.isHidden()


@pytest.mark.gui
def test_restage_batches_missing_image_metadata_resolution(qtbot) -> None:
    db = _db_with_no_errors()
    db.get_images_metadata_batch.return_value = [
        {"id": 101, "stored_image_path": "/path/to/img101.jpg"},
        {"id": 102, "stored_image_path": "/path/to/img102.jpg"},
    ]
    host = QWidget()
    staging_mgr = MagicMock(spec=StagingStateManager)
    dataset_mgr = MagicMock()
    dataset_mgr.get_image_by_id.return_value = None
    staging_mgr._dataset_state_manager = dataset_mgr

    host.staging_state_manager = staging_mgr  # type: ignore[attr-defined]
    layout = QVBoxLayout(host)
    widget = ErrorsTabWidget(db_manager=db, parent=host)
    layout.addWidget(widget)
    qtbot.addWidget(host)

    widget.triage_widget.restage_images_requested.emit([101, 102])

    db.get_images_metadata_batch.assert_called_once_with([101, 102], include_annotations=False)
    db.get_image_metadata.assert_not_called()
    assert dataset_mgr.cache_external_image_metadata.call_count == 2
    staging_mgr.add_image_ids.assert_called_once_with([101, 102])
