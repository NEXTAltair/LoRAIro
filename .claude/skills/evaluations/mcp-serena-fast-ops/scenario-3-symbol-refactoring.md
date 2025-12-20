# Scenario: Multi-Symbol Refactoring

## Input
**User request:** "I need to rename the method `get_by_hash` to `find_by_phash` across all repository classes. Find all occurrences and update them while preserving functionality."

**Context:**
- Codebase: LoRAIro project
- Multiple repository files in `src/lorairo/database/repositories/`
- Method exists in: ImageRepository, TagRepository, potentially others
- Need to:
  1. Find all `get_by_hash` method definitions
  2. Find all references (callers)
  3. Rename consistently across codebase

## Expected Behavior
1. Skill `mcp-serena-fast-ops` should be invoked automatically
2. Should use tools (in sequence):
   - `mcp__serena__search_for_pattern` or `mcp__serena__find_symbol` to locate method definitions
   - `mcp__serena__find_referencing_symbols` to find all callers
   - `mcp__serena__rename_symbol` (if available) OR `mcp__serena__replace_symbol_body` for each occurrence
3. Should produce:
   - List of all files/symbols to be updated
   - Confirmation before making changes (if interactive)
   - Consistent renaming across all occurrences
4. Should NOT:
   - Use generic text replacement (dangerous for partial matches)
   - Miss references in test files
   - Break functionality by inconsistent renaming

## Success Criteria
- [x] Correct skill invoked (mcp-serena-fast-ops)
- [x] Tools used efficiently (semantic search and refactoring tools)
- [x] Output meets requirements (all occurrences found and renamed)
- [x] Completes without errors
- [x] Functionality preserved (no broken references)
- [x] Tests still pass after refactoring

## Model Variations
- **Haiku:** May need explicit guidance to search for both definitions AND references; should handle basic renaming
- **Sonnet:** Should handle full workflow correctly; finds definitions, references, and renames consistently
- **Opus:** May proactively check for related patterns (e.g., similar method names in other contexts); may suggest running tests after refactoring

## Test Validation
After running this scenario:
1. Verify skill invoked: Check `mcp-serena-fast-ops` in metadata
2. Check tool usage sequence:
   - Symbol search: `find_symbol` or `search_for_pattern`
   - Reference finding: `find_referencing_symbols`
   - Renaming: `rename_symbol` or `replace_symbol_body`
3. Verify all occurrences renamed:
   ```bash
   grep -r "get_by_hash" src/lorairo/database/repositories/
   grep -r "find_by_phash" src/lorairo/database/repositories/
   ```
4. Run tests to verify functionality preserved:
   ```bash
   uv run pytest tests/unit/database/repositories/
   ```
5. Check consistency: All method definitions and references should use new name

## Edge Cases to Test
- Method exists in multiple classes (all should be renamed)
- Method has similar names (e.g., `get_by_hash_value` should NOT be renamed)
- References in test files (should also be updated)
- Docstrings mentioning method name (ideally updated, but not critical)
