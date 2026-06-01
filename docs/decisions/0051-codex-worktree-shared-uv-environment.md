# 0051. Codex worktree shared uv environment

## Status

Accepted

## Context

LoRAIro agents implement issue work in dedicated git worktrees under `/tmp/worktrees/`.
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

Codex sessions must set `UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv` once in the Codex shell
environment policy, then run normal commands such as `uv run pytest ...` from the target worktree.
Codex should not prefix every command with `UV_PROJECT_ENVIRONMENT=...` unless the shell environment
policy is unavailable. Because default `uv run` may sync the shared environment, it is only the
normal shape for single-agent commands where environment mutation is acceptable or intentionally
serialized.

`/workspaces/LoRAIro/.venv` is the canonical LoRAIro devcontainer path. If a different runtime
mounts the repository elsewhere, the Codex environment must point at that runtime's existing shared
LoRAIro `.venv`; it must not let `uv` create a new virtual environment at a stale or nonexistent
path.

Worktree-local `.venv` directories must not be created for normal Codex work. A `.venv` symlink to
`/workspaces/LoRAIro/.venv` is acceptable only as a fallback when the agent environment cannot set
`UV_PROJECT_ENVIRONMENT`; it must be treated as shared mutable state rather than an isolated
environment.

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
- `.venv` symlinks remain an emergency fallback, not the default worktree setup.
- Claude Code-specific behavior can be documented separately without coupling it to Codex policy.
