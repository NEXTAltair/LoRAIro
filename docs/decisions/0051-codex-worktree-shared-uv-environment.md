---
type: ADR
title: Codex Worktree Shared uv Environment
status: Accepted (amended 2026-10-11: OS user settings and independent Linux checkout)
timestamp: 2026-06-01
tags: []
---
# ADR 0051: Codex Worktree Shared uv Environment

## Context

LoRAIro agents implement issue work in dedicated git worktrees under `.agents/worktree/`.
Creating a separate `.venv` in each worktree is too expensive for this repository because
dependency installation and model/cache downloads can consume substantial time and disk space.

The repository already standardizes on reusing `/workspaces/LoRAIro/.venv` from worktrees via
`UV_PROJECT_ENVIRONMENT`. However, passing
`UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv uv ...` in every Codex command changes the command
shape that Codex approval rules see, which creates avoidable approval friction. A shared virtual
environment also remains mutable state, so verification must avoid accidentally using the wrong
checkout's editable install.

Claude Code behavior is being validated separately. This decision records the Codex-side rule only.

## Decision

Codex sessions set `UV_PROJECT_ENVIRONMENT` once in the **current OS user** Codex shell environment
policy, then run normal commands such as `uv run pytest ...` from the target worktree. Shared project
config must not contain OS-specific values because it overrides user config. The setup helper
removes legacy project overrides and merges the selected venv into OS user settings.
Codex should not prefix every command with `UV_PROJECT_ENVIRONMENT=...` unless the shell environment
policy is unavailable. Because default `uv run` may sync the shared environment, it is only the
normal shape for single-agent commands where environment mutation is acceptable or intentionally
serialized.

`/workspaces/LoRAIro-linux/.venv` is the canonical independent Linux checkout path. It mounts the
existing `lorairo-venv` volume; the old `/workspaces/LoRAIro/.venv` mount remains a compatibility
alias. Windows uses its host checkout `.venv`. If a different runtime
mounts the repository elsewhere, the Codex environment must point at that runtime's existing shared
LoRAIro `.venv`; it must not let `uv` create a new virtual environment at a stale or nonexistent
path.

Worktree-local `.venv` directories and symlinks must not be created. Configure the environment
explicitly; a package-manager Python-version mismatch can delete/recreate a symlink target.

For read-only verification or CLI smoke tests where the executed checkout must be unambiguous,
Codex must run from the target worktree with `uv run --no-sync` and set an explicit `PYTHONPATH`
that points at that worktree's `src` and local package `src` directories. `uv run --no-sync`
prevents environment syncing, while `PYTHONPATH` pins imports to the target worktree.

Environment-mutating `uv` operations such as `uv sync`, dependency updates, and lockfile changes
must not run concurrently against the shared `.venv`. Default-sync `uv run` is also treated as an
environment-mutating operation for parallel worker coordination.

## Consequences

- Codex commands keep their normal shape (`uv run ...`), reducing repeated approval friction.
- Worktrees avoid duplicate virtual environments and duplicate heavy dependency/model downloads.
- The shared `.venv` remains mutable state, so smoke tests that prove a worktree change may need
  `PYTHONPATH` to pin the executed code and `--no-sync` to avoid changing the environment.
- Parallel Codex workers can still share the `.venv`, but default-sync `uv run` and `uv sync`
  operations must be serialized.
- Worktree-local `.venv` symlinks are prohibited.
- Linux Git metadata/source/generated files live in an independent named-volume checkout. The
  host bind mount is read-only. Home volumes alone would leave branch/index/worktree conflicts.
- Claude Code-specific behavior can be documented separately without coupling it to Codex policy.
