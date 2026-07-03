"""RemovableChip 単体テスト (Issue #1105 DS 部品ライブラリ)。

favorite_filter / export_overlay_bar の × 削除可能 chip を統一する共通部品を検証する。
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel, QPushButton

from lorairo.gui import theme
from lorairo.gui.widgets.ds_removable_chip import RemovableChip

pytestmark = [pytest.mark.unit, pytest.mark.gui]


class TestRemovableChip:
    def test_static_chip_shows_text_and_accent_style(self, qtbot):
        chip = RemovableChip("⊘ tag")
        qtbot.addWidget(chip)
        assert chip.text() == "⊘ tag"
        # accent-soft 地 + accent border
        assert theme.ACCENT_SOFT in chip.styleSheet()
        assert theme.ACCENT_BORDER in chip.styleSheet()
        # 静的モードは本文が QLabel
        assert isinstance(chip._body, QLabel)

    def test_remove_button_emits_removed(self, qtbot):
        chip = RemovableChip("x")
        qtbot.addWidget(chip)
        with qtbot.waitSignal(chip.removed, timeout=1000):
            chip._remove_btn.click()

    def test_clickable_body_emits_clicked(self, qtbot):
        chip = RemovableChip("★ fav", clickable=True)
        qtbot.addWidget(chip)
        assert isinstance(chip._body, QPushButton)
        with qtbot.waitSignal(chip.clicked, timeout=1000):
            chip._body.click()

    def test_static_body_is_not_a_button(self, qtbot):
        chip = RemovableChip("static")
        qtbot.addWidget(chip)
        assert not isinstance(chip._body, QPushButton)

    def test_custom_radius_applied(self, qtbot):
        chip = RemovableChip("x", radius=theme.RADIUS_CHIP)
        qtbot.addWidget(chip)
        assert f"border-radius: {theme.RADIUS_CHIP}px" in chip.styleSheet()

    def test_default_radius_is_theme_radius(self, qtbot):
        chip = RemovableChip("x")
        qtbot.addWidget(chip)
        assert f"border-radius: {theme.RADIUS}px" in chip.styleSheet()

    def test_custom_remove_glyph(self, qtbot):
        chip = RemovableChip("x", remove_glyph="×")
        qtbot.addWidget(chip)
        assert chip._remove_btn.text() == "×"

    def test_set_text_updates_body(self, qtbot):
        chip = RemovableChip("old")
        qtbot.addWidget(chip)
        chip.set_text("new")
        assert chip.text() == "new"

    def test_remove_hover_uses_err_color(self, qtbot):
        chip = RemovableChip("x")
        qtbot.addWidget(chip)
        assert theme.ERR in chip._remove_btn.styleSheet()
