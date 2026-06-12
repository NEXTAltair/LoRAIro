"""JobLedgerService (ADR 0066) のユニットテスト。

セッションスコープ in-memory 台帳の register/update/finish ライフサイクルと
表示順 (新しい順)・終端状態判定を検証する。
"""

from __future__ import annotations

import pytest

from lorairo.services.job_ledger_service import (
    JOB_TYPE_MODEL_INSTALL,
    JobLedgerService,
    JobStatus,
)


@pytest.fixture
def ledger() -> JobLedgerService:
    return JobLedgerService()


@pytest.mark.unit
class TestJobLedgerService:
    def test_register_creates_running_entry(self, ledger):
        entry = ledger.register("annotation_1", "annotation", "アノテーション処理")

        assert entry.job_id == "annotation_1"
        assert entry.job_type == "annotation"
        assert entry.title == "アノテーション処理"
        assert entry.status is JobStatus.RUNNING
        assert entry.started_at is not None
        assert entry.finished_at is None
        assert entry.summary == ""

    def test_register_with_queued_status(self, ledger):
        entry = ledger.register("annotation_q", "annotation", "queued job", status=JobStatus.QUEUED)

        assert entry.status is JobStatus.QUEUED
        assert entry in ledger.running_entries()

    def test_register_duplicate_job_id_returns_existing_entry(self, ledger):
        first = ledger.register("job_1", "annotation", "first")
        second = ledger.register("job_1", "batch_import", "second")

        assert second is first
        assert len(ledger.list_entries()) == 1
        assert ledger.get("job_1").title == "first"

    def test_update_status_and_summary(self, ledger):
        ledger.register("job_1", "annotation", "title")

        entry = ledger.update("job_1", status=JobStatus.QUEUED, summary="待機中")

        assert entry is not None
        assert entry.status is JobStatus.QUEUED
        assert entry.summary == "待機中"

    def test_update_partial_keeps_other_fields(self, ledger):
        ledger.register("job_1", "annotation", "title")
        ledger.update("job_1", summary="only summary")

        entry = ledger.get("job_1")
        assert entry.status is JobStatus.RUNNING
        assert entry.summary == "only summary"

    def test_update_unknown_job_returns_none(self, ledger):
        assert ledger.update("missing", status=JobStatus.QUEUED) is None

    @pytest.mark.parametrize(
        "terminal_status",
        [JobStatus.FINISHED, JobStatus.FAILED, JobStatus.CANCELED],
    )
    def test_finish_sets_terminal_status_and_finished_at(self, ledger, terminal_status):
        ledger.register("job_1", "annotation", "title")

        entry = ledger.finish("job_1", terminal_status, summary="done")

        assert entry is not None
        assert entry.status is terminal_status
        assert entry.status.is_terminal
        assert entry.finished_at is not None
        assert entry.summary == "done"
        assert entry not in ledger.running_entries()

    @pytest.mark.parametrize("non_terminal", [JobStatus.RUNNING, JobStatus.QUEUED])
    def test_finish_rejects_non_terminal_status(self, ledger, non_terminal):
        ledger.register("job_1", "annotation", "title")

        with pytest.raises(ValueError, match="terminal status"):
            ledger.finish("job_1", non_terminal)

    def test_finish_unknown_job_returns_none(self, ledger):
        assert ledger.finish("missing", JobStatus.FINISHED) is None

    def test_list_entries_newest_first(self, ledger):
        ledger.register("job_1", "annotation", "first")
        ledger.register("job_2", "batch_registration", "second")
        ledger.register("job_3", "batch_import", "third")

        assert [entry.job_id for entry in ledger.list_entries()] == ["job_3", "job_2", "job_1"]

    def test_running_entries_excludes_terminal(self, ledger):
        ledger.register("job_1", "annotation", "running")
        ledger.register("job_2", "annotation", "finished")
        ledger.finish("job_2", JobStatus.FINISHED)

        running_ids = [entry.job_id for entry in ledger.running_entries()]
        assert running_ids == ["job_1"]

    def test_ledger_is_session_scoped_in_memory(self):
        """別インスタンスは台帳を共有しない (DB 永続化しない、ADR 0066 §2)"""
        first = JobLedgerService()
        first.register("job_1", "annotation", "title")

        assert JobLedgerService().list_entries() == []

    def test_model_install_job_type_reserved(self, ledger):
        """ADR 0066 §5: model installer 用 job_type 予約枠が利用できる"""
        entry = ledger.register("install_1", JOB_TYPE_MODEL_INSTALL, "モデルインストール")

        assert entry.job_type == "model_install"
