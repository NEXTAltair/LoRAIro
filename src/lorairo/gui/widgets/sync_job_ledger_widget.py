"""Sync job ledger section for the unified Jobs tab (ADR 0066).

JobLedgerService (in-memory 台帳) の「実行中 / 履歴」を 1 テーブルで表示する。
空状態でもテーブル枠は消さない (ADR 0066 §1: Jobs の半分は台帳)。
実行中の行にはキャンセルボタンを置き、進捗ポップアップ廃止 (§4) に伴う
キャンセル操作の移設先となる。
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lorairo.services.job_ledger_service import JobEntry, JobStatus

_COLUMNS = ("種別", "タイトル", "状態", "開始", "終了", "サマリー", "操作")
_STATUS_LABELS = {
    JobStatus.RUNNING: "実行中",
    JobStatus.QUEUED: "待機中",
    JobStatus.FINISHED: "完了",
    JobStatus.FAILED: "失敗",
    JobStatus.CANCELED: "キャンセル",
}


def _format_time(value: datetime | None) -> str:
    """台帳表示用に時刻を HH:MM:SS 文字列へ変換する。"""
    if value is None:
        return ""
    return value.strftime("%H:%M:%S")


class SyncJobLedgerWidget(QGroupBox):
    """実行中 / 履歴（同期ジョブ）セクション (session-scoped ledger view)."""

    cancel_requested = Signal(str)  # job_id (= worker_id)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("実行中 / 履歴（同期ジョブ）", parent)
        self.setObjectName("syncJobLedgerSection")

        self.tableSyncJobs = QTableWidget(self)
        self.tableSyncJobs.setObjectName("tableSyncJobs")
        self.tableSyncJobs.setColumnCount(len(_COLUMNS))
        self.tableSyncJobs.setHorizontalHeaderLabels(list(_COLUMNS))
        self.tableSyncJobs.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tableSyncJobs.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tableSyncJobs.verticalHeader().setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.tableSyncJobs)

    def set_entries(self, entries: list[JobEntry]) -> None:
        """台帳行を再描画する。

        Args:
            entries: 表示する JobEntry リスト (新しい順)。空でも枠は維持する。
        """
        table = self.tableSyncJobs
        table.setRowCount(0)
        for entry in entries:
            row = table.rowCount()
            table.insertRow(row)
            values = (
                entry.job_type,
                entry.title,
                _STATUS_LABELS.get(entry.status, entry.status.value),
                _format_time(entry.started_at),
                _format_time(entry.finished_at),
                entry.summary,
            )
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(value))
            if not entry.status.is_terminal:
                table.setCellWidget(row, len(_COLUMNS) - 1, self._build_cancel_button(entry.job_id))

    def _build_cancel_button(self, job_id: str) -> QPushButton:
        """実行中行のキャンセルボタンを生成する。"""
        button = QPushButton("キャンセル", self.tableSyncJobs)
        button.setObjectName(f"buttonSyncJobCancel_{job_id}")
        button.clicked.connect(lambda: self.cancel_requested.emit(job_id))
        return button
