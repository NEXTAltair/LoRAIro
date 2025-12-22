# Scenario: Library Documentation Research

## Input
**User request:** "I need to understand how to use Polars DataFrames for reading Parquet files. Show me the API and best practices."

**Context:**
- User is working on data export feature
- Needs library documentation for `/polars`
- Should use Context7 via Cipher MCP
- Expected research time: 10-30 seconds

## Expected Behavior
1. Skill `mcp-cipher-complex-analysis` should be invoked automatically
2. Should use tools (in sequence):
   - `mcp__cipher__resolve-library-id` to find Polars library ID (e.g., `/pola-rs/polars`)
   - `mcp__cipher__get-library-docs` with appropriate topic (e.g., "parquet", "dataframe")
   - Optional: `mcp__cipher__perplexity_ask` for clarifications or comparisons
3. Should produce:
   - Relevant Polars API documentation for Parquet operations
   - Code examples showing how to read/write Parquet files
   - Best practices for DataFrame operations
4. Should NOT:
   - Use WebSearch for official library docs (Context7 is better)
   - Return outdated documentation
   - Guess API without verification

## Success Criteria
- [x] Correct skill invoked (mcp-cipher-complex-analysis)
- [x] Tools used efficiently (resolve-library-id → get-library-docs)
- [x] Output meets requirements (accurate Polars API docs)
- [x] Completes without errors
- [x] Response time: 10-30 seconds (acceptable for complex analysis)
- [x] Documentation is current and accurate

## Model Variations
- **Haiku:** Should handle basic library lookup; may need guidance on which topic to query
- **Sonnet:** Should handle full workflow; resolves library ID, fetches relevant docs with appropriate topic
- **Opus:** May provide additional context about Polars vs Pandas trade-offs; may proactively suggest related APIs

## Test Validation
After running this scenario:
1. Verify skill invoked: Check `mcp-cipher-complex-analysis` in metadata
2. Check tool usage sequence:
   - `mcp__cipher__resolve-library-id` with query like "polars" or "pola-rs"
   - `mcp__cipher__get-library-docs` with library ID and topic
3. Verify output contains:
   - Polars API methods for Parquet I/O
   - Code examples (preferably with syntax highlighting)
   - Relevant parameter descriptions
4. Check documentation accuracy:
   - Compare against official Polars docs
   - Verify version compatibility mentioned
5. Measure response time: Should be 10-30s (not instant, but reasonable for deep research)
