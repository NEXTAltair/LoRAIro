"""コピー可能なメッセージボックスの共通ヘルパー (Issue #1160)。

``QMessageBox`` は既定で本文ラベルが選択不可のため、エラー/警告の本文をユーザーが
コピーして報告に貼れない。ここでは本文ラベルに ``TextSelectableByMouse |
TextSelectableByKeyboard`` を付与した ``QMessageBox`` を生成する共通関数を提供する。

長文 (traceback 等) は ``detail`` に渡すと ``setDetailedText`` へ載り、「詳細を表示」で
展開してコピーできる。

テスト規約 (``.claude/rules/testing.md``: QMessageBox は monkeypatch) と両立するよう、
公開関数は単一の呼び出しで、置換先はこれらを monkeypatch すればダイアログを抑止できる。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMessageBox, QWidget

# QMessageBox の本文ラベルの objectName (Qt 内部で固定)。
_MESSAGE_LABEL_OBJECT_NAME = "qt_msgbox_label"


def build_message_box(
    icon: QMessageBox.Icon,
    parent: QWidget | None,
    title: str,
    text: str,
    detail: str | None = None,
) -> QMessageBox:
    """本文を選択・コピー可能にした ``QMessageBox`` を構築して返す (exec しない)。

    Args:
        icon: 表示アイコン (Warning / Critical / Information)。
        parent: 親ウィジェット。
        title: ウィンドウタイトル。
        text: 本文 (選択・コピー可能にする)。
        detail: 長文の詳細 (traceback 等)。指定時は「詳細を表示」に載せる。

    Returns:
        設定済みの ``QMessageBox`` (呼び出し側で ``exec()`` する)。
    """
    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(text)
    if detail:
        box.setDetailedText(detail)
    # 本文ラベルを選択・コピー可能にする (既定は選択不可)。
    label = box.findChild(QLabel, _MESSAGE_LABEL_OBJECT_NAME)
    if label is not None:
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
    return box


def show_warning(parent: QWidget | None, title: str, text: str, detail: str | None = None) -> None:
    """本文コピー可能な警告ダイアログを表示する (Issue #1160)。"""
    build_message_box(QMessageBox.Icon.Warning, parent, title, text, detail).exec()


def show_critical(parent: QWidget | None, title: str, text: str, detail: str | None = None) -> None:
    """本文コピー可能なエラーダイアログを表示する (Issue #1160)。

    ``detail`` に traceback 等の長文を渡すと「詳細を表示」で展開・コピーできる。
    """
    build_message_box(QMessageBox.Icon.Critical, parent, title, text, detail).exec()


def show_information(parent: QWidget | None, title: str, text: str, detail: str | None = None) -> None:
    """本文コピー可能な情報ダイアログを表示する (Issue #1160)。"""
    build_message_box(QMessageBox.Icon.Information, parent, title, text, detail).exec()
