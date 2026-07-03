"""SyncJobLedgerWidget (ADR 0066 同期ジョブ台帳セクション) のユニットテスト。"""

from __future__ import annotations

from datetime import datetime

import pytest
from PySide6.QtWidgets import QProgressBar, QPushButton

from lorairo.gui.widgets.ds_card import DsCard
from lorairo.gui.widgets.sync_job_ledger_widget import SyncJobLedgerWidget
from lorairo.services.job_ledger_service import (
    JobEntry,
    JobsSummary,
    JobStatus,
    StageProgress,
)


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
        # DsCard 化に伴い見出しはタイトルラベルとして描画される (QGroupBox.title() 依存を除去)。
        assert widget._title_label is not None
        assert widget._title_label.text() == "実行中 / 履歴（同期ジョブ）"

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
        # 種別 (col0) / 状態 (col2) は DS chip 文法で cellWidget 化 (Issue #790)
        assert table.cellWidget(0, 0).text() == "annotation"
        assert table.item(0, 1).text() == "アノテーション処理"
        assert table.cellWidget(0, 2).text() == "実行中"
        assert table.item(0, 3).text() == "10:30:05"
        assert table.item(0, 4).text() == ""
        assert table.cellWidget(1, 2).text() == "完了"
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

    def test_status_chip_tone_matches_status(self, widget):
        from lorairo.gui import theme

        widget.set_entries(
            [
                _entry(status=JobStatus.FINISHED, finished_at=datetime(2026, 6, 12, 10, 32)),
                _entry(job_id="x", status=JobStatus.FAILED, finished_at=datetime(2026, 6, 12, 10, 33)),
            ]
        )
        # 完了 = ok tone、失敗 = err tone (DS status chip 文法)
        assert theme.OK_SOFT in widget.tableSyncJobs.cellWidget(0, 2).styleSheet()
        assert theme.ERR_SOFT in widget.tableSyncJobs.cellWidget(1, 2).styleSheet()

    def test_kind_badge_uses_badge_qss(self, widget):
        from lorairo.gui import theme

        widget.set_entries([_entry()])
        badge = widget.tableSyncJobs.cellWidget(0, 0)
        assert theme.PAPER_SHADE in badge.styleSheet()

    def test_set_entries_replaces_previous_rows(self, widget):
        widget.set_entries([_entry(), _entry(job_id="annotation_2")])
        widget.set_entries([_entry(job_id="annotation_3")])

        assert widget.tableSyncJobs.rowCount() == 1
        assert widget.tableSyncJobs.cellWidget(0, 0).text() == "annotation"


def _stage(**overrides) -> StageProgress:
    values = {
        "stage": "TAGS",
        "model_name": "wd-tagger",
        "meta": "local",
        "percentage": 67,
        "detail": "6 / 9",
        "tone": "info",
    }
    values.update(overrides)
    return StageProgress(**values)


@pytest.mark.unit
@pytest.mark.gui
class TestSyncJobLedgerSummaryStrip:
    """Issue #805: サマリ帯 (SummaryStat) の表示。"""

    def test_set_summary_updates_stat_values(self, widget):
        widget.set_summary(JobsSummary(running=1, queued=2, done_7d=17, failed_7d=3))

        assert widget._stat_running._value_label.text() == "1"
        assert widget._stat_queued._value_label.text() == "2"
        assert widget._stat_done._value_label.text() == "17"
        assert widget._stat_done._sub_label.text() == "失敗 3"

    def test_api_stat_shows_no_data_honestly(self, widget):
        """API レート使用量は台帳に無い → 捏造せず「データなし」を表示 (空状態の正直表示)。"""
        widget.set_summary(JobsSummary(running=0, queued=0, done_7d=0, failed_7d=0))

        assert widget._stat_api._value_label.text() == "—"
        assert widget._stat_api._sub_label.text() == "データなし"


@pytest.mark.unit
@pytest.mark.gui
class TestSyncJobLedgerRunningStages:
    """Issue #805: 実行中ジョブの per-stage progress カード。"""

    def test_running_entry_with_stages_renders_card(self, widget):
        entry = _entry(stage_progress=[_stage(), _stage(stage="CAPTION", percentage=33, detail="3 / 9")])
        widget.set_entries([entry])

        card = widget.findChild(DsCard, f"jobStageCard_{entry.job_id}")
        assert card is not None
        bars = card.findChildren(QProgressBar)
        assert len(bars) == 2
        assert {bar.value() for bar in bars} == {67, 33}
        assert widget._running_container.isVisibleTo(widget)

    def test_no_stage_data_hides_running_container(self, widget):
        """ステージデータが無ければ実行中コンテナを隠す (空カードを捏造しない)。"""
        widget.set_entries([_entry(stage_progress=[])])

        assert not widget._running_container.isVisibleTo(widget)

    def test_terminal_entry_with_stage_data_not_rendered(self, widget):
        """終端ジョブのステージ進捗カードは出さない (実行中のみ)。"""
        entry = _entry(
            job_id="finished_job",
            status=JobStatus.FINISHED,
            finished_at=datetime(2026, 6, 12, 10, 32),
            stage_progress=[_stage()],
        )
        widget.set_entries([entry])

        assert widget.findChild(DsCard, "jobStageCard_finished_job") is None
        assert not widget._running_container.isVisibleTo(widget)

    def test_set_entries_clears_previous_stage_cards(self, widget):
        widget.set_entries([_entry(job_id="job_a", stage_progress=[_stage()])])
        widget.set_entries([_entry(job_id="job_b", stage_progress=[_stage()])])

        assert widget.findChild(DsCard, "jobStageCard_job_a") is None
        assert widget.findChild(DsCard, "jobStageCard_job_b") is not None
