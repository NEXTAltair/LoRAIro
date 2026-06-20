"""実行詳細設定モーダル (Wireframes v12 Frame 3 RunSettings)。

パイプライン実行前の runtime オプションを 1 つのモーダルで提示する
(DS AnnotateScreen RunSettings)。並列実行数 / リトライ / 失敗時の挙動 /
rating ゲート / 既存値上書き / dedupe / dry-run の 7 項目を DS の行レイアウトで
並べる。

バックエンド配線状況 (Issue #789):
- ``rating_gate`` / ``dry_run``: 実装済の概念 (moderation preflight / dry-run)。
  操作可能で :class:`RunOptions` に反映する。
- ``concurrency`` / ``retries`` / ``on_fail`` / ``overwrite``: worker 側未実装の
  ため disabled 表示 (見せかけ操作を作らない)。実 run への適用は後続 backend
  issue で controller→worker_service→AnnotationWorker に配線する。
- ``dedupe``: multimodal は常時 dedupe (ledger と整合) のため ON 固定 disabled。

SegmentedControl は ADR 0073 に従い ``QButtonGroup`` + checkable flat
``QPushButton`` の連結行で表現する。
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import theme

_UNIMPLEMENTED_TOOLTIP = "バックエンド未実装 — 後続 issue で worker に配線予定"
_DEDUPE_TOOLTIP = "multimodal は常時 dedupe (同一推論を 1 回に集約)。常に ON。"


@dataclass(frozen=True)
class RunOptions:
    """パイプライン実行 runtime オプション (DS RunSettings の確定値)。

    Attributes:
        concurrency: 並列推論ワーカー数。
        retries: 失敗時の自動リトライ上限。
        on_fail: リトライ上限後の挙動 ("skip" / "stop")。
        rating_gate: 送信前 moderation preflight を行うか。
        overwrite: 既存アノテーションを上書きするか。
        dedupe: multimodal 推論を 1 回に集約するか (常時 True)。
        dry_run: 実推論せずジョブ件数・推定のみ検証するか。
    """

    concurrency: int = 4
    retries: int = 2
    on_fail: str = "skip"
    rating_gate: bool = True
    overwrite: bool = False
    dedupe: bool = True
    dry_run: bool = False


def _segment_button_qss(active: bool) -> str:
    """SegmentedControl セグメント 1 個分の QSS (active = accent-soft 塗り)。"""
    if active:
        return (
            f"QPushButton {{ background-color: {theme.ACCENT_SOFT}; color: {theme.ACCENT_HOVER};"
            f" border: {theme.BORDER_WIDTH}px solid {theme.ACCENT_BORDER};"
            f" border-radius: {theme.RADIUS_BADGE}px; padding: 2px 10px;"
            f" font-size: {theme.FONT_SIZE_SMALL}px; font-weight: {theme.FONT_WEIGHT_SEMIBOLD}; }}"
        )
    return (
        f"QPushButton {{ background-color: {theme.CARD}; color: {theme.INK_SOFT};"
        f" border: {theme.BORDER_WIDTH}px solid {theme.LINE}; border-radius: {theme.RADIUS_BADGE}px;"
        f" padding: 2px 10px; font-size: {theme.FONT_SIZE_SMALL}px; }}"
        f" QPushButton:disabled {{ color: {theme.INK_FAINT}; background-color: {theme.PAPER_SHADE}; }}"
    )


class SegmentedControl(QWidget):
    """bordered な横トグル (DS SegmentedControl、ADR 0073)。

    排他選択の checkable ``QPushButton`` を ``QButtonGroup`` で束ねる。active
    セグメントは accent-soft 塗り。``value()`` で現在値を返す。
    """

    def __init__(
        self,
        options: list[tuple[str, str]],
        value: str,
        parent: QWidget | None = None,
    ) -> None:
        """セグメントを構築する。

        Args:
            options: (value, label) のリスト。
            value: 初期選択 value。
            parent: 親 widget。
        """
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        for opt_value, label in options:
            button = QPushButton(label, self)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setChecked(opt_value == value)
            button.setStyleSheet(_segment_button_qss(opt_value == value))
            button.clicked.connect(lambda _checked=False, v=opt_value: self._select(v))
            self._group.addButton(button)
            self._buttons[opt_value] = button
            layout.addWidget(button)

        self._value = value

    def _select(self, value: str) -> None:
        """セグメント選択を更新し active 塗りを付け替える。"""
        self._value = value
        for opt_value, button in self._buttons.items():
            button.setStyleSheet(_segment_button_qss(opt_value == value))

    def value(self) -> str:
        """現在選択されている value を返す。"""
        return self._value


class RunSettingsDialog(QDialog):
    """実行詳細設定モーダル (DS Frame 3 RunSettings)。

    :meth:`run_options` で確定値を :class:`RunOptions` として返す。
    rating_gate / dry_run のみ操作可能、未実装オプションは disabled。
    """

    def __init__(self, staged_count: int, parent: QWidget | None = None) -> None:
        """モーダルを構築する。

        Args:
            staged_count: 対象ステージング枚数 (ヘッダ表示用)。
            parent: 親 widget。
        """
        super().__init__(parent)
        self.setWindowTitle("実行の詳細設定")
        self.setObjectName("runSettingsDialog")
        self.setModal(True)

        layout = QVBoxLayout(self)

        header = QLabel(f"このパイプライン実行に適用 · staged {staged_count} 枚", self)
        header.setObjectName("runSettingsHeader")
        header.setStyleSheet(f"color: {theme.INK_SOFT}; font-size: {theme.FONT_SIZE_SMALL}px;")
        layout.addWidget(header)

        # 並列実行数 (未実装 → disabled)
        self._concurrency = self._add_segment_row(
            layout,
            "並列実行数 concurrency",
            "同時に走らせる推論ワーカー数。多いほど速いが GPU/レート上限に注意。",
            [("1", "1"), ("2", "2"), ("4", "4"), ("8", "8")],
            "4",
            enabled=False,
        )
        # リトライ回数 (未実装 → disabled)
        self._retries = self._add_segment_row(
            layout,
            "リトライ回数 retries",
            "失敗した推論を自動再試行する上限回数 (指数バックオフ)。",
            [("0", "0"), ("1", "1"), ("2", "2"), ("3", "3")],
            "2",
            enabled=False,
        )
        # 失敗時の挙動 (未実装 → disabled)
        self._on_fail = self._add_segment_row(
            layout,
            "失敗時の挙動 on failure",
            "リトライ上限後の扱い。skip=その画像だけ飛ばす / stop=ジョブ全体を停止。",
            [("skip", "スキップ"), ("stop", "停止")],
            "skip",
            enabled=False,
        )
        # rating ゲート (実装済 → 操作可)
        self._rating_gate = self._add_segment_row(
            layout,
            "rating ゲート preflight",
            "X / XXX 判定の画像は annotation API に送らない (推奨)。",
            [("on", "ON"), ("off", "OFF")],
            "on",
            enabled=True,
        )
        # 既存値の上書き (未実装 → disabled)
        self._overwrite = self._add_segment_row(
            layout,
            "既存値の上書き overwrite",
            "既にアノテーション済みの枠はスキップ (off)。",
            [("off", "OFF"), ("on", "ON")],
            "off",
            enabled=False,
        )
        # dedupe (常時 ON → disabled)
        self._dedupe = self._add_segment_row(
            layout,
            "マルチモーダル dedupe",
            "同一モデルが複数ステージに跨る場合、推論を 1 回にまとめてコストを抑える。",
            [("on", "ON"), ("off", "OFF")],
            "on",
            enabled=False,
            tooltip=_DEDUPE_TOOLTIP,
        )

        # dry-run (実装済 → 操作可)
        self._dry_run = QCheckBox("ドライラン dry-run", self)
        self._dry_run.setObjectName("runSettingsDryRun")
        self._dry_run.setToolTip("実際に推論せずジョブ件数・推定コストだけを検証する。")
        layout.addWidget(self._dry_run)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setText("保存して実行")
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _add_segment_row(
        self,
        layout: QVBoxLayout,
        title: str,
        sub: str,
        options: list[tuple[str, str]],
        value: str,
        *,
        enabled: bool,
        tooltip: str | None = None,
    ) -> SegmentedControl:
        """1 行 (タイトル + 補足 + SegmentedControl) を追加し control を返す。"""
        row = QWidget(self)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 6, 0, 6)

        text_box = QVBoxLayout()
        title_label = QLabel(title, row)
        title_label.setStyleSheet(
            f"font-size: {theme.FONT_SIZE_SMALL}px; font-weight: {theme.FONT_WEIGHT_SEMIBOLD};"
        )
        sub_label = QLabel(sub, row)
        sub_label.setWordWrap(True)
        sub_label.setStyleSheet(f"color: {theme.INK_FAINT}; font-size: {theme.FONT_SIZE_META}px;")
        text_box.addWidget(title_label)
        text_box.addWidget(sub_label)
        row_layout.addLayout(text_box, 1)

        control = SegmentedControl(options, value, row)
        if not enabled:
            control.setEnabled(False)
            control.setToolTip(tooltip or _UNIMPLEMENTED_TOOLTIP)
        elif tooltip:
            control.setToolTip(tooltip)
        row_layout.addWidget(control)

        layout.addWidget(row)
        return control

    def run_options(self) -> RunOptions:
        """ダイアログの現在値を :class:`RunOptions` として返す。"""
        return RunOptions(
            concurrency=int(self._concurrency.value()),
            retries=int(self._retries.value()),
            on_fail=self._on_fail.value(),
            rating_gate=self._rating_gate.value() == "on",
            overwrite=self._overwrite.value() == "on",
            dedupe=self._dedupe.value() == "on",
            dry_run=self._dry_run.isChecked(),
        )
