# Python quality commands

Ruff owns formatting, lint and McCabe complexity checks. The explicit `C4` and
`C90` selectors retain the previous broad `C` selection; the existing default
complexity threshold (10) and migration exclusions are unchanged. Radon/Lizard
are no longer dev dependencies. This does not reproduce their separate metrics
reports; the supported replacement is Ruff's `C901` diagnostic.

With the shared project environment configured and dependencies installed:

```text
uv run --no-sync ruff check src/ tests/ --no-fix
uv run --no-sync ruff format src/ tests/ --check
```

These commands work in Windows and Linux shells. `make lint` is an alias for the
same two commands where Make is installed. Checks do not fix files. Automatic
formatting remains available through `make format`, editor save actions and the
existing pre-commit formatter; those paths explicitly request formatting/fixes.

Use the main checkout's actual shared environment when invoking commands from
a worktree. The remaining Makefile tasks still contain Linux-specific paths and
shell constructs; this change does not claim full Makefile portability. Do not
run `clean` or `venv-rebuild` as part of verification. Shared-environment routing
and safe cleanup are separate follow-up work, independent of the agent-kit.

References:

- https://docs.astral.sh/ruff/rules/complex-structure/
- https://docs.astral.sh/ruff/settings/#fix
