"""CLI `--log-level` オプションのテスト (Issue #539)。

ログ初期化は `@app.callback()` (`_configure`) でサブコマンド実行時に行われる。
`--log-level` 未指定で既定 INFO、明示指定で該当レベルが `initialize_logging` に
渡ることを検証する。実 annotation は呼ばず、軽量な `version` サブコマンドで検証する。
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app

runner = CliRunner()


@pytest.mark.unit
@pytest.mark.cli
def test_log_level_defaults_to_info(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test: `--log-level` 未指定で initialize_logging が level=INFO で呼ばれる。"""
    spy = MagicMock()
    monkeypatch.setattr("lorairo.cli.main.initialize_logging", spy)

    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    spy.assert_called_once()
    assert spy.call_args[0][0]["level"] == "INFO"


@pytest.mark.unit
@pytest.mark.cli
def test_log_level_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test: `--log-level WARNING` で initialize_logging が level=WARNING で呼ばれる。"""
    spy = MagicMock()
    monkeypatch.setattr("lorairo.cli.main.initialize_logging", spy)

    result = runner.invoke(app, ["--log-level", "WARNING", "version"])

    assert result.exit_code == 0
    spy.assert_called_once()
    assert spy.call_args[0][0]["level"] == "WARNING"


@pytest.mark.unit
@pytest.mark.cli
def test_log_level_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test: `--log-level DEBUG` で initialize_logging が level=DEBUG で呼ばれる。"""
    spy = MagicMock()
    monkeypatch.setattr("lorairo.cli.main.initialize_logging", spy)

    result = runner.invoke(app, ["--log-level", "DEBUG", "version"])

    assert result.exit_code == 0
    spy.assert_called_once()
    assert spy.call_args[0][0]["level"] == "DEBUG"


@pytest.mark.unit
@pytest.mark.cli
def test_log_level_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test: `--log-level` は大文字小文字を区別せず正規化される。"""
    spy = MagicMock()
    monkeypatch.setattr("lorairo.cli.main.initialize_logging", spy)

    result = runner.invoke(app, ["--log-level", "warning", "version"])

    assert result.exit_code == 0
    spy.assert_called_once()
    assert spy.call_args[0][0]["level"] == "WARNING"


@pytest.mark.unit
@pytest.mark.cli
def test_help_does_not_initialize_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test: `--help` では callback が走らず initialize_logging が呼ばれない (#540)。"""
    spy = MagicMock()
    monkeypatch.setattr("lorairo.cli.main.initialize_logging", spy)

    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    spy.assert_not_called()


@pytest.mark.unit
@pytest.mark.cli
def test_log_config_preserves_path_and_rotation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test: file_path と rotation が従来どおり維持される。"""
    spy = MagicMock()
    monkeypatch.setattr("lorairo.cli.main.initialize_logging", spy)

    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    config_arg = spy.call_args[0][0]
    log_path = Path(config_arg["file_path"])
    assert log_path.name == "lorairo-cli.log"
    assert config_arg["rotation"] == "25 MB"
