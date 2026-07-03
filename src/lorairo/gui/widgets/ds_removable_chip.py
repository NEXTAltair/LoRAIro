"""DS v12 削除可能チップ部品 (Issue #1105 DS 部品ライブラリ)。

「accent-soft 地 + ラベル + × 削除ボタン」の removable chip を共通部品化する。
``favorite_filter.py`` の保存クエリ chip と ``export_overlay_bar.py`` の overlay
chip が、ほぼ同構造の × 削除可能 chip を各々別実装していたのを 1 部品へ統一する。

``clickable=True`` で本文自体をクリック可能なボタンにでき (保存クエリ chip の
「クリックで適用」導線)、``removed`` / ``clicked`` シグナルで操作を通知する。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from lorairo.gui import theme


class RemovableChip(QFrame):
    """accent-soft 地の × 削除可能チップ。

    Args:
        text: チップ本文。
        clickable: True で本文をクリック可能なボタンにする (クリックで ``clicked``
            を emit)。False (既定) は静的ラベル。
        radius: 角丸半径 (px)。None (既定) は ``theme.RADIUS``。タグ寄りの丸みが
            必要なら ``theme.RADIUS_CHIP`` を渡す。
        remove_glyph: 削除ボタンの文字。既定は "✕"。
        parent: 親ウィジェット。

    Signals:
        removed: 削除ボタン押下時に emit。
        clicked: ``clickable=True`` のとき本文クリックで emit。
    """

    removed = Signal()
    clicked = Signal()

    def __init__(
        self,
        text: str,
        *,
        clickable: bool = False,
        radius: int | None = None,
        remove_glyph: str = "✕",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("dsRemovableChip")
        chip_radius = theme.RADIUS if radius is None else radius
        self.setStyleSheet(
            f"QFrame#dsRemovableChip {{ background: {theme.ACCENT_SOFT};"
            f" border: {theme.BORDER_WIDTH}px solid {theme.ACCENT_BORDER};"
            f" border-radius: {chip_radius}px; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 4, 2)
        layout.setSpacing(4)

        self._body = self._build_body(text, clickable)
        layout.addWidget(self._body)

        self._remove_btn = QPushButton(remove_glyph, self)
        self._remove_btn.setObjectName("dsRemovableChipRemove")
        self._remove_btn.setFixedSize(16, 16)
        self._remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._remove_btn.setStyleSheet(
            f"QPushButton {{ border: none; background: transparent; color: {theme.ACCENT_HOVER};"
            f" font-size: {theme.FONT_SIZE_META}px; }}"
            f" QPushButton:hover {{ color: {theme.ERR}; }}"
        )
        self._remove_btn.clicked.connect(lambda: self.removed.emit())
        layout.addWidget(self._remove_btn)

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def set_text(self, text: str) -> None:
        """チップ本文を更新する。"""
        self._body.setText(text)

    def text(self) -> str:
        """現在のチップ本文を返す。"""
        return self._body.text()

    # ------------------------------------------------------------------
    # 内部ヘルパー
    # ------------------------------------------------------------------

    def _build_body(self, text: str, clickable: bool) -> QLabel | QPushButton:
        """本文ウィジェット (静的ラベル or クリック可能ボタン) を生成する。"""
        body_qss = (
            f"color: {theme.ACCENT_HOVER}; font-size: {theme.FONT_SIZE_SMALL}px;"
            f" border: none; background: transparent;"
        )
        if clickable:
            button = QPushButton(text, self)
            button.setObjectName("dsRemovableChipBody")
            button.setFlat(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(f"QPushButton {{ {body_qss} text-align: left; }}")
            button.clicked.connect(lambda: self.clicked.emit())
            return button
        label = QLabel(text, self)
        label.setObjectName("dsRemovableChipBody")
        label.setStyleSheet(body_qss)
        return label
