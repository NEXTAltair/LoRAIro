"""ページナビゲーション用ウィジェット。"""

from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from .. import theme


class PaginationNavWidget(QWidget):
    """固定フッターに配置するページネーションUI。

    ビジュアルは Wireframes v12 / Design System の Pagination 文法に整合
    (件数・範囲を mono で表示・ADR 0006、borders-not-shadows のボタン)。
    """

    page_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_page = 1
        self._total_pages = 1
        self._is_loading = False
        self._total_items: int | None = None
        self._page_size: int | None = None

        self._btn_first = QPushButton("|<", self)
        self._btn_prev = QPushButton("<", self)
        self._label_page = QLabel("Page 1 / 1", self)
        self._btn_next = QPushButton(">", self)
        self._btn_last = QPushButton(">|", self)
        self._label_range = QLabel("", self)
        self._label_loading = QLabel("", self)

        for btn in (self._btn_first, self._btn_prev, self._btn_next, self._btn_last):
            btn.setStyleSheet(self._nav_button_qss())
        self._label_page.setStyleSheet(self._page_label_qss())
        self._label_range.setStyleSheet(self._range_label_qss())
        self._label_loading.setStyleSheet(self._range_label_qss())

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self._btn_first)
        layout.addWidget(self._btn_prev)
        layout.addWidget(self._label_page)
        layout.addWidget(self._btn_next)
        layout.addWidget(self._btn_last)
        layout.addWidget(self._label_range)
        layout.addStretch(1)
        layout.addWidget(self._label_loading)

        self._btn_first.clicked.connect(self._go_first)
        self._btn_prev.clicked.connect(self._go_prev)
        self._btn_next.clicked.connect(self._go_next)
        self._btn_last.clicked.connect(self._go_last)

        self.update_state(current=1, total=1, is_loading=False)

    @staticmethod
    def _nav_button_qss() -> str:
        """DS ナビゲーションボタン QSS (card 地・line border・shadow 不使用)。"""
        return (
            f"QPushButton {{ background: {theme.CARD}; color: {theme.INK};"
            f" border: 1px solid {theme.LINE}; border-radius: {theme.RADIUS}px;"
            f" padding: 2px 9px; font-size: {theme.FONT_SIZE_SMALL}px; }}"
            f" QPushButton:hover:enabled {{ border-color: {theme.ACCENT}; color: {theme.ACCENT}; }}"
            f" QPushButton:disabled {{ color: {theme.INK_FAINT};"
            f" background: {theme.PAPER_SHADE}; }}"
        )

    @staticmethod
    def _page_label_qss() -> str:
        """ページ番号ラベル QSS (mono)。"""
        return (
            f"color: {theme.INK}; font-family: 'JetBrains Mono';"
            f" font-size: {theme.FONT_SIZE_SMALL}px; padding: 0 4px;"
        )

    @staticmethod
    def _range_label_qss() -> str:
        """件数・範囲 / ローディングラベル QSS (mono・補助色)。"""
        return (
            f"color: {theme.INK_SOFT}; font-family: 'JetBrains Mono';"
            f" font-size: {theme.FONT_SIZE_SMALL}px; padding: 0 4px;"
        )

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

    def update_state(
        self,
        current: int,
        total: int,
        is_loading: bool,
        total_items: int | None = None,
        page_size: int | None = None,
    ) -> None:
        """ページ状態とボタン活性を更新する。

        Args:
            current: 現在ページ (1 始まり)。
            total: 総ページ数。
            is_loading: ロード中フラグ。
            total_items: 検索結果の総件数。指定時に件数・範囲を表示する (ADR 0006)。
            page_size: 1ページあたりの件数。total_items と併せて範囲を算出する。
        """
        self._current_page = max(1, current)
        self._total_pages = max(1, total)
        self._is_loading = is_loading
        self._total_items = total_items
        self._page_size = page_size

        self._label_page.setText(f"Page {self._current_page} / {self._total_pages}")
        self._label_range.setText(self._format_range())
        self._label_loading.setText("Loading..." if self._is_loading else "")

        can_go_prev = self._current_page > 1 and not self._is_loading
        can_go_next = self._current_page < self._total_pages and not self._is_loading

        self._btn_first.setEnabled(can_go_prev)
        self._btn_prev.setEnabled(can_go_prev)
        self._btn_next.setEnabled(can_go_next)
        self._btn_last.setEnabled(can_go_next)

    def _format_range(self) -> str:
        """現在ページの表示範囲と総件数を ``開始-終了 / 総件数件`` 形式で返す。

        total_items / page_size が未指定なら空文字を返す (件数・範囲を非表示)。
        """
        if self._total_items is None or self._page_size is None or self._page_size <= 0:
            return ""
        if self._total_items <= 0:
            return "0 件"
        start = (self._current_page - 1) * self._page_size + 1
        end = min(self._current_page * self._page_size, self._total_items)
        return f"{start:,}-{end:,} / {self._total_items:,} 件"
