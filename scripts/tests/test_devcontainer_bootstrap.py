"""Keep Dev Container startup explicit and independent of host npm state."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_image_installs_codex_and_post_create_rejects_a_pre_harness_checkout() -> None:
    script = (ROOT / ".devcontainer" / "postCreateCommand.sh").read_text(encoding="utf-8")
    dockerfile = (ROOT / ".devcontainer" / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM node:24-bookworm AS node-runtime" in dockerfile
    assert '"@openai/codex@${CODEX_VERSION}"' in dockerfile
    assert "ARG CODEX_VERSION=0.153.4" in dockerfile
    assert "codex --version" in script
    assert 'cd "$WORKSPACE"' in script
    assert "scripts/install_agent_harness.py" in script
    assert "scripts/validate_harness.py" in script
    assert "git pull --ff-only" in script
    assert "ghcr.io/devcontainers/features/node:1" not in (ROOT / ".devcontainer" / "devcontainer.json").read_text(
        encoding="utf-8"
    )
