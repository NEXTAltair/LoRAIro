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
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lorairo.gui import theme
from lorairo.services.job_ledger_service import (
    JobEntry,
    JobsSummary,
    JobStatus,
    StageProgress,
)

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

# Issue #805: ステージ進捗の tone → ProgressBar chunk 色 / done テキスト色
_STAGE_TONE_COLORS: dict[str, str] = {
    "ok": theme.OK,
    "info": theme.INFO,
    "err": theme.ERR,
}


def _format_time(value: datetime | None) -> str:
    """台帳表示用に時刻を HH:MM:SS 文字列へ変換する。"""
    if value is None:
        return ""
    return value.strftime("%H:%M:%S")


class _SummaryStatCard(QFrame):
    """サマリ帯 1 マス (DS SummaryStat 文法、Issue #805)。

    大きな値 + キャプション + 補助テキストの 3 段。tone で値の色を切り替える。
    """

    def __init__(self, caption: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("jobSummaryStat")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(1)

        self._value_label = QLabel("0", self)
        value_font = QFont()
        value_font.setPointSize(theme.FONT_SIZE_BASE + 4)
        value_font.setWeight(QFont.Weight.Bold)
        self._value_label.setFont(value_font)

        self._caption_label = QLabel(caption, self)
        caption_font = QFont()
        caption_font.setPointSize(theme.FONT_SIZE_SMALL)
        self._caption_label.setFont(caption_font)
        self._caption_label.setStyleSheet(f"color: {theme.INK_SOFT};")

        self._sub_label = QLabel("", self)
        self._sub_label.setFont(caption_font)
        self._sub_label.setStyleSheet(f"color: {theme.INK_FAINT};")

        layout.addWidget(self._value_label)
        layout.addWidget(self._caption_label)
        layout.addWidget(self._sub_label)

    def set_values(self, value: str, sub: str, tone: theme.ChipKind = "neutral") -> None:
        """値・補助テキスト・tone を更新する。"""
        self._value_label.setText(value)
        self._sub_label.setText(sub)
        color = _STAGE_TONE_COLORS.get(tone, theme.INK)
        if tone == "warn":
            color = theme.WARN
        elif tone == "neutral":
            color = theme.INK
        self._value_label.setStyleSheet(f"color: {color};")


class SyncJobLedgerWidget(QGroupBox):
    """実行中 / 履歴（同期ジョブ）セクション (session-scoped ledger view)."""

    cancel_requested = Signal(str)  # job_id (= worker_id)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("実行中 / 履歴（同期ジョブ）", parent)
        self.setObjectName("syncJobLedgerSection")

        # DS JobsScreen サマリ帯 (Issue #805): running / queued / done(7d) / API使用
        self._summary_strip = QWidget(self)
        self._summary_strip.setObjectName("jobSummaryStrip")
        summary_layout = QHBoxLayout(self._summary_strip)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(6)
        self._stat_running = _SummaryStatCard("実行中 running", self._summary_strip)
        self._stat_queued = _SummaryStatCard("待機 queued", self._summary_strip)
        self._stat_done = _SummaryStatCard("過去7日完了 done (7d)", self._summary_strip)
        self._stat_api = _SummaryStatCard("API使用 (1m)", self._summary_strip)
        for card in (self._stat_running, self._stat_queued, self._stat_done, self._stat_api):
            summary_layout.addWidget(card)

        # DS JobsScreen 実行中パイプライン (Issue #805): ジョブごとの per-stage カード
        self._running_container = QWidget(self)
        self._running_container.setObjectName("jobRunningStages")
        self._running_layout = QVBoxLayout(self._running_container)
        self._running_layout.setContentsMargins(0, 0, 0, 0)
        self._running_layout.setSpacing(6)

        self.tableSyncJobs = QTableWidget(self)
        self.tableSyncJobs.setObjectName("tableSyncJobs")
        self.tableSyncJobs.setColumnCount(len(_COLUMNS))
        self.tableSyncJobs.setHorizontalHeaderLabels(list(_COLUMNS))
        self.tableSyncJobs.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tableSyncJobs.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tableSyncJobs.verticalHeader().setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._summary_strip)
        layout.addWidget(self._running_container)
        layout.addWidget(self.tableSyncJobs)

        # 初期表示は空集計 (データなしを正直に出す)
        self.set_summary(JobsSummary(running=0, queued=0, done_7d=0, failed_7d=0))

    def set_summary(self, summary: JobsSummary) -> None:
        """サマリ帯を更新する (Issue #805)。

        Args:
            summary: 台帳から算出した集計値。API 使用量は台帳に無いため
                「データなし」を正直に表示する。
        """
        self._stat_running.set_values(
            str(summary.running), "同期ジョブ", "info" if summary.running else "neutral"
        )
        self._stat_queued.set_values(
            str(summary.queued), "GPU 直列待機", "warn" if summary.queued else "neutral"
        )
        done_sub = f"失敗 {summary.failed_7d}" if summary.failed_7d else "失敗 0"
        self._stat_done.set_values(str(summary.done_7d), done_sub, "ok" if summary.done_7d else "neutral")
        # API レート使用量は in-memory 台帳に無い → 捏造せず「データなし」を表示
        self._stat_api.set_values("—", "データなし", "neutral")

    def set_entries(self, entries: list[JobEntry]) -> None:
        """台帳行を再描画する。

        Args:
            entries: 表示する JobEntry リスト (新しい順)。空でも枠は維持する。
        """
        self._render_running_stages(entries)
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

    # -- 実行中パイプライン (per-stage progress カード, Issue #805) ------------

    def _render_running_stages(self, entries: list[JobEntry]) -> None:
        """実行中ジョブのステージ別進捗カードを再描画する。

        ステージ進捗データを持つ実行中 (非終端) ジョブのみカード化する。データが
        無ければコンテナを隠し、捏造した空カードは出さない (Issue #805)。

        Args:
            entries: 表示候補の JobEntry リスト (新しい順)。
        """
        self._clear_running_stages()
        running_with_stages = [
            entry for entry in entries if not entry.status.is_terminal and entry.stage_progress
        ]
        for entry in running_with_stages:
            self._running_layout.addWidget(self._build_stage_card(entry))
        self._running_container.setVisible(bool(running_with_stages))

    def _clear_running_stages(self) -> None:
        """実行中ステージカードを全削除する。"""
        while self._running_layout.count():
            item = self._running_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                # deleteLater は遅延削除のため、即座に親子関係を切って再描画と
                # findChild の整合を保つ。
                widget.setParent(None)
                widget.deleteLater()

    def _build_stage_card(self, entry: JobEntry) -> QGroupBox:
        """1 ジョブ分のステージ別進捗カードを生成する。"""
        card = QGroupBox(f"▶ 実行中 — {entry.title}", self._running_container)
        card.setObjectName(f"jobStageCard_{entry.job_id}")
        grid = QGridLayout(card)
        grid.setContentsMargins(6, 6, 6, 6)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(3)
        grid.setColumnStretch(2, 1)
        for row, stage in enumerate(entry.stage_progress):
            grid.addWidget(self._build_stage_label(stage.stage), row, 0)
            grid.addWidget(self._build_model_label(stage), row, 1)
            grid.addWidget(self._build_stage_bar(stage), row, 2)
            grid.addWidget(self._build_detail_label(stage), row, 3)
        return card

    def _build_stage_label(self, stage: str) -> QLabel:
        """ステージラベル (TAGS / CAPTION 等) を生成する。"""
        label = QLabel(stage, self._running_container)
        font = QFont()
        font.setPointSize(theme.FONT_SIZE_SMALL)
        font.setWeight(QFont.Weight.Bold)
        label.setFont(font)
        label.setStyleSheet(f"color: {theme.INK_SOFT};")
        return label

    def _build_model_label(self, stage: StageProgress) -> QLabel:
        """モデル名 + メタ (provider / 経路) ラベルを生成する。"""
        label = QLabel(f"{stage.model_name}  ·  {stage.meta}", self._running_container)
        font = QFont()
        font.setPointSize(theme.FONT_SIZE_SMALL)
        label.setFont(font)
        label.setStyleSheet(f"color: {theme.INK_FAINT};")
        return label

    def _build_stage_bar(self, stage: StageProgress) -> QProgressBar:
        """ステージ進捗バー (tone により chunk 色を変える) を生成する。"""
        bar = QProgressBar(self._running_container)
        bar.setRange(0, 100)
        bar.setValue(stage.percentage)
        bar.setTextVisible(False)
        bar.setFixedHeight(10)
        chunk_color = _STAGE_TONE_COLORS.get(stage.tone, theme.INFO)
        bar.setStyleSheet(f"QProgressBar::chunk {{ background-color: {chunk_color}; }}")
        return bar

    def _build_detail_label(self, stage: StageProgress) -> QLabel:
        """done テキスト (mono、tone 色) を生成する。"""
        label = QLabel(stage.detail, self._running_container)
        font = QFont(theme.FONT_MONO_FAMILIES[0])
        font.setPointSize(theme.FONT_SIZE_SMALL)
        label.setFont(font)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        color = _STAGE_TONE_COLORS.get(stage.tone, theme.INK_SOFT)
        label.setStyleSheet(f"color: {color};")
        return label
