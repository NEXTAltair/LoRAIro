"""CLI メインモジュール テスト。"""

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app

runner = CliRunner()


@pytest.mark.unit
@pytest.mark.cli
def test_cli_help() -> None:
    """Test: CLI help output."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "LoRAIro" in result.stdout
    assert "AI-powered" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_cli_version() -> None:
    """Test: version command."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "LoRAIro CLI" in result.stdout
    assert "v0.0.8" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_cli_status(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test: status command."""
    # LORAIRO_CLI_MODE を設定してから実行
    monkeypatch.setenv("LORAIRO_CLI_MODE", "true")

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "Service Status" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_project_help() -> None:
    """Test: project subcommand help."""
    result = runner.invoke(app, ["project", "--help"])
    assert result.exit_code == 0
    assert "Project management" in result.stdout
    assert "create" in result.stdout
    assert "list" in result.stdout
    assert "delete" in result.stdout
