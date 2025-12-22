# Timeout Strategies for Cipher Operations

Cipher operations take 10-30 seconds. Use these strategies to handle timeouts and maintain efficiency.

## Understanding Cipher Timing

### Normal Operation Times
- **cipher_memory_search**: 10-15s (semantic search)
- **resolve-library-id**: 5-10s (library lookup)
- **get-library-docs**: 15-30s (document retrieval)
- **perplexity_ask**: 10-20s (AI research)
- **cipher_extract_and_operate_memory**: 10-20s (knowledge storage)

### Timeout Thresholds
- **Expected**: < 30s
- **Warning**: 30-60s
- **Error**: > 60s (timeout)

## Incremental Approach

### Break Down Complex Operations

**Bad: Single large operation**
```
# Timeout risk: Too much in one operation
get-library-docs(library_id="/pyside6", topic="all features")
```

**Good: Incremental operations**
```
# Step 1: Resolve library (5-10s)
resolve-library-id(library_name="pyside6")

# Step 2: Get specific topic (15-20s)
get-library-docs(library_id="/qt/pyside6", topic="signals")

# Step 3: Get another topic if needed (15-20s)
get-library-docs(library_id="/qt/pyside6", topic="threading")
```

### Narrow Search Queries

**Bad: Broad query**
```
cipher_memory_search(query="all design patterns")
```

**Good: Specific query**
```
cipher_memory_search(query="repository pattern transaction handling")
```

## Error Handling

### Timeout Detection

When Cipher times out:
1. **Recognize timeout**: Operation exceeds 60s
2. **Stop waiting**: Don't retry immediately
3. **Switch strategy**: Use fallback approach

### Fallback Patterns

#### Pattern 1: Cipher → Serena + WebSearch
```
# Attempt 1: Cipher (timeout)
cipher_memory_search(query="pattern") → TIMEOUT

# Fallback: Serena + WebSearch
1. mcp__serena__search_for_pattern("pattern")
2. WebSearch("pattern best practices")
```

#### Pattern 2: Context7 → WebFetch
```
# Attempt 1: Context7 (timeout)
get-library-docs(library_id="/sqlalchemy") → TIMEOUT

# Fallback: Direct web fetch
WebFetch(url="https://docs.sqlalchemy.org/en/...")
```

#### Pattern 3: Complex → Simple
```
# Attempt 1: Complex multi-tool (timeout)
cipher_extract_and_operate_memory + workspace_store → TIMEOUT

# Fallback: Simple operations
1. Use Serena memory only (short-term)
2. Manual knowledge recording later
```

## Sequential vs Parallel

### Sequential Execution (Recommended)

**Correct approach:**
```
1. Wait for cipher_memory_search to complete
2. Then run get-library-docs
3. Then run cipher_extract_and_operate_memory
```

**Why:** Cipher operations are expensive; avoid stacking timeouts.

### Avoid Parallel Cipher Operations

**Bad: Parallel execution**
```
# Both running simultaneously → High timeout risk
cipher_memory_search(...) + get-library-docs(...)
```

**Good: Sequential execution**
```
# One at a time
result1 = cipher_memory_search(...)
result2 = get-library-docs(...)  # After result1 completes
```

## Performance Tips

### Use Mode Parameter Effectively

**get-library-docs modes:**
- `mode="code"`: API reference, code examples (faster)
- `mode="info"`: Conceptual guides, architecture (slower)

**Strategy:**
```
# Start with code mode (faster)
get-library-docs(library_id="/pyside6", topic="signals", mode="code")

# Use info mode only if needed
get-library-docs(library_id="/pyside6", topic="signals", mode="info")
```

### Pagination for Large Results

**memory_search pagination:**
```
# Page 1: Quick results
cipher_memory_search(query="pattern", page=1)

# If insufficient, get page 2
cipher_memory_search(query="pattern", page=2)
```

### Topic Specificity

**Bad: Broad topic**
```
get-library-docs(library_id="/sqlalchemy", topic="everything")
```

**Good: Specific topic**
```
get-library-docs(library_id="/sqlalchemy", topic="transactions")
```

## Timeout Recovery

### Step-by-Step Recovery

**When timeout occurs:**

1. **Acknowledge timeout**
   ```
   "Cipher operation timed out (>60s). Switching to fallback strategy."
   ```

2. **Identify what was attempted**
   ```
   "Attempted: cipher_memory_search for 'design patterns'"
   ```

3. **Execute fallback**
   ```
   "Fallback: Using Serena search + WebSearch instead"
   ```

4. **Continue workflow**
   ```
   "Proceeding with available results from fallback"
   ```

### Don't Retry Immediately

**Bad: Immediate retry**
```
cipher_memory_search(...) → TIMEOUT
cipher_memory_search(...) → TIMEOUT AGAIN
```

**Good: Fallback first**
```
cipher_memory_search(...) → TIMEOUT
→ Use Serena + WebSearch instead
→ Continue with workflow
```

## Connection Errors

### Network Issues

**Error types:**
- **Connection timeout**: Network unavailable
- **Server error**: Cipher MCP server down
- **Rate limit**: Too many requests

**Handling:**
```
1. Detect connection error
2. Switch to local operations (Serena)
3. Use WebSearch as backup
4. Record issue for later retry
```

### Graceful Degradation

**Priority order:**
1. **Cipher tools** (preferred, but slow)
2. **Serena + WebSearch** (fallback, faster)
3. **Manual research** (if all fail)

## Practical Examples

### Example 1: Library Research with Timeout

```
# Attempt: Full workflow
1. resolve-library-id("pyside6") → SUCCESS (8s)
2. get-library-docs("/qt/pyside6", "signals", mode="code") → SUCCESS (18s)
3. Total: 26s (within threshold)

# If timeout at step 2:
1. resolve-library-id("pyside6") → SUCCESS (8s)
2. get-library-docs(...) → TIMEOUT (>60s)
3. Fallback: WebFetch("https://doc.qt.io/qtforpython/...")
```

### Example 2: Memory Search with Fallback

```
# Attempt: Cipher memory search
cipher_memory_search(query="repository pattern") → TIMEOUT

# Fallback sequence:
1. mcp__serena__search_for_pattern("repository pattern")
   → Find local implementations
2. WebSearch("repository pattern sqlalchemy best practices")
   → Get general knowledge
3. Combine results and proceed
```

### Example 3: Knowledge Storage with Retry

```
# Attempt: Full knowledge storage
cipher_extract_and_operate_memory(...) → TIMEOUT

# Fallback: Simplified storage
1. mcp__serena__write_memory(
     memory_name="implementation-notes",
     content="Brief summary for now"
   )
2. Note: "Full knowledge extraction pending (Cipher timeout)"
3. Continue workflow with Serena memory
```

## Monitoring and Logging

### Track Operation Times

**Good practice:**
```
"Starting cipher_memory_search... (expected: 10-15s)"
[Wait...]
"cipher_memory_search completed in 12s"
```

### Report Timeouts

**Good practice:**
```
"cipher_memory_search timeout (exceeded 60s)"
"Fallback: Using Serena + WebSearch"
"Proceeding with partial results"
```

## Summary

**Key principles:**
1. **Sequential execution**: One Cipher operation at a time
2. **Specific queries**: Narrow scope to reduce time
3. **Fallback ready**: Have Serena + WebSearch as backup
4. **Don't retry**: Use fallback instead
5. **Monitor timing**: Track and report operation times
