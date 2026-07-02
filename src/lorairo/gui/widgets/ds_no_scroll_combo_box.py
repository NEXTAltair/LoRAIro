"""DS 部品ライブラリ — DsNoScrollComboBox (Issue #1051)。

Qt の ``QComboBox`` は既定でホバー中のホイールイベントを受け取って値を変更するため、
スクロール可能なパネル内に置くと「眺めてスクロールしているだけで選択が変わる」事故が
必ず起きる。この部品は定番の NoScrollComboBox パターンで対策する:

- ``StrongFocus``: ホバーだけではフォーカスしない (クリック / Tab でのみフォーカス)
- 非フォーカス時の ``wheelEvent`` は ``ignore()`` して親のスクロールに回す
- フォーカス済み (クリック後) のホイール操作は従来どおり値変更に使える

スクロール領域内に ``QComboBox`` を置く場合はこの部品を使うこと。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QComboBox, QWidget


class DsNoScrollComboBox(QComboBox):
    """ホイールスクロール通過で値が変わらない QComboBox (Issue #1051)。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # ホバーだけではフォーカスしない (クリック / Tab でのみフォーカス)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event: QWheelEvent) -> None:
        """非フォーカス時はホイールを無視して親のスクロールへ回す。"""
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)
