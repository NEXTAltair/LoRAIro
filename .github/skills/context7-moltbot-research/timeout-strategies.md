# Timeout Strategies for Web Research + Moltbot LTM

This document covers timeouts when using web.run and Moltbot LTM.

## Understanding Operation Timing

### Normal Operation Times
- **Serena operations**: 0.3-0.5s (fast)
- **Moltbot LTM search**: 2-5s (ltm_search.py)
- **Moltbot LTM write**: 1-3s (POST /hooks/lorairo-memory)
- **web.run search_query**: 2-5s

### Timeout Thresholds
- **Expected**: < 15s
- **Warning**: 15-30s
- **Error**: > 30s (consider fallback)

## Incremental Approach

### Narrow Queries First

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

**Good: Specific web search**
```json
{"search_query":[{"q":"PySide6 Signal Slot QThread official docs"}]}
```

## Error Handling

### Timeout Detection

When operations time out:
1. **Recognize timeout**: Operation exceeds expected time
2. **Stop waiting**: Don't retry immediately
3. **Switch strategy**: Use fallback approach

### Fallback Patterns

#### Pattern 1: Web search → narrower query
```
web.run search_query(...) → TIMEOUT
→ Narrow the query and retry
```

#### Pattern 2: Moltbot LTM → Serena + local search
```
ltm_search.py → ERROR
→ mcp__serena__read_memory + mcp__serena__search_for_pattern
```

#### Pattern 3: Complex → Simple
```
POST /hooks/lorairo-memory + ltm_search.py → TIMEOUT
→ mcp__serena__write_memory (short-term only)
```

## Sequential vs Parallel

### Sequential Execution (Recommended for heavy ops)

**Correct approach:**
```
1. Wait for ltm_search.py to complete
2. Then run web.run search_query
3. Then run POST /hooks/lorairo-memory
```

**Why:** Avoid stacking timeouts.

### Parallel Execution (OK for light ops)

**OK: Parallel light operations**
```
mcp__serena__read_memory(...) + mcp__serena__find_symbol(...)
```

## Timeout Recovery

### Step-by-Step Recovery

**When timeout occurs:**

1. **Acknowledge timeout**
   ```
   "Operation timed out. Switching to fallback strategy."
   ```

2. **Identify what was attempted**
   ```
   "Attempted: web search for 'pyside6 signals'"
   ```

3. **Execute fallback**
   ```
   "Fallback: Narrow query and retry, or use Serena/local context"
   ```

4. **Continue workflow**
   ```
   "Proceeding with available results from fallback"
   ```
