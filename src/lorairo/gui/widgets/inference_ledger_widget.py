"""DS v12 AnnotateScreen の INFERENCE LEDGER (推論台帳) card (表示専用)。

推論回数 = ユニークモデル × ステージング枚数 の DsSummaryStat グリッドと、
ユニークモデルごとのエントリチップ (multimodal は「N枠 → 1推論」バッジ併記) を
DsCard 面で描画する。
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from lorairo.gui import theme
from lorairo.gui.widgets.ds import DsCard, DsSummaryStat
from lorairo.services.cost_estimation_service import (
    CostEstimationService,
    format_duration,
)
from lorairo.services.pipeline_composition import InferenceLedger, LedgerEntry

_TITLE_TEXT = "INFERENCE LEDGER"
_PLACEHOLDER_TEXT = "モデル未選択"
_MULTI_NOTE_TEXT = "multimodal: 複数ステージに出力しても 1 推論として課金"

# DS v12 AnnotateScreen ledger (Issue #787): エントリ = TypeBadge 文法 (paper-shade 地 +
# line border の mono バッジ)、multimodal 集約バッジ = accent-soft の mono バッジ。
_ENTRY_CHIP_STYLE = (
    f"QLabel {{ font-family: {theme.FONT_MONO_CSS}; background-color: {theme.PAPER_SHADE};"
    f" color: {theme.INK_SOFT}; border: {theme.BORDER_WIDTH}px solid {theme.LINE};"
    f" border-radius: {theme.RADIUS_BADGE}px; padding: 1px 6px;"
    f" font-size: {theme.FONT_SIZE_META}px; }}"
)
_MULTI_BADGE_STYLE = (
    f"QLabel {{ font-family: {theme.FONT_MONO_CSS}; background-color: {theme.ACCENT_SOFT};"
    f" color: {theme.ACCENT_HOVER}; border: {theme.BORDER_WIDTH}px solid {theme.ACCENT_BORDER};"
    f" border-radius: {theme.RADIUS_BADGE}px; padding: 1px 6px;"
    f" font-size: {theme.FONT_SIZE_META}px; font-weight: {theme.FONT_WEIGHT_SEMIBOLD}; }}"
)


class InferenceLedgerWidget(DsCard):
    """DS v12 AnnotateScreen の INFERENCE LEDGER (推論台帳) card。

    DsCard を継承し、DsSummaryStat グリッド (ユニークモデル / × staged /
    推論ジョブ合計 / 推定) + モデルバッジ + multimodal dedupe 注記を描画する。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(title=_TITLE_TEXT, parent=parent)

        self._cost_service = CostEstimationService()

        # card 本体エリア
        body = QWidget(self)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(theme.SPACE_2)

        # ---- DsSummaryStat グリッド (4 KPI) ----
        # 非表示コンテナで show/hide を一括管理する
        self._stats_widget = QWidget(body)
        stats_row = QHBoxLayout(self._stats_widget)
        stats_row.setContentsMargins(0, 0, 0, 0)
        stats_row.setSpacing(theme.SPACE_3)

        self._stat_unique_models = DsSummaryStat(
            label="ユニークモデル", value="—", parent=self._stats_widget
        )
        self._stat_unique_models.setObjectName("ledgerStatUniqueModels")
        stats_row.addWidget(self._stat_unique_models)

        self._stat_staged = DsSummaryStat(label="× staged", value="—", parent=self._stats_widget)
        self._stat_staged.setObjectName("ledgerStatStaged")
        stats_row.addWidget(self._stat_staged)

        # 推論ジョブ合計 = accent 強調
        self._stat_total_jobs = DsSummaryStat(
            label="推論ジョブ合計", value="—", tone="accent", parent=self._stats_widget
        )
        self._stat_total_jobs.setObjectName("ledgerStatTotalJobs")
        stats_row.addWidget(self._stat_total_jobs)

        # 推定コスト・時間 = info 色
        self._stat_estimate = DsSummaryStat(label="推定", value="—", tone="info", parent=self._stats_widget)
        self._stat_estimate.setObjectName("ledgerStatEstimate")
        stats_row.addWidget(self._stat_estimate)

        stats_row.addStretch(1)
        body_layout.addWidget(self._stats_widget)

        # ---- モデルバッジ行 ----
        self._entries_layout = QHBoxLayout()
        self._entries_layout.setContentsMargins(0, 0, 0, 0)
        self._entries_layout.setSpacing(theme.SPACE_1)
        body_layout.addLayout(self._entries_layout)

        # multimodal dedupe 注記 (multimodal エントリが存在するときのみ表示)
        self._multi_note_label = QLabel(_MULTI_NOTE_TEXT, body)
        self._multi_note_label.setObjectName("ledgerMultiNote")
        self._multi_note_label.setStyleSheet(
            f"color: {theme.INK_FAINT}; font-size: {theme.FONT_SIZE_META}px;"
        )
        body_layout.addWidget(self._multi_note_label)

        # プレースホルダ (モデル未選択時)
        self._placeholder_label = QLabel(_PLACEHOLDER_TEXT, body)
        self._placeholder_label.setObjectName("ledgerPlaceholderLabel")
        self._placeholder_label.setStyleSheet(f"color: {theme.INK_FAINT};")
        body_layout.addWidget(self._placeholder_label)

        body_layout.addStretch(1)
        self.set_body(body)

        self.clear()

    def display(self, ledger: InferenceLedger) -> None:
        """台帳を再描画する。

        Args:
            ledger: 推論台帳データ。
        """
        self._clear_entries()
        if not ledger.entries or ledger.staged_count == 0:
            self._show_placeholder()
            return

        self._placeholder_label.setVisible(False)

        # ---- DsSummaryStat を更新 ----
        self._stat_unique_models._value_widget.setText(str(ledger.unique_model_count))
        self._stat_staged._value_widget.setText(str(ledger.staged_count))

        self._stat_total_jobs._value_widget.setText(str(ledger.total_jobs))
        breakdown_text = f"local {ledger.local_count} · API {ledger.api_count}"
        self._stat_total_jobs._sub_widget.setText(breakdown_text)
        self._stat_total_jobs._sub_widget.setVisible(True)

        # Issue #747: コスト・推定時間の概算 (has_unknown 時は + サフィックス)
        estimate = self._cost_service.estimate_batch(ledger)
        amount = f"${estimate.total_usd:.2f}"
        if estimate.has_unknown:
            amount += "+"
        est_value = f"{amount} · {format_duration(estimate.est_seconds)}"
        self._stat_estimate._value_widget.setText(est_value)
        unknown_note = "（一部モデルは料金不明）" if estimate.has_unknown else ""
        self._stat_estimate._sub_widget.setText(unknown_note)
        self._stat_estimate._sub_widget.setVisible(estimate.has_unknown)

        self._stats_widget.setVisible(True)

        # ---- モデルバッジ行 ----
        has_multimodal = False
        for entry in ledger.entries:
            self._add_entry_chip(entry, ledger.staged_count)
            if entry.model.is_multimodal:
                has_multimodal = True
        self._entries_layout.addStretch(1)

        # multimodal エントリが 1 件以上のとき dedupe 注記を表示
        self._multi_note_label.setVisible(has_multimodal)

    def clear(self) -> None:
        """空表示にする。"""
        self._clear_entries()
        self._show_placeholder()

    def _show_placeholder(self) -> None:
        """「モデル未選択」プレースホルダ状態に切り替える。"""
        self._stats_widget.setVisible(False)
        self._multi_note_label.setVisible(False)
        self._placeholder_label.setText(_PLACEHOLDER_TEXT)
        self._placeholder_label.setVisible(True)

    def _clear_entries(self) -> None:
        """既存のエントリチップを layout から外して破棄する。"""
        while self._entries_layout.count():
            item = self._entries_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                # findChildren で前回チップが見えないよう、即時に親子関係を切る
                widget.setParent(None)
                widget.deleteLater()

    def _add_entry_chip(self, entry: LedgerEntry, staged_count: int) -> None:
        """エントリチップ (+ multimodal バッジ) を 1 つ追加する。

        Args:
            entry: 台帳エントリ (モデル情報 + ステージ数)。
            staged_count: ステージング枚数。
        """
        chip = QLabel(f"{entry.model.display_name} ×{staged_count}枚", self)
        chip.setObjectName("ledgerChip")
        chip.setStyleSheet(_ENTRY_CHIP_STYLE)
        self._entries_layout.addWidget(chip)

        if entry.model.is_multimodal:
            badge = QLabel(f"{entry.stage_count}枠 → 1推論", self)
            badge.setObjectName("ledgerMultiBadge")
            badge.setStyleSheet(_MULTI_BADGE_STYLE)
            badge.setToolTip("multimodal モデルは複数ステージに出力しても 1 推論として課金されます")
            self._entries_layout.addWidget(badge)
