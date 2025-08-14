# Active Context — Docs/Rules Cleanup

Date: 2025-08-12

## Focus
- Documentation and rules cleanup (remove stale info, unify terminology and versions).

## Why now
- Naming mismatch in docs vs code: `MainWorkspaceWindow` (docs) vs `MainWindow` (code).
- Python version inconsistency: README 3.12+, technical.md 3.11+.
- Legacy/transition references remain in architecture text.
- Core task docs (`tasks/active_context.md`, `tasks/tasks_plan.md`) were missing.

## Decisions
- Standardize required Python to 3.12+ in docs.
- Treat `MainWorkspaceWindow` mentions as the same concept as `MainWindow`; add note in architecture and migrate wording gradually.
- Stage edits: low-risk text fixes first; deeper diagram and section rewrites next.

## Next 48h
- Phase 1 (today):
  - Create this file and `tasks/tasks_plan.md` (done).
  - Fix Python version in `docs/technical.md`.
  - Add naming note to `docs/architecture.md`.
- Phase 2:
  - Align GUI section/diagrams to `MainWindow` and actual file paths.
  - Verify worker file/class names in docs match `src/lorairo/gui/workers/`.
- Phase 3:
  - Sweep outdated references and broken links in rules/docs.
  - Add deprecations list and mark legacy items.

## Risks/Impact
- Low risk textual changes; larger diagram rewrites deferred to Phase 2.

## Done today
- Initialized active context and plan.

