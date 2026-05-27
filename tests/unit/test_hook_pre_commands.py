"""Tests for Claude pre-command hook."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HOOK = PROJECT_ROOT / ".claude" / "hooks" / "hook_pre_commands.py"


def _run_hook(command: str, *, cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    tool_input = {"command": command}
    if cwd is not None:
        tool_input["cwd"] = cwd

    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_input": tool_input}),
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


def test_blocks_uv_without_shared_environment_in_worktree() -> None:
    result = _run_hook("uv run pytest", cwd="/tmp/worktrees/issue-123")

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["decision"] == "block"
    assert "UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv" in payload["reason"]


def test_allows_uv_with_shared_environment_in_worktree() -> None:
    result = _run_hook(
        "UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv uv run pytest",
        cwd="/tmp/worktrees/issue-123",
    )

    assert result.returncode == 0
    assert result.stdout == ""


def test_blocks_similar_but_different_uv_environment_in_worktree() -> None:
    result = _run_hook(
        "UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv2 uv run pytest",
        cwd="/tmp/worktrees/issue-123",
    )

    assert result.returncode == 2


def test_allows_bare_uv_in_worktree() -> None:
    result = _run_hook("uv", cwd="/tmp/worktrees/issue-123")

    assert result.returncode == 0
    assert result.stdout == ""


def test_blocks_cd_worktree_uv_without_shared_environment() -> None:
    result = _run_hook("cd /tmp/worktrees/issue-123 && uv sync --dev")

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert "worktree" in payload["reason"]
