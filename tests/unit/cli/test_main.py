"""CLI メインモジュール テスト。"""

from unittest.mock import MagicMock, patch

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
@patch("lorairo.cli.main.DEFAULT_CONFIG_PATH")
@patch("lorairo.cli.main.get_service_container")
def test_cli_status(
    mock_get_container: MagicMock,
    mock_config_path: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test: status command in CLI mode shows LoRAIro CLI Status."""
    monkeypatch.setenv("LORAIRO_CLI_MODE", "true")
    mock_config_path.exists.return_value = True

    mock_container = MagicMock()
    mock_container.get_service_summary.return_value = {
        "environment": "CLI",
        "phase": "Phase 4 (Production Integration)",
        "initialized_services": {},
    }
    mock_config = MagicMock()
    mock_config.get_setting.return_value = ""
    mock_container.config_service = mock_config
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "CLI" in result.stdout
    assert "LoRAIro CLI Status" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.main.DEFAULT_CONFIG_PATH")
@patch("lorairo.cli.main.get_service_container")
def test_cli_status_shows_configured_api_key(
    mock_get_container: MagicMock,
    mock_config_path: MagicMock,
) -> None:
    """Test: status コマンドがAPIキー設定済みを正しく表示する。"""
    mock_config_path.exists.return_value = True

    mock_container = MagicMock()
    mock_container.get_service_summary.return_value = {
        "environment": "CLI",
        "phase": "Phase 4 (Production Integration)",
        "initialized_services": {},
    }
    mock_config = MagicMock()
    mock_config.get_setting.side_effect = lambda section, key, default="": (
        "sk-test-key" if key == "openai_key" else ""
    )
    mock_container.config_service = mock_config
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "Configured" in result.stdout
    assert "OpenAI" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.main.DEFAULT_CONFIG_PATH")
@patch("lorairo.cli.main.get_service_container")
def test_cli_status_shows_on_demand_note(
    mock_get_container: MagicMock,
    mock_config_path: MagicMock,
) -> None:
    """Test: status コマンドがCLIモードのオンデマンド初期化を説明する。"""
    mock_config_path.exists.return_value = False

    mock_container = MagicMock()
    mock_container.get_service_summary.return_value = {
        "environment": "CLI",
        "phase": "Phase 4 (Production Integration)",
        "initialized_services": {},
    }
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "on demand" in result.stdout
    assert "Not Ready" not in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.main.DEFAULT_CONFIG_PATH")
@patch("lorairo.cli.main.get_service_container")
def test_cli_status_config_not_found(
    mock_get_container: MagicMock,
    mock_config_path: MagicMock,
) -> None:
    """Test: 設定ファイルが存在しない場合は Not Found を表示しAPIキーセクションを省略する。"""
    mock_config_path.exists.return_value = False

    mock_container = MagicMock()
    mock_container.get_service_summary.return_value = {
        "environment": "CLI",
        "phase": "Phase 4 (Production Integration)",
        "initialized_services": {},
    }
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "Not Found" in result.stdout
    assert "API Key" not in result.stdout


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


@pytest.mark.unit
@pytest.mark.cli
def test_main_configures_logging_warning_level() -> None:
    """Test: main() が CLI モードで loguru を WARNING レベルに設定する。"""
    with patch("lorairo.cli.main.initialize_logging") as mock_init_log, patch("lorairo.cli.main.app"):
        from lorairo.cli.main import main

        main()
    mock_init_log.assert_called_once()
    config_arg = mock_init_log.call_args[0][0]
    assert config_arg["level"] == "WARNING"
