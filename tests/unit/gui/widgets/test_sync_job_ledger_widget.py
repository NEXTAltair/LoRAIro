"""SyncJobLedgerWidget (ADR 0066 同期ジョブ台帳セクション) のユニットテスト。"""

from __future__ import annotations

from datetime import datetime

import pytest
from PySide6.QtWidgets import QPushButton

from lorairo.gui.widgets.sync_job_ledger_widget import SyncJobLedgerWidget
from lorairo.services.job_ledger_service import JobEntry, JobStatus


@pytest.fixture
def widget(qtbot):
    ledger_widget = SyncJobLedgerWidget()
    qtbot.addWidget(ledger_widget)
    return ledger_widget


def _entry(**overrides) -> JobEntry:
    values = {
        "job_id": "annotation_1",
        "job_type": "annotation",
        "title": "アノテーション処理",
        "status": JobStatus.RUNNING,
        "started_at": datetime(2026, 6, 12, 10, 30, 5),
        "finished_at": None,
        "summary": "",
    }
    values.update(overrides)
    return JobEntry(**values)


@pytest.mark.unit
@pytest.mark.gui
class TestSyncJobLedgerWidget:
    def test_empty_state_keeps_table_frame(self, widget):
        """空状態でも履歴テーブルの枠は消さない (ADR 0066 §1)"""
        widget.set_entries([])

        assert widget.tableSyncJobs.isVisibleTo(widget)
        assert widget.tableSyncJobs.columnCount() == 7
        assert widget.tableSyncJobs.rowCount() == 0
        assert widget.title() == "実行中 / 履歴（同期ジョブ）"

    def test_set_entries_renders_rows(self, widget):
        entries = [
            _entry(),
            _entry(
                job_id="batch_reg_2",
                job_type="batch_registration",
                title="データベース登録",
                status=JobStatus.FINISHED,
                finished_at=datetime(2026, 6, 12, 10, 31, 45),
                summary="登録完了",
            ),
        ]

        widget.set_entries(entries)

        table = widget.tableSyncJobs
        assert table.rowCount() == 2
        assert table.item(0, 0).text() == "annotation"
        assert table.item(0, 1).text() == "アノテーション処理"
        assert table.item(0, 2).text() == "実行中"
        assert table.item(0, 3).text() == "10:30:05"
        assert table.item(0, 4).text() == ""
        assert table.item(1, 2).text() == "完了"
        assert table.item(1, 4).text() == "10:31:45"
        assert table.item(1, 5).text() == "登録完了"

    def test_running_entry_has_cancel_button(self, widget):
        widget.set_entries([_entry()])

        button = widget.tableSyncJobs.cellWidget(0, 6)
        assert isinstance(button, QPushButton)
        assert button.text() == "キャンセル"

    @pytest.mark.parametrize(
        "status",
        [JobStatus.FINISHED, JobStatus.FAILED, JobStatus.CANCELED],
    )
    def test_terminal_entry_has_no_cancel_button(self, widget, status):
        widget.set_entries([_entry(status=status, finished_at=datetime(2026, 6, 12, 10, 32))])

        assert widget.tableSyncJobs.cellWidget(0, 6) is None

    def test_cancel_button_emits_cancel_requested_with_job_id(self, widget, qtbot):
        widget.set_entries([_entry(job_id="annotation_cancel_me")])
        button = widget.tableSyncJobs.cellWidget(0, 6)

        with qtbot.waitSignal(widget.cancel_requested, timeout=1000) as blocker:
            button.click()

        assert blocker.args == ["annotation_cancel_me"]

    def test_set_entries_replaces_previous_rows(self, widget):
        widget.set_entries([_entry(), _entry(job_id="annotation_2")])
        widget.set_entries([_entry(job_id="annotation_3")])

        assert widget.tableSyncJobs.rowCount() == 1
        assert widget.tableSyncJobs.item(0, 0).text() == "annotation"
