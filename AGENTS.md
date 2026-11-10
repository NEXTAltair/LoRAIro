# Repository Guidelines

## Project Structure & Module Organization
- `src/lorairo/` holds the main Python package (entry point: `lorairo.main:main`).
- Key subpackages: `config/` (settings), `database/` (SQLAlchemy + Alembic), `gui/` (PySide6 UI), `image/` (image processing), `utils/` (shared helpers).
- `tests/` contains pytest suites and fixtures; `tests/resources/` stores test assets.
- `local_packages/` includes editable submodules used by the app (e.g., `genai-tag-db-tools/`, `image-annotator-lib/`).
- `docs/` contains developer references and ADRs; `site/` contains the multilingual Starlight user guide.
- `scripts/` contains portable dev utilities (GUI launcher, UI generation, tests).

## Build, Test, and Development Commands
- `uv sync` (or `make install`) installs runtime dependencies.
- `make install-dev` installs dev dependencies and editable package setup.
- `uv run --no-sync lorairo` or `make run-gui` starts the GUI on Windows; container tests are headless.
- `make test` runs pytest with repo defaults.
- `make mypy` runs strict type checks against the `lorairo` package.
- `make format` applies Ruff formatting and fixes.
- From `site/`, `npm ci` installs documentation dependencies, `npm run build` validates translations and builds
  the user guide, and `npm run preview` serves the build. See `site/README.md` for Japanese-first authoring.

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
- `src/lorairo/utils/config.py` sets `DEFAULT_LOG_PATH = user_log_path("LoRAIro", appauthor=False) / "lorairo.log"` via `platformdirs`:
  - Windows: `%LOCALAPPDATA%\LoRAIro\Logs\lorairo.log`
  - Linux / Dev Container: `~/.local/state/LoRAIro/log/lorairo.log` (alongside gitignored workspace `logs/lorairo.log` and `logs/image-annotator-lib.log`).
- These logs are first-class debugging context. When investigating runtime errors, failed GUI flows, annotation/model issues, worker failures, or test failures that may involve app behavior, inspect these logs proactively even if the user did not attach or mention them.
- Prefer bounded reads such as `tail -200 ~/.local/state/LoRAIro/log/lorairo.log`, `tail -200 logs/lorairo.log`, and `tail -200 logs/image-annotator-lib.log`; if a file is missing, note that and continue.
- Do not add these logs to git or include large log dumps in responses; summarize only the relevant lines.

## Commit & Pull Request Guidelines
- Commit messages follow Conventional Commits: `feat: ...`, `refactor: ...`, `docs: ...`, `test: ...`, `chore: ...`.
- PRs should include a clear description, test results, and screenshots for GUI changes.
- Link related issues and note any migration or config changes.

## LoRAIro Skills
Repository-specific skills live in `.agents/skills/` (tracked); `.claude/skills/<name>` links to them.
External skills (kit / third-party, e.g. `check-existing`, `pr-maintainer`, `pr-autoloop`) are untracked
and restored from `skills-lock.json` by `make setup` / `make skills-install`. Read the skill's `SKILL.md`
before starting the matching task; the skill holds the steps, safety constraints and verification.
See [`docs/development/agent-skills-guide.md`](docs/development/agent-skills-guide.md) for the full 32-skill
inventory, overlap resolution rules, workflow-by-workflow minimal checklists, and verified walkthroughs.

| Task | Skill | Key constraint |
|---|---|---|
| Read or edit the image DB (images, tags, annotations, errors) | `lorairo-cli-db-access` | Use `lorairo-cli`, never raw `sqlite3` against `lorairo_data/*` (9p mount + WAL) |
| New repository / persistence code | `lorairo-repository-pattern` | Typed transactions via `src/lorairo/database/repository/` (`BaseRepository`) |
| New or slow queries, N+1 review | `sqlalchemy-query-patterns` | Batch lookups (`selectinload`); check with EXPLAIN |
| PySide6 widget / worker / Qt Designer work | `lorairo-qt-widget` | `LoRAIroWorkerBase` (QObject + `moveToThread`); regenerate UI with `scripts/generate_ui.py` |
| UI design intent before Qt work | `interface-design` | Define intent/tokens (`src/lorairo/gui/theme.py`), then implement with `lorairo-qt-widget` |
| Sync app layout with the wireframes / claude.ai design | `lorairo-design-capture` | Capture the render-time state, not static HTML |
| Write tests | `lorairo-test-generator` | Mock `QMessageBox`; `qtbot.waitUntil`, no fixed waits |
| Add or edit ADRs / concept docs | `okf-bundle` | Frontmatter is the SSoT; regenerate the index (`make adr-index`) |
| Scope a feature (reuse vs build) | `check-existing` (external) | Check `local_packages/` first |
| Maintain an agent-created PR | `pr-maintainer` / `pr-autoloop` (external) | See "Agent Git Workflow" below |

**Skill Priority & Overlap Rules:**
- **Tracked LoRAIro skills first**: When a tracked skill in `.agents/skills/` overlaps with a generic external skill in `skills-lock.json`, always follow the LoRAIro skill (`lorairo-repository-pattern` + `sqlalchemy-query-patterns` over `sql-optimization-patterns` / `database-migration`; `lorairo-test-generator` over `python-testing-patterns` / `qa-expert`).
- **GUI workflow order**: Follow `interface-design` (intent/tokens) → `lorairo-design-capture` (render-time prototype state) → `lorairo-qt-widget` (PySide6 implementation). Do not apply React/Vercel external skills (`vercel-*`, `deploy-to-vercel`) to Python/Qt code; `web-design-guidelines` applies only to the `site/` Starlight web guide.

## Agent Git Workflow
- Issue resolution, feature work, PR preparation, and any multi-file implementation must start from a dedicated git worktree under `.agents/worktree/`.
- Do not edit, stage, commit, rebase, or push from the shared main checkout at `/workspaces/LoRAIro` for implementation work.
- Create worktrees from the current remote base, for example: `git fetch origin && git worktree add .agents/worktree/issue-123 -b fix/issue-123 origin/main`.
- For issue resolution or feature implementation, completion means: implement, validate, commit, push, open a ready-for-review PR, run PR maintenance automation through CI/review, and merge when safe, unless the user explicitly asks to stop before publishing or keep the PR as draft.
- Do not end issue or multi-file feature work after local implementation only. Report the PR URL and final monitored state as the outcome.
- If PR creation is blocked by auth, network, failing validation, or unclear scope, report the blocker explicitly instead of silently stopping at local changes.
- When running `uv` from a `.agents/worktree/` checkout, use this OS checkout's Git common root `.venv`.
  Windows uses the host checkout `.venv`; the Dev Container bind-mounts the same host checkout
  read-write at `/workspaces/LoRAIro` and uses `/workspaces/LoRAIro/.venv` (the existing
  `lorairo-venv` named volume mounted over the host `.venv`).
  Run `python scripts/configure_agent_environment.py` to set `UV_PROJECT_ENVIRONMENT` in the current
  OS **user** Codex config and Claude settings. Do not put OS-specific absolute paths in shared
  `.codex/config.toml`, `.claude/settings.json`, or `.claude/settings.local.json`. Project settings
  override user settings, so changing `CODEX_HOME` or adding a home volume alone does not fix them.
  This repository overrides kit guidance examples that place venv paths in project settings.
  If the shared environment is missing, stop and configure the actual OS environment rather than
  letting `uv` create a new one at a stale path.
  Do not prefix every Codex command with `UV_PROJECT_ENVIRONMENT=...`; it creates unnecessary command-approval friction and hides the normal command shape.
  In shells where that environment is not configured, explicitly set `UV_PROJECT_ENVIRONMENT` to
  this OS checkout's shared `.venv` for the command. This inline argument is the only fallback.
  Do not create a worktree-local `.venv`, and do not symlink a worktree `.venv` to the shared one. A worktree `.venv` (real or symlinked) only adds risk: `uv` can delete-and-recreate it on a Python-version mismatch and corrupt the shared environment, and it leaves residue to clean up. If the shared environment cannot be used, only a bare `uv` help/inspection command is allowed without `UV_PROJECT_ENVIRONMENT`.
  Run verification commands from the target worktree. For CLI smoke tests, read-only checks, or parallel worker verification, use `uv run --no-sync` plus an explicit `PYTHONPATH` pointing at the target worktree `src` and local package `src` directories when editable-install ambiguity matters.
  Treat default-sync `uv run`, `uv sync`, dependency updates, and other environment-mutating `uv` operations as shared `.venv` writes; do not run them concurrently across workers, and sequence them deliberately.
- Agent-created PRs should normally be created ready for review, not draft. When a draft PR exists because the user explicitly asked to keep it draft, mark it ready for review as soon as the user allows review, then immediately start or resume PR maintenance automation: poll CI, watch bot review artifacts/comments, repair actionable findings in the PR worktree, reply in Japanese, merge when safe, and report the final monitored state.
- After creating an agent PR, explicitly verify `gh pr view "$PR" --json isDraft -q .isDraft`. If it is
  `true`, run `gh pr ready "$PR"` and re-check. Do not set up `gh pr merge --auto` while the PR is still draft.
- After an agent-created PR is merged, immediately remove the clean worktree with `git worktree remove <path>` or run `make worktree-cleanup-merged` from the shared checkout. Do not leave merged worktrees behind.
- **`pr-autoloop` の Codex 実装 (wait mechanism override):** the shared PR maintenance loop is described by the `pr-autoloop` skill (policy in `pr-maintainer`, decision in ADR 0039). Codex runs that loop **inline in the same session**: after creating the PR, poll `gh pr view` / `gh pr checks` about every 3 minutes for up to 20 minutes, classify each cycle into continue / repair / escalate / merge / timeout, repair actionable findings in the PR worktree, reply in Japanese, and squash merge when safe. Codex does not use Claude Code's `ScheduleWakeup`; it polls within the session and reports the final monitored state, escalating instead of looping past the 4-repair limit.
- Keep agent-specific rules as references to this file and `.claude/rules/git-workflow.md` rather than duplicating conflicting workflow text.
- Windows and the Dev Container share one checkout, so worktrees created on one OS are registered
  with absolute paths the other OS cannot resolve (`git worktree list` shows them as `prunable`).
  Never prune/repair/remove another OS's worktree because its absolute path appears missing.
  Clean up only on its originating OS after checking local changes.
- Setup restores common hooks, rules, agents and skills in both checkouts. Skills are portable
  directory copies; `core.hooksPath=.githooks` selects shared hooks with the current OS interpreter.
  Do not run `pre-commit install` to generate a hook with one OS's Python path.

## Codex Parallel Agent Workflow
- For large, multi-issue, multi-PR, or broad refactoring work, Codex should proactively use sub-agents instead of serializing all work in one session.
- Use parallel workers when tasks can be split by issue, module, ownership boundary, or test/verification responsibility.
- Each worker must use its own dedicated git worktree under `.agents/worktree/`; do not let multiple workers edit the same worktree.
- Assign each worker a clear branch name and file/module ownership before implementation starts, for example:
  `git worktree add .agents/worktree/issue-304 -b fix/issue-304-thumbnail origin/main`.
- Keep worker write scopes disjoint whenever possible. If two workers must touch the same file, the lead agent should sequence those changes or handle that integration directly.
- The lead Codex session is responsible for coordination: defining worker scope, checking for overlapping edits, reviewing diffs, running or confirming tests, creating PRs, and updating parent issue checklists after merge.
- Prefer worker agents for implementation, explorer agents for codebase investigation, test-runner agents for verification, and code-reviewer agents for PR review when those roles can run independently.
- Do not spawn sub-agents for trivial single-file fixes, one-command tasks, or changes where coordination overhead is larger than the work.
- When a parent issue has a checklist of independent sub-issues, treat it as a default candidate for parallel workers and one PR per sub-issue unless the issue text explicitly requests a combined PR.

## Codex tmux Monitoring Workflow
- For large parallel work, Codex may create a `tmux` session to monitor worker progress in split panes.
- Prefer one pane per worker worktree when practical, plus one lead pane for coordination.
- Each worker pane should show the worker name, worktree path, branch, git status, latest commit, and current validation command or log.
- `tmux` monitoring is observational; it does not replace the rule that each worker must use a dedicated `.agents/worktree/` checkout.
- Use stable session names tied to the parent issue or branch, for example `codex-308` or `codex-agent-rules`.
- Do not leave required long-running `tmux` sessions active without reporting the session name, active panes, and commands to the user.

## Security & Configuration Tips
- Store API keys in a local `.env` (see `.env.example`). Never commit secrets.
- Keep local data and logs out of version control (`logs/`, `lorairo_data/`).
