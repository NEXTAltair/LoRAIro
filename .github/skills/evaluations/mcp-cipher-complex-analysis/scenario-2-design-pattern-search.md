# Scenario: Design Pattern Memory Search

## Input
**User request:** "What design patterns have we used in the past for handling async database operations in Qt applications? I'm implementing a new worker for batch updates."

**Context:**
- User is designing a new async worker
- Need to search Cipher long-term memory for past patterns
- LoRAIro has existing async patterns (WorkerManager, QThreadPool)
- Should find relevant design decisions from past implementations

## Expected Behavior
1. Skill `mcp-cipher-complex-analysis` should be invoked automatically
2. Should use tools:
   - `mcp__cipher__cipher_memory_search` with query like "async database Qt worker pattern"
   - `mcp__cipher__cipher_workspace_search` for team knowledge about async implementations
   - Optional: `mcp__serena__read_memory` for recent related work
3. Should produce:
   - Relevant design patterns from past implementations
   - Architectural decisions and rationale
   - Code patterns or references to existing implementations
   - Trade-offs considered (e.g., QThread vs QThreadPool)
4. Should NOT:
   - Invent patterns without checking memory
   - Return generic Qt documentation (should focus on LoRAIro-specific knowledge)
   - Miss relevant workspace context

## Success Criteria
- [x] Correct skill invoked (mcp-cipher-complex-analysis)
- [x] Tools used efficiently (memory search operations)
- [x] Output meets requirements (past patterns, design decisions, references)
- [x] Completes without errors
- [x] Memory results are relevant to the query
- [x] Combines long-term (Cipher) and short-term (Serena) memory appropriately

## Model Variations
- **Haiku:** Should handle basic memory search; may return limited context
- **Sonnet:** Should search both Cipher and Serena memory; provides good synthesis of results
- **Opus:** May provide deeper analysis of trade-offs; might suggest improvements to past patterns based on current context

## Test Validation
After running this scenario:
1. Verify skill invoked: Check `mcp-cipher-complex-analysis` in metadata
2. Check tool usage:
   - `mcp__cipher__cipher_memory_search` with appropriate query
   - Optional: `mcp__cipher__cipher_workspace_search` for team knowledge
   - Optional: `mcp__serena__read_memory` for recent context
3. Verify output quality:
   - Contains specific pattern references (e.g., "WorkerManager pattern")
   - Includes design rationale (why this pattern was chosen)
   - Mentions past implementations (file paths, examples)
4. Check memory relevance:
   - Results should relate to async, database, and Qt
   - Should include LoRAIro-specific knowledge, not generic Qt docs
5. Verify integration:
   - If both Cipher and Serena memory used, results should be synthesized coherently
