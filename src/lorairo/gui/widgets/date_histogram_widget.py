from __future__ import annotations

import datetime

from PySide6.QtCore import QSize, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPaintEvent, QPainter
from PySide6.QtWidgets import QWidget


class DateHistogramWidget(QWidget):
    """Image.created_at 分布ヒストグラム表示ウィジェット。

    バーをクリックすることで日付範囲フィルタを適用できる。
    """

    range_selected = Signal(datetime.datetime, datetime.datetime)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bins: list[tuple[datetime.datetime, datetime.datetime, int]] = []
        self._selected_idx: int | None = None
        self.setMinimumHeight(50)
        self.setToolTip("クリックして日付範囲でフィルタ")

    def update_histogram(self, bins: list[tuple[datetime.datetime, datetime.datetime, int]]) -> None:
        """ヒストグラムデータを更新して再描画する。

        Args:
            bins: (bin_start, bin_end, count) のリスト。空リストでクリア。
        """
        self._bins = bins
        self._selected_idx = None
        self.update()

    def clear(self) -> None:
        """ヒストグラムをクリアして空状態にする。"""
        self._bins = []
        self._selected_idx = None
        self.update()

    def sizeHint(self) -> QSize:
        """推奨サイズを返す。"""
        return QSize(300, 80)

    def paintEvent(self, event: QPaintEvent) -> None:
        """バーを描画する。"""
        if not self._bins:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        max_count = max(c for _, _, c in self._bins) or 1
        bar_w = w / len(self._bins)
        for i, (_, _, count) in enumerate(self._bins):
            bar_h = max(2, int(count / max_count * h * 0.85))
            x = int(i * bar_w)
            color = QColor("#cc5555") if i == self._selected_idx else QColor("#5588cc")
            painter.fillRect(x + 1, h - bar_h, int(bar_w) - 2, bar_h, color)
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """クリックされたバーに対応する range_selected シグナルを発火する。"""
        if not self._bins:
            return
        bar_w = self.width() / len(self._bins)
        idx = int(event.position().x() / bar_w)
        idx = max(0, min(idx, len(self._bins) - 1))
        self._selected_idx = idx
        self.update()
        start, end, _ = self._bins[idx]
        self.range_selected.emit(start, end)
