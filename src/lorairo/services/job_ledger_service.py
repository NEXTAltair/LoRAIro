"""In-memory job ledger service (ADR 0066 Unified Jobs Lifecycle View).

同期ジョブ (Pipeline / Operation レベル, ADR 0034) のセッションスコープ台帳。
ADR 0066 §2 に従い DB 永続化はしない (アプリ再起動で消える)。
Provider Batch は既存 ``provider_batch_jobs`` テーブルが SSoT のため本台帳には載せない。

Qt-free: GUI への変更通知は WorkerService (Qt 層) が ``job_ledger_changed``
シグナルとして担う。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

# ADR 0066 §5: model installer 用 job_type の予約枠 (DL の job 化実装は別 Phase)
JOB_TYPE_MODEL_INSTALL = "model_install"


class JobStatus(Enum):
    """Ledger-visible lifecycle status of one job (ADR 0066 §1)."""

    RUNNING = "running"
    QUEUED = "queued"
    FINISHED = "finished"
    FAILED = "failed"
    CANCELED = "canceled"

    @property
    def is_terminal(self) -> bool:
        """終端状態 (履歴セクション行き) かどうかを返す。"""
        return self in {JobStatus.FINISHED, JobStatus.FAILED, JobStatus.CANCELED}


@dataclass
class JobEntry:
    """One ledger row for a sync job (session-scoped, in-memory)."""

    job_id: str
    job_type: str
    title: str
    status: JobStatus = JobStatus.RUNNING
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None
    summary: str = ""


class JobLedgerService:
    """In-memory ledger of Pipeline/Operation level jobs (ADR 0066 §2, §3).

    register/update/finish の 3 操作で台帳行を管理する。検索/サムネイル等の
    UI 応答系 Worker は載せない (載せると firehose 化する、ADR 0066 §3)。
    """

    def __init__(self) -> None:
        # 挿入順を保持する dict (Python 3.7+)。表示は新しい順に返す。
        self._entries: dict[str, JobEntry] = {}

    def register(
        self,
        job_id: str,
        job_type: str,
        title: str,
        *,
        status: JobStatus = JobStatus.RUNNING,
    ) -> JobEntry:
        """ジョブを台帳に登録する。

        Args:
            job_id: ジョブ識別子 (worker_id をそのまま使う)。
            job_type: ジョブ種別 ("annotation", "batch_registration" 等)。
            title: 表示タイトル。
            status: 初期状態 (既定 RUNNING。キュー実装時は QUEUED)。

        Returns:
            登録した JobEntry。同一 job_id が既に存在する場合は既存行を返す。
        """
        existing = self._entries.get(job_id)
        if existing is not None:
            return existing
        entry = JobEntry(job_id=job_id, job_type=job_type, title=title, status=status)
        self._entries[job_id] = entry
        return entry

    def update(
        self,
        job_id: str,
        *,
        status: JobStatus | None = None,
        summary: str | None = None,
    ) -> JobEntry | None:
        """ジョブの状態・サマリーを更新する。

        Args:
            job_id: 対象ジョブ識別子。
            status: 新しい状態 (None なら据え置き)。
            summary: 新しいサマリー (None なら据え置き)。

        Returns:
            更新後の JobEntry。未登録の job_id なら None。
        """
        entry = self._entries.get(job_id)
        if entry is None:
            return None
        if status is not None:
            entry.status = status
        if summary is not None:
            entry.summary = summary
        return entry

    def finish(self, job_id: str, status: JobStatus, summary: str = "") -> JobEntry | None:
        """ジョブを終端状態にして finished_at を確定する。

        Args:
            job_id: 対象ジョブ識別子。
            status: 終端状態 (FINISHED / FAILED / CANCELED)。
            summary: 結果サマリー (件数・エラーメッセージ等)。

        Returns:
            更新後の JobEntry。未登録の job_id なら None。

        Raises:
            ValueError: 終端でない status が渡された場合。
        """
        if not status.is_terminal:
            raise ValueError(f"finish() requires a terminal status, got: {status.value}")
        entry = self._entries.get(job_id)
        if entry is None:
            return None
        entry.status = status
        entry.summary = summary
        entry.finished_at = datetime.now()
        return entry

    def get(self, job_id: str) -> JobEntry | None:
        """job_id で台帳行を取得する。"""
        return self._entries.get(job_id)

    def list_entries(self) -> list[JobEntry]:
        """全台帳行を新しい順 (登録の逆順) で返す。"""
        return list(reversed(self._entries.values()))

    def running_entries(self) -> list[JobEntry]:
        """非終端 (running / queued) の行を新しい順で返す。"""
        return [entry for entry in self.list_entries() if not entry.status.is_terminal]
