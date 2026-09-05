---
type: Guide
title: Development and headless tests
description: Separate Windows execution, container development and shared Python environments.
sidebar:
  order: 10
---

## Roles of Windows and containers

Edit code in a Dev Container and run the GUI on Windows. The container does not display the GUI; tests run with Qt offscreen. Windows and Linux do not share the same physical `.venv`. Within each OS, main and worktrees share that OS's environment.

## Install development dependencies

Run in the main shared checkout. Python, Git and uv are required.

```powershell
git submodule update --init --recursive
python scripts/dev_tasks.py install-dev
```

Use `python3` on Linux if `python` is unavailable. This updates the shared environment, so run it only when other apps, tests and agents are not using it. Kit installation and configuration are managed separately.

## Routine development commands

```powershell
python scripts/dev_tasks.py test
python scripts/dev_tasks.py test-all
python scripts/dev_tasks.py lint
python scripts/dev_tasks.py format
python scripts/dev_tasks.py test-all --dry-run
```

`test` runs LoRAIro tests. `test-all` runs three packages in separate test processes, sequentially. BDD continues to use pytest-bdd. `lint` is read-only; `format` applies Ruff formatting and fixes. Routine tasks do not automatically synchronize dependencies.

`test-runtime-local` runs real GPU models and `test-runtime-webapi` calls APIs that may incur charges. Both require explicit execution and are not included in routine `test-all`.

## Worktrees

Do not create a separate `.venv` in a worktree. Shared commands use Git to locate the main environment and run the target worktree's source. If `UV_PROJECT_ENVIRONMENT` is set, it must match the absolute path of that environment's main shared `.venv`.

When opening a worktree directly in VS Code, use Python: Select Interpreter to select the main shared interpreter. Do not use offscreen when launching the Windows GUI.

See the [development task documentation](https://github.com/NEXTAltair/LoRAIro/blob/main/scripts/DEV_TASKS.md) for command contracts.
