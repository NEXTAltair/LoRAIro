"""Tests for Claude pre-command hook."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HOOK = PROJECT_ROOT / ".claude" / "hooks" / "hook_pre_commands.py"


def _run_hook(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_input": {"command": command}}),
        text=True,
        capture_output=True,
        check=False,
    )


def test_blocks_draft_pr_create_command() -> None:
    result = _run_hook('gh pr create --draft --title "feat: x" --body "body"')

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["decision"] == "block"
    assert "draft" in payload["reason"]
    assert "agent-pr-maintainer" in payload["reason"]


def test_allows_ready_pr_create_command() -> None:
    result = _run_hook('gh pr create --title "feat: x" --body "body"')

    assert result.returncode == 0
    assert result.stdout == ""
