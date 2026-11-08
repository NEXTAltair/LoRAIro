# Shared-worktree profile (opt-in)

The default profile (`../devcontainer.json`) already uses the shared-worktree shape: host checkout
bind-mounted **rw** at `/workspaces/LoRAIro`, OS-specific worktrees under `.agents/worktree/`, the
existing `lorairo-venv` volume at `/workspaces/LoRAIro/.venv`, and `UV_PROJECT_ENVIRONMENT` set to
that path. This profile keeps that shape and adds only opt-in extras: a persist volume restored by
`bootstrap.sh` (Herdr binary, `~/.claude.json`, SSH `authorized_keys` / `known_hosts`), the sshd
Feature's default port mapping (`2222:2222`), and `LORAIRO_VOLUME_PREFIX` for seeding fresh volumes.
Unlike the default profile, it never runs `make setup`, `uv sync` or a clone.

Select it only explicitly: `--config .devcontainer/shared-worktree/devcontainer.json`.
The Dev Containers lockfile of the default profile is not shared; pin features separately if needed.

## What is persisted where

| State | Where |
| --- | --- |
| Codex / Claude / XDG config, cache, state | existing named volumes (`lorairo-codex-config`, `lorairo-claude-config`, `lorairo-linux-*`) |
| venv, worktrees | `lorairo-venv`, `lorairo-worktrees` |
| Herdr binary (0.9.x), `~/.claude.json`, `~/.ssh/authorized_keys`, `~/.ssh/known_hosts` (optional) | `lorairo-shared-persist` at `~/.persist`, restored by `bootstrap.sh restore` |
| sshd **host keys** | not persisted: a new container has new keys (see step 6) |

`bootstrap.sh restore` fails (exit 1) when a required file is not seeded, and never replaces an
existing destination that differs or is a symlink / directory / special file.
`bootstrap.sh save` keeps previous bytes of changed settings under `~/.persist/backups/` and refuses
to replace a differing Herdr binary (delete the persisted copy deliberately to upgrade).
`known_hosts` is preserved as optional opaque bytes; losing it only costs re-verification.

## Existing non-empty volumes: seed a fresh prefix

If `lorairo-codex-config`, `lorairo-linux-config/cache/state` already exist and are non-empty (their purpose
may be unknown), **keep them untouched** and seed new volumes under an explicit prefix instead. The prefix
selects five names: `<prefix>-codex-config`, `<prefix>-linux-config`, `<prefix>-linux-cache`,
`<prefix>-linux-state`, `<prefix>-shared-persist`. Claude, venv, worktrees, extensions and bash history
volumes keep their `lorairo-*` names. The migration helper (`--volume-prefix`) and the profile
(`LORAIRO_VOLUME_PREFIX`) must use the **same** value; the helper's XDG Git-config copy goes to the new
`<prefix>-linux-config` as well. `--volume-prefix` cannot be combined with `--volume` / `--shared-volume`,
and `lorairo` itself is rejected, before anything is written.

~~~powershell
$prefix = "lorairo-herdr-20261106"          # new, lower-case, never reuse a partially migrated prefix
# 1) all five targets must be absent or empty (read-only inspection)
foreach ($n in "codex-config","linux-config","linux-cache","linux-state","shared-persist") { docker volume inspect "$prefix-$n" }
# 2) seed (the source container is paused briefly while docker cp runs: agents, Herdr and SSH freeze for that time)
python scripts/migrate_container_codex.py --container <old-id> --backup-dir <new private dir> --with-shared-extras --volume-prefix $prefix
# 3) create the new container with the same prefix visible to the Dev Containers CLI
$env:LORAIRO_VOLUME_PREFIX = $prefix
devcontainer up --workspace-folder <host checkout> --config .devcontainer/shared-worktree/devcontainer.json --id-label <new-label>
~~~

A non-empty prefixed volume is refused as well. After a partial migration do **not** retry: keep the backup
directory and every volume, then choose a new prefix and a new backup directory deliberately. The backup
directory is created private (0700; files 0600; protected DACL on Windows). The profile sets
`shutdownAction: none` so closing VS Code does not stop Herdr or the agents.
These commands were not executed against Docker here (see the end of this file).

## Recreation runbook (commands marked `<placeholder>` are not verified against this host)

The currently running container has Codex/XDG on its **overlay** (no named home volumes) and no
`~/.persist` mount, so `bootstrap.sh save` alone cannot seed it: use the full migration.

1. **Drain**: stop agent work, save dirty worktrees, confirm nothing writes `~/.codex` / SQLite.
   Keep the old container; do not remove it.
2. **Choose the migration branch**
   - Codex/XDG on overlay (current container): full migration with extras
     `python scripts/migrate_container_codex.py --container <old-id> --backup-dir <new private dir> --with-shared-extras`
   - Codex/XDG already in the named volumes (a container created from this profile): extras only
     `python scripts/migrate_container_codex.py --container <id> --backup-dir <new private dir> --shared-extras-only`
     (in such a container, `bootstrap.sh save` over SSH refreshes the persist volume before recreation).
3. **Volume identity / empty check — before running the migration**: `docker volume inspect <name>` for
   `lorairo-codex-config`, `lorairo-linux-config`, `lorairo-linux-cache`, `lorairo-linux-state` (full
   migration only) and `lorairo-shared-persist`; every destination must be empty or absent. Migration
   refuses non-empty volumes and never deletes or overwrites existing state.
   A different `--backup-dir` does **not** clear a non-empty volume. `--volume` renames only the Codex
   volume and `--shared-volume` only the persist volume; the XDG volume names are fixed in the helper and
   in the profile mounts. If you choose custom volume names, change the matching `mounts` entries of the
   profile as well. After a partial migration, stop: keep the backup directory and every volume as they
   are and decide the recovery explicitly (inspect, then pick a fresh volume name plus matching mount).
   A required source (Herdr, `~/.claude.json`, `authorized_keys`) that is missing aborts before any artifact is written.
4. **Create the new container with the explicit config, old one kept**:
   `devcontainer up --workspace-folder <host checkout> --config .devcontainer/shared-worktree/devcontainer.json --id-label <new-label>`
   (`<new-label>` distinguishes it from the old container; `--remove-existing-container` is deliberately not used).
   Host port 2222 conflicts while the old container runs: stop the old one first (`docker stop <old-id>`), do not delete it.
5. postCreate runs `bootstrap.sh restore`; check its log for `restored` / `already present`, no `refusing`.
6. **SSH host key**: the new container's sshd host fingerprint differs. Obtain the fingerprint from a
   trusted channel — inside the new container via the Dev Containers terminal, one public key at a time:
   `for k in /etc/ssh/ssh_host_*_key.pub; do ssh-keygen -lf "$k"; done` — and compare it with what the client shows. `ssh-keyscan` output alone is not
   verification. Replace the stale `known_hosts` entry only after the match; never use
   `StrictHostKeyChecking=no`.
7. **Verify**: same Herdr session (`herdr --session val-orchestration status server --json`), a
   conversation round trip with both agents, and the existing monitor. Auth/hook/trust approvals remain
   the user's decision.
8. **Rollback**: stop the new container, `docker start <old-id>`. Backups and the old container are untouched;
   the named volumes are never deleted.

Docker-based steps above (build, seed, recreation) have **not** been executed or verified here.
