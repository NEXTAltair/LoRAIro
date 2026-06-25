"""JobLedgerService (ADR 0066) のユニットテスト。

セッションスコープ in-memory 台帳の register/update/finish ライフサイクルと
表示順 (新しい順)・終端状態判定を検証する。
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from lorairo.services.job_ledger_service import (
    JOB_TYPE_MODEL_INSTALL,
    JobLedgerService,
    JobStatus,
    StageModelInput,
    build_stage_progress,
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


@pytest.mark.unit
class TestStageProgress:
    """Issue #805: build_stage_progress / set_stage_progress のステージ別進捗。"""

    def test_capabilities_expand_to_stage_rows_in_display_order(self):
        models = [
            StageModelInput("wd-rating", "wd-rating", "local", ["ratings"], False),
            StageModelInput("wd-tagger", "wd-tagger", "local", ["tags", "captions"], False),
        ]

        stages = build_stage_progress(models, processed_count=3, total_count=9)

        # TAGS → CAPTION → SCORE → RATING の表示順にソートされる
        assert [s.stage for s in stages] == ["TAGS", "CAPTION", "RATING"]
        tags_row = stages[0]
        assert tags_row.model_name == "wd-tagger"
        assert tags_row.percentage == 33  # 3 / 9
        assert tags_row.detail == "3 / 9"
        assert tags_row.tone == "info"

    def test_finished_marks_all_stages_complete(self):
        models = [StageModelInput("wd-tagger", "wd-tagger", "local", ["tags"], False)]

        stages = build_stage_progress(models, processed_count=9, total_count=9, finished=True)

        assert stages[0].percentage == 100
        assert stages[0].detail == "9 / 9"
        assert stages[0].tone == "ok"

    def test_errored_model_marked_as_failure(self):
        models = [StageModelInput("gpt-4o", "gpt-4o", "openai", ["captions"], True)]

        stages = build_stage_progress(
            models,
            processed_count=0,
            total_count=9,
            errored_keys={"gpt-4o"},
        )

        assert stages[0].tone == "err"
        assert stages[0].detail == "失敗"
        assert stages[0].meta == "openai · api"

    def test_completed_model_subset_marked_done(self):
        models = [
            StageModelInput("done-model", "done-model", "local", ["tags"], False),
            StageModelInput("running-model", "running-model", "local", ["tags"], False),
        ]

        stages = build_stage_progress(
            models,
            processed_count=0,
            total_count=9,
            completed_keys={"done-model"},
        )

        by_name = {s.model_name: s for s in stages}
        assert by_name["done-model"].tone == "ok"
        assert by_name["done-model"].percentage == 100
        assert by_name["running-model"].tone == "info"
        # 未完了モデルは 0% (false 100% を出さない、Codex P2)
        assert by_name["running-model"].percentage == 0

    def test_completion_keyed_by_unique_key_not_display_name(self):
        """同一表示名へ解決する別ルートを取り違えない (Codex P2: route id 衝突)。"""
        models = [
            StageModelInput("route-direct", "gpt-4o", "openai", ["captions"], True),
            StageModelInput("route-openrouter", "gpt-4o", "openrouter", ["captions"], True),
        ]

        stages = build_stage_progress(
            models,
            processed_count=0,
            total_count=9,
            completed_keys={"route-direct"},
        )

        # 同じ model_name でもキーが違えば別行として完了/未完了が分かれる
        tones = [s.tone for s in stages]
        assert sorted(tones) == ["info", "ok"]

    def test_singular_capability_aliases_map_to_stages(self):
        """単数形 capability ("caption"/"score"/"rating"/"tag") も正しいステージへ (Codex P2)。"""
        models = [
            StageModelInput("m", "m", "openai", ["tag", "caption", "score", "rating"], True),
        ]

        stages = build_stage_progress(models, processed_count=0, total_count=1)

        assert {s.stage for s in stages} == {"TAGS", "CAPTION", "SCORE", "RATING"}
        assert all(s.stage != "ANNOTATE" for s in stages)

    def test_unknown_capability_falls_back_to_annotate_stage(self):
        models = [StageModelInput("mystery", "mystery", "", [], False)]

        stages = build_stage_progress(models, processed_count=0, total_count=4)

        assert stages[0].stage == "ANNOTATE"
        assert stages[0].meta == "local"

    def test_empty_total_count_yields_zero_percentage(self):
        models = [StageModelInput("wd-tagger", "wd-tagger", "local", ["tags"], False)]

        stages = build_stage_progress(models, processed_count=0, total_count=0)

        assert stages[0].percentage == 0
        assert stages[0].detail == ""

    def test_set_stage_progress_updates_entry(self, ledger):
        ledger.register("annotation_1", "annotation", "アノテーション処理")
        models = [StageModelInput("wd-tagger", "wd-tagger", "local", ["tags"], False)]
        stages = build_stage_progress(models, processed_count=1, total_count=2)

        entry = ledger.set_stage_progress("annotation_1", stages)

        assert entry is not None
        assert entry.stage_progress == stages
        assert ledger.get("annotation_1").stage_progress[0].stage == "TAGS"

    def test_set_stage_progress_unknown_job_returns_none(self, ledger):
        assert ledger.set_stage_progress("missing", []) is None


@pytest.mark.unit
class TestJobsSummary:
    """Issue #805: サマリ帯 (SummaryStat) の集計。"""

    def test_counts_running_queued_and_recent_terminal(self, ledger):
        ledger.register("run_1", "annotation", "running")
        ledger.register("queue_1", "annotation", "queued", status=JobStatus.QUEUED)
        ledger.register("done_1", "annotation", "done")
        ledger.finish("done_1", JobStatus.FINISHED)
        ledger.register("fail_1", "annotation", "failed")
        ledger.finish("fail_1", JobStatus.FAILED)

        summary = ledger.summary()

        assert summary.running == 1
        assert summary.queued == 1
        assert summary.done_7d == 1
        assert summary.failed_7d == 1

    def test_terminal_older_than_window_excluded(self, ledger):
        ledger.register("done_old", "annotation", "old done")
        ledger.finish("done_old", JobStatus.FINISHED)

        # 完了から 8 日後を基準にすると 7 日窓の外
        future = datetime.now() + timedelta(days=8)
        summary = ledger.summary(now=future)

        assert summary.done_7d == 0

    def test_empty_ledger_summary_is_zero(self, ledger):
        summary = ledger.summary()

        assert (summary.running, summary.queued, summary.done_7d, summary.failed_7d) == (0, 0, 0, 0)
