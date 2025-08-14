# Tasks Plan — Docs/Rules Cleanup

Date: 2025-08-12

## Objective
Unify and clean existing documentation and rule files to reflect the current codebase.

## Scope
- docs: `architecture.md`, `technical.md`, `product_requirement_docs.md`, `specs/*`
- rules: `.cursor/rules/*`, fetched workspace rules

## Work Items

### Phase 1 (Quick consistency fixes)
1. Technical spec Python version → 3.12+ (align with README)
2. Architecture: add note that `MainWorkspaceWindow` in docs refers to current `MainWindow` implementation

### Phase 2 (Architecture alignment)
3. Update GUI architecture section and diagrams to reference `src/lorairo/gui/window/main_window.py`
4. Verify worker class/file names and adjust wording: `annotation_worker.py`, `manager.py`, `base.py`

### Phase 3 (Deep cleanup)
5. Remove or mark legacy/transition paragraphs that conflict with current implementation
6. Link rules (logging, database) from docs; ensure paths and names match
7. Add deprecations list and dead-code note reference
8. Document MCP usage (cipher/serena) in `docs/technical.md` and `docs/architecture.md` (serena memory path: `.serena/memories/`)

## Acceptance Criteria
- No conflicting Python version statements remain
- Docs consistently reference `MainWindow`
- GUI/Worker diagrams match file/class names
- Obsolete references are marked or removed

## Tracking
- Owner: project maintainers
- Status: Phase 1 started
