from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

_SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "run_runtime_webapi_tests.py"
_SPEC = importlib.util.spec_from_file_location("run_runtime_webapi_tests", _SCRIPT_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
runner_script = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(runner_script)


class FakeConfigService:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    def get_setting(self, section: str, key: str, default: str = "") -> str:
        assert section == "api"
        return self.values.get(key, default)


def test_load_api_keys_reads_lorairo_config_names() -> None:
    config = FakeConfigService(
        {
            "openai_key": "sk-openai",
            "claude_key": "sk-anthropic",
            "google_key": "sk-google",
            "openrouter_key": "sk-openrouter",
        }
    )

    assert runner_script.load_api_keys(config) == {
        "openai": "sk-openai",
        "anthropic": "sk-anthropic",
        "google": "sk-google",
        "openrouter": "sk-openrouter",
    }


def test_load_api_keys_treats_none_as_missing() -> None:
    config = FakeConfigService({"openai_key": None})  # type: ignore[dict-item]

    assert runner_script.load_api_keys(config)["openai"] == ""


def test_build_child_env_removes_existing_api_env_when_config_missing() -> None:
    env = runner_script.build_child_env(
        {
            "openai": "",
            "anthropic": "configured-anthropic",
            "google": "",
            "openrouter": "",
        },
        base_env={
            "OPENAI_API_KEY": "leaked-openai",
            "ANTHROPIC_API_KEY": "leaked-anthropic",
            "GEMINI_API_KEY": "leaked-google",
            "OPENROUTER_API_KEY": "leaked-openrouter",
            "PATH": "/usr/bin",
        },
        repo_root=Path("/repo"),
    )

    assert "OPENAI_API_KEY" not in env
    assert env["ANTHROPIC_API_KEY"] == "configured-anthropic"
    assert "GEMINI_API_KEY" not in env
    assert "OPENROUTER_API_KEY" not in env
    assert env["UV_PROJECT_ENVIRONMENT"] == "/repo/.venv"
    assert env["PATH"] == "/usr/bin"


def test_build_child_env_uses_shared_venv_for_worktree() -> None:
    env = runner_script.build_child_env(
        {"openai": "", "anthropic": "", "google": "", "openrouter": ""},
        base_env={"PATH": "/usr/bin"},
        repo_root=Path("/tmp/worktrees/issue-123"),
    )

    assert env["UV_PROJECT_ENVIRONMENT"] == "/workspaces/LoRAIro/.venv"


def test_run_runtime_webapi_tests_invokes_iam_lib_pytest_without_printing_keys(capsys) -> None:
    calls = []
    config = FakeConfigService(
        {
            "openai_key": "secret-openai",
            "claude_key": "",
            "google_key": "secret-google",
            "openrouter_key": "",
        }
    )

    def fake_run(command, *, cwd, env, check):
        calls.append((command, cwd, env, check))
        return SimpleNamespace(returncode=7)

    exit_code = runner_script.run_runtime_webapi_tests(
        config_service=config,
        base_env={"OPENAI_API_KEY": "wrong", "PATH": "/usr/bin"},
        runner=fake_run,
    )

    assert exit_code == 7
    assert len(calls) == 1
    command, cwd, env, check = calls[0]
    assert command == [
        "uv",
        "run",
        "--no-sync",
        "pytest",
        "tests/runtime_validation/test_real_webapi_runtime.py",
        "-m",
        "calls_real_webapi",
    ]
    assert cwd == runner_script.IAM_LIB_DIR
    assert env["OPENAI_API_KEY"] == "secret-openai"
    assert env["GEMINI_API_KEY"] == "secret-google"
    assert "ANTHROPIC_API_KEY" not in env
    assert "OPENROUTER_API_KEY" not in env
    assert check is False

    output = capsys.readouterr().out
    assert "configured: openai, google" in output
    assert "missing: anthropic, openrouter" in output
    assert "secret-openai" not in output
    assert "secret-google" not in output
