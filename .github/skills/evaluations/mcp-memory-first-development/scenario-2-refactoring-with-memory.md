# Scenario: Refactoring with Memory Recording

## Input
**User request:** "I'm refactoring the DatabaseRepository base class to add connection pooling. Document this architectural change properly so we can reference it later."

**Context:**
- User is making significant architectural change
- Affects multiple repository implementations
- Need to record:
  - Why pooling was added (rationale)
  - How it's implemented (design)
  - Migration guide for existing repositories
- Should create both Serena (progress) and OpenClaw (knowledge) memories

## Expected Behavior
1. Skill `mcp-memory-first-development` should be invoked automatically
2. Should execute memory workflow:

   **Before Refactoring:**
   - Search OpenClaw for past refactoring patterns
   - Check if connection pooling was discussed before
   - Read current DatabaseRepository implementation

   **During Refactoring:**
   - Create Serena tracking memory: `refactoring-database-pooling-2025-12-20`
   - Record:
     - Current status (which repositories updated)
     - Decisions made (pool size, timeout settings)
     - Issues encountered

   **After Refactoring:**
   - Store in OpenClaw:
     - Design decision: Why pooling was needed
     - Implementation pattern: How to add pooling to repository
     - Migration guide: Steps for other repositories
   - Update Serena with completion

3. Should produce:
   - Well-documented refactoring process
   - Reusable knowledge for future similar tasks
   - Clear migration path for team members

4. Should NOT:
   - Store only code without context
   - Forget to record rationale
   - Mix temporary notes with permanent knowledge

## Success Criteria
- [x] Correct skill invoked (mcp-memory-first-development)
- [x] Memory search finds relevant past patterns
- [x] Serena memory tracks refactoring progress
- [x] OpenClaw LTM stores reusable knowledge
- [x] Documentation includes WHY, HOW, and MIGRATION
- [x] Completes without errors
- [x] Memory is useful for future reference

## Model Variations
- **Haiku:** Should handle basic memory operations; may need guidance on what to record
- **Sonnet:** Should record comprehensive documentation; good balance of progress tracking and knowledge storage
- **Opus:** May proactively structure memory for maximum reusability; may create multiple knowledge entries (design, migration, best practices)

## Test Validation
After running this scenario:
1. Verify skill invoked: Check `mcp-memory-first-development` in metadata
2. Check memory search:
   - Searched for "refactoring", "connection pooling", or "database patterns"
   - Results inform current implementation
3. Verify Serena memory (temporary):
   - File name: `refactoring-database-pooling-*`
   - Content includes:
     - Progress tracking (which files updated)
     - Decisions made during refactoring
     - Issues encountered and solutions
4. Verify OpenClaw LTM (permanent):
   - Stored via `lorairo-mem webhook`
   - Content includes:
     - Rationale (why pooling was needed)
     - Design pattern (how pooling is implemented)
     - Migration guide (steps for other repos)
5. Assess documentation quality:
   - Is it useful for someone else doing similar refactoring?
   - Does it explain WHY, not just WHAT?
   - Is migration path clear?
