"""DS 部品ライブラリ: KPI サマリタイル (SummaryStat) ウィジェット (Issue #852)。

claude.ai/design フィードバック SummaryStat に対応する DS 部品。
縦構成: label (キャプション) → value (数値/状態テキスト、tone で着色) → sub (任意サブテキスト)。
"""

from __future__ import annotations

from typing import Literal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from lorairo.gui import theme

# tone 文字列の型エイリアス
ToneLiteral = Literal["ok", "warn", "err", "info", "accent"]

# tone → トークン色のマッピング
_TONE_COLOR: dict[str, str] = {
    "ok": theme.OK,
    "warn": theme.WARN,
    "err": theme.ERR,
    "info": theme.INFO,
    "accent": theme.ACCENT,
}


class DsSummaryStat(QFrame):
    """DS KPI サマリタイル。

    DS ライブラリの SummaryStat コンポーネント。
    label / value / sub の 3 段縦構成で KPI を表示する。
    value は tone パラメータで着色できる。

    Examples:
        >>> stat = DsSummaryStat(
        ...     label="登録済み",
        ...     value="1,234",
        ...     sub="前回比 +12",
        ...     tone="ok",
        ... )
    """

    def __init__(
        self,
        label: str,
        value: str,
        sub: str | None = None,
        tone: ToneLiteral | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """KPI サマリタイルを初期化する。

        Args:
            label: タイル上部のキャプションテキスト (小さい補助テキスト)。
            value: タイル中央の主要数値・状態テキスト (大きい mono フォント)。
            sub: タイル下部のサブテキスト。None の場合は非表示。
            tone: value の着色トーン。
                "ok": 成功 / 正常 (OK 色)。
                "warn": 警告 (WARN 色)。
                "err": エラー (ERR 色)。
                "info": 情報 / 実行中 (INFO 色)。
                "accent": 強調 (ACCENT 色)。
                None: 通常文字色 (INK)。
            parent: 親ウィジェット。
        """
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # --- label: 小さいキャプション (FONT_SIZE_SMALL / INK_SOFT) ---
        self._label_widget = QLabel(label, self)
        self._label_widget.setObjectName("summaryStatLabel")
        self._label_widget.setStyleSheet(
            f"color: {theme.INK_SOFT};"
            f" font-size: {theme.FONT_SIZE_SMALL}px;"
            f" font-family: {theme.FONT_SANS_CSS};"
        )
        layout.addWidget(self._label_widget)

        # --- value: 大きい mono テキスト、tone で着色 ---
        value_color = _TONE_COLOR.get(tone or "", theme.INK)
        self._value_widget = QLabel(value, self)
        self._value_widget.setObjectName("summaryStatValue")
        self._value_widget.setStyleSheet(
            f"color: {value_color};"
            f" font-size: {theme.FONT_SIZE_H1}px;"
            f" font-family: {theme.FONT_MONO_CSS};"
            f" font-weight: {theme.FONT_WEIGHT_SEMIBOLD};"
        )
        layout.addWidget(self._value_widget)

        # --- sub: 任意サブテキスト (mono / INK_FAINT)、None なら非表示 ---
        self._sub_widget = QLabel(self)
        self._sub_widget.setObjectName("summaryStatSub")
        self._sub_widget.setStyleSheet(
            f"color: {theme.INK_FAINT};"
            f" font-size: {theme.FONT_SIZE_SMALL}px;"
            f" font-family: {theme.FONT_MONO_CSS};"
        )
        if sub is not None:
            self._sub_widget.setText(sub)
            self._sub_widget.setVisible(True)
        else:
            self._sub_widget.setVisible(False)
        layout.addWidget(self._sub_widget)
