"""DsSegmentedControl 単体テスト (Part of #852)。

DS 部品ライブラリの横方向排他トグルウィジェットを検証する。
"""

from __future__ import annotations

import pytest

from lorairo.gui.widgets.ds_segmented_control import DsSegmentedControl, SegmentOption

pytestmark = [pytest.mark.unit, pytest.mark.gui]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def basic_control(qtbot) -> DsSegmentedControl:
    """(value, label) タプル形式の基本的な DsSegmentedControl を返す。"""
    ctrl = DsSegmentedControl(
        [("a", "A"), ("b", "B"), ("c", "C")],
        value="b",
    )
    qtbot.addWidget(ctrl)
    return ctrl


@pytest.fixture
def segment_option_control(qtbot) -> DsSegmentedControl:
    """SegmentOption 形式の DsSegmentedControl を返す (count バッジ付き)。"""
    opts = [
        SegmentOption(value="all", label="すべて", count=100),
        SegmentOption(value="pending", label="保留", count=5),
        SegmentOption(value="done", label="完了"),
    ]
    ctrl = DsSegmentedControl(opts, value="all", size="small")
    qtbot.addWidget(ctrl)
    return ctrl


# ---------------------------------------------------------------------------
# 初期化・value()
# ---------------------------------------------------------------------------


class TestDsSegmentedControlInit:
    def test_initial_value_is_returned_by_value(self, basic_control: DsSegmentedControl) -> None:
        """初期選択値が value() で取得できること。"""
        assert basic_control.value() == "b"

    def test_initial_selected_button_is_checked(self, basic_control: DsSegmentedControl) -> None:
        """初期値に対応するボタンが checked になっていること。"""
        assert basic_control._buttons["b"].isChecked()

    def test_non_selected_buttons_are_unchecked(self, basic_control: DsSegmentedControl) -> None:
        """初期値以外のボタンは unchecked であること。"""
        assert not basic_control._buttons["a"].isChecked()
        assert not basic_control._buttons["c"].isChecked()

    def test_all_options_create_buttons(self, basic_control: DsSegmentedControl) -> None:
        """全オプションに対してボタンが生成されていること。"""
        assert set(basic_control._buttons.keys()) == {"a", "b", "c"}

    def test_base_size_is_default(self, qtbot) -> None:
        """size 未指定時はデフォルト 'base' になること。"""
        ctrl = DsSegmentedControl([("x", "X")], value="x")
        qtbot.addWidget(ctrl)
        assert ctrl._size == "base"

    def test_small_size_is_stored(self, segment_option_control: DsSegmentedControl) -> None:
        """size='small' が内部属性に保存されること。"""
        assert segment_option_control._size == "small"


# ---------------------------------------------------------------------------
# SegmentOption サポート
# ---------------------------------------------------------------------------


class TestSegmentOptionSupport:
    def test_segment_option_count_appears_in_button_text(
        self, segment_option_control: DsSegmentedControl
    ) -> None:
        """count が設定されているセグメントはボタンテキストに数値が含まれること。"""
        all_button = segment_option_control._buttons["all"]
        assert "100" in all_button.text()

    def test_segment_option_without_count_shows_label_only(
        self, segment_option_control: DsSegmentedControl
    ) -> None:
        """count=None のセグメントはラベルのみが表示されること。"""
        done_button = segment_option_control._buttons["done"]
        assert done_button.text() == "完了"

    def test_segment_option_initial_value(self, segment_option_control: DsSegmentedControl) -> None:
        """SegmentOption 形式での初期値が正しく選択されること。"""
        assert segment_option_control.value() == "all"
        assert segment_option_control._buttons["all"].isChecked()


# ---------------------------------------------------------------------------
# クリックによる選択変更 + value_changed Signal
# ---------------------------------------------------------------------------


class TestDsSegmentedControlClick:
    def test_click_changes_value(self, basic_control: DsSegmentedControl) -> None:
        """ボタンクリックで value() が更新されること。"""
        basic_control._buttons["c"].click()
        assert basic_control.value() == "c"

    def test_click_unchecks_previous_button(self, basic_control: DsSegmentedControl) -> None:
        """クリック後に前の選択ボタンが unchecked になること。"""
        basic_control._buttons["a"].click()
        assert not basic_control._buttons["b"].isChecked()

    def test_click_emits_value_changed_signal(self, qtbot, basic_control: DsSegmentedControl) -> None:
        """ボタンクリックで value_changed Signal が emit されること。"""
        with qtbot.waitSignal(basic_control.value_changed, timeout=1000) as blocker:
            basic_control._buttons["a"].click()
        assert blocker.args == ["a"]

    def test_click_emits_correct_value(self, qtbot, basic_control: DsSegmentedControl) -> None:
        """value_changed で emit される値がクリックしたセグメントの value であること。"""
        received: list[str] = []
        basic_control.value_changed.connect(received.append)
        basic_control._buttons["c"].click()
        assert received == ["c"]


# ---------------------------------------------------------------------------
# set_value() — プログラマティック変更 (emit なし)
# ---------------------------------------------------------------------------


class TestDsSegmentedControlSetValue:
    def test_set_value_updates_value(self, basic_control: DsSegmentedControl) -> None:
        """set_value() で value() が更新されること。"""
        basic_control.set_value("a")
        assert basic_control.value() == "a"

    def test_set_value_checks_correct_button(self, basic_control: DsSegmentedControl) -> None:
        """set_value() で対応するボタンが checked になること。"""
        basic_control.set_value("c")
        assert basic_control._buttons["c"].isChecked()

    def test_set_value_does_not_emit_signal(self, qtbot, basic_control: DsSegmentedControl) -> None:
        """set_value() は value_changed を emit しないこと。"""
        received: list[str] = []
        basic_control.value_changed.connect(received.append)
        basic_control.set_value("a")
        # シグナルが emit されないことを確認 (短い wait で検証)
        qtbot.waitSignal(basic_control.value_changed, timeout=100, raising=False)
        assert received == []

    def test_set_value_unknown_key_does_nothing(self, basic_control: DsSegmentedControl) -> None:
        """set_value() に存在しない value を渡しても状態が変わらないこと。"""
        original = basic_control.value()
        basic_control.set_value("nonexistent")
        assert basic_control.value() == original


# ---------------------------------------------------------------------------
# set_options() — 動的再構築
# ---------------------------------------------------------------------------


class TestDsSegmentedControlSetOptions:
    def test_set_options_replaces_buttons(self, basic_control: DsSegmentedControl) -> None:
        """set_options() で既存ボタンが新しいオプションに置き換わること。"""
        basic_control.set_options([("x", "X"), ("y", "Y")], value="x")
        assert set(basic_control._buttons.keys()) == {"x", "y"}

    def test_set_options_updates_value(self, basic_control: DsSegmentedControl) -> None:
        """set_options() の value 引数で初期選択が更新されること。"""
        basic_control.set_options([("x", "X"), ("y", "Y")], value="y")
        assert basic_control.value() == "y"

    def test_set_options_without_value_preserves_current(self, basic_control: DsSegmentedControl) -> None:
        """set_options() の value を省略すると現在値が引き継がれること。"""
        # 現在値 "b" は新しい options に存在しない → _value だけ "b" のまま
        basic_control.set_options([("b", "B2"), ("d", "D")])
        assert basic_control.value() == "b"

    def test_set_options_with_segment_option(self, basic_control: DsSegmentedControl) -> None:
        """set_options() に SegmentOption リストを渡せること。"""
        opts = [
            SegmentOption("p", "P", count=3),
            SegmentOption("q", "Q"),
        ]
        basic_control.set_options(opts, value="p")
        assert "p" in basic_control._buttons
        assert "3" in basic_control._buttons["p"].text()


# ---------------------------------------------------------------------------
# size による見た目の分岐 (QSS に size が反映されているか)
# ---------------------------------------------------------------------------


class TestDsSegmentedControlSize:
    def test_base_size_qss_uses_font_size_small(self, qtbot) -> None:
        """size='base' のボタン QSS に FONT_SIZE_SMALL が含まれること。"""
        from lorairo.gui import theme

        ctrl = DsSegmentedControl([("a", "A")], value="a", size="base")
        qtbot.addWidget(ctrl)
        qss = ctrl._buttons["a"].styleSheet()
        assert str(theme.FONT_SIZE_SMALL) in qss

    def test_small_size_qss_uses_font_size_meta(self, qtbot) -> None:
        """size='small' のボタン QSS に FONT_SIZE_META が含まれること。"""
        from lorairo.gui import theme

        ctrl = DsSegmentedControl([("a", "A")], value="a", size="small")
        qtbot.addWidget(ctrl)
        qss = ctrl._buttons["a"].styleSheet()
        assert str(theme.FONT_SIZE_META) in qss
