"""CLI メインモジュール テスト。"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import toml
from typer.testing import CliRunner

from lorairo.cli.introspection import StatusResult
from lorairo.cli.main import app, main
from lorairo.services.service_container import ServiceContainer
from lorairo.utils import config as config_module

runner = CliRunner()


@pytest.fixture(autouse=True)
def status_config_paths(tmp_path, monkeypatch):
    project = tmp_path / "portable" / "lorairo.toml"
    user = tmp_path / "user" / "lorairo.toml"
    monkeypatch.setattr("lorairo.cli.main.DEFAULT_CONFIG_PATH", project)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", project)
    monkeypatch.setattr(config_module, "USER_CONFIG_PATH", user)
    monkeypatch.chdir(tmp_path)
    return project, user


def status_container():
    container = MagicMock()
    container.get_service_summary.return_value = {"environment": "CLI", "phase": "test"}
    container.config_service.get_setting.side_effect = lambda section, key, default="": (
        config_module.get_config().get(section, {}).get(key, default)
    )
    return container


@pytest.mark.parametrize(
    "project_found,user_found", [(False, True), (True, False), (True, True), (False, False)]
)
def test_implicit_status_reports_user_and_project_sources(status_config_paths, project_found, user_found):
    project, user = status_config_paths
    if project_found:
        project.parent.mkdir()
        project.write_text(toml.dumps({"directories": {}, "log": {"level": "DEBUG"}}))
    if user_found:
        user.parent.mkdir()
        user.write_text(toml.dumps({"directories": {}, "api": {"openai_key": "local-test-key"}}))
    with patch("lorairo.cli.main.get_service_container", return_value=status_container()):
        result = runner.invoke(app, ["--json", "status"])
    assert result.exit_code == 0, result.output
    row = json.loads(result.stdout)
    validated = StatusResult.model_validate(row)
    assert validated.config_path == str(user)
    assert validated.config_found is user_found
    assert validated.user_config_path == str(user)
    assert validated.user_config_found is user_found
    assert validated.project_config_path == str(project)
    assert validated.project_config_found is project_found
    if user_found or project_found:
        assert row["api_keys"]["openai"] is user_found
    else:
        assert row["api_keys"] == {}
    assert "local-test-key" not in result.output


@pytest.mark.parametrize("read_only", [False, True])
def test_user_only_status_shows_configured_api_in_rich_and_readonly_json(status_config_paths, read_only):
    project, user = status_config_paths
    user.parent.mkdir()
    user.write_text(toml.dumps({"directories": {}, "api": {"openai_key": "local-test-key"}}))
    with patch("lorairo.cli.main.get_service_container", return_value=status_container()):
        arguments = ["--json", "--read-only", "status"] if read_only else ["status"]
        result = runner.invoke(app, arguments)
    assert result.exit_code == 0, result.output
    if read_only:
        row = json.loads(result.stdout)
        assert row["config_path"] == str(user)
        assert row["project_config_path"] == str(project)
        assert row["api_keys"]["openai"] is True
    else:
        assert "OpenAI" in result.stdout and "Configured" in result.stdout
    assert "local-test-key" not in result.output


def test_workspace_status_reports_user_api_without_changing_selected_config_found(
    status_config_paths, tmp_path
):
    _, user = status_config_paths
    user.parent.mkdir()
    user.write_text(toml.dumps({"directories": {}, "api": {"openai_key": "local-test-key"}}))
    workspace = tmp_path / "workspace"
    with patch("lorairo.cli.main.get_service_container", return_value=status_container()):
        result = runner.invoke(app, ["--json", "--workspace", str(workspace), "status"])
    assert result.exit_code == 0, result.output
    row = json.loads(result.stdout)
    assert row["config_path"] == str(workspace / "config" / "lorairo.toml")
    assert row["config_found"] is False
    assert row["user_config_path"] == str(user)
    assert row["user_config_found"] is True
    assert row["api_keys"]["openai"] is True
    assert "project_config_path" not in row
    assert not workspace.exists()


def test_explicit_status_does_not_advertise_or_use_implicit_config_sources(status_config_paths, tmp_path):
    project, user = status_config_paths
    for path in (project, user):
        path.parent.mkdir()
        path.write_text(toml.dumps({"directories": {}, "api": {"openai_key": "local-test-key"}}))
    explicit = tmp_path / "portable.toml"
    explicit.write_text("[directories]\n")
    with patch("lorairo.cli.main.get_service_container", return_value=status_container()):
        result = runner.invoke(app, ["--json", "--config", str(explicit), "status"])
    assert result.exit_code == 0, result.output
    row = json.loads(result.stdout)
    assert row["config_path"] == str(explicit)
    assert row["config_found"] is True
    assert row["api_keys"]["openai"] is False
    assert "user_config_path" not in row and "project_config_path" not in row


@pytest.mark.parametrize("json_output", [False, True])
@pytest.mark.parametrize("read_only", [False, True])
def test_status_reads_portable_api_without_creating_missing_user_config(
    status_config_paths, tmp_path, monkeypatch, json_output, read_only
):
    project, user = status_config_paths
    project.parent.mkdir()
    project.write_text(toml.dumps({"directories": {}, "api": {"openai_key": "portable-test-key"}}))
    before = project.read_bytes()
    monkeypatch.setenv("LORAIRO_CLI_MODE", "true")
    monkeypatch.setenv("LORAIRO_CLI_LOG_PATH", str(tmp_path / "logs" / "status.log"))
    monkeypatch.setattr(ServiceContainer, "_instance", None)
    monkeypatch.setattr(ServiceContainer, "_initialized", False)
    container = ServiceContainer()
    assert container._config_service is None
    arguments = (["--json"] if json_output else []) + (["--read-only"] if read_only else []) + ["status"]
    with patch("lorairo.cli.main.get_service_container", return_value=container):
        result = runner.invoke(app, arguments)
    assert result.exit_code == 0, result.output
    assert not user.exists() and not user.parent.exists()
    assert container._config_service is None
    assert project.read_bytes() == before
    assert "portable-test-key" not in result.output
    if json_output:
        row = json.loads(result.stdout)
        assert row["config_path"] == str(user)
        assert row["config_found"] is False
        assert row["user_config_found"] is False
        assert row["project_config_found"] is True
        assert row["api_keys"]["openai"] is True
    else:
        assert "OpenAI" in result.stdout and "Configured" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_cli_help() -> None:
    """Test: CLI help output."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "LoRAIro" in result.stdout
    assert "AI-powered" in result.stdout
    assert "models refresh --project" in result.stdout
    assert "openai/omni-moderation-latest" in result.stdout
    assert "images list --project" in result.stdout
    assert "--unrated" in result.stdout


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
@patch("lorairo.cli.main.get_user_config_path")
@patch("lorairo.cli.main.get_service_container")
def test_cli_status(
    mock_get_container: MagicMock,
    mock_config_path: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test: status command in CLI mode shows LoRAIro CLI Status."""
    monkeypatch.setenv("LORAIRO_CLI_MODE", "true")
    mock_config_path.return_value.exists.return_value = True

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
@patch("lorairo.cli.main.get_user_config_path")
@patch("lorairo.cli.main.get_service_container")
def test_cli_status_shows_configured_api_key(
    mock_get_container: MagicMock,
    mock_config_path: MagicMock,
    status_config_paths,
) -> None:
    """Test: status コマンドがAPIキー設定済みを正しく表示する。"""
    mock_config_path.return_value.exists.return_value = True
    _, user = status_config_paths
    user.parent.mkdir()
    user.write_text(toml.dumps({"directories": {}, "api": {"openai_key": "sk-test-key"}}))

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
@patch("lorairo.cli.main.get_user_config_path")
@patch("lorairo.cli.main.get_service_container")
def test_cli_status_shows_on_demand_note(
    mock_get_container: MagicMock,
    mock_config_path: MagicMock,
) -> None:
    """Test: status コマンドがCLIモードのオンデマンド初期化を説明する。"""
    mock_config_path.return_value.exists.return_value = False

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
@patch("lorairo.cli.main.get_user_config_path")
@patch("lorairo.cli.main.get_service_container")
def test_cli_status_config_not_found(
    mock_get_container: MagicMock,
    mock_config_path: MagicMock,
) -> None:
    """Test: 設定ファイルが存在しない場合は Not Found を表示しAPIキーセクションを省略する。"""
    mock_config_path.return_value.exists.return_value = False

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
def test_version_json_emits_single_result_line() -> None:
    """Test: version --json は stdout に result 行を1つだけ出す (Issue #662)。"""
    result = runner.invoke(app, ["--json", "version"])

    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["kind"] == "result"
    assert payload["ok"] is True
    assert payload["name"] == "lorairo-cli"
    assert payload["version"] == "0.0.8"
    # rich 装飾 (cyan マークアップ) が stdout に混入しないこと。
    assert "[bold cyan]" not in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.main.get_user_config_path")
@patch("lorairo.cli.main.get_service_container")
def test_status_json_emits_pure_jsonl_result(
    mock_get_container: MagicMock,
    mock_config_path: MagicMock,
    status_config_paths,
) -> None:
    """Test: status --json は stdout が純 JSONL の単一 result になる (Issue #662)。"""
    mock_config_path.return_value.exists.return_value = True
    _, user = status_config_paths
    user.parent.mkdir()
    user.write_text(toml.dumps({"directories": {}, "api": {"openai_key": "sk-test-key"}}))

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

    result = runner.invoke(app, ["--json", "status"])

    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["kind"] == "result"
    assert payload["ok"] is True
    assert payload["environment"] == "CLI"
    assert payload["config_found"] is True
    assert payload["api_keys"] == {"openai": True, "anthropic": False, "google": False}
    # rich テーブルの装飾が stdout に混入していないこと。
    assert "LoRAIro CLI Status" not in result.stdout
    assert "┏" not in result.stdout  # テーブル罫線 (┏)


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.main.get_user_config_path")
@patch("lorairo.cli.main.get_service_container")
def test_status_json_omits_api_keys_when_config_missing(
    mock_get_container: MagicMock,
    mock_config_path: MagicMock,
) -> None:
    """Test: 設定ファイルが無い場合 status --json は api_keys を空にする (Issue #662)。"""
    mock_config_path.return_value.exists.return_value = False

    mock_container = MagicMock()
    mock_container.get_service_summary.return_value = {
        "environment": "CLI",
        "phase": "Phase 4 (Production Integration)",
        "initialized_services": {},
    }
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["--json", "status"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout.strip())
    assert payload["config_found"] is False
    assert payload["api_keys"] == {}


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
def test_callback_configures_logging_default_info(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test: @app.callback が CLI モードで専用ログファイルを既定 INFO レベルに設定する (#539)。"""
    spy = MagicMock()
    monkeypatch.setattr("lorairo.cli.main.initialize_logging", spy)
    # 既定パスの検証なので conftest の隔離用 env 上書き (Issue #1176) を外す
    monkeypatch.delenv("LORAIRO_CLI_LOG_PATH", raising=False)

    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    spy.assert_called_once()
    config_arg = spy.call_args[0][0]
    assert config_arg["level"] == "INFO"
    log_path = Path(config_arg["file_path"])
    assert log_path.name == "lorairo-cli.log"
    from platformdirs import user_log_path

    assert log_path.parent == user_log_path("LoRAIro", appauthor=False)
    assert config_arg["rotation"] == "25 MB"


@pytest.mark.unit
@pytest.mark.cli
def test_main_preserves_post_command_json_flag(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """main() の prescan 後も callback が明示 --json を env で上書きしない。"""
    monkeypatch.delenv("LORAIRO_CLI_JSON", raising=False)
    monkeypatch.setattr("lorairo.cli.main.initialize_logging", MagicMock())
    monkeypatch.setattr("lorairo.cli.commands.project.api_list_projects", MagicMock(return_value=[]))

    main(["project", "list", "--json"])

    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "kind": "result",
        "ok": True,
        "message": "0 project(s) found",
        "count": 0,
    }


# Issue #254: stdio init / Windows console code page / loguru sink クリア の test は
# tests/unit/cli/test_early_init.py に移行した。Console factory は test_console.py、
# glyph 定数は test_glyphs.py に移行している。
