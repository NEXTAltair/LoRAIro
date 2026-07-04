# tests/integration/gui/conftest.py
"""
統合GUIテスト層の共有フィクスチャ

責務:
- QMessageBox 自動モック（ヘッドレス環境でネイティブダイアログを防止）
"""

from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QMessageBox


@pytest.fixture(autouse=True)
def auto_mock_qmessagebox(monkeypatch):
    """QMessageBox を自動モック（全統合GUIテストで自動実行）

    ヘッドレス環境では QMessageBox のネイティブダイアログがイベントループを
    ブロックしてテストがハングするため、全てのスタティックメソッドをモック化する。
    """
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **kw: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **kw: QMessageBox.StandardButton.Ok)

    # コピー可能ダイアログのヘルパー (message_box) も抑止する (#1160)。
    def mock_build_message_box(*args, **kwargs):
        box = Mock()
        box.exec.return_value = QMessageBox.StandardButton.Ok
        return box

    monkeypatch.setattr("lorairo.gui.message_box.build_message_box", mock_build_message_box)
