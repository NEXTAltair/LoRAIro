#!/usr/bin/env bash
echo "[postCreate] ran $(date -Is)" | tee -a /workspaces/LoRAIro/.devcontainer/postCreate.log
set -euo pipefail

echo "[postCreate] start"

# Make sure Node feature's nvm is usable (safe even if already loaded)
export NVM_DIR="/usr/local/share/nvm"
# shellcheck disable=SC1091
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
nvm use 20 >/dev/null || true

# 1) venv ownership
sudo chown -R vscode:vscode /workspaces/LoRAIro/.venv || true

# 2) Keep any nested virtual environments from the Windows workspace.
# The host checkout is also used to run LoRAIro directly on Windows, so its
# environments must not be removed during Dev Container initialization.

# 3) fetch submodules + install python deps (single source of truth: `make setup`)
make setup

# Claude Code is pre-installed in Dockerfile. Do not reinstall retired agent CLIs.

echo "[postCreate] done"
