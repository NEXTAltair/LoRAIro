# tests/bdd/conftest.py
"""BDD テスト層の共有設定

- tests/bdd 配下のテストに @pytest.mark.bdd を自動付与する。
- QMessageBox を autouse でモックする (tests/unit/gui/conftest.py と同じ実装)。
  実 QMessageBox が開くとヘッドレスでテストがハングするため、ステップファイル側で
  個別に autouse mock を書かない。回答や呼び出し回数を制御したいステップは、
  この上から monkeypatch.setattr(QMessageBox, ...) で上書きする。

命名規約: tests/ 配下に __init__.py が無いため、unit と同じ basename の
tests/bdd/steps/test_<feature>.py は同一セッションで import file mismatch を起こす。
steps は test_<feature>_flow.py とし、重複は tests/unit/test_test_basename_unique.py が検出する。
"""

import pytest
from PySide6.QtWidgets import QMessageBox


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """tests/bdd 配下のテストに @pytest.mark.bdd を自動付与"""
    for item in items:
        if "tests/bdd" in str(item.fspath):
            item.add_marker(pytest.mark.bdd)


@pytest.fixture(autouse=True)
def auto_mock_qmessagebox(monkeypatch: pytest.MonkeyPatch) -> None:
    """QMessageBox の静的ダイアログを全 BDD テストで自動モックする。"""
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **kw: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **kw: QMessageBox.StandardButton.Ok)
