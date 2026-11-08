from __future__ import annotations

import datetime

from PySide6.QtCore import QSize, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

from lorairo.domain.registration_date_range import LocalDayRange
from lorairo.gui import theme

HistogramBin = tuple[datetime.date, datetime.date, int]


class DateHistogramWidget(QWidget):
    """Image.created_at 分布ヒストグラム表示ウィジェット (ローカル暦日単位のビン)。

    バーをクリックすると、そのビンの暦日範囲を ``range_selected`` で通知する。
    このウィジェット自身は選択状態を持たない。強調表示するバーは、検索条件の
    唯一の状態である登録日スライダーの範囲から :meth:`set_selected_range` で決まる
    (ADR 0100)。
    """

    # (開始日, 終了日 (含む)) の datetime.date
    range_selected = Signal(object, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bins: list[HistogramBin] = []
        self._selected_range: LocalDayRange | None = None
        self.setMinimumHeight(50)
        self.setToolTip("クリックして登録日の範囲に設定")

    def update_histogram(self, bins: list[HistogramBin]) -> None:
        """ヒストグラムデータを更新して再描画する。

        Args:
            bins: (開始日, 終了日 (含む), count) のリスト。空リストでクリア。
        """
        self._bins = bins
        self.update()

    def clear(self) -> None:
        """ヒストグラムをクリアして空状態にする。"""
        self._bins = []
        self._selected_range = None
        self.update()

    def set_selected_range(self, day_range: LocalDayRange | None) -> None:
        """強調表示する範囲を設定する (シグナルは発火しない)。

        Args:
            day_range: 登録日フィルタの暦日範囲。None は強調なし。
        """
        self._selected_range = day_range
        self.update()

    def selected_index(self) -> int | None:
        """強調表示中のビン (範囲がビンと完全に一致するもの) の位置を返す。"""
        if self._selected_range is None:
            return None
        for i, (start, end, _) in enumerate(self._bins):
            if LocalDayRange(start, end) == self._selected_range:
                return i
        return None

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
        selected_idx = self.selected_index()
        for i, (_, _, count) in enumerate(self._bins):
            bar_h = max(2, int(count / max_count * h * 0.85))
            x = int(i * bar_w)
            # Theme v1 (Issue #760): 選択バー = accent、非選択バー = info
            color = QColor(theme.ACCENT) if i == selected_idx else QColor(theme.INFO)
            painter.fillRect(x + 1, h - bar_h, int(bar_w) - 2, bar_h, color)
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """クリックされたバーの暦日範囲を range_selected で通知する。"""
        if not self._bins:
            return
        bar_w = self.width() / len(self._bins)
        idx = int(event.position().x() / bar_w)
        idx = max(0, min(idx, len(self._bins) - 1))
        start, end, _ = self._bins[idx]
        self.range_selected.emit(start, end)
