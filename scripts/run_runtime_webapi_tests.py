"""Run iam-lib real WebAPI runtime validation through LoRAIro config.

This script bridges LoRAIro's production config path to image-annotator-lib's
runtime validation tests without making iam-lib depend on LoRAIro.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from lorairo.services.configuration_service import ConfigurationService

REPO_ROOT = Path(__file__).resolve().parents[1]
IAM_LIB_DIR = REPO_ROOT / "local_packages" / "image-annotator-lib"
RUNTIME_TEST_PATH = "tests/runtime_validation/test_real_webapi_runtime.py"
WORKTREE_ROOT = Path("/tmp/worktrees")
SHARED_UV_PROJECT_ENVIRONMENT = Path("/workspaces/LoRAIro/.venv")

PROVIDER_CONFIG_KEYS = {
    "openai": "openai_key",
    "anthropic": "claude_key",
    "google": "google_key",
    "openrouter": "openrouter_key",
}

PROVIDER_ENV_KEYS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def normalize_api_key(value: Any) -> str:
    """Normalize a config value into an API key string."""
    if value is None:
        return ""
    return str(value).strip()


def load_api_keys(config_service: ConfigurationService | None = None) -> dict[str, str]:
    """Load provider API keys from LoRAIro ConfigurationService."""
    config = config_service or ConfigurationService()
    return {
        provider: normalize_api_key(config.get_setting("api", config_key, ""))
        for provider, config_key in PROVIDER_CONFIG_KEYS.items()
    }


def resolve_uv_project_environment(repo_root: Path) -> Path:
    """Use the shared LoRAIro venv for /tmp/worktrees checkouts."""
    try:
        if repo_root.resolve().is_relative_to(WORKTREE_ROOT):
            return SHARED_UV_PROJECT_ENVIRONMENT
    except (OSError, RuntimeError):
        if str(repo_root).startswith(f"{WORKTREE_ROOT}/"):
            return SHARED_UV_PROJECT_ENVIRONMENT

    return repo_root / ".venv"


def build_child_env(
    api_keys: Mapping[str, str],
    *,
    base_env: Mapping[str, str] | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict[str, str]:
    """Build subprocess env, keeping API keys sourced only from LoRAIro config."""
    env = dict(base_env or os.environ)
    for env_key in PROVIDER_ENV_KEYS.values():
        env.pop(env_key, None)

    for provider, env_key in PROVIDER_ENV_KEYS.items():
        api_key = normalize_api_key(api_keys.get(provider, ""))
        if api_key:
            env[env_key] = api_key

    env["UV_PROJECT_ENVIRONMENT"] = str(resolve_uv_project_environment(repo_root))
    return env


def build_pytest_command() -> list[str]:
    """Return the iam-lib runtime validation pytest command."""
    return [
        "uv",
        "run",
        "--no-sync",
        "pytest",
        RUNTIME_TEST_PATH,
        "-m",
        "calls_real_webapi",
    ]


def print_key_status(api_keys: Mapping[str, str]) -> None:
    """Print provider key presence without exposing key values."""
    configured = [
        provider for provider in PROVIDER_ENV_KEYS if normalize_api_key(api_keys.get(provider, ""))
    ]
    missing = [provider for provider in PROVIDER_ENV_KEYS if provider not in configured]
    print("LoRAIro config API key status:")
    print(f"  configured: {', '.join(configured) if configured else '(none)'}")
    print(f"  missing: {', '.join(missing) if missing else '(none)'}")


def run_runtime_webapi_tests(
    *,
    config_service: ConfigurationService | None = None,
    base_env: Mapping[str, str] | None = None,
    runner: Any = subprocess.run,
) -> int:
    """Run iam-lib real WebAPI runtime validation and return its exit code."""
    api_keys = load_api_keys(config_service)
    print_key_status(api_keys)

    command = build_pytest_command()
    env = build_child_env(api_keys, base_env=base_env)
    result = runner(command, cwd=IAM_LIB_DIR, env=env, check=False)
    return int(result.returncode)


def main() -> int:
    return run_runtime_webapi_tests()


if __name__ == "__main__":
    sys.exit(main())
