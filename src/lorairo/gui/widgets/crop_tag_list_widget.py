"""クリックでタグを移動できる軽量タグリスト (#1345)。

クロップダイアログの「候補タグ」「採用タグ」の 2 リストで使う最小構成のウィジェット。

``FlowLayout`` (tag_cloud_widget.py) を ``widgetResizable=True`` の ``QScrollArea``
へ入れる構成は ``minimumSizeHint`` が暴れる既知の罠があるため (docs/lessons-learned.md
PySide6 節)、スクロールが安定している ``QListWidget`` をそのまま使う。
"""

from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem, QWidget

from .. import theme


class ClickableTagListWidget(QListWidget):
    """タグを 1 行 1 件で並べ、クリックでタグ名を通知するリスト。

    Signals:
        tag_clicked (str): 行がクリックされた際にそのタグ名を emit する。
    """

    tag_clicked = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """リストを構築する。

        Args:
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        # クリックは「移動」操作なので選択状態を残さない
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setUniformItemSizes(True)
        self.setAlternatingRowColors(False)
        self.setStyleSheet(
            f"QListWidget {{ background-color: {theme.CARD};"
            f" border: {theme.BORDER_WIDTH}px solid {theme.LINE};"
            f" border-radius: {theme.RADIUS}px;"
            f" font-size: {theme.FONT_SIZE_SMALL}px; }}"
            f" QListWidget::item {{ padding: 3px 6px; }}"
            f" QListWidget::item:hover {{ background-color: {theme.ACCENT_SOFT};"
            f" color: {theme.INK}; }}"
        )
        self.itemClicked.connect(self._on_item_clicked)

    def set_tags(self, tags: list[str]) -> None:
        """表示するタグ一覧を差し替える (与えられた順序を保つ)。

        Args:
            tags: 表示するタグ文字列のリスト。
        """
        self.clear()
        for tag in tags:
            self.addItem(QListWidgetItem(tag))

    def tags(self) -> list[str]:
        """表示中のタグ一覧を表示順で返す。"""
        result: list[str] = []
        for row in range(self.count()):
            item = self.item(row)
            if item is not None:
                result.append(item.text())
        return result

    @Slot(QListWidgetItem)
    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """クリックされた行のタグ名を Signal で通知する。"""
        self.tag_clicked.emit(item.text())
