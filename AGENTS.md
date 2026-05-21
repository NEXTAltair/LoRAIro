# Repository Guidelines

## Project Structure & Module Organization
- `src/lorairo/` holds the main Python package (entry point: `lorairo.main:main`).
- Key subpackages: `config/` (settings), `database/` (SQLAlchemy + Alembic), `gui/` (PySide6 UI), `image/` (image processing), `utils/` (shared helpers).
- `tests/` contains pytest suites and fixtures; `tests/resources/` stores test assets.
- `local_packages/` includes editable submodules used by the app (e.g., `genai-tag-db-tools/`, `image-annotator-lib/`).
- `docs/` contains Sphinx docs; `scripts/` contains dev utilities (e.g., GUI launcher, UI generation).

## Build, Test, and Development Commands
- `uv sync` (or `make install`) installs runtime dependencies.
- `make install-dev` installs dev dependencies and editable package setup.
- `uv run lorairo` or `make run-gui` starts the GUI.
- `make test` runs pytest with repo defaults.
- `make mypy` runs strict type checks against the `lorairo` package.
- `make format` applies Ruff formatting and fixes.
- `make docs` builds Sphinx documentation; `make docs-serve` serves it locally.

## Coding Style & Naming Conventions
- Python 3.12; 4-space indentation; line length 108.
- Ruff is the formatter and linter. Use double quotes and let Ruff handle imports.
- Generated Qt Designer code lives under `*/gui/designer/` and is excluded from linting; avoid manual edits unless necessary.

## Testing Guidelines
- Frameworks: `pytest`, `pytest-qt`, and `pytest-bdd`.
- Naming: files `test_*.py`, classes `Test*`, functions `test_*`.
- Coverage: fails under 75% (`coverage` config in `pyproject.toml`).
- Example: `uv run pytest -m "fast"` to run quick unit tests.

## Diagnostic Log Context
- `logs/lorairo.log` and `logs/image-annotator-lib.log` are intentionally gitignored, but they are first-class debugging context.
- When investigating runtime errors, failed GUI flows, annotation/model issues, worker failures, or test failures that may involve app behavior, inspect these logs proactively even if the user did not attach or mention them.
- Prefer bounded reads such as `tail -200 logs/lorairo.log` and `tail -200 logs/image-annotator-lib.log`; if a file is missing, note that and continue.
- Do not add these logs to git or include large log dumps in responses; summarize only the relevant lines.

## Commit & Pull Request Guidelines
- Commit messages follow Conventional Commits: `feat: ...`, `refactor: ...`, `docs: ...`, `test: ...`, `chore: ...`.
- PRs should include a clear description, test results, and screenshots for GUI changes.
- Link related issues and note any migration or config changes.

## Agent Git Workflow
- Issue resolution, feature work, PR preparation, and any multi-file implementation must start from a dedicated git worktree under `/tmp/worktrees/`.
- Do not edit, stage, commit, rebase, or push from the shared main checkout at `/workspaces/LoRAIro` for implementation work.
- Create worktrees from the current remote base, for example: `git fetch origin && git worktree add /tmp/worktrees/issue-123 -b fix/issue-123 origin/main`.
- Keep agent-specific rules as references to this file and `.claude/rules/git-workflow.md` rather than duplicating conflicting workflow text.

## Codex Parallel Agent Workflow
- For large, multi-issue, multi-PR, or broad refactoring work, Codex should proactively use sub-agents instead of serializing all work in one session.
- Use parallel workers when tasks can be split by issue, module, ownership boundary, or test/verification responsibility.
- Each worker must use its own dedicated git worktree under `/tmp/worktrees/`; do not let multiple workers edit the same worktree.
- Assign each worker a clear branch name and file/module ownership before implementation starts, for example:
  `git worktree add /tmp/worktrees/issue-304 -b fix/issue-304-thumbnail origin/main`.
- Keep worker write scopes disjoint whenever possible. If two workers must touch the same file, the lead agent should sequence those changes or handle that integration directly.
- The lead Codex session is responsible for coordination: defining worker scope, checking for overlapping edits, reviewing diffs, running or confirming tests, creating PRs, and updating parent issue checklists after merge.
- Prefer worker agents for implementation, explorer agents for codebase investigation, test-runner agents for verification, and code-reviewer agents for PR review when those roles can run independently.
- Do not spawn sub-agents for trivial single-file fixes, one-command tasks, or changes where coordination overhead is larger than the work.
- When a parent issue has a checklist of independent sub-issues, treat it as a default candidate for parallel workers and one PR per sub-issue unless the issue text explicitly requests a combined PR.

## Codex tmux Monitoring Workflow
- For large parallel work, Codex may create a `tmux` session to monitor worker progress in split panes.
- Prefer one pane per worker worktree when practical, plus one lead pane for coordination.
- Each worker pane should show the worker name, worktree path, branch, git status, latest commit, and current validation command or log.
- `tmux` monitoring is observational; it does not replace the rule that each worker must use a dedicated `/tmp/worktrees/` checkout.
- Use stable session names tied to the parent issue or branch, for example `codex-308` or `codex-agent-rules`.
- Do not leave required long-running `tmux` sessions active without reporting the session name, active panes, and commands to the user.

## Security & Configuration Tips
- Store API keys in a local `.env` (see `.env.example`). Never commit secrets.
- Keep local data and logs out of version control (`logs/`, `lorairo_data/`).
