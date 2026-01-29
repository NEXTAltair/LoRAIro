# Timeout Strategies for Complex Analysis Operations

Complex analysis operations using Context7 and Moltbot LTM have varying response times. Use these strategies to handle timeouts and maintain efficiency.

## Understanding Operation Timing

### Normal Operation Times
- **Serena operations**: 0.3-0.5s (fast)
- **Moltbot LTM search**: 2-5s (ltm_search.py)
- **Moltbot LTM write**: 1-3s (POST /hooks/lorairo-memory)
- **Context7 library-id**: 2-5s (resolve-library-id)
- **Context7 docs**: 3-10s (get-library-docs)
- **WebSearch**: 2-5s

### Timeout Thresholds
- **Expected**: < 15s
- **Warning**: 15-30s
- **Error**: > 30s (consider fallback)

## Incremental Approach

### Break Down Complex Operations

**Bad: Single large operation**
```
# Timeout risk: Too broad
get-library-docs(library_id="/pyside6", topic="all features")
```

**Good: Incremental operations**
```
# Step 1: Resolve library (2-5s)
mcp__context7__resolve-library-id(libraryName="pyside6")

# Step 2: Get specific topic (3-10s)
mcp__context7__get-library-docs(
  context7CompatibleLibraryID="/qt/pyside6",
  topic="signals"
)

# Step 3: Get another topic if needed (3-10s)
mcp__context7__get-library-docs(
  context7CompatibleLibraryID="/qt/pyside6",
  topic="threading"
)
```

### Narrow Search Queries

**Bad: Broad query**
```bash
python3 .github/skills/lorairo-mem/scripts/ltm_search.py <<'JSON'
{"limit": 100, "filters": {}}
JSON
```

**Good: Specific query**
```bash
python3 .github/skills/lorairo-mem/scripts/ltm_search.py <<'JSON'
{"limit": 10, "filters": {"type": ["decision"], "tags": ["repository-pattern"]}}
JSON
```

## Error Handling

### Timeout Detection

When operations time out:
1. **Recognize timeout**: Operation exceeds expected time
2. **Stop waiting**: Don't retry immediately
3. **Switch strategy**: Use fallback approach

### Fallback Patterns

#### Pattern 1: Context7 → WebSearch
```
# Attempt 1: Context7 (timeout)
mcp__context7__get-library-docs(...) → TIMEOUT

# Fallback: WebSearch
WebSearch("pyside6 signal slot documentation")
```

#### Pattern 2: Moltbot LTM → Serena + WebSearch
```
# Attempt 1: Moltbot LTM (timeout/error)
ltm_search.py → ERROR

# Fallback: Serena + WebSearch
1. mcp__serena__read_memory("current-project-status")
2. WebSearch("design pattern best practices")
```

#### Pattern 3: Complex → Simple
```
# Attempt 1: Complex multi-tool
POST /hooks/lorairo-memory + ltm_search.py → TIMEOUT

# Fallback: Serena only
mcp__serena__write_memory("active-development-tasks", ...)
```

## Sequential vs Parallel

### Sequential Execution (Recommended for heavy ops)

**Correct approach:**
```
1. Wait for ltm_search.py to complete
2. Then run mcp__context7__get-library-docs
3. Then run POST /hooks/lorairo-memory
```

**Why:** Avoid stacking timeouts.

### Parallel Execution (OK for light ops)

**OK: Parallel light operations**
```
# Both are fast
mcp__serena__read_memory(...) + mcp__serena__find_symbol(...)
```

**Caution: Mixed weight**
```
# Context7 is slower - may want to run separately
mcp__context7__get-library-docs(...) + ltm_search.py
```

## Performance Tips

### Use Mode Parameter Effectively

**Context7 get-library-docs modes:**
- `mode="code"`: API reference, code examples (faster)
- `mode="info"`: Conceptual guides, architecture (slower)

**Strategy:**
```
# Start with code mode (faster)
mcp__context7__get-library-docs(
  context7CompatibleLibraryID="/qt/pyside6",
  topic="signals",
  mode="code"
)

# Use info mode only if needed
mcp__context7__get-library-docs(
  context7CompatibleLibraryID="/qt/pyside6",
  topic="signals",
  mode="info"
)
```

### Limit Results

**Moltbot LTM search:**
```bash
# Limit results to reduce response time
python3 .github/skills/lorairo-mem/scripts/ltm_search.py <<'JSON'
{"limit": 5, "filters": {"type": ["decision"], "tags": ["pattern"]}}
JSON
```

### Topic Specificity

**Bad: Broad topic**
```
mcp__context7__get-library-docs(
  context7CompatibleLibraryID="/sqlalchemy",
  topic="everything"
)
```

**Good: Specific topic**
```
mcp__context7__get-library-docs(
  context7CompatibleLibraryID="/sqlalchemy",
  topic="transactions"
)
```

## Timeout Recovery

### Step-by-Step Recovery

**When timeout occurs:**

1. **Acknowledge timeout**
   ```
   "Context7 operation timed out. Switching to fallback strategy."
   ```

2. **Identify what was attempted**
   ```
   "Attempted: get-library-docs for 'pyside6 signals'"
   ```

3. **Execute fallback**
   ```
   "Fallback: Using WebSearch instead"
   ```

4. **Continue workflow**
   ```
   "Proceeding with available results from fallback"
   ```

### Don't Retry Immediately

**Bad: Immediate retry**
```
mcp__context7__get-library-docs(...) → TIMEOUT
mcp__context7__get-library-docs(...) → TIMEOUT AGAIN
```

**Good: Fallback first**
```
mcp__context7__get-library-docs(...) → TIMEOUT
→ Use WebSearch instead
→ Continue with workflow
```

## Connection Errors

### Network Issues

**Error types:**
- **Connection timeout**: Network unavailable
- **Server error**: Moltbot gateway or Context7 down
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
1. **Moltbot LTM + Context7** (preferred, comprehensive)
2. **Serena + WebSearch** (fallback, faster)
3. **Manual research** (if all fail)

## Practical Examples

### Example 1: Library Research with Timeout

```
# Attempt: Full workflow
1. mcp__context7__resolve-library-id("pyside6") → SUCCESS (3s)
2. mcp__context7__get-library-docs("/qt/pyside6", "signals", mode="code") → SUCCESS (7s)
3. Total: 10s (within threshold)

# If timeout at step 2:
1. mcp__context7__resolve-library-id("pyside6") → SUCCESS (3s)
2. mcp__context7__get-library-docs(...) → TIMEOUT (>30s)
3. Fallback: WebSearch("pyside6 signal slot tutorial")
```

### Example 2: LTM Search with Fallback

```
# Attempt: Moltbot LTM search
ltm_search.py → CONNECTION ERROR

# Fallback sequence:
1. mcp__serena__read_memory("current-project-status")
   → Get local context
2. WebSearch("repository pattern sqlalchemy best practices")
   → Get general knowledge
3. Combine results and proceed
```

### Example 3: Knowledge Storage with Retry

```
# Attempt: Full knowledge storage
POST /hooks/lorairo-memory → CONNECTION ERROR

# Fallback: Serena memory
1. mcp__serena__write_memory(
     memory_file_name="implementation-notes",
     content="Brief summary for now"
   )
2. Note: "Full LTM storage pending (connection issue)"
3. Continue workflow with Serena memory
```

## Monitoring and Logging

### Track Operation Times

**Good practice:**
```
"Starting Context7 get-library-docs... (expected: 3-10s)"
[Wait...]
"get-library-docs completed in 7s"
```

### Report Issues

**Good practice:**
```
"Context7 get-library-docs timeout (exceeded 30s)"
"Fallback: Using WebSearch"
"Proceeding with WebSearch results"
```

## Summary

**Key principles:**
1. **Specific queries**: Narrow scope to reduce time
2. **Sequential for heavy ops**: One Context7/LTM operation at a time
3. **Fallback ready**: Have Serena + WebSearch as backup
4. **Don't retry**: Use fallback instead
5. **Monitor timing**: Track and report operation times

**Timing reference:**
| Operation | Expected | Warning | Error |
|-----------|----------|---------|-------|
| Serena | <1s | 1-3s | >3s |
| Moltbot LTM | <5s | 5-15s | >15s |
| Context7 | <10s | 10-30s | >30s |
| WebSearch | <5s | 5-10s | >10s |
