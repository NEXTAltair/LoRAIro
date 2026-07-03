"""DsBadge 単体テスト (Issue #1105 DS 部品ライブラリ)。

badge_qss() 直書き QLabel を置換する公式部品の振る舞いを検証する。
"""

from __future__ import annotations

import pytest

from lorairo.gui import theme
from lorairo.gui.widgets.ds_badge import DsBadge

pytestmark = [pytest.mark.unit, pytest.mark.gui]


class TestDsBadge:
    def test_default_kind_is_none_and_neutral_style(self, qtbot):
        badge = DsBadge("openai")
        qtbot.addWidget(badge)
        assert badge.text() == "openai"
        assert badge.kind is None
        # 中立 type バッジ = paper-shade 地
        assert theme.PAPER_SHADE in badge.styleSheet()
        assert badge.styleSheet() == theme.badge_qss()

    def test_kind_applies_recolored_badge_qss(self, qtbot):
        badge = DsBadge("batch", kind="accent")
        qtbot.addWidget(badge)
        assert badge.kind == "accent"
        assert badge.styleSheet() == theme.badge_qss("accent")
        assert theme.ACCENT_SOFT in badge.styleSheet()

    def test_set_kind_reapplies_style(self, qtbot):
        badge = DsBadge("x")
        qtbot.addWidget(badge)
        badge.set_kind("info")
        assert badge.kind == "info"
        assert badge.styleSheet() == theme.badge_qss("info")

    def test_set_kind_none_returns_to_neutral(self, qtbot):
        badge = DsBadge("x", kind="ok")
        qtbot.addWidget(badge)
        badge.set_kind(None)
        assert badge.kind is None
        assert badge.styleSheet() == theme.badge_qss()

    def test_set_text_updates_label(self, qtbot):
        badge = DsBadge("old")
        qtbot.addWidget(badge)
        badge.set_text("new")
        assert badge.text() == "new"

    def test_uses_badge_radius_not_chip_radius(self, qtbot):
        # バッジは chip より小角丸 (RADIUS_BADGE) を使う
        badge = DsBadge("x")
        qtbot.addWidget(badge)
        assert f"border-radius: {theme.RADIUS_BADGE}px" in badge.styleSheet()
