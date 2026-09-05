#!/usr/bin/env bash
set -Eeuo pipefail

readonly WORKSPACE=/workspaces/LoRAIro
cd "$WORKSPACE"
readonly LOG="$WORKSPACE/.devcontainer/postCreate.log"
exec > >(tee -a "$LOG") 2>&1
trap 'status=$?; echo "[postCreate] failed at line ${LINENO} (exit ${status})" >&2; exit "$status"' ERR

echo "[postCreate] ran $(date -Is)"

echo "[postCreate] start"

# Image-owned CLIs must exist before any workspace initialization begins.
node --version
codex --version
claude --version

# The harness installer was added with LoRAIro #1296. Do not silently complete
# setup from an older bind-mounted checkout: it would omit the restored hooks.
if [[ ! -f scripts/install_agent_harness.py ]]; then
    echo "[postCreate] Missing scripts/install_agent_harness.py. Update the host checkout (git pull --ff-only), then rebuild." >&2
    exit 1
fi

# 1) venv ownership
sudo chown -R vscode:vscode /workspaces/LoRAIro/.venv || true

# 2) Keep any nested virtual environments from the Windows workspace.
# The host checkout is also used to run LoRAIro directly on Windows, so its
# environments must not be removed during Dev Container initialization.

# 3) fetch submodules + install python deps (single source of truth: `make setup`)
make setup
python -X utf8 scripts/validate_harness.py

# Claude Code is pre-installed in Dockerfile. Gemini CLI and Cursor are retired.

echo "[postCreate] done"
