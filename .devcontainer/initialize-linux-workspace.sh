#!/usr/bin/env bash
set -Eeuo pipefail

# Read the host's committed main; never change its index, branch, submodules or worktrees.
SOURCE=${LORAIRO_HOST_SOURCE:-/workspaces/LoRAIro}
WORKSPACE=${LORAIRO_LINUX_WORKSPACE:-/workspaces/LoRAIro-linux}
mkdir -p "$WORKSPACE"
if [[ ! -d "$WORKSPACE/.git" ]]; then
    if find "$WORKSPACE" -mindepth 1 -maxdepth 1 ! -name .venv | grep -q .; then
        echo "Linux workspace contains existing files; refusing to overwrite it." >&2
        exit 1
    fi
    git init -b main "$WORKSPACE"
    git -C "$WORKSPACE" remote add origin "$(git -C "$SOURCE" remote get-url origin)"
    git -C "$WORKSPACE" fetch --no-recurse-submodules "$SOURCE" main:refs/remotes/host/main
    git -C "$WORKSPACE" checkout -b main refs/remotes/host/main
    git -C "$WORKSPACE" config branch.main.remote origin
    git -C "$WORKSPACE" config branch.main.merge refs/heads/main
else
    if [[ "$(git -C "$WORKSPACE" branch --show-current)" != main ]] ||
       [[ -n "$(git -C "$WORKSPACE" status --porcelain)" ]]; then
        echo "Linux checkout has work in progress; preserve it and finish setup manually." >&2
        exit 1
    fi
    git -C "$WORKSPACE" fetch --no-recurse-submodules "$SOURCE" main:refs/remotes/host/main
    git -C "$WORKSPACE" merge --ff-only refs/remotes/host/main
fi
