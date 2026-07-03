"""DS v12 AnnotateScreen の INFERENCE LEDGER (推論台帳) card (表示専用)。

推論回数 = ユニークモデル × ステージング枚数 の DsSummaryStat グリッドと、
ユニークモデルごとのエントリチップ (multimodal は「N枠 → 1推論」バッジ併記) を
DsCard 面で描画する。
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from lorairo.gui import theme
from lorairo.gui.widgets.ds_card import DsCard
from lorairo.gui.widgets.ds_summary_stat import DsSummaryStat
from lorairo.gui.widgets.tag_cloud_widget import FlowLayout
from lorairo.services.cost_estimation_service import (
    CostEstimationService,
    format_duration,
)
from lorairo.services.pipeline_composition import InferenceLedger, LedgerEntry

_TITLE_TEXT = "INFERENCE LEDGER"
_PLACEHOLDER_TEXT = "モデル未選択"
_MULTI_NOTE_TEXT = "multimodal: 複数ステージに出力しても 1 推論として課金"
# #884 Phase 4b: SYNC / PROVIDER BATCH 2バンド (ADR 0038 / wireframes v12)
_SYNC_BAND_TITLE = "SYNC"
_BATCH_BAND_TITLE = "PROVIDER BATCH (非同期)"
_BATCH_ROUTE_BADGE_TEXT = "batch·api"

# DS v12 AnnotateScreen ledger (Issue #787): エントリ = TypeBadge 文法 (paper-shade 地 +
# line border の mono バッジ)、multimodal 集約バッジ = accent-soft の mono バッジ。
# #1105: 手書き QSS 定数を theme.chip_qss(kind, ...) の構造パラメータへ置換。
# 色は palette (entry=neutral / multi・route-api=accent / route-local=muted) が SSoT、
# バッジ意匠 (mono / RADIUS_BADGE / FONT_SIZE_META / padding 1px 6px) は引数で再現する。
_ENTRY_CHIP_STYLE = theme.chip_qss(
    "neutral",
    mono=True,
    radius=theme.RADIUS_BADGE,
    size=theme.FONT_SIZE_META,
    padding="1px 6px",
    weight=None,
)
_MULTI_BADGE_STYLE = theme.chip_qss(
    "accent",
    mono=True,
    radius=theme.RADIUS_BADGE,
    size=theme.FONT_SIZE_META,
    padding="1px 6px",
    weight=theme.FONT_WEIGHT_SEMIBOLD,
)

# #884 Phase 4a: route バッジ。local = 中立 (paper-shade / ink-faint)、
# api = accent-soft の mono バッジ。dispatch の sync/batch 区別は Phase 4b で足す。
_ROUTE_BADGE_STYLE_LOCAL = theme.chip_qss(
    "muted", mono=True, radius=theme.RADIUS_BADGE, size=theme.FONT_SIZE_META, padding="1px 6px", weight=None
)
_ROUTE_BADGE_STYLE_API = theme.chip_qss(
    "accent",
    mono=True,
    radius=theme.RADIUS_BADGE,
    size=theme.FONT_SIZE_META,
    padding="1px 6px",
    weight=None,
)

# #884 Phase 4b: バンド見出し (SYNC / PROVIDER BATCH)
_BAND_HEADER_STYLE = (
    f"color: {theme.INK_SOFT}; font-size: {theme.FONT_SIZE_META}px;"
    f" font-weight: {theme.FONT_WEIGHT_SEMIBOLD};"
)


class InferenceLedgerWidget(DsCard):
    """DS v12 AnnotateScreen の INFERENCE LEDGER (推論台帳) card。

    DsCard を継承し、DsSummaryStat グリッド (ユニークモデル / × staged /
    推論回数合計 / 推定) + モデルバッジ + multimodal dedupe 注記を描画する。
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

        # 推論回数合計 = accent 強調
        self._stat_total_jobs = DsSummaryStat(
            label="推論回数合計", value="—", tone="accent", parent=self._stats_widget
        )
        self._stat_total_jobs.setObjectName("ledgerStatTotalJobs")
        stats_row.addWidget(self._stat_total_jobs)

        # 推定コスト・時間 = info 色
        self._stat_estimate = DsSummaryStat(label="推定", value="—", tone="info", parent=self._stats_widget)
        self._stat_estimate.setObjectName("ledgerStatEstimate")
        stats_row.addWidget(self._stat_estimate)

        stats_row.addStretch(1)
        body_layout.addWidget(self._stats_widget)

        # ---- SYNC / PROVIDER BATCH 2バンド (#884 Phase 4b) ----
        # entries は FlowLayout で折り返す (#1100: 狭幅で縦長崩れを防ぐ)。
        self._sync_band, self._sync_entries_layout = self._build_band(body, _SYNC_BAND_TITLE)
        self._sync_band.setObjectName("ledgerSyncBand")
        body_layout.addWidget(self._sync_band)

        self._batch_band, self._batch_entries_layout = self._build_band(body, _BATCH_BAND_TITLE)
        self._batch_band.setObjectName("ledgerBatchBand")
        body_layout.addWidget(self._batch_band)

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

    def _build_band(self, body: QWidget, title: str) -> tuple[QWidget, FlowLayout]:
        """見出し付きバンド (header + 折り返しエントリ行) を構築して返す。

        エントリ行は自作 ``FlowLayout`` を載せた専用コンテナ widget に閉じる。
        FlowLayout は ``hasHeightForWidth`` を持ち、``minimumSize`` は
        「単一エントリ幅」なので、``widgetResizable=True`` の QScrollArea 内でも
        最小高さが暴れず、実幅に応じてチップが折り返す (#1100、
        docs/lessons-learned.md「FlowLayout in widgetResizable...」参照)。
        """
        band = QWidget(body)
        band_layout = QVBoxLayout(band)
        band_layout.setContentsMargins(0, 0, 0, 0)
        band_layout.setSpacing(theme.SPACE_1)

        header = QLabel(title, band)
        header.setStyleSheet(_BAND_HEADER_STYLE)
        band_layout.addWidget(header)

        entries_container = QWidget(band)
        entries_container.setObjectName("ledgerEntriesContainer")
        # 縦は Preferred (heightForWidth で必要行数に応じて伸びる。Minimum だと
        # 過大 sizeHint に固定されスクロール空白が出る — lessons #1025)。
        entries_container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        entries_layout = FlowLayout(entries_container, spacing=theme.SPACE_1)
        band_layout.addWidget(entries_container)
        return band, entries_layout

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

        # ---- SYNC バンド (常時表示) ----
        sync_entries = ledger.sync_entries
        for entry in sync_entries:
            self._add_entry_chip(entry, ledger.staged_count, self._sync_entries_layout)
        self._sync_band.setVisible(True)

        # ---- PROVIDER BATCH バンド (batch エントリがある時のみ表示) ----
        batch_entries = ledger.batch_entries
        for entry in batch_entries:
            self._add_entry_chip(entry, ledger.staged_count, self._batch_entries_layout)
        self._batch_band.setVisible(bool(batch_entries))

        # multimodal エントリが 1 件以上のとき dedupe 注記を表示
        has_multimodal = any(e.model.is_multimodal for e in ledger.entries)
        self._multi_note_label.setVisible(has_multimodal)

    def clear(self) -> None:
        """空表示にする。"""
        self._clear_entries()
        self._show_placeholder()

    def _show_placeholder(self) -> None:
        """「モデル未選択」プレースホルダ状態に切り替える。"""
        self._stats_widget.setVisible(False)
        self._sync_band.setVisible(False)
        self._batch_band.setVisible(False)
        self._multi_note_label.setVisible(False)
        self._placeholder_label.setText(_PLACEHOLDER_TEXT)
        self._placeholder_label.setVisible(True)

    def _clear_entries(self) -> None:
        """既存のエントリチップを両バンドの layout から外して破棄する。"""
        for layout in (self._sync_entries_layout, self._batch_entries_layout):
            while layout.count():
                item = layout.takeAt(0)
                if item is None:
                    continue
                widget = item.widget()
                if widget is not None:
                    # findChildren で前回チップが見えないよう、即時に親子関係を切る
                    widget.setParent(None)
                    widget.deleteLater()

    def _add_entry_chip(self, entry: LedgerEntry, staged_count: int, entries_layout: FlowLayout) -> None:
        """エントリチップ (+ route / multimodal バッジ) を 1 つ追加する。

        route バッジ・チップ・multimodal バッジは 1 モデル分をまとめた
        コンテナ widget に閉じ、それを FlowLayout に載せる。折り返しは
        モデル境界で起き、バッジとチップが行をまたいで分断されない (#1100)。

        Args:
            entry: 台帳エントリ (モデル情報 + ステージ数 + route)。
            staged_count: ステージング枚数。
            entries_layout: 追加先バンドのエントリ行 FlowLayout。
        """
        group = QWidget(self)
        group.setObjectName("ledgerEntryGroup")
        group_layout = QHBoxLayout(group)
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_layout.setSpacing(theme.SPACE_1)

        # route バッジ: batch route = "batch·api" (#884 Phase 4b)、
        # sync route = local/api (#884 Phase 4a、is_api が canonical 判定)。
        is_api = entry.model.is_api
        if entry.route == "batch":
            badge_text = _BATCH_ROUTE_BADGE_TEXT
            badge_style = _ROUTE_BADGE_STYLE_API
        else:
            badge_text = "api" if is_api else "local"
            badge_style = _ROUTE_BADGE_STYLE_API if is_api else _ROUTE_BADGE_STYLE_LOCAL
        route_badge = QLabel(badge_text, group)
        route_badge.setObjectName("ledgerRouteBadge")
        route_badge.setStyleSheet(badge_style)
        group_layout.addWidget(route_badge)

        chip = QLabel(f"{entry.model.display_name} ×{staged_count}枚", group)
        chip.setObjectName("ledgerChip")
        chip.setStyleSheet(_ENTRY_CHIP_STYLE)
        group_layout.addWidget(chip)

        if entry.model.is_multimodal:
            badge = QLabel(f"{entry.stage_count}枠 → 1推論", group)
            badge.setObjectName("ledgerMultiBadge")
            badge.setStyleSheet(_MULTI_BADGE_STYLE)
            badge.setToolTip("multimodal モデルは複数ステージに出力しても 1 推論として課金されます")
            group_layout.addWidget(badge)

        entries_layout.addWidget(group)
