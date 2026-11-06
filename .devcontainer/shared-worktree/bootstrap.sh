#!/usr/bin/env bash
# Shared-worktree profile: persist and restore the few user files that named volumes do not cover.
#   bootstrap.sh restore   (postCreate) restore missing files from the persistent volume
#   bootstrap.sh save      (before recreation) copy live files into the persistent volume
# Existing files that differ are never overwritten; the script refuses and exits 1 instead.
# Contents are copied as opaque bytes and never printed.
set -Eeuo pipefail

HOME_DIR="${HOME:?}"
PERSIST="${LORAIRO_PERSIST_DIR:-$HOME_DIR/.persist}"
# 名前 | 永続領域内パス | 通常の場所 | mode
ENTRIES=(
    "herdr|bin/herdr|$HOME_DIR/.local/bin/herdr|755"
    "claude.json|claude.json|$HOME_DIR/.claude.json|600"
    "authorized_keys|ssh/authorized_keys|$HOME_DIR/.ssh/authorized_keys|600"
)

refused=0

install_file() { # source destination mode: 一時ファイル経由で原子的に置く
    local source=$1 destination=$2 mode=$3 staged
    mkdir -p "$(dirname "$destination")"
    staged=$(mktemp "$destination.XXXXXX")
    cp -- "$source" "$staged"
    chmod "$mode" "$staged"
    mv -- "$staged" "$destination"
}

restore() {
    local entry name relative live mode saved
    for entry in "${ENTRIES[@]}"; do
        IFS='|' read -r name relative live mode <<<"$entry"
        saved="$PERSIST/$relative"
        if [[ ! -f $saved ]]; then
            echo "[shared-worktree] $name: not seeded in persistent volume (skipped)"
        elif [[ ! -e $live ]]; then
            install_file "$saved" "$live" "$mode"
            echo "[shared-worktree] $name: restored"
        elif cmp -s -- "$saved" "$live"; then
            echo "[shared-worktree] $name: already present"
        else
            echo "[shared-worktree] $name: existing file differs from persisted copy; refusing to overwrite" >&2
            refused=1
        fi
    done
}

save() {
    local entry name relative live mode saved
    for entry in "${ENTRIES[@]}"; do
        IFS='|' read -r name relative live mode <<<"$entry"
        saved="$PERSIST/$relative"
        if [[ ! -f $live ]]; then
            echo "[shared-worktree] $name: no live file (skipped)"
        elif [[ -f $saved ]] && cmp -s -- "$saved" "$live"; then
            echo "[shared-worktree] $name: already saved"
        elif [[ $name == herdr && -e $saved ]]; then
            # 実行体の差し替えは意図的な操作に限る
            echo "[shared-worktree] $name: persisted binary differs; refusing to overwrite" >&2
            refused=1
        else
            mkdir -p "$(dirname "$saved")"
            install_file "$live" "$saved" "$mode"
            echo "[shared-worktree] $name: saved"
        fi
    done
}

case "${1:-}" in
restore | save)
    if [[ $1 == restore && ! -d $PERSIST ]]; then
        echo "[shared-worktree] persistent directory $PERSIST missing; nothing to restore" >&2
        exit 1
    fi
    mkdir -p "$PERSIST"
    "$1"
    ;;
*)
    echo "usage: bootstrap.sh restore|save" >&2
    exit 2
    ;;
esac
exit "$refused"
