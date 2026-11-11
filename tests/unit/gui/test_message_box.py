"""コピー可能メッセージボックスヘルパー (Issue #1160) のユニットテスト。

``build_message_box`` を直接 import することで、autouse の
``auto_mock_qmessagebox`` が module 属性を差し替えても実関数を検証する。
"""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow, QMessageBox, QWidget

from lorairo.gui.message_box import build_message_box, show_status_message

pytestmark = pytest.mark.gui


def test_build_message_box_makes_body_text_selectable(qapp):
    """本文ラベルに TextSelectableByMouse | TextSelectableByKeyboard が付く (#1160)。"""
    box = build_message_box(QMessageBox.Icon.Critical, None, "タイトル", "コピーしたい本文")
    label = box.findChild(QLabel, "qt_msgbox_label")
    assert label is not None
    flags = label.textInteractionFlags()
    assert bool(flags & Qt.TextInteractionFlag.TextSelectableByMouse)
    assert bool(flags & Qt.TextInteractionFlag.TextSelectableByKeyboard)
    assert label.text() == "コピーしたい本文"


def test_build_message_box_sets_detailed_text(qapp):
    """detail 付きは setDetailedText に載る (「詳細を表示」で展開・コピー可) (#1160)。"""
    box = build_message_box(
        QMessageBox.Icon.Critical, None, "エラー", "処理に失敗しました", detail="Traceback...\n  line 2"
    )
    assert box.detailedText() == "Traceback...\n  line 2"


def test_build_message_box_no_detail_when_omitted(qapp):
    """detail 省略時は detailedText が空 (#1160)。"""
    box = build_message_box(QMessageBox.Icon.Warning, None, "警告", "本文のみ")
    assert box.detailedText() == ""


def test_build_message_box_applies_icon(qapp):
    """指定アイコンが反映される (#1160)。"""
    box = build_message_box(QMessageBox.Icon.Warning, None, "警告", "本文")
    assert box.icon() == QMessageBox.Icon.Warning


def test_show_status_message_uses_window_status_bar(qtbot):
    """所属ウィンドウのステータスバーへ表示できる (#1569)。"""
    window = QMainWindow()
    qtbot.addWidget(window)
    child = QWidget(window)

    assert show_status_message(child, "保存しました", 5000) is True
    assert window.statusBar().currentMessage() == "保存しました"


def test_show_status_message_without_status_bar_returns_false(qtbot):
    """ステータスバーを持たないウィンドウでは何もせず False を返す (#1569)。"""
    widget = QWidget()
    qtbot.addWidget(widget)

    assert show_status_message(widget, "x") is False
    assert show_status_message(None, "x") is False
