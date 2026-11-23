# tests/unit/gui/conftest.py
"""
GUI テスト層の共有フィクスチャ

責務:
- QApplication 初期化・管理
- QMessageBox 自動モック
- pytest-qt ベストプラクティス実装

このファイルは tests/conftest.py (ルート) の qapp に依存します。
"""

from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QFileDialog, QMessageBox

# ===== Qt Configuration (inherited from root) =====
# tests/conftest.py で qapp フィクスチャと configure_qt_for_tests が
# 既に定義されています。

# ===== QMessageBox Mocking =====


@pytest.fixture(autouse=True)
def auto_mock_qmessagebox(monkeypatch):
    """
    QMessageBox を自動モック（全GUI テストで自動実行）

    使用: GUI テストで QMessageBox.question() 等が呼ばれると、
    自動的に QMessageBox.Yes を返す
    """

    def mock_question(*args, **kwargs):
        return QMessageBox.StandardButton.Yes

    def mock_warning(*args, **kwargs):
        return QMessageBox.StandardButton.Ok

    def mock_information(*args, **kwargs):
        return QMessageBox.StandardButton.Ok

    def mock_critical(*args, **kwargs):
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "question", mock_question)
    monkeypatch.setattr(QMessageBox, "warning", mock_warning)
    monkeypatch.setattr(QMessageBox, "information", mock_information)
    monkeypatch.setattr(QMessageBox, "critical", mock_critical)

    # コピー可能ダイアログのヘルパー (message_box) も抑止する (#1160)。show_warning/
    # show_critical/show_information は build_message_box(...).exec() を呼ぶため、
    # build_message_box を neutralize すれば実ダイアログの exec ブロックを防げる。
    def mock_build_message_box(*args, **kwargs):
        box = Mock()
        box.exec.return_value = QMessageBox.StandardButton.Ok
        return box

    monkeypatch.setattr("lorairo.gui.message_box.build_message_box", mock_build_message_box)


@pytest.fixture(autouse=True)
def auto_mock_qfiledialog(monkeypatch):
    """QFileDialogをautouseでモック化（全GUIテストで自動実行）

    headless環境でネイティブファイルダイアログがイベントループをブロックするのを防止。
    テスト内で個別にファイル選択をテストする場合は monkeypatch でオーバーライド可能。
    """
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **kw: "")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **kw: ("", ""))
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **kw: ([], ""))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **kw: ("", ""))


# ===== Qt Widget Test Helpers =====


@pytest.fixture
def find_child_widget():
    """objectName でウィジェットを安全に検索するヘルパーフィクスチャ。

    Returns:
        (parent, widget_type, name) -> widget の検索関数。
        見つからない場合は AssertionError（タイポ等の即時検出）。

    Usage:
        def test_something(self, qtbot, find_child_widget):
            table = find_child_widget(dialog, QTableWidget, "errorTable")
    """
    from PySide6.QtCore import QObject

    def _find(parent: QObject, widget_type: type, name: str) -> QObject:
        widget = parent.findChild(widget_type, name)
        assert widget is not None, (
            f"{widget_type.__name__}(objectName='{name}') が見つかりません。"
            f" setObjectName('{name}') が設定されているか確認してください。"
        )
        return widget

    return _find


# ===== Automatic Marker Application =====


def pytest_collection_modifyitems(config, items):
    """tests/unit/gui 配下のテストに @pytest.mark.gui を自動付与"""
    for item in items:
        if "tests/unit/gui" in str(item.fspath) or "tests/integration/gui" in str(item.fspath):
            item.add_marker(pytest.mark.gui)
