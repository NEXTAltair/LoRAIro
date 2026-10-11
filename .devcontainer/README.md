# Windows / Linux environment isolation

Windows owns the host checkout. The container mounts it **read-only** at
/workspaces/LoRAIro and develops in an independent checkout at
/workspaces/LoRAIro-linux. The Linux checkout has its own index, branches,
submodule repositories and .agents/worktree/. Configuration isolation alone
cannot make Git worktree absolute paths or branch switching portable.

| State | Windows | Container |
| --- | --- | --- |
| Git/source/project hooks, rules, agents, skills | Host checkout | lorairo-linux-checkout volume, same committed main |
| Shared Python per OS | Host .venv/Scripts/python.exe | Existing lorairo-venv, at Linux checkout .venv/bin/python |
| Codex user settings/auth/history | Windows user .codex | lorairo-codex-config at /home/vscode/.codex |
| Claude user settings/auth/history | Windows user .claude | Existing lorairo-claude-config at /home/vscode/.claude |
| LoRAIro user config/log | LocalAppData/LoRAIro | Linux XDG config/state volumes |
| Annotator user config/runtime cache/install markers/log | LocalAppData/image-annotator-lib | Linux XDG config/cache/state volumes |
| node_modules/build/test and type caches/coverage | Host checkout | Linux checkout volume |

The old host-mounted .venv remains covered by the same lorairo-venv volume
for compatibility. Both Linux mounts reference that one existing volume.
Windows environments and all existing named volumes are retained.
Project .claude/.codex directories are not covered by home volumes.
Common settings remain readable in each checkout.

## First migration and rebuild

Finish agent work first. Inspect processes and dirty worktrees; preserve any
in-progress work. Never prune/repair a worktree because its other-OS path looks
missing. Existing mixed worktree registrations are retained on the host;
clean them only from their originating OS after verifying their work is saved.

Before replacing the old container, back up and migrate its **Linux** Codex
home. Specify a new, ignored backup directory. The helper creates its leaf with
POSIX mode 0700 and every archive, copied Git config and manifest with mode 0600,
before writing any bytes. On Windows it atomically creates a protected DACL
granting access only to the current user, verifies that ACL before writing, and
refuses storage which cannot enforce it. Existing backup directories/files are
retained and refused; choose a new destination after a partial migration.
The helper freezes
SQLite writers while copying all state, retains an opaque archive, refuses to
overwrite a nonempty destination volume, and verifies credential bytes without
printing them. It never accesses Windows Codex credentials.

~~~powershell
python scripts/migrate_container_codex.py --container <old-container-id> --backup-dir <private-new-directory>
~~~

If the formerly ignored project Codex config contained active sandbox/inherit
preferences, add `--project-config <original-project-config.toml>` before replacing
that file. Only those portable preferences are retained in the Linux user config;
project environment paths and Windows user-home state are never imported. Missing
optional XDG directories or a legacy .gitconfig are treated as empty state.

Back up Linux-only app/XDG state before removing the container too. Do not seed
Linux user settings from Windows absolute paths. Move the host's existing
config/lorairo.toml to the Windows user config only after preserving both files;
the shared file is read-only defaults and should contain portable paths. Legacy
annotator overrides require explicit migration to the corresponding OS user
directory; they are not automatically adopted by another OS.

After the PR is merged, update the host main checkout with git pull --ff-only.
Use **Dev Containers: Rebuild Container** or the installed Dev Containers CLI:

~~~powershell
node <devContainersSpecCLI.js> up --workspace-folder H:/LoRAIro --remove-existing-container
~~~

No volume deletion is required. Initialization imports the host's committed main
into the Linux checkout, never its uncommitted files. An existing dirty Linux
checkout or another checked-out branch causes setup to stop with its work intact.
A divergent main refuses fast-forward; it is never reset. Save/publish that work
before rerunning setup. The startup log is Linux-only:
/home/vscode/.local/state/LoRAIro/postCreate.log.

## Setup and priority

make setup deliberately serializes submodule initialization, dependency sync,
OS user agent configuration, tracked Git hook installation, skill restoration,
and harness restoration. On Windows without Make, run those scripts in that
order. Ordinary scripts/dev_tasks.py commands never synchronize dependencies.

scripts/configure_agent_environment.py merges UV_PROJECT_ENVIRONMENT into
the **current OS user** Codex and Claude settings. It removes that key from
project Codex config and Claude local/project settings, since project settings
override user settings. Changing CODEX_HOME alone is insufficient. Other
preferences are retained, with private backups before migration.

The default environment is this OS checkout's Git common root .venv, also
when configuring from a linked worktree. Windows resolves Scripts/python.exe;
Linux resolves bin/python. Never create worktree or nested package environments.
Existing Linux local_packages/*/.venv on the host are retained but unused.

Skills are projected as ordinary directories rather than OS-specific symlinks
or junctions. Reinstallation checks the projection manifest and preserves user
edits. Tracked .githooks/pre-commit selects the current OS shared interpreter;
core.hooksPath=.githooks prevents a generated Linux hook from replacing the
Windows hook. pre-commit install is unnecessary; rerun the project setup.

LoRAIro config precedence is code defaults < portable project defaults < OS user
settings. Explicit config paths remain supported for isolated tests. Annotator
system catalog/model weights remain project assets; user overrides, runtime
metadata and installation markers are local to the OS. Do not copy caches or
native executables across OS boundaries.

## Verify after rebuild

~~~bash
cd /workspaces/LoRAIro-linux
python scripts/dev_tasks.py lint --dry-run
python -X utf8 scripts/validate_harness.py
git config --local --get core.hooksPath
uv run --no-sync python -c 'import sys; print(sys.executable)'
codex login status
~~~

Repeat setup and confirm the host's settings, venv and worktree registrations
are unchanged. Validate with test data only. Interactive Qt belongs on Windows;
container Qt tests use offscreen. Simultaneous Windows GUI/container CLI
access to a real SQLite database remains unsupported.

The old shared caches and logs were real collision candidates. Site
node_modules was absent at migration, so its issue was prospective. Separate
checkouts isolate future generated files as well as today's caches.

The image installs Node/Codex/Claude as vscode. Their executables are image
state; their user data is volume state. Cached image layers may retain an older
CLI; rebuild without cache only when a CLI update is intended.

References: [Docker read-only bind mounts](https://docs.docker.com/engine/storage/bind-mounts/),
[VS Code source mount configuration](https://code.visualstudio.com/remote/advancedcontainers/change-default-source-mount).
