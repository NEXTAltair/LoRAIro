---
name: mcp-cipher-complex-analysis
description: Complex analysis using Cipher MCP (10-30s) for library research via context7, design pattern memory search, and multi-tool integration for strategic planning. Use when researching libraries, analyzing architectural decisions, or comparing multiple approaches.
allowed-tools:
  # Memory search
  - mcp__cipher__cipher_memory_search
  - mcp__cipher__cipher_workspace_search
  # Memory operations
  - mcp__cipher__cipher_extract_and_operate_memory
  - mcp__cipher__cipher_workspace_store
  # Library research (Context7 via Cipher)
  - mcp__cipher__resolve-library-id
  - mcp__cipher__get-library-docs
  - mcp__cipher__perplexity_ask
  # Web search
  - WebSearch
  - WebFetch
  # Serena tools (for code integration)
  - mcp__serena__find_symbol
  - mcp__serena__search_for_pattern
  # Bash operations (if needed)
  - mcp__cipher__cipher_bash
---

# Cipher Complex Analysis

Complex analysis (10-30s) using Cipher MCP for library research, design pattern memory, and strategic decisions.

## When to Use

Use this skill when:
- **Design pattern search**: Researching past similar designs
- **Library research**: Getting technical docs via context7
- **Long-term memory**: Storing design decisions and rationale
- **Dependency analysis**: Understanding architectural relationships
- **Strategic decisions**: Evaluating approaches and trade-offs

## Core Patterns

### 1. Design Knowledge Search (10-30s)

**cipher_memory_search** - Past design patterns
- Searches design decisions, implementation patterns, lessons learned
- Params: `query`, `top_k`
- Targets: Design approaches, architecture patterns, technical decisions

**cipher_workspace_search** - Team knowledge
- Searches team progress, bugs, collaboration context
- Params: `query`, `filters` (domain, project, status)

### 2. Long-term Memory Storage

**cipher_extract_and_operate_memory** - Store knowledge
- Extracts and stores design knowledge automatically
- Use: After implementation, after major decisions
- Content: Design approach, rationale, results, lessons learned

**cipher_workspace_store** - Team context
- Stores project progress, bugs, collaboration info
- Auto-extracts workspace information from interactions

### 3. Library Research (Context7)

**resolve-library-id** - Library ID resolution
- Resolves library name to Context7 ID
- Example: `"pyside6"` → `/qt/pyside6`

**get-library-docs** - Library documentation
- Retrieves official docs, API reference, guides
- Params: `context7CompatibleLibraryID`, `topic`, `mode` (code/info)
- Mode: `code` for API/examples, `info` for concepts/guides

**perplexity_ask** - AI-powered research
- Uses Perplexity for comparisons and clarifications
- Use: When Context7 lacks information

### 4. Web Integration

**WebSearch** - Latest information
- Searches blogs, case studies, recent updates
- Use: When Context7 lacks information

**WebFetch** - Specific URL content
- Fetches detailed content from URLs
- Use: Deep-diving into search results

## Workflow Guidelines

### Design Phase
```
1. Memory search (cipher_memory_search) - Past designs
2. Library research (Context7) - Technical details
3. Store decision (cipher_extract_and_operate_memory) - For future
```

### Implementation Phase
```
1. Memory search - Implementation patterns
2. Library docs - API details
3. Code integration (Serena tools)
4. Store knowledge - After completion
```

## Serena vs Cipher

**Serena (1-3s)** - Use for:
- Symbol search (classes, methods)
- File structure
- Short-term memory (progress)
- Basic code editing

**Cipher (10-30s)** - Use for:
- Design pattern search
- Library research (Context7)
- Long-term memory
- Strategic decisions

### Combined Workflow
```
1. Serena: Check status (read_memory)
2. Cipher: Search past designs (cipher_memory_search)
3. Cipher: Research library (Context7)
4. Serena: Implement (find_symbol, replace_symbol_body)
5. Serena: Track progress (write_memory)
6. Cipher: Store knowledge (cipher_extract_and_operate_memory)
```

## Timeout Strategies

See [timeout-strategies.md](./timeout-strategies.md) for:
- Incremental approach
- Error handling
- Fallback patterns
- Performance tips

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

### Query Examples
- "widget signal slot direct communication pattern"
- "sqlalchemy repository pattern best practices"
- "pytest fixture setup teardown pattern"
- "pyside6 qthread worker pattern"

## Examples

See [examples.md](./examples.md) for detailed scenarios.

## Reference

See [reference.md](./reference.md) for complete Cipher and Context7 API reference.
