"""DS 部品ライブラリ — ホイール誤操作防止コントロール群 (Issue #1051 / #1567)。

Qt の ``QComboBox`` / ``QSpinBox`` / ``QDoubleSpinBox`` / ``QSlider`` は既定でホバー中の
ホイールイベントを受け取って値を変更するため、スクロール可能なパネル内に置くと
「眺めてスクロールしているだけで選択や数値が変わる」事故が必ず起きる。
このモジュールは定番の NoScroll パターンで対策する:

- ``StrongFocus``: ホバーだけではフォーカスしない (クリック / Tab でのみフォーカス)
- 非フォーカス時の ``wheelEvent`` は ``ignore()`` して親のスクロールに回す
- フォーカス済み (クリック後) のホイール操作は従来どおり値変更に使える

スクロール領域内にこれらの入力部品を置く場合は ``DsNoScroll*`` サブクラスを使うか、
Qt Designer 生成の既存ウィジェットには :func:`install_no_scroll_wheel_guard` を適用すること。
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QSlider, QSpinBox, QWidget


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


class DsNoScrollSpinBox(QSpinBox):
    """ホイールスクロール通過で値が変わらない QSpinBox (Issue #1567)。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event: QWheelEvent) -> None:
        """非フォーカス時はホイールを無視して親のスクロールへ回す。"""
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


class DsNoScrollDoubleSpinBox(QDoubleSpinBox):
    """ホイールスクロール通過で値が変わらない QDoubleSpinBox (Issue #1567)。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event: QWheelEvent) -> None:
        """非フォーカス時はホイールを無視して親のスクロールへ回す。"""
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


class DsNoScrollSlider(QSlider):
    """ホイールスクロール通過で値が変わらない QSlider (Issue #1567)。"""

    def __init__(
        self,
        orientation_or_parent: Qt.Orientation | QWidget | None = None,
        parent: QWidget | None = None,
    ) -> None:
        if isinstance(orientation_or_parent, Qt.Orientation):
            super().__init__(orientation_or_parent, parent)
        else:
            super().__init__(orientation_or_parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event: QWheelEvent) -> None:
        """非フォーカス時はホイールを無視して親のスクロールへ回す。"""
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


class _NoScrollWheelEventFilter(QObject):
    """非フォーカス時のホイールイベントを無視するイベントフィルタ (Issue #1567)。"""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Wheel and isinstance(watched, QWidget) and not watched.hasFocus():
            event.ignore()
            return True
        return super().eventFilter(watched, event)


def install_no_scroll_wheel_guard(widget: QWidget) -> None:
    """既存ウィジェット (.ui 生成など) にホイール誤操作防止ガードを適用する (Issue #1567)。"""
    widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    guard = _NoScrollWheelEventFilter(widget)
    guard.setObjectName("_dsNoScrollWheelGuard")
    widget.installEventFilter(guard)
