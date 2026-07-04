"""QCheckBox テーマ描画の runtime ピクセル検証 (Issue #1092 再オープン)。

静的な QSS 文字列検査だけでは「枠が見えない / チェックマークが出ない」実機不具合を
捕捉できなかった (教訓: 静的ソース正しい != 実行時正しい)。offscreen 描画を grab して
ピクセルを走査し、(1) 未チェック枠が背景に対し十分なコントラストで描画される、
(2) チェック時に白 ✓ が実際に描画される、ことを assert する。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QRect
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QStyle,
    QStyleOptionButton,
    QVBoxLayout,
    QWidget,
)

from lorairo.gui import theme

pytestmark = [pytest.mark.unit, pytest.mark.gui]

_PAPER_RGB = (0xFB, 0xFA, 0xF6)


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    """sRGB → 相対輝度 (WCAG)。"""
    channels = []
    for value in rgb:
        srgb = value / 255
        channels.append(srgb / 12.92 if srgb <= 0.03928 else ((srgb + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    """2 色間の WCAG コントラスト比。"""
    la, lb = _relative_luminance(a), _relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _hex_rgb(token: str) -> tuple[int, int, int]:
    return (int(token[1:3], 16), int(token[3:5], 16), int(token[5:7], 16))


@pytest.fixture(autouse=True)
def _global_qss(qapp):
    """テーマのグローバル QSS を適用する (checkbox 描画に必須)。"""
    previous = qapp.styleSheet()
    qapp.setStyleSheet(theme.build_global_qss())
    yield
    qapp.setStyleSheet(previous)


def _render_checkbox(qtbot, *, checked: bool) -> tuple[QRect, QImage]:
    """PAPER 地のホストに空ラベル checkbox を描画し、(indicator 矩形, host画像) を返す。

    offscreen では合成カーソルが (0,0) に居座り左上の indicator を hover 扱いにするため、
    Leave イベントを送って既定 (非 hover) 状態で描画させる。indicator の正確な矩形は
    QStyle から取得して host 座標系へ写す。
    """
    host = QWidget()
    host.setStyleSheet(f"background: {theme.PAPER};")
    layout = QVBoxLayout(host)
    layout.setContentsMargins(40, 40, 10, 10)  # indicator を (0,0) から離す
    checkbox = QCheckBox("")
    checkbox.setChecked(checked)
    layout.addWidget(checkbox)
    qtbot.addWidget(host)
    host.resize(80, 80)
    host.show()
    qtbot.waitExposed(host)
    QApplication.sendEvent(checkbox, QEvent(QEvent.Type.Leave))
    QApplication.processEvents()

    option = QStyleOptionButton()
    checkbox.initStyleOption(option)
    indicator = checkbox.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, checkbox)
    origin = checkbox.geometry().topLeft()
    host_rect = QRect(
        indicator.x() + origin.x(),
        indicator.y() + origin.y(),
        indicator.width(),
        indicator.height(),
    )
    return host_rect, host.grab().toImage()


def _count_interior(image: QImage, rect: QRect, *, inset: int = 4) -> tuple[int, int]:
    """indicator 内側 (border を除いた塗り領域) の (ACCENT塗り数, 白数) を返す。"""
    accent = QColor(theme.ACCENT)
    orange = white = 0
    for x in range(rect.x() + inset, rect.x() + rect.width() - inset):
        for y in range(rect.y() + inset, rect.y() + rect.height() - inset):
            color = QColor(image.pixel(x, y))
            r, g, b = color.red(), color.green(), color.blue()
            if abs(r - accent.red()) < 50 and abs(g - accent.green()) < 50 and abs(b - accent.blue()) < 50:
                orange += 1
            if r > 235 and g > 235 and b > 235:
                white += 1
    return orange, white


class TestCheckboxBorderContrast:
    """未チェック枠が背景に対し視認できるコントラストを持つこと。"""

    def test_inksoft_vs_paper_contrast_is_sufficient(self):
        # 回帰の核: LINE_STRONG(~1.4:1) では見えなかった → INK_SOFT(~7:1) へ。
        assert _contrast(_hex_rgb(theme.INK_SOFT), _PAPER_RGB) >= 3.0

    def test_line_strong_would_have_failed(self):
        # 旧実装 (LINE_STRONG) が 3:1 を満たさないことを固定し、退行を防ぐ。
        assert _contrast(_hex_rgb(theme.LINE_STRONG), _PAPER_RGB) < 3.0

    def test_rendered_unchecked_border_is_dark(self, qtbot):
        rect, image = _render_checkbox(qtbot, checked=False)
        # indicator 矩形内で最も暗いピクセル (= 枠) を拾い、背景との色差を測る
        darkest = (255, 255, 255)
        for x in range(rect.x() - 1, rect.x() + rect.width() + 1):
            for y in range(rect.y() - 1, rect.y() + rect.height() + 1):
                color = QColor(image.pixel(x, y))
                rgb = (color.red(), color.green(), color.blue())
                if sum(rgb) < sum(darkest):
                    darkest = rgb
        assert _contrast(darkest, _PAPER_RGB) >= 3.0


class TestCheckboxCheckmark:
    """チェック時に白 ✓ が実際に描画されること (data URI 撤去で ✓ を落とした回帰)。"""

    def test_checked_indicator_has_white_check_over_accent_fill(self, qtbot):
        rect, image = _render_checkbox(qtbot, checked=True)
        orange, white = _count_interior(image, rect)
        # 塗りは ACCENT、その上に白 ✓ が存在する (icon 未描画なら white=0 で失敗)
        assert orange > 30, f"ACCENT 塗りが描画されていない (orange={orange})"
        assert white >= 5, f"白チェックマークが描画されていない (white={white})"

    def test_unchecked_indicator_interior_is_not_accent(self, qtbot):
        rect, image = _render_checkbox(qtbot, checked=False)
        orange, _white = _count_interior(image, rect)
        assert orange == 0


class TestCheckboxQssStatic:
    """QSS / アセットの静的検証。"""

    def test_checkmark_svg_asset_exists(self):
        assert Path(theme.CHECK_ICON_PATH).is_file()

    def test_checked_qss_references_check_icon_file(self):
        qss = theme.build_global_qss()
        assert f"image: url({theme.CHECK_ICON_PATH})" in qss
        # CSS data URI ではない (Qt QSS 非対応、#1092)
        assert "data:image" not in qss

    def test_unchecked_border_uses_ink_soft(self):
        qss = theme.build_global_qss()
        unchecked = qss.split("QCheckBox::indicator:unchecked, QGroupBox::indicator:unchecked {")[1].split(
            "}"
        )[0]
        assert f"1px solid {theme.INK_SOFT}" in unchecked

    def test_indicator_is_enlarged(self):
        qss = theme.build_global_qss()
        indicator = qss.split("QCheckBox::indicator, QGroupBox::indicator {")[1].split("}")[0]
        assert "width: 16px" in indicator
        assert "height: 16px" in indicator


def _render_groupbox(qtbot, *, checked: bool) -> tuple[QRect, QImage]:
    """PAPER 地に checkable QGroupBox を描画し、(indicator 矩形, host画像) を返す (#1146)。

    折りたたみチェックは QGroupBox::indicator で描画される。indicator 矩形は QStyle の
    SC_GroupBoxCheckBox から取得して host 座標系へ写す。
    """
    from PySide6.QtWidgets import QGroupBox, QStyleOptionGroupBox

    host = QWidget()
    host.setStyleSheet(f"background: {theme.PAPER};")
    layout = QVBoxLayout(host)
    layout.setContentsMargins(20, 20, 20, 20)
    group = QGroupBox("お気に入り")
    group.setCheckable(True)
    group.setChecked(checked)
    layout.addWidget(group)
    qtbot.addWidget(host)
    host.resize(200, 120)
    host.show()
    qtbot.waitExposed(host)
    QApplication.sendEvent(group, QEvent(QEvent.Type.Leave))
    QApplication.processEvents()

    option = QStyleOptionGroupBox()
    group.initStyleOption(option)
    indicator = group.style().subControlRect(
        QStyle.ComplexControl.CC_GroupBox, option, QStyle.SubControl.SC_GroupBoxCheckBox, group
    )
    origin = group.mapTo(host, indicator.topLeft())
    host_rect = QRect(origin.x(), origin.y(), indicator.width(), indicator.height())
    return host_rect, host.grab().toImage()


class TestGroupBoxIndicator:
    """#1146: checkable QGroupBox 折りたたみチェックも QCheckBox と同トーンで視認できる。"""

    def test_unchecked_border_is_dark(self, qtbot):
        rect, image = _render_groupbox(qtbot, checked=False)
        darkest = (255, 255, 255)
        for x in range(rect.x() - 1, rect.x() + rect.width() + 1):
            for y in range(rect.y() - 1, rect.y() + rect.height() + 1):
                color = QColor(image.pixel(x, y))
                rgb = (color.red(), color.green(), color.blue())
                if sum(rgb) < sum(darkest):
                    darkest = rgb
        assert _contrast(darkest, _PAPER_RGB) >= 3.0

    def test_checked_has_white_check_over_accent_fill(self, qtbot):
        rect, image = _render_groupbox(qtbot, checked=True)
        orange, white = _count_interior(image, rect)
        assert orange > 20, f"ACCENT 塗りが描画されていない (orange={orange})"
        assert white >= 5, f"白チェックマークが描画されていない (white={white})"

    def test_qss_shares_checkbox_indicator_rules(self):
        qss = theme.build_global_qss()
        # QGroupBox::indicator が QCheckBox::indicator と併記で定義されている
        assert "QGroupBox::indicator:unchecked" in qss
        assert "QGroupBox::indicator:checked" in qss
        unchecked = qss.split("QGroupBox::indicator:unchecked")[1].split("{")[1].split("}")[0]
        assert f"1px solid {theme.INK_SOFT}" in unchecked
