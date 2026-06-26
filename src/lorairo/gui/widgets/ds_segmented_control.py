"""DS 部品ライブラリ — DsSegmentedControl (DS SegmentedControl v1、ADR 0073 昇格)。

ADR 0073 の QButtonGroup + checkable QPushButton 実装を昇格・拡張した DS 公式部品。
2 サイズ (base / small)、count バッジ、value_changed Signal を追加している。

``run_settings_dialog.py`` の旧ローカル ``SegmentedControl`` はこの部品に差し替え済み。
他画面でも横方向排他トグルが必要な場合はこの部品を使うこと (Part of #852)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QWidget

from lorairo.gui import theme


@dataclass
class SegmentOption:
    """セグメント 1 件分のオプションデータ。

    Attributes:
        value: 内部 value (選択状態の返却値)。
        label: ボタン表示テキスト。
        count: 末尾に付くバッジ数値 (None の場合は表示なし)。
    """

    value: str
    label: str
    count: int | None = None


def _make_button_label(opt: SegmentOption) -> str:
    """バッジ付き表示テキストを生成する。

    Args:
        opt: ラベルとバッジ数を持つオプションデータ。

    Returns:
        count が設定されている場合は "label  N" 形式、なければ label のみ。
    """
    if opt.count is not None:
        return f"{opt.label}  {opt.count}"
    return opt.label


def _segment_button_qss(active: bool, size: Literal["base", "small"] = "base") -> str:
    """セグメントボタン 1 個分の QSS を返す。

    トークン定数のみを参照し、ハードコードした hex / px 値は持たない。

    Args:
        active: True の場合は accent-soft 塗り (選択中)、False は非選択塗り。
        size: "base" は標準パディング / フォントサイズ、"small" は縮小サイズ。

    Returns:
        QPushButton に適用する QSS 文字列。
    """
    # サイズ別パディング・フォントサイズをトークンから算出する
    if size == "small":
        padding = f"1px {theme.SPACE_2}px"
        font_size = theme.FONT_SIZE_META
    else:
        # base: ADR 0073 互換 padding (2px 10px)
        padding = f"2px {theme.SPACE_3}px"
        font_size = theme.FONT_SIZE_SMALL

    if active:
        return (
            f"QPushButton {{ background-color: {theme.ACCENT_SOFT}; color: {theme.ACCENT_HOVER};"
            f" border: {theme.BORDER_WIDTH}px solid {theme.ACCENT_BORDER};"
            f" border-radius: {theme.RADIUS_BADGE}px; padding: {padding};"
            f" font-size: {font_size}px; font-weight: {theme.FONT_WEIGHT_SEMIBOLD}; }}"
        )
    return (
        f"QPushButton {{ background-color: {theme.CARD}; color: {theme.INK_SOFT};"
        f" border: {theme.BORDER_WIDTH}px solid {theme.LINE};"
        f" border-radius: {theme.RADIUS_BADGE}px;"
        f" padding: {padding}; font-size: {font_size}px; }}"
        f" QPushButton:disabled {{ color: {theme.INK_FAINT};"
        f" background-color: {theme.PAPER_SHADE}; }}"
    )


class DsSegmentedControl(QWidget):
    """DS 部品ライブラリ — 横方向排他トグル (DS SegmentedControl)。

    ADR 0073 の QButtonGroup + checkable QPushButton 実装を昇格し、
    2 サイズ / count バッジ / value_changed Signal を追加した公式 DS 部品。

    Signals:
        value_changed (str): ユーザーがセグメントをクリックして選択が変わった際に
            新しい value を emit する。プログラマティックな ``set_value()`` 呼び出し
            では emit しない。

    Example::

        control = DsSegmentedControl(
            [("skip", "スキップ"), ("stop", "停止")],
            value="skip",
            size="base",
        )
        control.value_changed.connect(lambda v: print("選択:", v))

        # SegmentOption で count バッジを使う例
        opts = [
            SegmentOption("all", "すべて", count=42),
            SegmentOption("pending", "保留", count=5),
        ]
        control2 = DsSegmentedControl(opts, value="all", size="small")
    """

    value_changed = Signal(str)

    def __init__(
        self,
        options: list[tuple[str, str]] | list[SegmentOption],
        value: str,
        size: Literal["base", "small"] = "base",
        parent: QWidget | None = None,
    ) -> None:
        """セグメントを構築する。

        Args:
            options: (value, label) タプルのリスト、または :class:`SegmentOption` のリスト。
                両者を混在させることはできない。
            value: 初期選択 value。options に含まれない値を指定した場合は
                どのセグメントも選択済みにならない (checked=False)。
            size: ボタンサイズ。"base" = 標準 (デフォルト)、"small" = 縮小。
            parent: 親 widget。
        """
        super().__init__(parent)
        self._size: Literal["base", "small"] = size
        self._value = value

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        # value → QPushButton マップ (後方互換: テストが _buttons に直接アクセスする)
        self._buttons: dict[str, QPushButton] = {}

        self._build_options(options)

    # ------------------------------------------------------------------
    # 内部ヘルパー
    # ------------------------------------------------------------------

    def _normalize_options(
        self, options: list[tuple[str, str]] | list[SegmentOption]
    ) -> list[SegmentOption]:
        """options を :class:`SegmentOption` のリストに正規化する。

        Args:
            options: タプルリストまたは SegmentOption リスト。

        Returns:
            SegmentOption の統一リスト。
        """
        result: list[SegmentOption] = []
        for opt in options:
            if isinstance(opt, SegmentOption):
                result.append(opt)
            else:
                # (value, label) タプル
                result.append(SegmentOption(value=opt[0], label=opt[1]))
        return result

    def _build_options(self, options: list[tuple[str, str]] | list[SegmentOption]) -> None:
        """正規化されたオプション群からボタンを生成してレイアウトに追加する。

        Args:
            options: タプルまたは SegmentOption のリスト。
        """
        normalized = self._normalize_options(options)
        for opt in normalized:
            button = QPushButton(_make_button_label(opt), self)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            is_active = opt.value == self._value
            button.setChecked(is_active)
            button.setStyleSheet(_segment_button_qss(is_active, self._size))
            # クリック時は emit あり (_on_click)
            button.clicked.connect(lambda _checked=False, v=opt.value: self._on_click(v))
            self._group.addButton(button)
            self._buttons[opt.value] = button
            self._layout.addWidget(button)

    def _on_click(self, value: str) -> None:
        """ユーザークリック時の選択更新 + value_changed emit。"""
        self._select(value)
        self.value_changed.emit(value)

    def _select(self, value: str) -> None:
        """選択 value を更新し active / 非 active の QSS を付け替える (emit なし)。

        Args:
            value: 新しい選択 value。
        """
        self._value = value
        for opt_value, button in self._buttons.items():
            button.setStyleSheet(_segment_button_qss(opt_value == value, self._size))

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def value(self) -> str:
        """現在選択されている value を返す。

        Returns:
            選択中のセグメント value 文字列。
        """
        return self._value

    def set_value(self, value: str) -> None:
        """選択セグメントをプログラマティックに切り替える。

        ``value_changed`` は emit しない (UI 同期のみ)。
        emit が必要な場合は ``value_changed.emit(value)`` を明示的に呼ぶこと。

        Args:
            value: 選択したい value 文字列。``_buttons`` に存在しない値の場合は何もしない。
        """
        if value not in self._buttons:
            return
        self._buttons[value].setChecked(True)
        self._select(value)

    def set_options(
        self,
        options: list[tuple[str, str]] | list[SegmentOption],
        value: str | None = None,
    ) -> None:
        """オプション一覧を再構築する。

        既存のボタンを全て削除し、新しい options でボタン群を再生成する。

        Args:
            options: 新しいオプションリスト。
            value: 新しい初期選択 value。None の場合は現在の value を引き継ぐ
                (options に含まれない場合は checked=False のセグメントなしになる)。
        """
        # 既存ボタンを削除
        for button in list(self._buttons.values()):
            self._layout.removeWidget(button)
            self._group.removeButton(button)
            button.deleteLater()
        self._buttons.clear()

        if value is not None:
            self._value = value

        self._build_options(options)
