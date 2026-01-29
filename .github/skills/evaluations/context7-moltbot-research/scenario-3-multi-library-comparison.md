# Scenario: Multi-Library Comparison and Integration Strategy

## Input
**User request:** "I need to choose between Pydantic AI and LangChain for our annotation workflow. Compare their APIs, integration complexity, and performance. We're already using Anthropic and OpenAI."

**Context:**
- User is making a strategic architectural decision
- Need to compare multiple libraries
- Should consider LoRAIro's existing tech stack
- Requires both library docs research AND memory search for past decisions

## Expected Behavior
1. Skill `context7-moltbot-research` should be invoked automatically
2. Should use tools (complex multi-tool workflow):
   - `web.run search_query` for official docs and comparisons
   - `lorairo-mem ltm_search.py` to check if we've evaluated these before
   - Optional: `mcp__serena__find_symbol` to understand current annotation implementation
   - Optional: store decision summary to Moltbot LTM (Moltbot will refine)
3. Should produce:
   - Detailed comparison table (features, pros/cons)
   - Integration complexity assessment for each option
   - Performance considerations
   - Recommendation with rationale
   - References to past decisions if available
4. Should NOT:
   - Make recommendation without researching both options
   - Ignore existing codebase constraints
   - Provide outdated comparison (should use current library versions)

## Success Criteria
- [x] Correct skill invoked (context7-moltbot-research)
- [x] Tools used efficiently (multi-tool integration)
- [x] Output meets requirements (comprehensive comparison)
- [x] Completes without errors (even with multiple tool calls)
- [x] Response time: Acceptable for strategic decision (may take 20-30s)
- [x] Recommendation is well-justified
- [x] Considers LoRAIro-specific context

## Model Variations
- **Haiku:** May struggle with complex multi-tool workflow; should handle basic comparison but may miss nuances
- **Sonnet:** Should handle full workflow correctly; good comparison and recommendation
- **Opus:** Should provide deep analysis with multiple perspectives; may proactively suggest third option or hybrid approach; excellent justification

## Test Validation
After running this scenario:
1. Verify skill invoked: Check `context7-moltbot-research` in metadata
2. Check tool usage sequence (complex workflow):
   - Documentation fetch: `web.run search_query` (multiple queries)
   - Comparison research: `web.run search_query` for trade-offs
   - Memory check: `ltm_search.py` for past evaluations
   - Code exploration: `mcp__serena__find_symbol` (optional)
3. Verify output completeness:
   - Comparison covers key dimensions (API, complexity, performance)
   - Both libraries analyzed in depth
   - Clear recommendation with reasoning
   - References to LoRAIro's existing architecture
4. Assess recommendation quality:
   - Justified by research (not arbitrary)
   - Considers integration cost
   - Acknowledges trade-offs
   - Actionable for implementation
5. Check timeout handling:
   - If Moltbot times out, should fallback gracefully
   - Should still provide partial results if possible

## Edge Cases to Test
- One library has no official docs found (should use web.run search_query)
- Memory search returns conflicting past decisions (should acknowledge and explain)
- Both libraries are equally viable (should present trade-offs clearly)
- Current implementation uses neither library (should consider migration cost)
