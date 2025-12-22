# Scenario: Memory Management Workflow

## Input
**User request:** "I just finished implementing the new TagRepository. Save this as a completed task in project memory, and note that we're using the same transaction pattern as ImageRepository."

**Context:**
- Codebase: LoRAIro project
- User has completed implementation work
- Need to record completion + design decision in Serena memory
- Memory file: Should update or create `implementation-tag-repository.md`

## Expected Behavior
1. Skill `mcp-serena-fast-ops` should be invoked automatically
2. Should use tools:
   - `mcp__serena__list_memories` to check existing memory files
   - `mcp__serena__read_memory` (if file exists) to read current content
   - `mcp__serena__write_memory` or `mcp__serena__edit_memory` to record completion
3. Should produce: Updated memory file with:
   - Task completion status
   - Design decision (transaction pattern reused)
   - Timestamp or session context
4. Should NOT:
   - Create duplicate memory files
   - Overwrite unrelated memory content
   - Use generic Write tool instead of memory operations

## Success Criteria
- [x] Correct skill invoked (mcp-serena-fast-ops)
- [x] Tools used efficiently (memory operations, not generic file I/O)
- [x] Output meets requirements (completion recorded, design decision noted)
- [x] Completes without errors
- [x] Memory file is well-structured and readable

## Model Variations
- **Haiku:** Should handle basic memory write; may need guidance on memory file naming conventions
- **Sonnet:** Should handle memory workflow correctly; good naming and structure
- **Opus:** May proactively suggest related memories to update (e.g., repository pattern knowledge); may recommend Cipher memory for long-term knowledge

## Test Validation
After running this scenario:
1. Verify skill invoked: Check `mcp-serena-fast-ops` in response metadata
2. Check tool usage: Should see memory operations (`write_memory` or `edit_memory`)
3. Read memory file: Verify content includes completion status and design decision
4. Check file naming: Should follow project conventions (e.g., `implementation-tag-repository`)
5. Verify no duplicate files created
