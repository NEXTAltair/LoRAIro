"""DS v12 種別バッジ部品 (Issue #1105 DS 部品ライブラリ)。

claude.ai/design の TypeBadge に対応する再利用可能な QLabel サブクラス。
``theme.badge_qss`` をラップし、provider 名や job 種別などの中立的なメタ情報を
控えめなバッジ面で表示する。

``preflight_summary_widget.py`` のコメント「DsBadge 未実装」が想定していた公式
部品。``badge_qss()`` 直書きの QLabel を置換する。DsChip と同じ作法
(テキスト + 任意 kind) で使う。
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QWidget

from lorairo.gui import theme
from lorairo.gui.theme import ChipKind


class DsBadge(QLabel):
    """DS v12 種別バッジ — テキスト + 任意 kind をカプセル化した QLabel。

    既存コードが ``QLabel + badge_qss()`` を直書きしている箇所を置換する公式部品。
    chip より小角丸で控えめな地色のバッジ (provider 名 / job 種別など)。

    Args:
        text: バッジに表示するテキスト。
        kind: バッジ色種別。None (既定) は中立の type バッジ (paper-shade 地)。
            ``ChipKind`` を渡すと geometry は保ったまま色だけ差し替える。
        parent: 親ウィジェット。

    Example:
        >>> badge = DsBadge("openai")
        >>> badge2 = DsBadge("batch", kind="accent")
    """

    def __init__(
        self,
        text: str,
        kind: ChipKind | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self._kind: ChipKind | None = kind
        self._apply_style()

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def set_text(self, text: str) -> None:
        """バッジのテキストを更新する。"""
        super().setText(text)

    def set_kind(self, kind: ChipKind | None) -> None:
        """バッジ色種別を変更し、スタイルを再適用する。

        Args:
            kind: 新しいバッジ色種別。None で中立の type バッジへ戻す。
        """
        self._kind = kind
        self._apply_style()

    @property
    def kind(self) -> ChipKind | None:
        """現在のバッジ色種別 (None は中立)。"""
        return self._kind

    # ------------------------------------------------------------------
    # 内部ヘルパー
    # ------------------------------------------------------------------

    def _apply_style(self) -> None:
        """theme.badge_qss を適用する。"""
        self.setStyleSheet(theme.badge_qss(self._kind))
