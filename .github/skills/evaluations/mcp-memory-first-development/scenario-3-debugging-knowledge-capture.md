# Scenario: Debugging Knowledge Capture

## Input
**User request:** "I'm debugging a race condition in the annotation worker. As I investigate, help me record findings so we don't lose this knowledge if the same issue appears later."

**Context:**
- User is debugging complex issue (race condition)
- Investigation involves:
  - Hypothesis testing
  - Failed attempts
  - Root cause analysis
  - Final solution
- Need to capture debugging journey, not just final fix
- Should create debugging memory that's useful for future troubleshooting

## Expected Behavior
1. Skill `mcp-memory-first-development` should be invoked automatically
2. Should guide debugging knowledge capture:

   **Investigation Phase (Serena):**
   - Create `mcp__serena__write_memory` for active investigation
   - Memory file: `debugging-annotation-race-condition-2025-12-20`
   - Record structure:
     - Symptoms observed
     - Hypotheses tested (including failed ones)
     - Investigation steps
     - Findings at each step

   **Resolution Phase (Serena update):**
   - Update Serena memory with:
     - Root cause identified
     - Solution implemented
     - Verification results

   **Knowledge Storage (OpenClaw LTM):**
   - Extract to OpenClaw: `lorairo-mem webhook`
   - Create reusable knowledge:
     - Problem pattern: Race condition in async workers
     - Root cause: Specific threading issue
     - Solution pattern: How to fix similar issues
     - Prevention: How to avoid in future code

3. Should produce:
   - Complete debugging narrative
   - Failed attempts documented (valuable negative knowledge)
   - Reusable troubleshooting pattern
   - Prevention guidance

4. Should NOT:
   - Only record final solution (lose investigation context)
   - Skip failed attempts (they're valuable!)
   - Store temporary debugging notes in OpenClaw
   - Forget to generalize for reuse

## Success Criteria
- [x] Correct skill invoked (mcp-memory-first-development)
- [x] Serena memory captures complete investigation
- [x] Failed attempts are documented (not hidden)
- [x] Root cause is clearly identified
- [x] OpenClaw LTM generalizes for reuse
- [x] Completes without errors
- [x] Knowledge is actionable for future debugging

## Model Variations
- **Haiku:** Should record basic debugging steps; may need guidance on capturing failed attempts
- **Sonnet:** Should capture complete investigation narrative; good balance of detail and structure
- **Opus:** May provide deeper analysis of root cause; may proactively suggest related bugs to check; excellent knowledge generalization

## Test Validation
After running this scenario:
1. Verify skill invoked: Check `mcp-memory-first-development` in metadata
2. Check Serena memory (investigation log):
   - File name: `debugging-annotation-race-condition-*`
   - Structure includes:
     - **Symptoms:** What was observed
     - **Hypotheses:** What was suspected (all of them)
     - **Investigation:** Steps taken
     - **Failed Attempts:** What didn't work (critical!)
     - **Root Cause:** What was actually wrong
     - **Solution:** How it was fixed
     - **Verification:** How fix was validated
3. Check OpenClaw LTM (knowledge):
   - Stored via `lorairo-mem webhook`
   - Generalized pattern:
     - Problem category (race conditions in async workers)
     - Symptoms to look for
     - Diagnostic approach
     - Common solutions
     - Prevention strategies
4. Verify failed attempts documented:
   - Not hidden or deleted
   - Explained why they failed
   - Valuable for avoiding same dead ends
5. Assess reusability:
   - Could another developer use this to debug similar issue?
   - Is it specific enough to be actionable?
   - Is it general enough to apply to variations?

## Edge Cases to Test
- Investigation is ongoing (memory updated incrementally)
- Multiple solutions attempted before finding right one
- Root cause is unclear initially (documented uncertainty)
- Solution requires code changes + configuration changes (both recorded)
