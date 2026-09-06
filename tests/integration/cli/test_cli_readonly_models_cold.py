"""Cold CLI model registry imports must obey strict configuration I/O policy."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("prepared", ["missing", "ready", "malformed"])
def test_cold_models_list_configuration_policy(tmp_path: Path, prepared: str) -> None:
    cwd = tmp_path / "cold 日本語 workspace"
    cwd.mkdir()
    config = cwd / "config" / "annotator_config.toml"
    if prepared != "missing":
        config.parent.mkdir()
        config.write_text("[invalid\n" if prepared == "malformed" else "# prepared model configuration\n")
    env = os.environ.copy()
    env.pop("PYTEST_CURRENT_TEST", None)
    env.pop("IMAGE_ANNOTATOR_CONFIG_READ_ONLY", None)
    env["LORAIRO_CLI_LOG_PATH"] = str(tmp_path / "cli.log")
    code = """
import json, os, socket
from pathlib import Path
from unittest.mock import patch
with patch.object(socket.socket, 'connect', side_effect=AssertionError('network forbidden')):
    from typer.testing import CliRunner
    from lorairo.cli.main import app
    runner = CliRunner()
    config = Path('config/annotator_config.toml')
    before = config.read_bytes() if config.exists() else None
    first = runner.invoke(app, ['--json', '--read-only', 'models', 'list'])
    after = config.read_bytes() if config.exists() else None
    result = {
        'first_exit': first.exit_code,
        'first_payload': json.loads(first.stdout.splitlines()[-1]),
        'config_preserved': before == after,
        'policy_restored': 'IMAGE_ANNOTATOR_CONFIG_READ_ONLY' not in os.environ,
    }
    if before is None:
        legacy = runner.invoke(app, ['--json', 'models', 'list'])
        prepared = config.read_bytes() if config.exists() else None
        retry = runner.invoke(app, ['--json', '--read-only', 'models', 'list'])
        result.update(legacy_exit=legacy.exit_code, legacy_prepared=prepared is not None,
            retry_exit=retry.exit_code, retry_preserved=prepared == config.read_bytes())
    result['final_policy_restored'] = 'IMAGE_ANNOTATOR_CONFIG_READ_ONLY' not in os.environ
print(json.dumps(result))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code], cwd=cwd, env=env, capture_output=True, text=True, timeout=120
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout.splitlines()[-1])
    assert result["config_preserved"] is True
    assert result["policy_restored"] is True
    assert result["final_policy_restored"] is True
    if prepared == "malformed":
        assert result["first_exit"] == 1, result
        assert result["first_payload"]["code"] == "PRECONDITION_FAILED"
        assert "Back up" in result["first_payload"]["hint"]
        assert "does not repair" in result["first_payload"]["hint"]
    elif prepared == "ready":
        assert result["first_exit"] == 0, result
    else:
        assert result["first_exit"] == 1, result
        assert result["first_payload"]["code"] == "PRECONDITION_FAILED"
        assert "models list without --read-only" in result["first_payload"]["hint"]
        assert result["legacy_exit"] == result["retry_exit"] == 0, result
        assert result["legacy_prepared"] is result["retry_preserved"] is True
