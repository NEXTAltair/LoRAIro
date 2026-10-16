#!/usr/bin/env bash
set -Eeuo pipefail

readonly SOURCE=/workspaces/LoRAIro
readonly WORKSPACE=/workspaces/LoRAIro-linux
readonly LOG=/home/vscode/.local/state/LoRAIro/postCreate.log
export GIT_CONFIG_GLOBAL=/home/vscode/.config/git/config
# Named volumes start root-owned. Keep all existing data and only fix ownership.
sudo chown vscode:vscode "$WORKSPACE" /home/vscode/.codex /home/vscode/.config \
    /home/vscode/.cache /home/vscode/.local/state
mkdir -p "$(dirname "$LOG")"
mkdir -p "$(dirname "$GIT_CONFIG_GLOBAL")"
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
if [[ ! -f "$SOURCE/scripts/install_agent_harness.py" ]]; then
    echo "[postCreate] Missing scripts/install_agent_harness.py. Update the host checkout (git pull --ff-only), then rebuild." >&2
    exit 1
fi

# 1) venv ownership
sudo chown -R vscode:vscode "$WORKSPACE/.venv"

# Docker Desktop exposes the Windows checkout with a different owner. Trust
# the workspace and its two submodules before setup invokes Git. Submodule
# repositories have their own ownership checks; do not trust arbitrary paths.
for repository in \
    "$SOURCE" "$WORKSPACE" \
    "$WORKSPACE/local_packages/genai-tag-db-tools" \
    "$WORKSPACE/local_packages/image-annotator-lib"; do
    if ! git config --global --get-all safe.directory | grep -Fxq "$repository"; then
        git config --global --add safe.directory "$repository"
    fi
done

# Match CRLF files from a Windows checkout against Git's LF index without
# rewriting the files. Preserve any explicit container-user preference.
if ! git config --global --get core.autocrlf >/dev/null; then
    git config --global core.autocrlf input
fi

bash "$SOURCE/.devcontainer/initialize-linux-workspace.sh"
cd "$WORKSPACE"
export UV_PROJECT_ENVIRONMENT="$WORKSPACE/.venv"
export CODEX_HOME=/home/vscode/.codex
export CLAUDE_CONFIG_DIR=/home/vscode/.claude

# 2) Keep any nested virtual environments from the Windows workspace.
# The H: checkout is also used to run LoRAIro directly on Windows, so its
# environments must not be removed during Dev Container initialization.

# 3) fetch submodules + install python deps (single source of truth: `make setup`)
make setup
python -X utf8 scripts/validate_harness.py

# Claude Code is pre-installed in Dockerfile. Gemini CLI and Cursor are retired.

echo "[postCreate] done"
