# Portable development tasks

Windows PowerShell and Linux can use the same entrypoint (Python 3.12+):

```text
python scripts/dev_tasks.py test
python scripts/dev_tasks.py test-all
python scripts/dev_tasks.py lint
python scripts/dev_tasks.py format
python scripts/dev_tasks.py run-gui
python scripts/dev_tasks.py test-all --dry-run
```

`make test`, `make lint`, and the other migrated targets delegate to this script.
On Linux without a `python` alias, use `python3`. Make chooses the appropriate
default; `make PYTHON=...` can override it.

## One-time setup / dependency changes

From the **main shared checkout**, initialize submodules and install the workspace:

```text
git submodule update --init --recursive
python scripts/dev_tasks.py install-dev
```

This is an explicit shared environment write. Stop other tasks using that environment
while synchronizing. `make setup` additionally restores external agent skills as
before; skill-lock failures are not bypassed here. Runtime-only installation uses
`install`. New worktrees should initialize the submodules needed by their tasks,
but must not run install/install-dev or create their own `.venv`.

## Task requirements

The `TASKS` registry in `dev_tasks.py` is the source of prerequisite declarations.
Command selection does not grant additional prerequisites or permission to sync.

| Tasks | Interpreter / tools | Required local package checkouts |
| --- | --- | --- |
| `adr-drift`, `adr-index`, `adr-okf`, `docs-okf` | Launcher Python, standard library only | None; `docs-okf` also checks package docs when present |
| `lint`, `format`, `generate-ui` | Installed shared Python with Ruff / PySide6 | None |
| `format-iam-lib`, `format-genai-tag` | Installed shared Python with Ruff | Only the named package |
| `test-iam-lib`, `test-genai-tag` | Installed shared Python with test dependencies | Only the named package |
| `test-runtime-local`, `test-runtime-webapi` | Installed shared Python with IAM/runtime dependencies | image-annotator-lib only; WebAPI also reads LoRAIro config |
| `test`, `test-all`, `mypy`, `run-gui` | Installed shared Python with app/test/type dependencies | Both packages |
| `install`, `install-dev` | uv; existing shared Python is not required | Both packages, main checkout only |

Document tasks work without `.git`, `.venv`, uv, or initialized submodules, even
when `UV_PROJECT_ENVIRONMENT` contains an obsolete path. `adr-drift` uses Git
history when available and otherwise retains its existing limited fallback.
Other tasks use Git to locate the shared environment. Missing required submodules
are an error, never an implicit fetch; unrelated submodules are not inspected.

Only install tasks synchronize the shared environment. This does **not** mean all
other tasks are read-only: format and UI/index generation write their outputs,
tests write caches and fixtures, and explicit runtime tests can download models
or make paid API calls. The registry controls prerequisites, not an OS sandbox.

## Environment safety

The default environment is `.venv` in the main checkout found through Git, not a
hardcoded `/workspaces` path. `UV_PROJECT_ENVIRONMENT`, if set, must be an absolute
path to that same environment. An old Linux value in Windows is rejected. Correct
the setting at its source; do not create a directory at the stale path to satisfy it.

Shared-runtime tasks check the installed interpreter and execute it directly,
without invoking uv or discovering a project environment. Missing dependencies
must be installed explicitly, not during a test. For tasks importing application
code, the active worktree's required source directories override shared editable
install paths using `PYTHONPATH`. `VIRTUAL_ENV` and the command's `PATH` select the
same shared environment for child tools. Static tools do not inject app sources.
The three packages retain separate pytest processes, working directories and coverage.

Test tasks select Qt `offscreen`; Windows GUI runs do not acquire that setting from
this runner. Real model and paid API tests remain explicit `test-runtime-local` and
`test-runtime-webapi` tasks; they are not part of normal `test-all`.

## UI, ADR and cleanup

`generate-ui`, `adr-drift`, `adr-index`, `adr-okf` and `docs-okf` use the same
portable runner. Existing `.ui` generation remains available without Qt Designer
editing tools. UIC runs under the selected interpreter, without a shell or extra sync.

Preview maintenance before applying it:

```text
python scripts/safe_cleanup.py clean --dry-run
python scripts/safe_cleanup.py venv-rebuild --dry-run
```

Omit `--dry-run` to execute, or use `make clean` / `make venv-rebuild`.
Clean only removes named root build outputs and Python caches beneath `src`,
`tests`, and `scripts`. It never traverses nested repositories, environments,
links/junctions, data directories or worktrees. Removed caches are regenerable,
but not backed up. Local package caches are intentionally left alone.

Rebuild must run from the main checkout using a **system Python**. Stop other
environment users first. The old `.venv` is renamed to `.venv.backup-<unique ID>`
before explicit `install-dev`; the backup is kept even if installation fails.
No automatic deletion or rollback is performed. Inspect the printed backup path
and recover it manually if needed; do not run rebuild concurrently with other tasks.

Worktree cleanup remains owned by the separate kit effort. No kit hooks or Codex
configuration are changed here.
