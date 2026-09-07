"""関連画像 (クロップ親子) セクションのウィジェット (#1346 / ADR 0092)。

現在表示中の画像の「直接の親」と「子一覧」を切り出し座標つきで並べ、行のクリックで
その画像へ遷移する要求を Signal で上げるだけの表示専用ウィジェット。

``lorairo.database`` / ``lorairo.services`` を import せず、表示に必要な値を
:class:`RelatedImageEntry` として受け取る (#983 TagPanelWidget / ADR 0083 と同じ
「見える部分を DB 非依存に保つ」方式)。DB からの取得は
``lorairo.gui.services.crop_relation_service`` が担う。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from .. import theme

_EMPTY_TEXT = "なし"


@dataclass(frozen=True, slots=True)
class RelatedImageEntry:
    """関連画像 1 件の表示情報。

    Attributes:
        image_id: 関連画像の ``images.id``。
        x: 直接の親画像基準の左上 x 座標 (px)。
        y: 直接の親画像基準の左上 y 座標 (px)。
        width: 切り出し幅 (px)。
        height: 切り出し高さ (px)。
        origin: 切り出し由来 ("manual" / 検出器名等)。
    """

    image_id: int
    x: int
    y: int
    width: int
    height: int
    origin: str

    def display_text(self) -> str:
        """1 行に表示する文字列を返す。"""
        return f"#{self.image_id}  x={self.x}, y={self.y}, {self.width}×{self.height} ({self.origin})"


class RelatedImagesWidget(QWidget):
    """クロップの親 / 子を一覧表示し、クリックで遷移要求を上げるウィジェット。

    Signals:
        image_activated (int): 行がクリックされた関連画像の ``images.id``。
    """

    image_activated = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        """関連画像セクションを構築する。

        Args:
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self.setObjectName("relatedImagesWidget")
        self._parent_entry: RelatedImageEntry | None = None
        self._child_entries: list[RelatedImageEntry] = []
        self._entry_buttons: list[QPushButton] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(2)

        self._title_label = QLabel("関連画像 (クロップ)", self)
        self._title_label.setStyleSheet(
            f"color: {theme.INK_SOFT}; font-size: {theme.FONT_SIZE_SMALL}px; font-weight: bold;"
        )
        layout.addWidget(self._title_label)

        self._parent_caption = self._caption_label("親")
        layout.addWidget(self._parent_caption)
        self._parent_empty = self._empty_label()
        layout.addWidget(self._parent_empty)

        self._parent_layout = QVBoxLayout()
        self._parent_layout.setContentsMargins(0, 0, 0, 0)
        self._parent_layout.setSpacing(2)
        layout.addLayout(self._parent_layout)

        self._children_caption = self._caption_label("子")
        layout.addWidget(self._children_caption)
        self._children_empty = self._empty_label()
        layout.addWidget(self._children_empty)

        self._children_layout = QVBoxLayout()
        self._children_layout.setContentsMargins(0, 0, 0, 0)
        self._children_layout.setSpacing(2)
        layout.addLayout(self._children_layout)

        self.clear()

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def set_related(
        self,
        parent_entry: RelatedImageEntry | None,
        child_entries: Sequence[RelatedImageEntry],
    ) -> None:
        """親 / 子の表示内容を差し替える。

        Args:
            parent_entry: 直接の親。クロップ画像でなければ None。
            child_entries: この画像から切り出した子の一覧 (登録順)。
        """
        self._parent_entry = parent_entry
        self._child_entries = list(child_entries)
        self._rebuild_rows()

    def clear(self) -> None:
        """表示をクリアし、親子ともに「なし」表示へ戻す。"""
        self.set_related(None, [])

    def parent_entry(self) -> RelatedImageEntry | None:
        """現在表示中の親エントリ。"""
        return self._parent_entry

    def child_entries(self) -> list[RelatedImageEntry]:
        """現在表示中の子エントリ一覧 (表示順)。"""
        return list(self._child_entries)

    def entry_buttons(self) -> list[QPushButton]:
        """親 → 子の表示順に並んだ行ボタン一覧 (クリック操作用)。"""
        return list(self._entry_buttons)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _caption_label(self, text: str) -> QLabel:
        """「親」「子」の見出しラベルを作る。"""
        label = QLabel(text, self)
        label.setStyleSheet(f"color: {theme.INK_FAINT}; font-size: {theme.FONT_SIZE_SMALL}px;")
        return label

    def _empty_label(self) -> QLabel:
        """関連が無いときの「なし」ラベルを作る。"""
        label = QLabel(_EMPTY_TEXT, self)
        label.setStyleSheet(f"color: {theme.INK_FAINT}; font-size: {theme.FONT_SIZE_SMALL}px;")
        return label

    def _rebuild_rows(self) -> None:
        """保持しているエントリから行ボタンを組み直す。"""
        for button in self._entry_buttons:
            button.setParent(None)
            button.deleteLater()
        self._entry_buttons = []

        if self._parent_entry is not None:
            self._parent_layout.addWidget(self._make_row(self._parent_entry))
        self._parent_empty.setVisible(self._parent_entry is None)

        for entry in self._child_entries:
            self._children_layout.addWidget(self._make_row(entry))
        self._children_empty.setVisible(not self._child_entries)

    def _make_row(self, entry: RelatedImageEntry) -> QPushButton:
        """1 件分のリンク風ボタンを作り、クリックを image_activated へ束ねる。"""
        button = QPushButton(entry.display_text(), self)
        button.setFlat(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolTip(f"画像 #{entry.image_id} を表示する")
        button.setStyleSheet(
            f"QPushButton {{ text-align: left; border: none; padding: 1px 2px;"
            f" color: {theme.ACCENT}; font-family: {theme.FONT_MONO_CSS};"
            f" font-size: {theme.FONT_SIZE_SMALL}px; }}"
            f" QPushButton:hover {{ background-color: {theme.PAPER_SHADE}; }}"
        )
        image_id = entry.image_id
        button.clicked.connect(lambda: self.image_activated.emit(image_id))
        self._entry_buttons.append(button)
        return button
