# Scenario: New Feature Implementation with Memory-First Workflow

## Input
**User request:** "I'm about to implement a new export feature for CSV format. Help me follow the memory-first workflow: search past patterns, track implementation, and store knowledge afterward."

**Context:**
- User is starting new feature development
- Should follow 3-phase memory workflow (Before → During → After)
- LoRAIro has existing export patterns (Parquet export in dataset builder)
- Need to leverage both Serena (short-term) and Moltbot (long-term) memory

## Expected Behavior
1. Skill `mcp-memory-first-development` should be invoked automatically
2. Should guide user through 3-phase workflow:

   **Phase 1: Before Implementation**
   - `lorairo-mem ltm_search.py` for "export patterns" or "CSV export"
   - `mcp__serena__read_memory` for recent export-related work
   - Provide summary of relevant past implementations

   **Phase 2: During Implementation**
   - Create `mcp__serena__write_memory` for tracking progress
   - Suggest memory file name (e.g., `implementation-csv-export-2025-12-20`)
   - Guide user to record decisions and blockers

   **Phase 3: After Implementation**
   - `lorairo-mem webhook` to store design knowledge
   - Update Serena memory with completion status
   - Suggest creating reusable examples

3. Should produce:
   - Clear phase-by-phase guidance
   - Memory operations at appropriate times
   - Well-structured memory content

4. Should NOT:
   - Skip memory search phase
   - Store temporary notes in Moltbot (use Serena instead)
   - Create duplicate memory entries

## Success Criteria
- [x] Correct skill invoked (mcp-memory-first-development)
- [x] All 3 phases executed in order
- [x] Both Serena and Moltbot LTM used appropriately
- [x] Memory content is well-structured and useful
- [x] User is guided through workflow (not just executing commands)
- [x] Completes without errors

## Model Variations
- **Haiku:** Should understand basic workflow; may need explicit prompting for each phase
- **Sonnet:** Should guide user through all 3 phases autonomously; good memory structure
- **Opus:** May provide deeper context from memory search; may suggest related patterns proactively

## Test Validation
After running this scenario:
1. Verify skill invoked: Check `mcp-memory-first-development` in metadata
2. Check Phase 1 (Before Implementation):
   - `ltm_search.py` used with relevant query
   - Results synthesized and presented to user
3. Check Phase 2 (During Implementation):
   - `serena_write_memory` creates tracking file
   - File name follows conventions
   - Content includes progress tracking structure
4. Check Phase 3 (After Implementation):
   - `lorairo-mem webhook` stores knowledge
   - Serena memory updated with completion
5. Verify memory structure:
   - Serena: Temporary, implementation-focused
   - Moltbot: Reusable knowledge, design decisions
6. Check workflow guidance:
   - User is told WHEN to do each step
   - Clear instructions for WHAT to record
   - WHY explanation for memory strategy
