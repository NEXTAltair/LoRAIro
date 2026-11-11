# tests/unit/gui/widgets/test_ds_no_scroll_combo_box.py
"""DsNoScrollComboBox のホイール誤操作防止テスト (Issue #1051)。"""

from PySide6.QtCore import QCoreApplication, QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QComboBox, QSlider

from lorairo.gui.widgets.dataset_select_dialog import DatasetSelectDialog
from lorairo.gui.widgets.ds_no_scroll_combo_box import (
    DsNoScrollComboBox,
    DsNoScrollDoubleSpinBox,
    DsNoScrollSlider,
    DsNoScrollSpinBox,
    install_no_scroll_wheel_guard,
)
from lorairo.gui.widgets.filter_search_panel import FilterSearchPanel, _ValueComboBox
from lorairo.gui.widgets.rating_score_edit_widget import RatingScoreEditWidget
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


class TestDsNoScrollSpinAndSlider:
    """#1567: SpinBox / DoubleSpinBox / Slider / eventFilter ガードの検証。"""

    def test_spin_box_ignores_wheel_without_focus(self, qtbot, monkeypatch) -> None:
        spin = DsNoScrollSpinBox()
        qtbot.addWidget(spin)
        spin.setRange(0, 100)
        spin.setValue(10)
        assert spin.focusPolicy() == Qt.FocusPolicy.StrongFocus

        event = _wheel_event(spin)
        spin.wheelEvent(event)
        assert spin.value() == 10
        assert not event.isAccepted()

        monkeypatch.setattr(spin, "hasFocus", lambda: True)
        spin.wheelEvent(_wheel_event(spin))
        assert spin.value() != 10

    def test_double_spin_box_ignores_wheel_without_focus(self, qtbot, monkeypatch) -> None:
        spin = DsNoScrollDoubleSpinBox()
        qtbot.addWidget(spin)
        spin.setRange(0.0, 10.0)
        spin.setValue(5.0)
        assert spin.focusPolicy() == Qt.FocusPolicy.StrongFocus

        event = _wheel_event(spin)
        spin.wheelEvent(event)
        assert spin.value() == 5.0
        assert not event.isAccepted()

        monkeypatch.setattr(spin, "hasFocus", lambda: True)
        spin.wheelEvent(_wheel_event(spin))
        assert spin.value() != 5.0

    def test_slider_ignores_wheel_without_focus(self, qtbot, monkeypatch) -> None:
        slider = DsNoScrollSlider(Qt.Orientation.Horizontal)
        qtbot.addWidget(slider)
        slider.setRange(0, 100)
        slider.setValue(50)
        assert slider.focusPolicy() == Qt.FocusPolicy.StrongFocus

        event = _wheel_event(slider)
        slider.wheelEvent(event)
        assert slider.value() == 50
        assert not event.isAccepted()

        monkeypatch.setattr(slider, "hasFocus", lambda: True)
        slider.wheelEvent(_wheel_event(slider))
        assert slider.value() != 50

    def test_install_no_scroll_wheel_guard_blocks_unfocused_wheel(self, qtbot, monkeypatch) -> None:
        combo = QComboBox()
        qtbot.addWidget(combo)
        combo.addItems(["a", "b", "c"])
        combo.setCurrentIndex(0)
        install_no_scroll_wheel_guard(combo)
        assert combo.focusPolicy() == Qt.FocusPolicy.StrongFocus

        event = _wheel_event(combo)
        QCoreApplication.sendEvent(combo, event)
        assert combo.currentIndex() == 0
        assert not event.isAccepted()

        monkeypatch.setattr(combo, "hasFocus", lambda: True)
        QCoreApplication.sendEvent(combo, _wheel_event(combo))
        assert combo.currentIndex() == 1

    def test_rollout_across_panels_and_dialogs(self, qtbot) -> None:
        assert issubclass(_ValueComboBox, DsNoScrollComboBox)

        panel = FilterSearchPanel()
        qtbot.addWidget(panel)
        assert panel.ui.comboResolution.focusPolicy() == Qt.FocusPolicy.StrongFocus
        assert panel.ui.comboAspectRatio.focusPolicy() == Qt.FocusPolicy.StrongFocus

        dlg = DatasetSelectDialog()
        qtbot.addWidget(dlg)
        assert isinstance(dlg.parent_version_combo, DsNoScrollComboBox)

        rating_widget = RatingScoreEditWidget()
        qtbot.addWidget(rating_widget)
        assert rating_widget.ui.sliderScore.focusPolicy() == Qt.FocusPolicy.StrongFocus
        assert rating_widget.ui.comboBoxRating.focusPolicy() == Qt.FocusPolicy.StrongFocus

        slider: QSlider = rating_widget.ui.sliderScore
        slider.setValue(500)
        event = _wheel_event(slider)
        QCoreApplication.sendEvent(slider, event)
        assert slider.value() == 500
        assert not event.isAccepted()
