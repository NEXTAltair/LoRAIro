"""DS v12 ステータスチップ部品 (Issue #852 DS 部品ライブラリ)。

claude.ai/design の Chip 定義に対応する再利用可能な QLabel サブクラス。
``theme.chip_qss`` をラップし、ドット文法を内包する。

ドット文法 (DS 仕様):
    ●(filled) = ok / info / accent / err — 「利用可 / 完了 / 実行中 / 失敗」
    ○(open)   = warn / neutral / muted  — 「要対応 / 待機 / 無効」
    dot="none" で非表示、dot 明示でオーバーライド可能。
"""

from __future__ import annotations

from typing import Literal

from PySide6.QtWidgets import QLabel, QWidget

from lorairo.gui import theme
from lorairo.gui.theme import ChipKind

# kind 別のデフォルトドット文字
_DOT_FILLED = "●"
_DOT_OPEN = "○"

# filled ドットを使う kind 集合
_FILLED_KINDS: frozenset[ChipKind] = frozenset({"ok", "info", "accent", "err"})


def _resolve_dot(kind: ChipKind, dot: Literal["filled", "open", "none"] | None) -> str:
    """ドット指示と kind から表示するドット文字を返す。

    Args:
        kind: チップ種別。
        dot: ドット明示指定。None の場合は kind から自動決定。

    Returns:
        表示するドット文字列。"none" 指定時は空文字。
    """
    if dot is None:
        # kind に応じた既定ドット
        return _DOT_FILLED if kind in _FILLED_KINDS else _DOT_OPEN
    if dot == "none":
        return ""
    if dot == "filled":
        return _DOT_FILLED
    # dot == "open"
    return _DOT_OPEN


class DsChip(QLabel):
    """DS v12 ステータスチップ — kind・ドット・テキストをカプセル化した QLabel。

    既存コードが ``QLabel + chip_qss()`` を直書きしている箇所を置換する
    公式部品。2 画面以上で使う chip は本クラスに統一する (Issue #852)。

    Args:
        text: チップに表示するテキスト (ドットを除く本文)。
        kind: チップ種別。既定は "neutral"。
        dot: ドット文法の明示指定。None (既定) は kind に従って自動決定。
            "filled" で ●、"open" で ○、"none" でドット非表示。
        parent: 親ウィジェット。

    Example:
        >>> chip = DsChip("完了", kind="ok")
        >>> chip2 = DsChip("保留", kind="warn", dot="none")
        >>> chip3 = DsChip("タグ名", kind="accent", dot="filled")
    """

    def __init__(
        self,
        text: str,
        kind: ChipKind = "neutral",
        dot: Literal["filled", "open", "none"] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._raw_text = text
        self._kind: ChipKind = kind
        self._dot: Literal["filled", "open", "none"] | None = dot

        self._apply_style()
        self._refresh_text()

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def set_text(self, text: str) -> None:
        """チップのテキストを更新する (ドット文字は自動付与)。

        Args:
            text: 新しいテキスト (ドットを除く本文)。
        """
        self._raw_text = text
        self._refresh_text()

    def set_kind(self, kind: ChipKind) -> None:
        """チップ種別を変更し、スタイルとテキストを再描画する。

        dot が None (自動) のとき、kind 変更に伴いドット文字も更新される。

        Args:
            kind: 新しいチップ種別。
        """
        self._kind = kind
        self._apply_style()
        self._refresh_text()

    # ------------------------------------------------------------------
    # 内部ヘルパー
    # ------------------------------------------------------------------

    def _apply_style(self) -> None:
        """theme.chip_qss を適用する。"""
        self.setStyleSheet(theme.chip_qss(self._kind))

    def _refresh_text(self) -> None:
        """ドット文字 + 本文を組み合わせて QLabel テキストを更新する。"""
        dot_char = _resolve_dot(self._kind, self._dot)
        if dot_char:
            # ドットと本文の間にスペースを挿入
            super().setText(f"{dot_char} {self._raw_text}")
        else:
            super().setText(self._raw_text)
