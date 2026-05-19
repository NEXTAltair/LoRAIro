"""Subprocess smoke tests for the installed CLI entrypoint."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


@pytest.mark.integration
@pytest.mark.cli
@pytest.mark.e2e
def test_lorairo_cli_console_script_starts() -> None:
    """The console script defined in pyproject can start outside CliRunner."""
    repo_root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        ["uv", "run", "--no-sync", "lorairo-cli", "version"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "LoRAIro CLI" in result.stdout
