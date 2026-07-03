"""登録完了サマリパネル (Wireframes v11 Frame 1 / ADR 0061 §4)。

専用 Import frame の代わりに、Search タブ上部へ常設するサマリパネル。
registered / variant / skipped / errors の件数と、重複 / 別版に分類された
ファイルの内訳（「既存 #N を表示」リンク付き）を表示する。statusBar の
5 秒表示と異なり、✕ で閉じるまで残る。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lorairo.database.db_manager import RegistrationOutcome

from .ds_chip import DsChip

if TYPE_CHECKING:
    from lorairo.gui.workers.registration_worker import (
        DatabaseRegistrationResult,
        RegistrationDetailItem,
    )

# 内訳行に出す outcome（重複 / 別版のみ。新規は通常ケースなので出さない）。
_DETAIL_OUTCOMES = (RegistrationOutcome.DUPLICATE, RegistrationOutcome.VARIANT)


class RegistrationSummaryWidget(QWidget):
    """登録完了サマリパネル。

    Signals:
        view_image_requested: 内訳行の「#N を表示」リンク押下時に image_id を送出。
    """

    view_image_requested = Signal(int)

    # 一度に描画する内訳行の上限。非スクロールのパネルに数千行を積んで GUI を
    # 固めないため、超過分は「他 N件」の overflow ラベルへ畳む。
    MAX_DETAIL_ROWS = 50

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("registrationSummaryWidget")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(4)

        # ヘッダ行: ✓ 登録完了 — <dir> · N枚 · X.Xs   [counts]   [▾ 内訳] [✕]
        header_row = QHBoxLayout()
        self._header_label = QLabel(self)
        self._header_label.setObjectName("registrationSummaryHeader")
        self._counts_label = QLabel(self)
        self._counts_label.setObjectName("registrationSummaryCounts")

        self._toggle_button = QPushButton("▾ skip / 別版 の内訳", self)
        self._toggle_button.setObjectName("registrationSummaryToggle")
        self._toggle_button.setFlat(True)
        self._toggle_button.clicked.connect(self._on_toggle_clicked)

        self._dismiss_button = QPushButton("✕", self)
        self._dismiss_button.setObjectName("registrationSummaryDismiss")
        self._dismiss_button.setFlat(True)
        self._dismiss_button.clicked.connect(self.hide)

        header_row.addWidget(self._header_label)
        header_row.addWidget(self._counts_label)
        header_row.addStretch(1)
        header_row.addWidget(self._toggle_button)
        header_row.addWidget(self._dismiss_button)
        outer.addLayout(header_row)

        # 内訳コンテナ（既定で折りたたみ）
        self._detail_container = QWidget(self)
        self._detail_container.setObjectName("registrationSummaryDetail")
        self._detail_layout = QVBoxLayout(self._detail_container)
        self._detail_layout.setContentsMargins(0, 0, 0, 0)
        self._detail_layout.setSpacing(2)
        self._detail_container.setVisible(False)
        outer.addWidget(self._detail_container)

        # 結果到来までは非表示
        self.setVisible(False)

    def show_result(self, result: DatabaseRegistrationResult) -> None:
        """登録結果を表示する（パネルを可視化、内訳は折りたたんだ状態で開始）。

        Args:
            result: 登録ワーカーの結果。
        """
        directory_name = result.directory.name if result.directory is not None else "—"
        total = result.registered_count + result.variant_count + result.skipped_count + result.error_count
        self._header_label.setText(
            f"✓ 登録完了 — {directory_name} · {total}枚 · {result.total_processing_time:.1f}s"
        )
        self._counts_label.setText(
            f"新規 {result.registered_count} · 別版 {result.variant_count} · "
            f"skip {result.skipped_count} · エラー {result.error_count}"
        )

        self._rebuild_detail(result.detail)
        # 内訳が無ければトグル自体を隠す
        has_detail = self._detail_layout.count() > 0
        self._toggle_button.setVisible(has_detail)
        self._detail_container.setVisible(False)

        self.setVisible(True)

    def _rebuild_detail(self, detail: list[RegistrationDetailItem]) -> None:
        """内訳行を再構築する（重複 / 別版のみ、既存呼び出しの残骸を破棄）。"""
        while self._detail_layout.count():
            item = self._detail_layout.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.deleteLater()

        eligible = [
            entry for entry in detail if entry.outcome in _DETAIL_OUTCOMES and entry.image_id is not None
        ]
        for entry in eligible[: self.MAX_DETAIL_ROWS]:
            self._detail_layout.addWidget(self._build_detail_row(entry))

        overflow = len(eligible) - self.MAX_DETAIL_ROWS
        if overflow > 0:
            label = QLabel(f"… 他 {overflow}件の重複 / 別版", self._detail_container)
            label.setObjectName("registrationSummaryOverflow")
            self._detail_layout.addWidget(label)

    def _build_detail_row(self, entry: RegistrationDetailItem) -> QFrame:
        """内訳1行を構築する。"""
        is_variant = entry.outcome is RegistrationOutcome.VARIANT
        row = QFrame(self._detail_container)
        row.setObjectName("registrationSummaryDetailRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)

        filename = QLabel(entry.filename, row)
        filename.setObjectName("registrationSummaryDetailFilename")

        # DS 公式 chip 部品へ寄せる (Issue #1105 項目1)。見た目維持のためドット無し。
        badge = DsChip(
            "VARIANT" if is_variant else "DUPLICATE",
            "accent" if is_variant else "info",
            dot="none",
            parent=row,
        )

        reason = QLabel(
            "同一 pHash でも属性差 → 別版として新規登録"
            if is_variant
            else "同一 pHash · 属性差なし → 自動 skip（alias 記録済）",
            row,
        )
        reason.setObjectName("registrationSummaryDetailReason")

        link_text = f"→ 新規 #{entry.image_id} を表示" if is_variant else f"→ 既存 #{entry.image_id} を表示"
        link = QPushButton(link_text, row)
        link.setObjectName(f"registrationSummaryImageLink_{entry.image_id}")
        link.setFlat(True)
        image_id = entry.image_id
        link.clicked.connect(lambda _checked=False, iid=image_id: self.view_image_requested.emit(iid))

        layout.addWidget(filename)
        layout.addWidget(badge)
        layout.addWidget(reason)
        layout.addStretch(1)
        layout.addWidget(link)
        return row

    def _on_toggle_clicked(self) -> None:
        """内訳の開閉を切り替える。"""
        self._detail_container.setVisible(not self._detail_container.isVisible())
