"""Wireframes v11 Frame 2A の INFERENCE LEDGER (推論台帳) widget (Phase 6a: 表示専用)。

推論回数 = ユニークモデル × ステージング枚数 の式と、ユニークモデルごとの
エントリチップ (multimodal は「N枠 → 1推論」バッジ併記) を描画する。
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from lorairo.gui import theme
from lorairo.services.cost_estimation_service import (
    CostEstimationService,
    format_duration,
)
from lorairo.services.pipeline_composition import InferenceLedger, LedgerEntry

_TITLE_TEXT = "INFERENCE LEDGER — 推論回数 = ユニークモデル × ステージング枚数"
_PLACEHOLDER_TEXT = "モデル未選択"

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


class InferenceLedgerWidget(QWidget):
    """Wireframes v11 Frame 2A の INFERENCE LEDGER (推論台帳)。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._cost_service = CostEstimationService()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel(_TITLE_TEXT, self)
        title.setObjectName("ledgerTitleLabel")
        title_font = title.font()
        title_font.setBold(True)
        title.setFont(title_font)
        # DS: ledger 見出しは UPPERCASE + letter-caps + ink-soft
        title.setStyleSheet(
            f"color: {theme.INK_SOFT}; letter-spacing: {theme.LETTER_CAPS};"
            f" font-size: {theme.FONT_SIZE_SMALL}px;"
        )
        layout.addWidget(title)

        self._entries_layout = QHBoxLayout()
        self._entries_layout.setContentsMargins(0, 2, 0, 2)
        layout.addLayout(self._entries_layout)

        # DS: 推論回数の式・コスト概算は mono 数値メタ
        _meta_qss = (
            f"font-family: {theme.FONT_MONO_CSS}; color: {theme.INK_SOFT};"
            f" font-size: {theme.FONT_SIZE_SMALL}px;"
        )
        self._formula_label = QLabel("", self)
        self._formula_label.setObjectName("ledgerFormulaLabel")
        self._formula_label.setStyleSheet(_meta_qss)
        layout.addWidget(self._formula_label)

        self._cost_label = QLabel("", self)
        self._cost_label.setObjectName("ledgerCostLabel")
        self._cost_label.setStyleSheet(_meta_qss)
        layout.addWidget(self._cost_label)

        self._placeholder_label = QLabel(_PLACEHOLDER_TEXT, self)
        self._placeholder_label.setObjectName("ledgerPlaceholderLabel")
        self._placeholder_label.setStyleSheet(f"color: {theme.INK_FAINT};")
        layout.addWidget(self._placeholder_label)

        layout.addStretch(1)

        self.clear()

    def display(self, ledger: InferenceLedger) -> None:
        """台帳を再描画する。"""
        self._clear_entries()
        if not ledger.entries or ledger.staged_count == 0:
            self._show_placeholder()
            return

        self._placeholder_label.setText("")
        self._placeholder_label.setVisible(False)

        for entry in ledger.entries:
            self._add_entry_chip(entry, ledger.staged_count)
        self._entries_layout.addStretch(1)

        formula = (
            f"{ledger.unique_model_count} ユニークモデル × {ledger.staged_count} 枚"
            f" = {ledger.total_jobs} 推論ジョブ"
            f" （local {ledger.local_count} · API {ledger.api_count}）"
        )
        self._formula_label.setText(formula)
        self._formula_label.setVisible(True)

        # Issue #747: コスト・推定時間の概算行 (has_unknown 時は不明含む旨を併記)
        estimate = self._cost_service.estimate_batch(ledger)
        amount = f"${estimate.total_usd:.2f}"
        if estimate.has_unknown:
            amount += "+"
        cost_text = f"推定 {amount} · {format_duration(estimate.est_seconds)}"
        if estimate.has_unknown:
            cost_text += "（一部モデルは料金不明）"
        self._cost_label.setText(cost_text)
        self._cost_label.setVisible(True)

    def clear(self) -> None:
        """空表示にする。"""
        self._clear_entries()
        self._show_placeholder()

    def _show_placeholder(self) -> None:
        """「モデル未選択」プレースホルダ状態に切り替える。"""
        self._formula_label.setText("")
        self._formula_label.setVisible(False)
        self._cost_label.setText("")
        self._cost_label.setVisible(False)
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
        """エントリチップ (+ multimodal バッジ) を 1 つ追加する。"""
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
