"""クリックでタグを移動できる軽量タグリスト (#1345)。

クロップダイアログの「候補タグ」「採用タグ」の 2 リストで使う最小構成のウィジェット。

``FlowLayout`` (tag_cloud_widget.py) を ``widgetResizable=True`` の ``QScrollArea``
へ入れる構成は ``minimumSizeHint`` が暴れる既知の罠があるため (docs/lessons-learned.md
PySide6 節)、スクロールが安定している ``QListWidget`` をそのまま使う。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem, QWidget

from .. import theme


class ClickableTagListWidget(QListWidget):
    """タグを 1 行 1 件で並べ、クリックでタグ名を通知するリスト。

    表示ラベルは翻訳付き (``blue hair / 青い髪``) にできるが、``tags()`` と
    ``tag_clicked`` が返すのは常に原文タグ (#1355)。原文は行の
    ``Qt.ItemDataRole.UserRole`` に持たせ、表示文字列と分離する。

    Signals:
        tag_clicked (str): 行がクリックされた際にその原文タグを emit する。
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

    def set_tags(self, tags: Sequence[str], labels: Mapping[str, str] | None = None) -> None:
        """表示するタグ一覧を差し替える (与えられた順序を保つ)。

        Args:
            tags: 表示する原文タグのリスト。
            labels: 原文タグ -> 表示文字列の対応表 (翻訳表示用、#1355)。
                与えられなかったタグは原文をそのまま表示する。
        """
        self.clear()
        for tag in tags:
            item = QListWidgetItem(labels.get(tag, tag) if labels else tag)
            # 表示文字列と原文を分離し、クリック通知と tags() は常に原文を返す
            item.setData(Qt.ItemDataRole.UserRole, tag)
            self.addItem(item)

    def tags(self) -> list[str]:
        """表示中の原文タグ一覧を表示順で返す。"""
        result: list[str] = []
        for row in range(self.count()):
            item = self.item(row)
            if item is not None:
                result.append(self._tag_of(item))
        return result

    def labels(self) -> list[str]:
        """表示中の行ラベル一覧を表示順で返す (翻訳表示の検証用)。"""
        result: list[str] = []
        for row in range(self.count()):
            item = self.item(row)
            if item is not None:
                result.append(item.text())
        return result

    @staticmethod
    def _tag_of(item: QListWidgetItem) -> str:
        """行から原文タグを取り出す (UserRole 未設定の行は表示文字列を使う)。"""
        stored = item.data(Qt.ItemDataRole.UserRole)
        return str(stored) if stored is not None else item.text()

    @Slot(QListWidgetItem)
    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """クリックされた行の原文タグを Signal で通知する。"""
        self.tag_clicked.emit(self._tag_of(item))
