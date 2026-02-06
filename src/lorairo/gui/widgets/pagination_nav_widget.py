"""ページナビゲーション用ウィジェット。"""

from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


class PaginationNavWidget(QWidget):
    """固定フッターに配置するページネーションUI。"""

    page_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_page = 1
        self._total_pages = 1
        self._is_loading = False

        self._btn_first = QPushButton("|<", self)
        self._btn_prev = QPushButton("<", self)
        self._label_page = QLabel("Page 1 / 1", self)
        self._btn_next = QPushButton(">", self)
        self._btn_last = QPushButton(">|", self)
        self._label_loading = QLabel("", self)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.addWidget(self._btn_first)
        layout.addWidget(self._btn_prev)
        layout.addWidget(self._label_page)
        layout.addWidget(self._btn_next)
        layout.addWidget(self._btn_last)
        layout.addStretch(1)
        layout.addWidget(self._label_loading)

        self._btn_first.clicked.connect(self._go_first)
        self._btn_prev.clicked.connect(self._go_prev)
        self._btn_next.clicked.connect(self._go_next)
        self._btn_last.clicked.connect(self._go_last)

        self.update_state(current=1, total=1, is_loading=False)

    @Slot()
    def _go_first(self) -> None:
        self.page_requested.emit(1)

    @Slot()
    def _go_prev(self) -> None:
        self.page_requested.emit(self._current_page - 1)

    @Slot()
    def _go_next(self) -> None:
        self.page_requested.emit(self._current_page + 1)

    @Slot()
    def _go_last(self) -> None:
        self.page_requested.emit(self._total_pages)

    def update_state(self, current: int, total: int, is_loading: bool) -> None:
        """ページ状態とボタン活性を更新する。"""
        self._current_page = max(1, current)
        self._total_pages = max(1, total)
        self._is_loading = is_loading

        self._label_page.setText(f"Page {self._current_page} / {self._total_pages}")
        self._label_loading.setText("Loading..." if self._is_loading else "")

        can_go_prev = self._current_page > 1 and not self._is_loading
        can_go_next = self._current_page < self._total_pages and not self._is_loading

        self._btn_first.setEnabled(can_go_prev)
        self._btn_prev.setEnabled(can_go_prev)
        self._btn_next.setEnabled(can_go_next)
        self._btn_last.setEnabled(can_go_next)
