"""Sync job ledger section for the unified Jobs tab (ADR 0066).

JobLedgerService (in-memory 台帳) の「実行中 / 履歴」を 1 テーブルで表示する。
空状態でもテーブル枠は消さない (ADR 0066 §1: Jobs の半分は台帳)。
実行中の行にはキャンセルボタンを置き、進捗ポップアップ廃止 (§4) に伴う
キャンセル操作の移設先となる。
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lorairo.gui import theme
from lorairo.services.job_ledger_service import JobEntry, JobStatus

_COLUMNS = ("種別", "タイトル", "状態", "開始", "終了", "サマリー", "操作")
_STATUS_LABELS = {
    JobStatus.RUNNING: "実行中",
    JobStatus.QUEUED: "待機中",
    JobStatus.FINISHED: "完了",
    JobStatus.FAILED: "失敗",
    JobStatus.CANCELED: "キャンセル",
}

# DS v12 JobsScreen 履歴 (Issue #790): 状態 → chip 文法の kind
_STATUS_CHIP_KINDS: dict[JobStatus, theme.ChipKind] = {
    JobStatus.RUNNING: "info",
    JobStatus.QUEUED: "neutral",
    JobStatus.FINISHED: "ok",
    JobStatus.FAILED: "err",
    JobStatus.CANCELED: "muted",
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

            # 種別 = TypeBadge 文法、状態 = status chip 文法 (DS v12)
            table.setCellWidget(row, 0, self._build_badge(entry.job_type))
            table.setItem(row, 1, QTableWidgetItem(entry.title))
            status_label = _STATUS_LABELS.get(entry.status, entry.status.value)
            table.setCellWidget(row, 2, self._build_status_chip(status_label, entry.status))
            table.setItem(row, 3, QTableWidgetItem(_format_time(entry.started_at)))
            table.setItem(row, 4, QTableWidgetItem(_format_time(entry.finished_at)))
            table.setItem(row, 5, self._build_summary_item(entry.summary, entry.status))

            if not entry.status.is_terminal:
                table.setCellWidget(row, len(_COLUMNS) - 1, self._build_cancel_button(entry.job_id))

    def _build_badge(self, job_type: str) -> QLabel:
        """種別バッジ (DS TypeBadge 文法) を生成する。"""
        label = QLabel(job_type, self.tableSyncJobs)
        label.setObjectName("jobKindBadge")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(theme.badge_qss())
        return label

    def _build_status_chip(self, text: str, status: JobStatus) -> QLabel:
        """状態 chip (DS status chip 文法、tone は JobStatus 由来) を生成する。"""
        label = QLabel(text, self.tableSyncJobs)
        label.setObjectName("jobStatusChip")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(theme.chip_qss(_STATUS_CHIP_KINDS.get(status, "neutral")))
        return label

    def _build_summary_item(self, summary: str, status: JobStatus) -> QTableWidgetItem:
        """結果サマリーセル (mono、失敗は err 色) を生成する。"""
        item = QTableWidgetItem(summary)
        font = QFont(theme.FONT_MONO_FAMILIES[0])
        font.setPointSize(theme.FONT_SIZE_SMALL)
        item.setFont(font)
        if status is JobStatus.FAILED:
            item.setForeground(QColor(theme.ERR))
        else:
            item.setForeground(QColor(theme.INK_SOFT))
        return item

    def _build_cancel_button(self, job_id: str) -> QPushButton:
        """実行中行のキャンセルボタンを生成する。"""
        button = QPushButton("キャンセル", self.tableSyncJobs)
        button.setObjectName(f"buttonSyncJobCancel_{job_id}")
        button.clicked.connect(lambda: self.cancel_requested.emit(job_id))
        return button
