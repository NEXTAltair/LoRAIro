# Scenario: Library Documentation Research

## Input
**User request:** "I need to understand how to use Polars DataFrames for reading Parquet files. Show me the API and best practices."

**Context:**
- User is working on data export feature
- Needs library documentation for `/polars`
- Should use web research + Moltbot LTM (保存時に Moltbot が Context7/Perplexity で補強)
- Expected research time: 10-30 seconds

## Expected Behavior
1. Skill `context7-moltbot-research` should be invoked automatically
2. Should use tools (in sequence):
   - `web.run search_query` for official docs and API references
   - Optional: store a summary to Moltbot LTM (Moltbot will refine)
3. Should produce:
   - Relevant Polars API documentation for Parquet operations
   - Code examples showing how to read/write Parquet files
   - Best practices for DataFrame operations
4. Should NOT:
   - Guess API without checking sources
   - Return outdated documentation

## Success Criteria
- [x] Correct skill invoked (context7-moltbot-research)
- [x] Tools used efficiently (web.run search_query)
- [x] Output meets requirements (accurate Polars API docs)
- [x] Completes without errors
- [x] Response time: 10-30 seconds (acceptable for complex analysis)
- [x] Documentation is current and accurate

## Model Variations
- **Haiku:** Should handle basic library lookup; may need guidance on which topic to query
- **Sonnet:** Should handle full workflow; uses web.run to find official docs with appropriate queries
- **Opus:** May provide additional context about Polars vs Pandas trade-offs; may proactively suggest related APIs

## Test Validation
After running this scenario:
1. Verify skill invoked: Check `context7-moltbot-research` in metadata
2. Check tool usage sequence:
   - `web.run search_query` with query like "polars parquet read"
3. Verify output contains:
   - Polars API methods for Parquet I/O
   - Code examples (preferably with syntax highlighting)
   - Relevant parameter descriptions
4. Check documentation accuracy:
   - Compare against official Polars docs
   - Verify version compatibility mentioned
5. Measure response time: Should be 10-30s (not instant, but reasonable for deep research)
