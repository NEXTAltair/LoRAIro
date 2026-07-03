"""Provider Batch 追跡カード (ProviderBatchJobCard).

Issue #1103: Jobs タブの Provider Batch セクションをフラットテーブルから
追跡カードへ再設計する。デザイン SSoT は claude.ai/design「LoRAIro-01」の
``Jobs Tab - Provider Batch Redesign.html`` フレーム B (7 状態バリエーション)。

ストリップ文法:
- 通過済み = ink 塗り ● + 実線
- 現在地 = accent ● + ring + 状態 pill
- 未到達 = 破線 ○ + 破線
- 色は accent 1色 + 失敗のみ err (expired は warn、canceled は faint)

進捗は終了/未了の 2 値のみ (2026-07-03 ユーザ確定)。per-request の件数進捗
(「完了 6/9」等) は provider が提供しないため描画しない。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lorairo.gui import theme

# 内部 status → カード表示状態
CardViewState = Literal["active", "collectable", "imported", "failed", "canceled", "expired"]

_ACTIVE_STATUSES = {"submitted", "validating", "running", "canceling"}
_CANCELABLE_STATUSES = {"submitted", "validating", "running", "canceling"}

_CHECKPOINT_LABELS = ("submit", "provider status", "fetch", "import → DB")

# node 状態 → (背景色, border 色, 文字)
_NODE_STYLES: dict[str, tuple[str, str, str]] = {
    "done": (theme.INK_SOFT, theme.INK_SOFT, "✓"),
    "cur": (theme.ACCENT, theme.ACCENT, ""),
    "cur_bad": (theme.ERR, theme.ERR, "✕"),
    "cur_off": (theme.INK_FAINT, theme.INK_FAINT, "⊘"),
    "cur_warn": (theme.INK_FAINT, theme.INK_FAINT, "◷"),
    "wait": (theme.CARD, theme.LINE, ""),
}


def derive_view_state(job: Any) -> CardViewState:
    """ジョブの内部 status からカード表示状態を導出する。

    Args:
        job: provider_batch_jobs レコード (status / imported_at を参照)。

    Returns:
        カード表示状態。
    """
    status = str(getattr(job, "status", "") or "")
    if status == "imported" or getattr(job, "imported_at", None) is not None:
        return "imported"
    if status == "completed":
        return "collectable"
    if status == "failed":
        return "failed"
    if status == "canceled":
        return "canceled"
    if status == "expired":
        return "expired"
    return "active"


def _shorten_batch_id(job: Any) -> str:
    """provider_job_id を「batch_68a…9f2c」形式に短縮する。無ければ PB-{id}。"""
    provider_job_id = str(getattr(job, "provider_job_id", "") or "")
    if not provider_job_id:
        return f"PB-{getattr(job, 'id', '?')}"
    if len(provider_job_id) <= 14:
        return provider_job_id
    return f"{provider_job_id[:9]}…{provider_job_id[-4:]}"


def _now_like(reference: datetime) -> datetime:
    """reference と同じ aware/naive 性質の現在時刻を返す (SQLite は naive)。"""
    if reference.tzinfo is None:
        return datetime.now()
    return datetime.now(UTC)


def _format_duration(start: datetime | None, end: datetime | None = None) -> str:
    """経過時間を「3日 2h」「7h 12m」「41m」形式で返す。start 不明は「—」。"""
    if start is None:
        return "—"
    reference = end if end is not None else _now_like(start)
    total_seconds = max(0, int((reference - start).total_seconds()))
    days, rest = divmod(total_seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"{days}日 {hours}h"
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


def _format_dt(value: Any) -> str:
    """timestamp フィールドを「7/2 23:41」形式で返す。None は「—」。"""
    if not isinstance(value, datetime):
        return "—"
    return f"{value.month}/{value.day} {value:%H:%M}"


class _TrackCheckpoint(QWidget):
    """トラッキングストリップの 1 チェックポイント (rail + label + value + sub)。"""

    def __init__(
        self,
        *,
        label: str,
        node_state: str,
        value_text: str,
        value_chip_kind: theme.ChipKind | None,
        sub_text: str,
        line_left: str,
        line_right: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        layout.addLayout(self._build_rail(node_state, line_left, line_right))

        label_widget = QLabel(label.upper())
        label_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label_color = theme.INK_FAINT if node_state == "wait" else theme.INK_SOFT
        label_widget.setStyleSheet(
            f"QLabel {{ color: {label_color}; font-size: 9px; letter-spacing: 1px;"
            f" font-family: {theme.FONT_MONO_CSS}; }}"
        )
        layout.addWidget(label_widget)

        self.value_label = QLabel(value_text)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if value_chip_kind is not None:
            self.value_label.setStyleSheet(theme.chip_qss(value_chip_kind))
            chip_row = QHBoxLayout()
            chip_row.setContentsMargins(0, 0, 0, 0)
            chip_row.addStretch(1)
            chip_row.addWidget(self.value_label)
            chip_row.addStretch(1)
            layout.addLayout(chip_row)
        else:
            value_color = theme.INK_FAINT if node_state == "wait" else theme.INK
            weight = 400 if node_state == "wait" else 600
            self.value_label.setStyleSheet(
                f"QLabel {{ color: {value_color}; font-size: {theme.FONT_SIZE_SMALL}px;"
                f" font-weight: {weight}; }}"
            )
            layout.addWidget(self.value_label)

        self.sub_label = QLabel(sub_text)
        self.sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub_label.setStyleSheet(
            f"QLabel {{ color: {theme.INK_FAINT}; font-size: 10px; font-family: {theme.FONT_MONO_CSS}; }}"
        )
        layout.addWidget(self.sub_label)
        layout.addStretch(1)

    def _build_rail(self, node_state: str, line_left: str, line_right: str) -> QHBoxLayout:
        """node と左右の接続線 (実線/破線/透明) を組む。"""
        rail = QHBoxLayout()
        rail.setContentsMargins(0, 0, 0, 0)
        rail.setSpacing(0)
        rail.addWidget(self._build_line(line_left), 1)
        rail.addWidget(self._build_node(node_state), 0, Qt.AlignmentFlag.AlignVCenter)
        rail.addWidget(self._build_line(line_right), 1)
        return rail

    @staticmethod
    def _build_line(style: str) -> QLabel:
        """接続線 1 本を返す。style: "solid" / "dash" / "off"。"""
        line = QLabel()
        line.setFixedHeight(9)
        if style == "solid":
            line.setStyleSheet(f"QLabel {{ border-bottom: 1px solid {theme.LINE_STRONG}; }}")
        elif style == "dash":
            line.setStyleSheet(f"QLabel {{ border-bottom: 1px dashed {theme.LINE}; }}")
        else:
            line.setStyleSheet("QLabel { border: none; }")
        return line

    @staticmethod
    def _build_node(node_state: str) -> QWidget:
        """チェックポイント node (●/○) を返す。現在地は ring 付き。"""
        background, border, text = _NODE_STYLES[node_state]
        node = QLabel(text)
        node.setFixedSize(14, 14)
        node.setAlignment(Qt.AlignmentFlag.AlignCenter)
        border_style = "dashed" if node_state == "wait" else "solid"
        text_color = "#ffffff" if node_state != "wait" else theme.INK_FAINT
        node.setStyleSheet(
            f"QLabel {{ background-color: {background}; border: 1px {border_style} {border};"
            f" border-radius: 7px; color: {text_color}; font-size: 9px; }}"
        )
        if not node_state.startswith("cur"):
            return node
        ring = QFrame()
        ring.setFixedSize(22, 22)
        ring.setStyleSheet(
            f"QFrame {{ border: 1px solid {border}; border-radius: 11px; background: transparent; }}"
        )
        ring_layout = QHBoxLayout(ring)
        ring_layout.setContentsMargins(3, 3, 3, 3)
        ring_layout.addWidget(node)
        return ring


class ProviderBatchJobCard(QFrame):
    """Provider Batch ジョブ 1 件の追跡カード (監視専用 · ADR 0076)。

    上部 = ジョブ ID 短縮 + provider badge + N requests + 経過。
    中央 = 4 チェックポイント・トラッキングストリップ。
    下部 = その状態に効くアクションのみ (右クリック隠蔽なし)。
    展開 = identity / requests / timeline の kv グリッド + 項目テーブル。
    """

    check_requested = Signal(int)  # ↻ 状態を確認 / ↓ 結果を取得 (refresh→fetch→import 連鎖)
    cancel_requested = Signal(int)
    expand_toggled = Signal(int, bool)

    def __init__(self, job: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._job = job
        self._job_id = int(job.id)
        self._view_state: CardViewState = derive_view_state(job)
        self._expanded = False
        self._items: list[Any] = []

        self.setObjectName("providerBatchJobCard")
        background = theme.PAPER if self._is_terminal() else theme.CARD
        self.setStyleSheet(
            f"QFrame#providerBatchJobCard {{ background-color: {background};"
            f" border: 1px solid {theme.LINE}; border-radius: {theme.RADIUS}px; }}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())
        root.addWidget(self._build_track())
        root.addWidget(self._build_footer())
        self._expansion = self._build_expansion()
        self._expansion.setVisible(False)
        root.addWidget(self._expansion)

    # -- 公開 API --------------------------------------------------------------

    @property
    def job_id(self) -> int:
        """ジョブ ID を返す。"""
        return self._job_id

    @property
    def view_state(self) -> CardViewState:
        """カード表示状態を返す。"""
        return self._view_state

    @property
    def expanded(self) -> bool:
        """展開中かどうかを返す。"""
        return self._expanded

    def set_expanded(self, expanded: bool) -> None:
        """展開状態を切り替える (progressive disclosure)。"""
        self._expanded = expanded
        self._expansion.setVisible(expanded)
        self._disc_button.setText("詳細 ▾" if expanded else "詳細 ▸")

    def set_items(self, items: list[Any]) -> None:
        """展開部の項目テーブルへ項目一覧を反映する (client-side filter)。"""
        self._items = list(items)
        self._render_items()

    # -- 上部: ID + provider + 規模 + 経過 -------------------------------------

    def _build_header(self) -> QWidget:
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(14, 9, 14, 9)
        layout.setSpacing(8)

        bid_color = theme.INK_SOFT if self._is_terminal() else theme.INK
        bid = QLabel(_shorten_batch_id(self._job))
        bid.setObjectName("labelCardBatchId")
        bid.setStyleSheet(
            f"QLabel {{ color: {bid_color}; font-weight: 700;"
            f" font-family: {theme.FONT_MONO_CSS}; font-size: {theme.FONT_SIZE_BASE}px; }}"
        )
        layout.addWidget(bid)

        provider = str(getattr(self._job, "provider", "") or "")
        if provider:
            provider_badge = QLabel(provider)
            provider_badge.setStyleSheet(theme.badge_qss())
            layout.addWidget(provider_badge)

        request_count = int(getattr(self._job, "request_count", 0) or 0)
        req = QLabel(f"{request_count} requests")
        req.setStyleSheet(
            f"QLabel {{ color: {theme.INK_SOFT}; font-family: {theme.FONT_MONO_CSS};"
            f" font-size: {theme.FONT_SIZE_SMALL}px; }}"
        )
        layout.addWidget(req)
        layout.addStretch(1)

        if self._view_state == "imported":
            chip = QLabel("● 取込済み")
            chip.setStyleSheet(theme.chip_qss("ok"))
            layout.addWidget(chip)

        elapsed = QLabel(self._elapsed_text())
        elapsed.setObjectName("labelCardElapsed")
        elapsed.setStyleSheet(
            f"QLabel {{ color: {theme.INK_SOFT}; font-family: {theme.FONT_MONO_CSS};"
            f" font-size: {theme.FONT_SIZE_SMALL}px; }}"
        )
        layout.addWidget(elapsed)

        header.setStyleSheet(f"border-bottom: 1px solid {theme.LINE};")
        return header

    def _elapsed_text(self) -> str:
        submitted_at = getattr(self._job, "submitted_at", None)
        if self._view_state == "imported":
            return f"所要 {_format_duration(submitted_at, getattr(self._job, 'imported_at', None))}"
        if self._view_state == "canceled":
            return (
                f"キャンセルまで {_format_duration(submitted_at, getattr(self._job, 'canceled_at', None))}"
            )
        return f"送信から {_format_duration(submitted_at)}"

    # -- 中央: トラッキングストリップ -------------------------------------------

    def _build_track(self) -> QWidget:
        track = QWidget()
        layout = QHBoxLayout(track)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(0)
        checkpoints = self._checkpoint_specs()
        for index, spec in enumerate(checkpoints):
            line_left = "off" if index == 0 else spec["line_in"]
            line_right = "off" if index == len(checkpoints) - 1 else checkpoints[index + 1]["line_in"]
            layout.addWidget(
                _TrackCheckpoint(
                    label=_CHECKPOINT_LABELS[index],
                    node_state=spec["node"],
                    value_text=spec["value"],
                    value_chip_kind=spec["chip"],
                    sub_text=spec["sub"],
                    line_left=line_left,
                    line_right=line_right,
                ),
                1,
            )
        return track

    def _checkpoint_specs(self) -> list[dict[str, Any]]:
        """表示状態から 4 チェックポイントの描画仕様を導出する。

        line_in はそのチェックポイントへ入ってくる線 (通過済み到達なら実線)。
        """
        job = self._job
        request_count = int(getattr(job, "request_count", 0) or 0)
        submit_spec: dict[str, Any] = {
            "node": "done",
            "value": f"✓ {request_count} items",
            "chip": None,
            "sub": _format_dt(getattr(job, "submitted_at", None)),
            "line_in": "solid",
        }
        wait_fetch: dict[str, Any] = {
            "node": "wait",
            "value": "— 自動",
            "chip": None,
            "sub": "完了後に取得",
            "line_in": "dash",
        }
        wait_import: dict[str, Any] = {
            "node": "wait",
            "value": "— 自動",
            "chip": None,
            "sub": "→ Results",
            "line_in": "dash",
        }
        unreached = {"value": "—", "sub": "到達せず"}

        provider_spec: dict[str, Any]
        fetch_spec: dict[str, Any]
        import_spec: dict[str, Any]
        if self._view_state == "active":
            provider_status = str(getattr(job, "provider_status", "") or getattr(job, "status", ""))
            provider_spec = {
                "node": "cur",
                "value": f"◷ {provider_status}",
                "chip": "accent",
                "sub": "内訳なし",
                "line_in": "solid",
            }
            return [submit_spec, provider_spec, wait_fetch, wait_import]
        if self._view_state == "collectable":
            provider_spec = {
                "node": "done",
                "value": "✓ completed",
                "chip": None,
                "sub": f"{_format_dt(getattr(job, 'completed_at', None))} に確認",
                "line_in": "solid",
            }
            fetch_spec = {
                "node": "cur",
                "value": "↓ 未回収",
                "chip": "accent",
                "sub": "結果ファイル待機中",
                "line_in": "solid",
            }
            return [submit_spec, provider_spec, fetch_spec, wait_import]
        if self._view_state == "imported":
            provider_spec = {
                "node": "done",
                "value": "✓ completed",
                "chip": None,
                "sub": _format_dt(getattr(job, "completed_at", None)),
                "line_in": "solid",
            }
            fetch_spec = {
                "node": "done",
                "value": "✓ 自動",
                "chip": None,
                "sub": "artifact 保存済",
                "line_in": "solid",
            }
            import_spec = {
                "node": "done",
                "value": "✓ 自動",
                "chip": None,
                "sub": _format_dt(getattr(job, "imported_at", None)),
                "line_in": "solid",
            }
            return [submit_spec, provider_spec, fetch_spec, import_spec]
        if self._view_state == "failed":
            provider_spec = {
                "node": "cur_bad",
                "value": "✕ failed",
                "chip": "err",
                "sub": "",
                "line_in": "solid",
            }
        elif self._view_state == "canceled":
            provider_spec = {
                "node": "cur_off",
                "value": "⊘ canceled",
                "chip": "muted",
                "sub": "provider 側も取消済",
                "line_in": "solid",
            }
        else:  # expired
            provider_spec = {
                "node": "cur_warn",
                "value": "◷ expired",
                "chip": "warn",
                "sub": "24h 内に完了せず",
                "line_in": "solid",
            }
        return [
            submit_spec,
            provider_spec,
            {**wait_fetch, **unreached},
            {**wait_import, **unreached},
        ]

    # -- 下部: そのカードに効くアクションだけ -----------------------------------

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(8)
        footer.setStyleSheet(f"border-top: 1px solid {theme.LINE};")

        self._disc_button = QPushButton("詳細 ▸")
        self._disc_button.setObjectName("buttonCardDisclosure")
        self._disc_button.setFlat(True)
        self._disc_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._disc_button.setStyleSheet(
            f"QPushButton {{ border: none; color: {theme.INK_FAINT}; font-size: 10px;"
            f" font-family: {theme.FONT_MONO_CSS}; padding: 2px 4px; text-align: left; }}"
            f"QPushButton:hover {{ color: {theme.ACCENT}; }}"
        )
        self._disc_button.clicked.connect(self._on_disclosure_clicked)
        layout.addWidget(self._disc_button)

        note_text, note_is_error = self._footer_note()
        note = QLabel(note_text)
        note.setObjectName("labelCardNote")
        note_color = theme.ERR if note_is_error else theme.INK_FAINT
        note.setStyleSheet(
            f"QLabel {{ color: {note_color}; font-size: 10px; font-family: {theme.FONT_MONO_CSS}; }}"
        )
        layout.addWidget(note)
        layout.addStretch(1)

        self.cancel_button: QPushButton | None = None
        self.check_button: QPushButton | None = None
        if self._view_state == "active":
            self.cancel_button = QPushButton("キャンセル")
            self.cancel_button.setObjectName("buttonCardCancel")
            self.cancel_button.setEnabled(str(getattr(self._job, "status", "")) in _CANCELABLE_STATUSES)
            self.cancel_button.clicked.connect(lambda: self.cancel_requested.emit(self._job_id))
            layout.addWidget(self.cancel_button)
            self.check_button = QPushButton("↻ 状態を確認")
        elif self._view_state == "collectable":
            self.check_button = QPushButton("↓ 結果を取得")
        if self.check_button is not None:
            self.check_button.setObjectName("buttonCardCheck")
            self.check_button.setStyleSheet(
                f"QPushButton {{ background-color: {theme.ACCENT}; color: #ffffff;"
                f" border: 1px solid {theme.ACCENT}; border-radius: {theme.RADIUS}px;"
                f" padding: 3px 10px; font-weight: 600; }}"
                f"QPushButton:hover {{ background-color: {theme.ACCENT_HOVER}; }}"
            )
            self.check_button.clicked.connect(lambda: self.check_requested.emit(self._job_id))
            layout.addWidget(self.check_button)
        return footer

    def _footer_note(self) -> tuple[str, bool]:
        """footer の note テキストと err 表示かどうかを返す。"""
        if self._view_state == "active":
            expires_at = getattr(self._job, "expires_at", None)
            if isinstance(expires_at, datetime):
                return f"期限 あと {_format_duration(_now_like(expires_at), expires_at)}", False
            return "provider 側で進行中", False
        if self._view_state == "collectable":
            return "回収すると fetch → import まで自動", False
        if self._view_state == "imported":
            return f"{_format_dt(getattr(self._job, 'imported_at', None))} 取込完了", False
        if self._view_state == "failed":
            return "provider が受理後に拒否 — 再送は Annotate から", True
        if self._view_state == "canceled":
            return "provider 側も取消済み — 回収する結果はありません", False
        return "24h window 超過で provider が打ち切り — 再送は Annotate から", False

    # -- 展開 (progressive disclosure) -----------------------------------------

    def _on_disclosure_clicked(self) -> None:
        self.set_expanded(not self._expanded)
        self.expand_toggled.emit(self._job_id, self._expanded)

    def _build_expansion(self) -> QWidget:
        """identity / requests / timeline の kv グリッド + 項目テーブルを組む。"""
        job = self._job
        expansion = QFrame()
        expansion.setObjectName("cardExpansion")
        expansion.setStyleSheet(
            f"QFrame#cardExpansion {{ background-color: {theme.PAPER};"
            f" border-top: 1px dashed {theme.LINE}; }}"
        )
        layout = QVBoxLayout(expansion)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        layout.addWidget(self._kv_heading("identity"))
        layout.addWidget(
            self._kv_grid(
                [
                    ("provider_batch_id", str(getattr(job, "provider_job_id", "") or "—")),
                    ("local job id", f"PB-{self._job_id}"),
                    ("provider", str(getattr(job, "provider", "") or "—")),
                    ("endpoint", str(getattr(job, "endpoint", "") or "—")),
                    ("model_id", str(getattr(job, "model_id", "") or "—")),
                    ("status", str(getattr(job, "status", "") or "—")),
                ]
            )
        )
        layout.addWidget(self._kv_heading("requests"))
        layout.addWidget(
            self._kv_grid(
                [
                    ("total", str(getattr(job, "request_count", 0) or 0)),
                    ("progress", "—（提供なし · 終了/未了のみ）"),
                    ("last status", str(getattr(job, "provider_status", "") or "—")),
                    ("succeeded", str(getattr(job, "succeeded_count", 0) or 0)),
                    ("failed", str(getattr(job, "failed_count", 0) or 0)),
                    (
                        "canceled / expired",
                        f"{getattr(job, 'canceled_count', 0) or 0} / {getattr(job, 'expired_count', 0) or 0}",
                    ),
                ]
            )
        )
        layout.addWidget(self._kv_heading("timeline"))
        layout.addWidget(
            self._kv_grid(
                [
                    ("submitted_at", _format_dt(getattr(job, "submitted_at", None))),
                    ("completed_at", _format_dt(getattr(job, "completed_at", None))),
                    ("canceled_at", _format_dt(getattr(job, "canceled_at", None))),
                    ("expires_at", _format_dt(getattr(job, "expires_at", None))),
                    ("imported_at", _format_dt(getattr(job, "imported_at", None))),
                    ("", ""),
                ]
            )
        )

        layout.addWidget(self._kv_heading("items"))
        self.items_table = QTableWidget()
        self.items_table.setColumnCount(5)
        self.items_table.setHorizontalHeaderLabels(
            ["Custom ID", "Image ID", "Status", "Error Type", "Error Message"]
        )
        self.items_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.setMaximumHeight(180)
        layout.addWidget(self.items_table)
        return expansion

    @staticmethod
    def _kv_heading(text: str) -> QLabel:
        heading = QLabel(text.upper())
        heading.setStyleSheet(
            f"QLabel {{ color: {theme.INK_FAINT}; font-size: 9px; letter-spacing: 1px;"
            f" font-weight: 600; font-family: {theme.FONT_MONO_CSS}; margin-top: 4px; }}"
        )
        return heading

    @staticmethod
    def _kv_grid(pairs: list[tuple[str, str]]) -> QWidget:
        """3 列の kv グリッド (mock .kv) を組む。"""
        grid_widget = QFrame()
        grid_widget.setStyleSheet(
            f"QFrame {{ background-color: {theme.CARD}; border: 1px solid {theme.LINE};"
            f" border-radius: {theme.RADIUS}px; }}"
        )
        grid = QGridLayout(grid_widget)
        grid.setContentsMargins(1, 1, 1, 1)
        grid.setSpacing(1)
        for index, (key, value) in enumerate(pairs):
            row, column = divmod(index, 3)
            cell = QWidget()
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(10, 4, 10, 4)
            cell_layout.setSpacing(0)
            key_label = QLabel(key.upper())
            key_label.setStyleSheet(
                f"QLabel {{ color: {theme.INK_FAINT}; font-size: 9px;"
                f" font-family: {theme.FONT_MONO_CSS}; border: none; }}"
            )
            value_label = QLabel(value)
            value_label.setStyleSheet(
                f"QLabel {{ color: {theme.INK}; font-size: {theme.FONT_SIZE_SMALL}px;"
                f" font-family: {theme.FONT_MONO_CSS}; border: none; }}"
            )
            cell_layout.addWidget(key_label)
            cell_layout.addWidget(value_label)
            grid.addWidget(cell, row, column)
        return grid_widget

    def _render_items(self) -> None:
        self.items_table.setRowCount(0)
        for item_obj in self._items:
            row = self.items_table.rowCount()
            self.items_table.insertRow(row)
            values = [
                str(getattr(item_obj, "custom_id", "")),
                str(getattr(item_obj, "image_id", "") or ""),
                str(getattr(item_obj, "status", "")),
                str(getattr(item_obj, "error_type", "") or ""),
                str(getattr(item_obj, "error_message", "") or ""),
            ]
            for column, value in enumerate(values):
                self.items_table.setItem(row, column, QTableWidgetItem(value))

    # -- 内部ヘルパ --------------------------------------------------------------

    def _is_terminal(self) -> bool:
        return self._view_state in {"imported", "failed", "canceled", "expired"}
