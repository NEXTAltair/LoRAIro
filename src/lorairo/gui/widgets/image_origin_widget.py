"""画像の「由来」セクションのウィジェット (Issue #1661 / ADR 0112)。

別プロジェクトからコピーした画像について、コピー元のプロジェクト名と、そのプロジェクトでの
画像 ID を並べる表示専用ウィジェット。``DatasetUsageWidget`` と同じく ``lorairo.database`` /
``lorairo.services`` を import せず、表示に必要な値を :class:`ImageOriginEntry` として受け取る。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from .. import theme

_EMPTY_TEXT = "このプロジェクトで登録した画像 (コピー元なし)"


@dataclass(frozen=True, slots=True)
class ImageOriginEntry:
    """画像の由来 1 件の表示情報。

    Attributes:
        source_project_name: コピー元のプロジェクト名。
        source_image_id: コピー元のプロジェクトでの画像 ID。
    """

    source_project_name: str
    source_image_id: int


def format_origins(entries: Sequence[ImageOriginEntry]) -> str:
    """由来を「プロジェクト名 #画像 ID」の並びにする。由来が無ければ "-"。"""
    if not entries:
        return "-"
    return ", ".join(f"{entry.source_project_name} #{entry.source_image_id}" for entry in entries)


class ImageOriginWidget(QWidget):
    """画像の由来 (コピー元のプロジェクトと画像 ID) を表示する。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        """セクションを構築する。

        Args:
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self.setObjectName("imageOriginWidget")
        self._entries: list[ImageOriginEntry] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(2)

        title = QLabel("由来", self)
        title.setStyleSheet(
            f"color: {theme.INK_SOFT}; font-size: {theme.FONT_SIZE_SMALL}px; font-weight: bold;"
        )
        layout.addWidget(title)

        self._value_label = QLabel(self)
        self._value_label.setObjectName("imageOriginValueLabel")
        self._value_label.setWordWrap(True)
        self._value_label.setStyleSheet(f"color: {theme.INK}; font-size: {theme.FONT_SIZE_SMALL}px;")
        layout.addWidget(self._value_label)
        self.clear()

    def set_entries(self, entries: Sequence[ImageOriginEntry]) -> None:
        """表示する由来を差し替える。

        Args:
            entries: 由来 (記録順)。空ならコピー元なしと表示する。
        """
        self._entries = list(entries)
        if self._entries:
            lines = [
                f"{entry.source_project_name} の画像 #{entry.source_image_id} からコピー"
                for entry in self._entries
            ]
            self._value_label.setText("\n".join(lines))
        else:
            self._value_label.setText(_EMPTY_TEXT)

    def clear(self) -> None:
        """由来なしの表示へ戻す。"""
        self.set_entries([])

    def entries(self) -> list[ImageOriginEntry]:
        """現在表示中の由来。"""
        return list(self._entries)

    def text(self) -> str:
        """表示中の文言 (テスト・確認用)。"""
        return self._value_label.text()
