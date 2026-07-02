# tests/unit/gui/widgets/test_ds_no_scroll_combo_box.py
"""DsNoScrollComboBox のホイール誤操作防止テスト (Issue #1051)。"""

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent

from lorairo.gui.widgets.ds_no_scroll_combo_box import DsNoScrollComboBox
from lorairo.gui.widgets.tag_panel_widget import TagPanelWidget


def _wheel_event(widget) -> QWheelEvent:
    """下方向 1 ノッチのホイールイベントを作る。"""
    pos = QPointF(widget.rect().center())
    global_pos = QPointF(widget.mapToGlobal(widget.rect().center()))
    return QWheelEvent(
        pos,
        global_pos,
        QPoint(0, 0),
        QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )


class TestDsNoScrollComboBox:
    def _make_combo(self, qtbot) -> DsNoScrollComboBox:
        combo = DsNoScrollComboBox()
        qtbot.addWidget(combo)
        combo.addItems(["english", "japanese", "chinese"])
        combo.setCurrentIndex(0)
        return combo

    def test_wheel_without_focus_does_not_change_value(self, qtbot) -> None:
        """ホバー通過のホイール (非フォーカス) では値が変わらない。"""
        combo = self._make_combo(qtbot)
        assert not combo.hasFocus()

        event = _wheel_event(combo)
        combo.wheelEvent(event)

        assert combo.currentIndex() == 0
        # 親スクロールへ回すため accept しない
        assert not event.isAccepted()

    def test_focus_policy_is_strong_focus(self, qtbot) -> None:
        """ホバーだけではフォーカスしない (クリック / Tab のみ)。"""
        combo = self._make_combo(qtbot)
        assert combo.focusPolicy() == Qt.FocusPolicy.StrongFocus

    def test_wheel_with_focus_changes_value(self, qtbot, monkeypatch) -> None:
        """クリック等でフォーカス済みなら従来どおりホイールで値変更できる。"""
        combo = self._make_combo(qtbot)
        # offscreen ではウィンドウが activate されず本物のフォーカスが取れないため、
        # hasFocus をインスタンス単位で差し替えてフォーカス済み状態を模擬する
        monkeypatch.setattr(combo, "hasFocus", lambda: True)

        combo.wheelEvent(_wheel_event(combo))

        assert combo.currentIndex() == 1


class TestTagPanelCombosUseNoScroll:
    """#1051: タグパネルの言語/頻度コンボが NoScroll 部品に差し替わっている。"""

    def test_panel_combos_are_no_scroll(self, qtbot) -> None:
        panel = TagPanelWidget()
        qtbot.addWidget(panel)

        assert isinstance(panel._lang_combo, DsNoScrollComboBox)
        assert isinstance(panel._metric_combo, DsNoScrollComboBox)
