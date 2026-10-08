"""Show every caption row and keep manual correction tied to its source ID."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .. import theme


class CaptionReviewPanel(QWidget):
    edit_requested = Signal(int, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(theme.SPACE_1)
        self._rows: list[dict[str, Any]] = []
        self._warning_ids: set[int] = set()
        self._editable = False

    def set_editable(self, editable: bool) -> None:
        self._editable = editable
        self._render()

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        self._rows = [row.copy() for row in rows if row.get("rejected_at") is None]
        self._warning_ids.clear()
        self._render()

    def set_warning_ids(self, caption_ids: set[int]) -> None:
        self._warning_ids = caption_ids.copy()
        self._render()

    def _render(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item is not None and (widget := item.widget()) is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        for row in self._rows:
            caption_id = row.get("id")
            text = str(row.get("caption", ""))
            if not isinstance(caption_id, int):
                continue
            container = QWidget(self)
            layout = QHBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            label = QLabel(text, container)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label.setObjectName(f"captionRow{caption_id}")
            if caption_id in self._warning_ids:
                label.setText(f"⚠ 要確認\n{text}")
                label.setStyleSheet(
                    f"color: {theme.WARN}; border-left: 3px solid {theme.WARN}; padding: 4px;"
                )
            layout.addWidget(label, 1)
            if self._editable:
                edit = QPushButton("編集", container)
                edit.setObjectName(f"editCaption{caption_id}")
                edit.clicked.connect(
                    lambda checked=False, row_id=caption_id, original=text: self.edit_requested.emit(
                        row_id, original
                    )
                )
                layout.addWidget(edit)
            self._layout.addWidget(container)
        self.setVisible(bool(self._rows))
