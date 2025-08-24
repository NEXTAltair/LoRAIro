# Archived Tasks Plan — Docs/Rules Cleanup (2025-08-12)

**原ファイル**: `tasks/tasks_plan.md`
**移行日**: 2025-08-24
**状況**: 完了済みプランのアーカイブ

## 当時のObjective
Unify and clean existing documentation and rule files to reflect the current codebase.

## 当時のScope
- docs: `architecture.md`, `technical.md`, `product_requirement_docs.md`, `specs/*`
- rules: `.cursor/rules/*`, fetched workspace rules

## 計画されていたWork Items

### Phase 1 (Quick consistency fixes) ✅ 完了
1. Technical spec Python version → 3.12+ (align with README)
2. Architecture: add note that `MainWorkspaceWindow` in docs refers to current `MainWindow` implementation

### Phase 2 (Architecture alignment) ✅ 完了
3. Update GUI architecture section and diagrams to reference `src/lorairo/gui/window/main_window.py`
4. Verify worker class/file names and adjust wording: `annotation_worker.py`, `manager.py`, `base.py`

### Phase 3 (Deep cleanup) ✅ 完了 + 🔄 MCP統合で刷新
5. Remove or mark legacy/transition paragraphs that conflict with current implementation
6. Link rules (logging, database) from docs; ensure paths and names match
7. Add deprecations list and dead-code note reference
8. Document MCP usage (cipher/serena) in `docs/technical.md` and `docs/architecture.md` (serena memory path: `.serena/memories/`)

## Acceptance Criteria達成状況
- ✅ No conflicting Python version statements remain
- ✅ Docs consistently reference `MainWindow`
- ✅ GUI/Worker diagrams match file/class names
- ✅ Obsolete references are marked or removed
- 🔄 MCP Serena統合により管理方式を刷新

## 現在の進化 (2025-08-24)
**Context Migration**: MCP Serena統合により、以下の新しい管理方式に移行:
- active_context.md/tasks_plan.md → Serena memory
- 文書管理から実装知識管理へシフト
- 動的な開発コンテキスト管理

## 教訓
- 段階的クリーンアップアプローチの有効性
- ドキュメント一貫性の重要性
- MCP統合による管理方式進化の必要性