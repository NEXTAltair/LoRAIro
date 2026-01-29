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

# 2) remove nested venvs (if any)
find /workspaces/LoRAIro/local_packages -type d -name .venv -exec rm -rf {} + || true

# 3) install python deps
make install-dev

# 4) install global CLIs (only after node/npm are ready)
npm -v
npm i -g @anthropic-ai/claude-code @google/gemini-cli

echo "[postCreate] done"
