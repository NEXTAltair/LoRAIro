#!/usr/bin/env bash
# Shared-worktree profile: persist and restore the few user files that named volumes do not cover.
#   bootstrap.sh restore   (postCreate) restore missing files from the persistent volume.
#                          Required entries absent from the volume are a FAILURE (exit 1);
#                          set LORAIRO_ALLOW_UNSEEDED=1 only for an intentionally fresh container.
#   bootstrap.sh save      copy live files into the volume (run before recreation, e.g. over SSH).
# Destinations are never replaced when they exist in any form (differing file, symlink, directory,
# special file): the script refuses with exit 1. save keeps the previous persisted bytes of
# claude.json / authorized_keys / known_hosts under backups/; a differing Herdr binary is refused.
# Contents are copied as opaque bytes and never printed.
set -Eeuo pipefail
umask 077

HOME_DIR="${HOME:?}"
PERSIST="${LORAIRO_PERSIST_DIR:-$HOME_DIR/.persist}"
# 名前|永続領域内パス|通常の場所|mode|必須(1)/任意(0)
ENTRIES=(
    "herdr|bin/herdr|$HOME_DIR/.local/bin/herdr|755|1"
    "claude.json|claude.json|$HOME_DIR/.claude.json|600|1"
    "authorized_keys|ssh/authorized_keys|$HOME_DIR/.ssh/authorized_keys|600|1"
    "known_hosts|ssh/known_hosts|$HOME_DIR/.ssh/known_hosts|644|0"
)

failed=0

refuse() { echo "[shared-worktree] $1" >&2; failed=1; }
absent() { [[ ! -e $1 && ! -L $1 ]]; }
regular() { [[ -f $1 && ! -L $1 ]]; }

# 各段階の失敗を明示的に伝播する (呼び出し元が if/|| で使っても errexit 無効の影響を受けない)。
# 失敗時は temp をその場で削除し、宛先には何も公開しない。
install_new() { # source destination mode: 宛先が存在すれば失敗 (ln -T は宛先を常に通常パスとして扱う no-clobber)
    local source=$1 destination=$2 mode=$3 temp
    mkdir -p -- "$(dirname "$destination")" || return 1
    temp=$(mktemp "$destination.XXXXXX") || return 1
    if cp -- "$source" "$temp" && chmod -- "$mode" "$temp" && ln -T -- "$temp" "$destination" 2>/dev/null; then
        rm -f -- "$temp"
        return 0
    fi
    rm -f -- "$temp"
    return 1
}

replace_file() { # 既存の通常ファイルを原子的に置換 (呼び出し側で旧 bytes を退避済み)
    local source=$1 destination=$2 mode=$3 temp
    temp=$(mktemp "$destination.XXXXXX") || return 1
    if cp -- "$source" "$temp" && chmod -- "$mode" "$temp" && mv -T -- "$temp" "$destination"; then
        return 0
    fi
    rm -f -- "$temp"
    return 1
}

restore() {
    local entry name relative live mode required saved missing=0
    for entry in "${ENTRIES[@]}"; do
        IFS='|' read -r name relative live mode required <<<"$entry"
        saved="$PERSIST/$relative"
        if ! regular "$saved"; then
            if [[ $required == 1 && ${LORAIRO_ALLOW_UNSEEDED:-0} != 1 ]]; then
                refuse "$name: required file not seeded in persistent volume"
                missing=1
            else
                echo "[shared-worktree] $name: not seeded (skipped)"
            fi
        elif absent "$live"; then
            if install_new "$saved" "$live" "$mode"; then
                echo "[shared-worktree] $name: restored"
            else
                refuse "$name: could not install (destination appeared or copy failed); nothing published"
            fi
        elif regular "$live" && cmp -s -- "$saved" "$live"; then
            echo "[shared-worktree] $name: already present"
        else
            refuse "$name: existing destination (differs, symlink, directory or special file); refusing to overwrite"
        fi
    done
    [[ $missing == 0 ]] || echo "[shared-worktree] seed the volume first (migrate_container_codex.py --shared-extras-only, or bootstrap.sh save in the old container)" >&2
}

save() {
    local entry name relative live mode required saved digest backup
    for entry in "${ENTRIES[@]}"; do
        IFS='|' read -r name relative live mode required <<<"$entry"
        saved="$PERSIST/$relative"
        if [[ ! -f $live ]]; then
            if [[ $required == 1 ]]; then refuse "$name: required live file missing"; else echo "[shared-worktree] $name: no live file (skipped)"; fi
        elif absent "$saved"; then
            mkdir -p "$(dirname "$saved")"
            if install_new "$live" "$saved" "$mode"; then echo "[shared-worktree] $name: saved"; else refuse "$name: could not save (unreadable source or persisted path appeared)"; fi
        elif ! regular "$saved"; then
            refuse "$name: persisted path is not a regular file; refusing"
        elif cmp -s -- "$saved" "$live"; then
            echo "[shared-worktree] $name: already saved"
        elif [[ $name == herdr ]]; then
            refuse "$name: persisted binary differs; refusing to replace it (remove it deliberately to upgrade)"
        else
            digest=$(sha256sum -- "$saved" | cut -d' ' -f1)
            backup="$PERSIST/backups/${relative//\//_}.$digest"
            mkdir -p "$PERSIST/backups"
            if [[ -e $backup ]]; then
                cmp -s -- "$saved" "$backup" || { refuse "$name: backup path holds different bytes; refusing"; continue; }
            else
                install_new "$saved" "$backup" 600 || { refuse "$name: could not back up previous copy"; continue; }
            fi
            if replace_file "$live" "$saved" "$mode"; then
                echo "[shared-worktree] $name: updated (previous copy kept in backups/)"
            else
                refuse "$name: could not update persisted copy; previous copy untouched"
            fi
        fi
    done
}

if [[ ${BASH_SOURCE[0]} != "$0" ]]; then
    return 0 2>/dev/null || true # テスト用: source された場合は関数定義のみ
fi

case "${1:-}" in
restore | save)
    if [[ $1 == restore && ! -d $PERSIST ]]; then
        echo "[shared-worktree] persistent directory $PERSIST missing" >&2
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
exit "$failed"
