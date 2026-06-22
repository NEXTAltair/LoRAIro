"""DsSummaryStat ウィジェット単体テスト (Issue #852)。"""

from __future__ import annotations

import pytest

from lorairo.gui import theme
from lorairo.gui.widgets.ds.ds_summary_stat import DsSummaryStat

pytestmark = [pytest.mark.unit, pytest.mark.gui]


@pytest.fixture
def make_stat(qtbot):
    """DsSummaryStat を生成するファクトリフィクスチャ。"""

    def _factory(
        label: str = "テスト",
        value: str = "42",
        sub: str | None = None,
        tone=None,
    ) -> DsSummaryStat:
        w = DsSummaryStat(label=label, value=value, sub=sub, tone=tone)
        qtbot.addWidget(w)
        return w

    return _factory


class TestDsSummaryStatLabel:
    """label ラベルの生成・表示テスト。"""

    def test_label_text_is_set(self, make_stat):
        w = make_stat(label="登録済み")
        assert w._label_widget.text() == "登録済み"

    def test_label_uses_ink_soft_color(self, make_stat):
        w = make_stat()
        assert theme.INK_SOFT in w._label_widget.styleSheet()

    def test_label_uses_small_font_size(self, make_stat):
        w = make_stat()
        assert str(theme.FONT_SIZE_SMALL) in w._label_widget.styleSheet()

    def test_label_uses_sans_font(self, make_stat):
        # FONT_SANS_CSS の先頭フォント名が含まれているか確認
        w = make_stat()
        assert "Noto Sans JP" in w._label_widget.styleSheet()


class TestDsSummaryStatValue:
    """value の生成・色・フォントテスト。"""

    def test_value_text_is_set(self, make_stat):
        w = make_stat(value="1,234")
        assert w._value_widget.text() == "1,234"

    def test_value_uses_mono_font(self, make_stat):
        w = make_stat(value="99")
        assert "JetBrains Mono" in w._value_widget.styleSheet()

    def test_value_no_tone_uses_ink_color(self, make_stat):
        w = make_stat(tone=None)
        assert theme.INK in w._value_widget.styleSheet()

    def test_tone_ok_uses_ok_color(self, make_stat):
        w = make_stat(tone="ok")
        assert theme.OK in w._value_widget.styleSheet()

    def test_tone_warn_uses_warn_color(self, make_stat):
        w = make_stat(tone="warn")
        assert theme.WARN in w._value_widget.styleSheet()

    def test_tone_err_uses_err_color(self, make_stat):
        w = make_stat(tone="err")
        assert theme.ERR in w._value_widget.styleSheet()

    def test_tone_info_uses_info_color(self, make_stat):
        w = make_stat(tone="info")
        assert theme.INFO in w._value_widget.styleSheet()

    def test_tone_accent_uses_accent_color(self, make_stat):
        w = make_stat(tone="accent")
        assert theme.ACCENT in w._value_widget.styleSheet()


class TestDsSummaryStatSub:
    """sub テキストの表示制御テスト。"""

    def test_sub_none_is_hidden(self, make_stat):
        w = make_stat(sub=None)
        assert not w._sub_widget.isVisible()

    def test_sub_text_is_set_and_not_hidden(self, make_stat):
        w = make_stat(sub="前回比 +12")
        assert w._sub_widget.text() == "前回比 +12"
        assert not w._sub_widget.isHidden()

    def test_sub_uses_ink_faint_color(self, make_stat):
        w = make_stat(sub="補助情報")
        assert theme.INK_FAINT in w._sub_widget.styleSheet()

    def test_sub_uses_mono_font(self, make_stat):
        w = make_stat(sub="補助情報")
        assert "JetBrains Mono" in w._sub_widget.styleSheet()

    def test_sub_uses_small_font_size(self, make_stat):
        w = make_stat(sub="補助情報")
        assert str(theme.FONT_SIZE_SMALL) in w._sub_widget.styleSheet()


class TestDsSummaryStatConstruction:
    """生成パターンの組み合わせテスト。"""

    def test_all_params_set(self, make_stat):
        """全パラメータ指定で生成できる。"""
        w = make_stat(label="エラー数", value="3", sub="前回 0", tone="err")
        assert w._label_widget.text() == "エラー数"
        assert w._value_widget.text() == "3"
        assert w._sub_widget.text() == "前回 0"
        assert theme.ERR in w._value_widget.styleSheet()

    def test_minimal_label_and_value_only(self, make_stat):
        """label / value のみでも生成できる。"""
        w = make_stat(label="件数", value="0")
        assert w._label_widget.text() == "件数"
        assert w._value_widget.text() == "0"
        assert not w._sub_widget.isVisible()

    def test_parent_widget_accepted(self, qtbot):
        """parent ウィジェットを指定して生成できる。"""
        from PySide6.QtWidgets import QWidget

        parent = QWidget()
        qtbot.addWidget(parent)
        w = DsSummaryStat(label="L", value="V", parent=parent)
        assert w.parent() is parent
