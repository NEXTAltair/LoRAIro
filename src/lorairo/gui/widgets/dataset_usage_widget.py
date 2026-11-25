"""「学習に使ったデータセット」セクションのウィジェット (#1647 / ADR 0104)。

現在表示中の画像が使われたデータセット・版・フォルダ・繰り返し数を表で並べ、行の選択で
その版・フォルダの学習テキスト (.txt) の要素を ``highlight_changed`` で上げるだけの
表示専用ウィジェット。古い版の行も出すので、通常タグに載らない古い版のタグもここで確認できる。

``lorairo.database`` / ``lorairo.services`` を import せず、表示に必要な値を
:class:`DatasetUsageEntry` として受け取る (``RelatedImagesWidget`` と同じ
「見える部分を DB 非依存に保つ」方式)。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import theme

_EMPTY_TEXT = "なし"
_HEADERS: tuple[str, ...] = ("データセット", "版", "フォルダ", "繰り返し")


@dataclass(frozen=True, slots=True)
class DatasetUsageEntry:
    """画像が使われたフォルダ 1 件の表示情報。

    Attributes:
        dataset_name: データセット名。
        version_name: 版名。
        dir_name: フォルダ名 (例: ``10_raikou``)。
        num_repeats: 繰り返し数。
        elements: そのフォルダの学習テキスト (.txt) の要素。強調に使う。
    """

    dataset_name: str
    version_name: str
    dir_name: str
    num_repeats: int
    elements: tuple[str, ...]


class DatasetUsageWidget(QWidget):
    """画像が使われたデータセット・版・フォルダの表。行の選択でタグ欄の強調を要求する。

    Signals:
        highlight_changed (object): 選んだ行の要素の集合 (``set[str]``)。選択解除で ``None``。
    """

    highlight_changed = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        """セクションを構築する。

        Args:
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self.setObjectName("datasetUsageWidget")
        self._entries: list[DatasetUsageEntry] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(2)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        self._title_label = QLabel("学習に使ったデータセット", self)
        self._title_label.setStyleSheet(
            f"color: {theme.INK_SOFT}; font-size: {theme.FONT_SIZE_SMALL}px; font-weight: bold;"
        )
        header.addWidget(self._title_label)
        header.addStretch(1)
        self._clear_button = QPushButton("選択を解除", self)
        self._clear_button.setObjectName("datasetUsageClearButton")
        self._clear_button.setEnabled(False)
        self._clear_button.clicked.connect(self.clear_selection)
        header.addWidget(self._clear_button)
        layout.addLayout(header)

        self._empty_label = QLabel(_EMPTY_TEXT, self)
        self._empty_label.setStyleSheet(f"color: {theme.INK_MUTED}; font-size: {theme.FONT_SIZE_SMALL}px;")
        layout.addWidget(self._empty_label)

        self._table = QTableWidget(0, len(_HEADERS), self)
        self._table.setObjectName("datasetUsageTable")
        self._table.setHorizontalHeaderLabels(list(_HEADERS))
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setToolTip("行を選ぶと、その版・フォルダの .txt で使ったタグをタグ欄で強調します")
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._table)

        self.clear()

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def set_entries(self, entries: Sequence[DatasetUsageEntry]) -> None:
        """表の内容を差し替える。選択は解除する。

        Args:
            entries: 表示する行 (データセット名、版、フォルダの順)。
        """
        self._table.blockSignals(True)
        self._table.clearSelection()
        self._entries = list(entries)
        self._table.setRowCount(len(self._entries))
        for row, entry in enumerate(self._entries):
            values = (entry.dataset_name, entry.version_name, entry.dir_name, str(entry.num_repeats))
            for column, value in enumerate(values):
                self._table.setItem(row, column, QTableWidgetItem(value))
        self._table.blockSignals(False)
        has_rows = bool(self._entries)
        self._table.setVisible(has_rows)
        self._empty_label.setVisible(not has_rows)
        self._clear_button.setEnabled(False)
        self._fit_table_height()

    def clear(self) -> None:
        """表を空にして「なし」表示へ戻す。"""
        self.set_entries([])

    def entries(self) -> list[DatasetUsageEntry]:
        """現在表示中の行。"""
        return list(self._entries)

    def select_row(self, row: int) -> None:
        """行を選ぶ (行の選択と同じく ``highlight_changed`` を上げる)。

        Args:
            row: 行番号 (0 始まり)。
        """
        self._table.selectRow(row)

    def clear_selection(self) -> None:
        """行の選択を解除する (``highlight_changed(None)`` を上げる)。"""
        self._table.clearSelection()

    def selected_row(self) -> int | None:
        """選択中の行番号。未選択なら None。"""
        rows = self._table.selectionModel().selectedRows()
        return rows[0].row() if rows else None

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _on_selection_changed(self) -> None:
        row = self.selected_row()
        self._clear_button.setEnabled(row is not None)
        if row is None or row >= len(self._entries):
            self.highlight_changed.emit(None)
            return
        self.highlight_changed.emit(set(self._entries[row].elements))

    def _fit_table_height(self) -> None:
        """行数ぶんの高さに合わせ、詳細ペイン内で二重スクロールにしない。"""
        height = self._table.horizontalHeader().height() + 2 * self._table.frameWidth()
        for row in range(self._table.rowCount()):
            height += self._table.rowHeight(row)
        self._table.setFixedHeight(height)
