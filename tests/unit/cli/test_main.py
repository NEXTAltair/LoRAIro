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


# --- Issue #254: cp932 環境での stdout/stderr UTF-8 reconfigure ---


@pytest.mark.unit
@pytest.mark.cli
def test_ensure_stdout_utf8_reconfigures_cp932(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #254: cp932 stream は UTF-8 に reconfigure される。"""
    import io
    import sys

    from lorairo.cli.main import _ensure_stdout_utf8

    mock_stdout = io.TextIOWrapper(io.BytesIO(), encoding="cp932")
    mock_stderr = io.TextIOWrapper(io.BytesIO(), encoding="cp932")
    monkeypatch.setattr(sys, "stdout", mock_stdout)
    monkeypatch.setattr(sys, "stderr", mock_stderr)

    _ensure_stdout_utf8()

    assert sys.stdout.encoding.lower() == "utf-8"
    assert sys.stderr.encoding.lower() == "utf-8"


@pytest.mark.unit
@pytest.mark.cli
def test_ensure_stdout_utf8_no_op_for_utf8(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #254: 既に UTF-8 環境では reconfigure を呼ばない (no-op)。"""
    import io
    import sys

    from lorairo.cli.main import _ensure_stdout_utf8

    mock_stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    monkeypatch.setattr(sys, "stdout", mock_stdout)

    called: list[tuple] = []
    original_reconfigure = mock_stdout.reconfigure

    def spy_reconfigure(*args, **kwargs):
        called.append((args, kwargs))
        return original_reconfigure(*args, **kwargs)

    monkeypatch.setattr(mock_stdout, "reconfigure", spy_reconfigure)

    _ensure_stdout_utf8()

    assert called == []  # reconfigure 未呼び出し


@pytest.mark.unit
@pytest.mark.cli
def test_ensure_stdout_utf8_handles_missing_encoding(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #254: encoding 属性が None の stream は skip して落ちない。"""
    import sys

    from lorairo.cli.main import _ensure_stdout_utf8

    mock_stdout = MagicMock(spec=["encoding", "reconfigure"])
    mock_stdout.encoding = None
    monkeypatch.setattr(sys, "stdout", mock_stdout)

    # 例外で落ちないこと
    _ensure_stdout_utf8()
    mock_stdout.reconfigure.assert_not_called()


@pytest.mark.unit
@pytest.mark.cli
def test_ensure_stdout_utf8_handles_missing_reconfigure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #254: reconfigure 不能な stream (pytest capture 等) も skip。"""
    import sys

    from lorairo.cli.main import _ensure_stdout_utf8

    # reconfigure attribute を持たない stream
    mock_stdout = MagicMock(spec=["encoding"])
    mock_stdout.encoding = "cp932"
    monkeypatch.setattr(sys, "stdout", mock_stdout)

    # 例外で落ちないこと (reconfigure 不在をハンドル)
    _ensure_stdout_utf8()


# --- Issue #254 (reopen): Windows console code page 切替 ---


@pytest.mark.unit
@pytest.mark.cli
def test_ensure_stdout_utf8_skips_console_cp_on_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #254: 非 Windows 環境では console code page 切替を呼ばない。"""
    import sys

    import lorairo.cli.main as cli_main

    monkeypatch.setattr(sys, "platform", "linux")
    called: list[None] = []
    monkeypatch.setattr(cli_main, "_set_windows_console_utf8", lambda: called.append(None))

    cli_main._ensure_stdout_utf8()

    assert called == []


@pytest.mark.unit
@pytest.mark.cli
def test_ensure_stdout_utf8_invokes_console_cp_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #254: Windows 環境では console code page 切替が呼ばれる。"""
    import sys

    import lorairo.cli.main as cli_main

    monkeypatch.setattr(sys, "platform", "win32")
    called: list[None] = []
    monkeypatch.setattr(cli_main, "_set_windows_console_utf8", lambda: called.append(None))

    cli_main._ensure_stdout_utf8()

    assert called == [None]


@pytest.mark.unit
@pytest.mark.cli
def test_set_windows_console_utf8_calls_set_console_output_cp(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #254: cp932 console で SetConsoleOutputCP(65001) と SetConsoleCP(65001) が呼ばれる。"""
    import ctypes
    import sys

    monkeypatch.setattr(sys, "platform", "win32")

    kernel32 = MagicMock()
    kernel32.GetConsoleOutputCP.return_value = 932
    kernel32.GetConsoleCP.return_value = 932
    kernel32.SetConsoleOutputCP.return_value = 1  # 成功 (non-zero)

    windll = MagicMock()
    windll.kernel32 = kernel32
    monkeypatch.setattr(ctypes, "windll", windll, raising=False)

    registered: list = []
    monkeypatch.setattr("atexit.register", lambda f: registered.append(f))

    from lorairo.cli.main import _set_windows_console_utf8

    _set_windows_console_utf8()

    kernel32.SetConsoleOutputCP.assert_called_once_with(65001)
    kernel32.SetConsoleCP.assert_called_once_with(65001)
    assert len(registered) == 1  # 復元 callback が atexit に登録される


@pytest.mark.unit
@pytest.mark.cli
def test_set_windows_console_utf8_noop_when_already_utf8(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #254: 既に code page 65001 の console では SetConsoleOutputCP を呼ばない。"""
    import ctypes
    import sys

    monkeypatch.setattr(sys, "platform", "win32")

    kernel32 = MagicMock()
    kernel32.GetConsoleOutputCP.return_value = 65001
    kernel32.GetConsoleCP.return_value = 65001

    windll = MagicMock()
    windll.kernel32 = kernel32
    monkeypatch.setattr(ctypes, "windll", windll, raising=False)

    registered: list = []
    monkeypatch.setattr("atexit.register", lambda f: registered.append(f))

    from lorairo.cli.main import _set_windows_console_utf8

    _set_windows_console_utf8()

    kernel32.SetConsoleOutputCP.assert_not_called()
    kernel32.SetConsoleCP.assert_not_called()
    assert registered == []


@pytest.mark.unit
@pytest.mark.cli
def test_set_windows_console_utf8_skips_on_set_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #254: SetConsoleOutputCP が 0 (失敗) を返す場合は atexit 復元を登録しない。"""
    import ctypes
    import sys

    monkeypatch.setattr(sys, "platform", "win32")

    kernel32 = MagicMock()
    kernel32.GetConsoleOutputCP.return_value = 932
    kernel32.GetConsoleCP.return_value = 932
    kernel32.SetConsoleOutputCP.return_value = 0  # 失敗 (console 不在等)

    windll = MagicMock()
    windll.kernel32 = kernel32
    monkeypatch.setattr(ctypes, "windll", windll, raising=False)

    registered: list = []
    monkeypatch.setattr("atexit.register", lambda f: registered.append(f))

    from lorairo.cli.main import _set_windows_console_utf8

    _set_windows_console_utf8()

    kernel32.SetConsoleOutputCP.assert_called_once_with(65001)
    kernel32.SetConsoleCP.assert_not_called()  # output 失敗時は input も呼ばない
    assert registered == []  # 復元 callback も登録しない


@pytest.mark.unit
@pytest.mark.cli
def test_set_windows_console_utf8_restores_original_on_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #254: atexit hook が元の code page を SetConsoleOutputCP / SetConsoleCP で復元する。"""
    import ctypes
    import sys

    monkeypatch.setattr(sys, "platform", "win32")

    kernel32 = MagicMock()
    kernel32.GetConsoleOutputCP.return_value = 932
    kernel32.GetConsoleCP.return_value = 850  # 異なる initial CP
    kernel32.SetConsoleOutputCP.return_value = 1

    windll = MagicMock()
    windll.kernel32 = kernel32
    monkeypatch.setattr(ctypes, "windll", windll, raising=False)

    registered: list = []
    monkeypatch.setattr("atexit.register", lambda f: registered.append(f))

    from lorairo.cli.main import _set_windows_console_utf8

    _set_windows_console_utf8()

    # 切替直後: SetConsoleOutputCP(65001), SetConsoleCP(65001)
    assert kernel32.SetConsoleOutputCP.call_args_list == [((65001,),)]
    assert kernel32.SetConsoleCP.call_args_list == [((65001,),)]

    # 登録された atexit callback を実行 → 元の code page に戻る
    assert len(registered) == 1
    registered[0]()

    # SetConsoleOutputCP / SetConsoleCP の最終呼び出しが original
    kernel32.SetConsoleOutputCP.assert_called_with(932)
    kernel32.SetConsoleCP.assert_called_with(850)
