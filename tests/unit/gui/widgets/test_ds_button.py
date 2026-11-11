"""DsButton 単体テスト (Issue #1601 DS 部品ライブラリ)。"""

from __future__ import annotations

import pytest

from lorairo.gui import theme
from lorairo.gui.widgets.ds_button import DsButton, DsButtonKind, ds_button_qss

pytestmark = [pytest.mark.unit, pytest.mark.gui]


class TestDsButtonStyle:
    def test_default_kind_is_primary_accent_fill(self, qtbot) -> None:
        btn = DsButton("実行")
        qtbot.addWidget(btn)
        assert btn.kind() == "primary"
        qss = btn.styleSheet()
        assert f"background-color: {theme.ACCENT}" in qss
        assert f"color: {theme.TEXT_ON_ACCENT}" in qss
        assert f"background-color: {theme.ACCENT_HOVER}" in qss

    def test_secondary_uses_paper_shade_fill(self, qtbot) -> None:
        btn = DsButton("検証", kind="secondary")
        qtbot.addWidget(btn)
        qss = btn.styleSheet()
        assert f"background-color: {theme.PAPER_SHADE}" in qss
        assert f"color: {theme.INK_SOFT}" in qss
        # secondary は accent 塗りを持たない (hover の LINE 塗りのみ)
        assert f"background-color: {theme.ACCENT};" not in qss

    @pytest.mark.parametrize("kind", ["primary", "secondary"])
    def test_focus_and_disabled_states_defined(self, kind: DsButtonKind) -> None:
        qss = ds_button_qss(kind)
        assert "QPushButton:focus" in qss
        assert "QPushButton:disabled" in qss
        assert theme.INK_FAINT in qss

    def test_primary_focus_is_visible_against_accent_border(self) -> None:
        # accent 塗り + accent 枠ではフォーカスが見えないため ink 枠へ切り替える
        qss = ds_button_qss("primary")
        assert f"QPushButton:focus {{ border-color: {theme.INK}; }}" in qss

    def test_small_size_uses_small_font(self) -> None:
        assert f"font-size: {theme.FONT_SIZE_SMALL}px" in ds_button_qss("primary", "small")
        assert f"font-size: {theme.FONT_SIZE_BASE}px" in ds_button_qss("primary", "base")

    def test_set_kind_reapplies_style(self, qtbot) -> None:
        btn = DsButton("x", kind="primary")
        qtbot.addWidget(btn)
        btn.set_kind("secondary")
        assert btn.kind() == "secondary"
        assert f"background-color: {theme.PAPER_SHADE}" in btn.styleSheet()


class TestDsButtonBehavior:
    def test_click_emits_clicked(self, qtbot) -> None:
        btn = DsButton("実行")
        qtbot.addWidget(btn)
        with qtbot.waitSignal(btn.clicked, timeout=1000):
            btn.click()

    def test_disabled_button_does_not_emit(self, qtbot) -> None:
        btn = DsButton("実行")
        qtbot.addWidget(btn)
        btn.setEnabled(False)
        received: list[bool] = []
        btn.clicked.connect(lambda _checked=False: received.append(True))
        btn.click()
        assert received == []

    def test_text_preserved(self, qtbot) -> None:
        btn = DsButton("エクスポート", kind="primary", size="small")
        qtbot.addWidget(btn)
        assert btn.text() == "エクスポート"
