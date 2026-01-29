# LoRAIro Development Standards (Cipher統合記録)

**移行元**: Cipher長期記憶 (2026-01-28にSerenaへ移行)

---

## Core Principles
1. Do what has been asked; nothing more, nothing less
2. NEVER create files unless absolutely necessary
3. ALWAYS prefer editing existing files
4. YAGNI, Readability First, Single Responsibility

## Code Style
- Ruff: line-length 108, double quotes, 4 spaces
- Modern Python: list[str] (not List[str]), str | None (not Optional)
- Strict mypy, No type:ignore/noqa
- Specific nouns for class names (ModelLoad not Loader)
- Half-width characters only

## Error Handling
- Catch specific errors only
- logger.error(..., exc_info=True) for tracebacks
- Unrecoverable → raise, Recoverable → INFO/WARNING

## Architecture Patterns
- Repository Pattern: DB access through repository layer
- Service Layer: Business logic separated from GUI
- Worker Pattern: Qt QRunnable/QThreadPool for async
- State Management: DatasetStateManager (centralized)
- Dependency Injection: ServiceContainer

## MCP Role Division (旧方式 - Cipher移行前)
- **serena**: Code reading, summarization, plan drafting
- **cipher**: Implementation, command execution, external MCP calls
- Workflow: PLAN (serena) → ACT (cipher)
- NOTE: Cipher→Moltbot移行に伴い、この役割分担は変更予定
