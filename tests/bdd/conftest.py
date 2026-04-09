# tests/bdd/conftest.py
"""BDD テスト層の共有設定

tests/bdd 配下のテストに @pytest.mark.bdd を自動付与する。
"""

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """tests/bdd 配下のテストに @pytest.mark.bdd を自動付与"""
    for item in items:
        if "tests/bdd" in str(item.fspath):
            item.add_marker(pytest.mark.bdd)
