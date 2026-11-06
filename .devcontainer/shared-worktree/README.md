# Shared-worktree profile (opt-in)

Rebuilds the *current* shared-worktree container shape: host checkout bind-mounted **rw** at
`/workspaces/LoRAIro`, OS-specific worktrees under `.agents/worktree/`, the existing `lorairo-venv`
volume at `/workspaces/LoRAIro/.venv`, and `UV_PROJECT_ENVIRONMENT` unified to that path for the
container, SSH and CLI sessions. The default profile (`../devcontainer.json`, read-only mount +
independent `-linux` checkout) is unchanged. This profile never runs `make setup`, `uv sync` or a clone.

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
3. **Volume identity / empty check**: `docker volume inspect <name>` for `lorairo-codex-config`,
   `lorairo-linux-config`, `lorairo-linux-cache`, `lorairo-linux-state`, `lorairo-shared-persist`;
   migration refuses non-empty volumes. After a partial failure keep the backup, inspect the volume,
   and retry with a new `--shared-volume` / `--volume` name (or a new backup dir); never force.
   A required source (Herdr, `~/.claude.json`, `authorized_keys`) that is missing aborts before any artifact is written.
4. **Create the new container with the explicit config, old one kept**:
   `devcontainer up --workspace-folder <host checkout> --config .devcontainer/shared-worktree/devcontainer.json --id-label <new-label>`
   (`<new-label>` distinguishes it from the old container; `--remove-existing-container` is deliberately not used).
   Host port 2222 conflicts while the old container runs: stop the old one first (`docker stop <old-id>`), do not delete it.
5. postCreate runs `bootstrap.sh restore`; check its log for `restored` / `already present`, no `refusing`.
6. **SSH host key**: the new container's sshd host fingerprint differs. Obtain the fingerprint from a
   trusted channel (`ssh-keygen -lf /etc/ssh/ssh_host_*_key.pub` run inside the new container via the
   Dev Containers terminal) and compare it with what the client shows. `ssh-keyscan` output alone is not
   verification. Replace the stale `known_hosts` entry only after the match; never use
   `StrictHostKeyChecking=no`.
7. **Verify**: same Herdr session (`herdr --session val-orchestration status server --json`), a
   conversation round trip with both agents, and the existing monitor. Auth/hook/trust approvals remain
   the user's decision.
8. **Rollback**: stop the new container, `docker start <old-id>`. Backups and the old container are untouched;
   the named volumes are never deleted.

Docker-based steps above (build, seed, recreation) have **not** been executed or verified here.
