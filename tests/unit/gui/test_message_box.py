"""コピー可能メッセージボックスヘルパー (Issue #1160) のユニットテスト。

``build_message_box`` を直接 import することで、autouse の
``auto_mock_qmessagebox`` が module 属性を差し替えても実関数を検証する。
"""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMessageBox

from lorairo.gui.message_box import build_message_box

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
