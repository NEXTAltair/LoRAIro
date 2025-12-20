---
name: mcp-memory-first-development
description: Memory-First development workflow integrating Serena short-term project memory and Cipher long-term design knowledge for efficient development. Use this skill to guide the 3-phase workflow (Before → During → After implementation) with proper memory management.
allowed-tools:
  # Serena memory (short-term)
  - mcp__serena__read_memory
  - mcp__serena__write_memory
  - mcp__serena__list_memories
  - mcp__serena__edit_memory
  # Cipher memory (long-term)
  - mcp__cipher__cipher_memory_search
  - mcp__cipher__cipher_extract_and_operate_memory
  - mcp__cipher__cipher_workspace_search
  - mcp__cipher__cipher_workspace_store
---

# Memory-First Development

Integrates Serena short-term project memory and Cipher long-term design knowledge for efficient development workflow.

## When to Use

Use this skill to guide development with proper memory management:
- **Before implementation**: Review past patterns and current project status
- **During implementation**: Track progress, decisions, and blockers continuously
- **After completion**: Store implementation knowledge as long-term memory

## 2-Tier Memory Architecture

```
┌─────────────────────────────────────────────┐
│ Serena Memory (Short-Term, Project-Specific)│
├─────────────────────────────────────────────┤
│ • Current implementation status             │
│ • Active development decisions              │
│ • Temporary issues and solutions            │
│ • Debug information and validation results  │
│ • Refactoring plans                         │
├─────────────────────────────────────────────┤
│ Characteristics:                            │
│ • Fast access (0.3-0.5s)                    │
│ • Frequent updates during implementation    │
│ • Temporary (archive or delete after task)  │
│ • Project-specific (LoRAIro only)           │
└─────────────────────────────────────────────┘
            ↓ (filter & consolidate)
┌─────────────────────────────────────────────┐
│ Cipher Memory (Long-Term, Design Knowledge) │
├─────────────────────────────────────────────┤
│ • Design approaches and rationale           │
│ • Architectural intent and background       │
│ • Performance and maintainability analysis  │
│ • Implementation challenges and solutions   │
│ • Best practices and anti-patterns          │
│ • Technology selection criteria and results │
├─────────────────────────────────────────────┤
│ Characteristics:                            │
│ • Persistent (project-wide reference)       │
│ • Searchable (discover past cases)          │
│ • Reusable (applicable to other projects)   │
│ • Structured (title, context, decisions)    │
└─────────────────────────────────────────────┘
```

### Serena Memory (Short-Term)
**Purpose:** Current development progress and temporary notes
**Access:** 0.3-0.5s (fast)
**Lifecycle:** Temporary (archive or delete after task completion)
**Scope:** Project-specific (LoRAIro only)

### Cipher Memory (Long-Term)
**Purpose:** Reusable design pattern assets
**Access:** 10-15s (via semantic search)
**Lifecycle:** Persistent (project-wide, cross-project reference)
**Scope:** Universal (applicable to future projects)

## Memory-First Development Cycle

### Phase 1: Pre-Implementation (Before)

**Goal:** Leverage past knowledge, avoid duplicate work

**Checklist:**
1. **Check project status (Serena):**
   - `mcp__serena__list_memories()` → Available memories
   - `mcp__serena__read_memory("current-project-status")` → Current branch, latest changes, next priorities

2. **Search past implementations (Cipher):**
   - `mcp__cipher__cipher_memory_search(query="implementation keywords")` → Past design patterns, approaches, lessons learned

3. **Search workspace context (Cipher):**
   - `mcp__cipher__cipher_workspace_search(query="project context")` → Team progress, bugs, collaboration history

**Outcome:** Start implementation efficiently with existing knowledge

### Phase 2: During Implementation (During)

**Goal:** Visualize progress and decisions, enable easy restart after interruption

**Continuous Recording (Serena):**
- **When:** After important decisions, at work breakpoints, before interruptions
- **Tool:** `mcp__serena__write_memory(memory_name, content)`
- **Template:** See [memory-templates.md](./memory-templates.md) for Serena template

**Content to Record:**
- Current task in progress
- Completed work items
- Next steps
- Technical decisions with rationale
- Issues and blockers

**Update Frequency:** Every 1-2 hours during active development

### Phase 3: Post-Implementation (After)

**Goal:** Persist implementation knowledge as future development asset

**Long-Term Storage (Cipher):**
- **When:** Feature completion, refactoring completion, after major technical decisions
- **Tool:** `mcp__cipher__cipher_extract_and_operate_memory(interaction, memoryMetadata)`
- **Alternative:** `mcp__cipher__cipher_workspace_store(interaction)` for team context
- **Template:** See [memory-templates.md](./memory-templates.md) for Cipher template

**Content to Store:**
- Implementation overview and motivation
- Design approach and technology selection
- Implementation details and patterns
- Results and effects (performance, code reduction)
- Challenges and solutions
- Lessons learned and best practices
- Anti-patterns to avoid

## Memory Naming Conventions

### Serena Memory (Short-Term)
- `current-project-status` - Overall project status
- `active-development-tasks` - Current development tasks and progress
- `{feature}_wip_{YYYY_MM_DD}` - Work-in-progress feature implementation
- `debug_{issue}_{YYYY_MM_DD}` - Debug information and solutions
- `archived_{name}` - Completed task archive

### Cipher Memory (Long-Term)
**Title Format:** "LoRAIro [Feature] [Content] Design/Implementation"

**Examples:**
- "LoRAIro Direct Widget Communication Pattern Adoption"
- "LoRAIro Repository Pattern Database Design"
- "LoRAIro QRunnable Async Processing Implementation"

**Tags:** Technical domain, feature area, technology stack

## Workflow Integration

### Decision Tree
```
Development Task
├─ Before starting?
│  ├─ list_memories → check available memories
│  ├─ read_memory → review current status
│  └─ cipher_memory_search → find past patterns
├─ During implementation?
│  ├─ write_memory → record progress (Serena)
│  ├─ write_memory → record decisions (Serena)
│  └─ edit_memory → update existing notes (Serena)
└─ After completion?
   ├─ cipher_extract_and_operate_memory → store knowledge
   ├─ cipher_workspace_store → store team context
   └─ write_memory → update project status (Serena)
```

### Memory-First Best Practices

**Efficient Memory Usage:**
1. **Always check memory before implementation** - Leverage past knowledge
2. **Record regularly during implementation** - Easy restart after interruption
3. **Always persist after completion** - Build future development assets

**Recording Timing:**
- **Serena write:** After important decisions, work breakpoints, before interruptions
- **Cipher store:** Feature completion, refactoring completion, major technical decisions

**Content Guidelines:**

**Serena (Short-Term):**
- What are you working on now?
- What will you do next?
- What issues exist?
- What decisions were made? (temporary)

**Cipher (Long-Term):**
- Why was this design chosen?
- What technology selection was made?
- What results were obtained?
- What lessons were learned?

## LoRAIro-Specific Strategy

### Serena Memory Usage
- **current-project-status**: Check at start of each development session
- **active-development-tasks**: Update every 1-2 hours during implementation
- **Feature implementation notes**: Continuous recording for multi-day implementations

### Cipher Memory Usage
- **Architectural decisions**: Repository Pattern, Service Layer, Direct Widget Communication
- **Technology selection**: SQLAlchemy, PySide6, pytest rationale
- **Performance improvements**: Cache unification, async processing, approach
- **Refactoring**: Large-scale change intent, effects, lessons learned

### Search Keywords
- **Cipher search:** Specific pattern names ("repository pattern", "widget communication")
- **Technology + Purpose:** "sqlalchemy transaction", "pyside6 threading"
- **LoRAIro terms:** "direct widget communication", "memory-first development"

## Reference Files

- [memory-templates.md](./memory-templates.md) - Serena and Cipher memory templates
- [examples.md](./examples.md) - Complete implementation workflow examples
- [reference.md](./reference.md) - Full memory operation patterns and workflows
