---
name: context7-moltbot-research
version: "2.0.0"
description: Library research via web search (Codex) and long-term memory via Moltbot LTM. Moltbot may enrich stored content using Context7/Perplexity.
metadata:
  short-description: ライブラリ調査（web検索 + Moltbot委譲）と長期記憶（Moltbot LTM）。
allowed-tools:
  # Web research (Codex)
  - web.run
  # Serena tools (for code integration)
  - mcp__serena__find_symbol
  - mcp__serena__search_for_pattern
  - mcp__serena__read_memory
  - mcp__serena__write_memory
  # Bash for Moltbot LTM operations
  - Bash
dependencies:
  - lorairo-mem
---

# Complex Analysis (Library Research + Long-Term Memory)

Complex analysis using web research and Moltbot LTM for design pattern memory and strategic decisions.

Note: Codex には Context7 MCP は入っていません。ライブラリ調査は web.run で実施し、LTM 保存時に Moltbot が Context7/Perplexity を使って内容をブラッシュアップして保存します。

## When to Use

Use this skill when:
- **Design pattern search**: Researching past similar designs (Moltbot LTM)
- **Library research**: web.run で公式ドキュメント/仕様を確認し、保存時に Moltbot が補強
- **Long-term memory**: Storing design decisions and rationale (Moltbot LTM)
- **Dependency analysis**: Understanding architectural relationships
- **Strategic decisions**: Evaluating approaches and trade-offs

## Core Patterns

### 1. Design Knowledge Search (Moltbot LTM)

**ltm_search.py** - Past design patterns
- Searches design decisions, implementation patterns, lessons learned
- Usage:
```bash
python3 .github/skills/lorairo-mem/scripts/ltm_search.py <<'JSON'
{"limit": 10, "filters": {"type": ["decision", "howto"], "tags": ["repository-pattern"]}}
JSON
```

**ltm_latest.py** - Recent entries
```bash
python3 .github/skills/lorairo-mem/scripts/ltm_latest.py <<'JSON'
{"limit": 5}
JSON
```

### 2. Long-term Memory Storage (Moltbot LTM)

**POST /hooks/lorairo-memory** - Store knowledge
- Stores design knowledge with proper metadata
- Use: After implementation, after major decisions
- Content: Design approach, rationale, results, lessons learned

```bash
HOOK_TOKEN=$(jq -r '.hooks.token' ~/.clawdbot/clawdbot.json)

curl -sS -X POST http://host.docker.internal:18789/hooks/lorairo-memory \
  -H "Authorization: Bearer $HOOK_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "LoRAIro [Feature] Design Decision",
    "summary": "Brief summary of the decision",
    "body": "# Design Details\n\n## Background\n...\n\n## Decision\n...\n\n## Rationale\n...",
    "type": "decision",
    "importance": "High",
    "tags": ["architecture", "pattern-name"],
    "source": "Container"
  }'
```

### 3. Library Research (Web + Moltbot)

Codex では Context7 MCP を直接使いません。ライブラリ調査は web.run で公式ドキュメントを確認し、要点をまとめて LTM 保存時に Moltbot が補強します。

Example (web search):
```json
{"search_query":[{"q":"PySide6 Signal Slot QThread official docs"}]}
```

### 4. Web Research (Codex)

**web.run** - Latest information
- Searches official docs, blogs, case studies, recent updates
- Use: When you need up-to-date or external sources

## Workflow Guidelines

### Design Phase
```
1. LTM search (ltm_search.py) - Past designs
2. Library research (web.run) - Technical details
3. Store decision (POST /hooks/lorairo-memory) - For future
```

### Implementation Phase
```
1. LTM search - Implementation patterns
2. Web docs - API details
3. Code integration (Serena tools)
4. Store knowledge - After completion
```

## Serena vs Moltbot LTM

**Serena (0.3-0.5s)** - Use for:
- Symbol search (classes, methods)
- File structure
- Short-term memory (progress)
- Basic code editing

**Moltbot LTM (1-3s)** - Use for:
- Design pattern search
- Long-term memory
- Strategic decisions
- Cross-project knowledge

### Combined Workflow
```
1. Serena: Check status (read_memory)
2. Moltbot: Search past designs (ltm_search.py)
3. Web: Research library (web.run)
4. Serena: Implement (find_symbol, replace_symbol_body)
5. Serena: Track progress (write_memory)
6. Moltbot: Store knowledge (POST /hooks/lorairo-memory)
```

## LoRAIro-Specific Usage

### Design Decisions to Store
- Architecture patterns (Repository, Service Layer, Direct Widget Communication)
- Technical choices (SQLAlchemy, PySide6, pytest rationale)
- Performance improvements (caching, async decisions)
- Refactoring (intent and effects)

### Libraries to Research
- **PySide6**: Signal/Slot, QThread, Qt Designer
- **SQLAlchemy**: ORM, transactions, migrations
- **pytest**: Fixtures, mocks, parametrization
- **Pillow**: Image processing, metadata

### Query Examples (Moltbot LTM)
```bash
# Widget patterns
python3 .github/skills/lorairo-mem/scripts/ltm_search.py <<'JSON'
{"limit": 5, "filters": {"tags": ["widget", "signal-slot", "direct-communication"]}}
JSON

# Repository patterns
python3 .github/skills/lorairo-mem/scripts/ltm_search.py <<'JSON'
{"limit": 5, "filters": {"tags": ["repository-pattern", "sqlalchemy"]}}
JSON

# Testing patterns
python3 .github/skills/lorairo-mem/scripts/ltm_search.py <<'JSON'
{"limit": 5, "filters": {"tags": ["pytest", "testing"]}}
JSON
```

## Performance Characteristics

| Operation | Tool | Time |
|-----------|------|------|
| LTM search | ltm_search.py | 2-5s |
| LTM write | POST /hooks/lorairo-memory | 1-3s |
| Web search | web.run | 2-5s |
| Serena ops | mcp__serena__* | 0.3-0.5s |

## Examples

See [examples.md](./examples.md) for detailed scenarios.

## Reference

See [reference.md](./reference.md) for Moltbot LTM + web.run reference.
