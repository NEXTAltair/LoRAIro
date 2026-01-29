---
name: mcp-serena-fast-ops
version: "1.0.0"
description: Fast code operations using Serena MCP (1-3s) for symbol search, memory read/write, and basic code editing in LoRAIro project. Use when exploring code, managing project memory, or performing quick edits.
metadata:
  short-description: Serena MCPの高速操作（シンボル検索、メモリ操作、軽量編集）。
allowed-tools:
  # Symbol operations
  - mcp__serena__find_symbol
  - mcp__serena__get_symbols_overview
  - mcp__serena__find_referencing_symbols
  # Editing operations
  - mcp__serena__replace_symbol_body
  - mcp__serena__insert_after_symbol
  - mcp__serena__insert_before_symbol
  # Pattern search
  - mcp__serena__search_for_pattern
  # File operations
  - mcp__serena__list_dir
  - mcp__serena__find_file
  # Memory operations
  - mcp__serena__read_memory
  - mcp__serena__write_memory
  - mcp__serena__list_memories
  - mcp__serena__edit_memory
dependencies: []
---

# Serena Fast Operations

Fast code operations (1-3s) using Serena MCP semantic tools for symbol search, memory management, and code editing.

## When to Use

Use this skill when:
- **Symbol search**: Finding class, function, or method definitions
- **File structure**: Understanding project directory organization
- **Memory operations**: Recording/referencing development progress
- **Code editing**: Symbol-level implementation, insertion, replacement
- **Reference tracking**: Identifying symbol usage locations

## Core Patterns

### 1. Symbol Operations (1-3s)

**get_symbols_overview** - File structure
- Retrieves top-level symbols (classes, functions, variables)
- Use: Initial file exploration
- Params: `relative_path`

**find_symbol** - Search by name path
- Finds specific class, method, or function
- Params: `name_path`, `relative_path` (optional), `include_body`, `depth`, `substring_matching`
- Example: `name_path="ThumbnailWidget/handle_click"`

**search_for_pattern** - Regex pattern search
- Searches code patterns or strings
- Params: `substring_pattern`, `relative_path`, `restrict_search_to_code_files`, `paths_include_glob`, `paths_exclude_glob`

### 2. Memory Operations (Short-term)

**list_memories** - Available memories
- Lists project memory files

**read_memory** - Current progress/status
- Reads project-specific short-term memory
- Examples: `current-project-status`, `active-development-tasks`

**write_memory** - Progress tracking
- Records implementation progress and temporary decisions
- Content: Current status, next steps, temporary issues, debug info

**edit_memory** - Update existing memory
- Modifies memory content without full rewrite

### 3. Code Editing (Symbol-level)

**replace_symbol_body** - Replace symbol
- Rewrites function, method, or class
- Params: `name_path`, `relative_path`, `body`

**insert_after_symbol** - Add after
- Adds new method, function, or class
- Params: `name_path`, `relative_path`, `body`

**insert_before_symbol** - Add before
- Inserts imports or preamble code
- Params: `name_path`, `relative_path`, `body`

### 4. Reference Tracking

**find_referencing_symbols** - Usage locations
- Identifies where a symbol is used
- Use: Impact analysis before refactoring
- Params: `name_path`, `relative_path`

## Workflow Guidelines

### Code Exploration Sequence
```
Task Decision Tree:
├─ Need to explore code?
│  ├─ New file → get_symbols_overview
│  ├─ Find symbol → find_symbol
│  └─ Find usage → find_referencing_symbols
├─ Need to edit code?
│  ├─ Replace symbol → replace_symbol_body
│  ├─ Add after → insert_after_symbol
│  └─ Add before → insert_before_symbol
└─ Need memory?
   ├─ Read → read_memory
   ├─ Write → write_memory
   └─ Update → edit_memory
```

### Memory-First Approach
1. **Before implementation**: `list_memories` → `read_memory` (check status)
2. **During implementation**: `write_memory` (track progress)
3. **After completion**: `write_memory` (update status for next task)

### Performance
- **Fast operations (1-3s)**: Use Serena tools
- **Full file read**: Last resort; prefer symbol-level retrieval
- **Progressive disclosure**: Retrieve only needed information

## LoRAIro-Specific Guidance

See [lorairo-patterns.md](./lorairo-patterns.md) for:
- Project structure
- Architecture patterns
- Memory naming conventions
- Code organization

## Examples

See [examples.md](./examples.md) for detailed usage scenarios.

## Reference

See [reference.md](./reference.md) for complete Serena tool API reference.
