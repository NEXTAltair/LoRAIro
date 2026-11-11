"""DS v12 ボタン部品 (Issue #1601、#1571 follow-up)。

claude.ai/design の Button 定義 (primary / secondary) に対応する ``QPushButton`` サブクラス。
これまで各 widget が ``setStyleSheet`` で個別に組んでいた「主ボタン (accent 塗り)」と
「補助ボタン (paper-shade 塗り)」を 1 部品へ統一する。

スタイルはすべて ``lorairo.gui.theme`` のトークンから組み立て、ハードコード値は持たない。
``:hover`` / ``:focus`` / ``:disabled`` の各状態を部品側で定義するので、呼び出し側は
QSS を上書きしないこと (見た目を変えたい場合は部品側へ kind / size を追加する)。
"""

from __future__ import annotations

from typing import Literal

from PySide6.QtWidgets import QPushButton, QWidget

from lorairo.gui import theme

DsButtonKind = Literal["primary", "secondary"]
DsButtonSize = Literal["base", "small"]


def ds_button_qss(kind: DsButtonKind = "primary", size: DsButtonSize = "base") -> str:
    """DsButton 用 QSS を返す。

    Args:
        kind: "primary" = accent 塗りの主アクション、"secondary" = paper-shade 塗りの補助。
        size: "base" = 標準パディング / 本文フォント、"small" = 縮小 (補助テキストサイズ)。

    Returns:
        ``QPushButton`` に適用する QSS 文字列。
    """
    if size == "small":
        padding = f"{theme.SPACE_1 - 1}px {theme.SPACE_2 + 2}px"
        font_size = theme.FONT_SIZE_SMALL
    else:
        padding = f"{theme.SPACE_1}px {theme.SPACE_3}px"
        font_size = theme.FONT_SIZE_BASE

    common = (
        f"border-radius: {theme.RADIUS}px; padding: {padding}; font-size: {font_size}px;"
        f" font-weight: {theme.FONT_WEIGHT_SEMIBOLD};"
    )
    disabled = (
        f" QPushButton:disabled {{ background-color: {theme.PAPER_SHADE}; color: {theme.INK_FAINT};"
        f" border: {theme.BORDER_WIDTH}px solid {theme.LINE}; }}"
    )
    if kind == "primary":
        return (
            f"QPushButton {{ background-color: {theme.ACCENT}; color: {theme.TEXT_ON_ACCENT};"
            f" border: {theme.BORDER_WIDTH}px solid {theme.ACCENT}; {common} }}"
            f" QPushButton:hover {{ background-color: {theme.ACCENT_HOVER};"
            f" border-color: {theme.ACCENT_HOVER}; }}"
            # accent 塗りと同色の枠ではフォーカスが見えないため、枠色を ink へ切り替える
            f" QPushButton:focus {{ border-color: {theme.INK}; }}" + disabled
        )
    return (
        f"QPushButton {{ background-color: {theme.PAPER_SHADE}; color: {theme.INK_SOFT};"
        f" border: {theme.BORDER_WIDTH}px solid {theme.LINE}; {common} }}"
        f" QPushButton:hover {{ background-color: {theme.LINE}; }}"
        f" QPushButton:focus {{ border-color: {theme.ACCENT}; }}" + disabled
    )


class DsButton(QPushButton):
    """DS v12 ボタン — primary / secondary の 2 種別を持つ QPushButton。

    2 画面以上で使うボタン種別は本クラスに統一する。``clicked`` など ``QPushButton``
    の Signal / API はそのまま使える。

    Args:
        text: ボタンに表示するテキスト。
        kind: ボタン種別。"primary" (既定) は accent 塗りの主アクション、
            "secondary" は paper-shade 塗りの補助アクション。
        size: ボタンサイズ。"base" (既定) は標準、"small" は縮小。
        parent: 親ウィジェット。

    Example:
        >>> run = DsButton("実行", kind="primary")
        >>> validate = DsButton("検証", kind="secondary", size="small")
    """

    def __init__(
        self,
        text: str = "",
        kind: DsButtonKind = "primary",
        size: DsButtonSize = "base",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self._kind: DsButtonKind = kind
        self._size: DsButtonSize = size
        self._apply_style()

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def kind(self) -> DsButtonKind:
        """現在のボタン種別を返す。"""
        return self._kind

    def set_kind(self, kind: DsButtonKind) -> None:
        """ボタン種別を変更しスタイルを再適用する。

        Args:
            kind: 新しいボタン種別。
        """
        self._kind = kind
        self._apply_style()

    # ------------------------------------------------------------------
    # 内部ヘルパー
    # ------------------------------------------------------------------

    def _apply_style(self) -> None:
        """kind / size に応じた QSS を適用する。"""
        self.setStyleSheet(ds_button_qss(self._kind, self._size))
