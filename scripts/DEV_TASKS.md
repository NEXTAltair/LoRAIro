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
`install`. New worktrees should initialize their submodule checkouts, but must not
run install/install-dev or create their own `.venv`.

## Environment safety

The default environment is `.venv` in the main checkout found through Git, not a
hardcoded `/workspaces` path. `UV_PROJECT_ENVIRONMENT`, if set, must be an absolute
path to that same environment. An old Linux value in Windows is rejected. Correct
the setting at its source; do not create a directory at the stale path to satisfy it.

Normal tasks check the installed interpreter and use `uv run --no-sync`. Missing
dependencies must be installed explicitly, not during a test. The active worktree's
source directories override shared editable-install paths using `PYTHONPATH`.
The three packages retain separate pytest processes, working directories and coverage.

Test tasks select Qt `offscreen`; Windows GUI runs do not acquire that setting from
this runner. Real model and paid API tests remain explicit `test-runtime-local` and
`test-runtime-webapi` tasks; they are not part of normal `test-all`.

## Not migrated here

UI generation, documentation/ADR utilities, `clean`, `venv-rebuild` and worktree
cleanup still use their existing implementations. Do not assume those targets are
Windows-safe. No kit hooks, Codex config, stored API keys, existing venvs or volumes
are modified by this migration.
