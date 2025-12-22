# Scenario: File Exploration for New Repository

## Input
**User request:** "I need to understand how the ImageRepository class works. Show me its structure and main methods."

**Context:**
- Codebase: LoRAIro project
- Relevant file: `src/lorairo/database/repositories/image_repository.py`
- User has not read this file before
- User wants high-level overview, not full implementation

## Expected Behavior
1. Skill `mcp-serena-fast-ops` should be invoked automatically
2. Should use tools:
   - `mcp__serena__get_symbols_overview` to get file structure
   - `mcp__serena__find_symbol` (optional) if user asks for specific method details
3. Should produce: Clear overview of ImageRepository class structure
   - List of methods with brief descriptions
   - Method signatures (params, return types)
   - No full method bodies (unless explicitly requested)
4. Should NOT:
   - Read the entire file with Read tool
   - Generate code without understanding existing patterns
   - Use generic tools when semantic tools are available

## Success Criteria
- [x] Correct skill invoked (mcp-serena-fast-ops)
- [x] Tools used efficiently (get_symbols_overview, not Read)
- [x] Output meets requirements (structure overview, not full file)
- [x] Completes without errors
- [x] Response time: 1-3 seconds

## Model Variations
- **Haiku:** Should invoke skill correctly; may need explicit guidance to use get_symbols_overview vs Read
- **Sonnet:** Baseline behavior; should automatically choose semantic tools
- **Opus:** Should provide more context about repository pattern; may proactively suggest related symbols to explore

## Test Validation
After running this scenario:
1. Verify skill was invoked by checking response metadata
2. Check tool usage log: Should see `mcp__serena__get_symbols_overview`
3. Verify response contains class structure but not full implementation
4. Measure response time (target: < 3s)
