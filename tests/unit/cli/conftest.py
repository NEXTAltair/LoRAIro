"""CLI テスト共通設定。

Rich/Typer のカラー出力を無効化する autouse フィクスチャを提供する。
"""

import pytest


@pytest.fixture(autouse=True)
def disable_rich_color(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rich/Typer のカラー出力をテスト環境で無効化する。

    Rich は help 出力中の `--flag` パターンに ANSI エスケープ (`\\x1b[1;36m`) を挿入するため、
    CI 環境のようにカラーが強制される条件下では `assert "--project" in result.stdout` が
    `\\x1b[1;36m-\\x1b[0m\\x1b[1;36m-project\\x1b[0m` との比較になり失敗する。

    NO_COLOR と TERM=dumb を設定して Rich の自動検出を抑制する。
    """
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("TERM", "dumb")
