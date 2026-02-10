---
name: mcp-memory-first-development
version: "2.0.0"
description: Memory-First development workflow integrating Serena short-term project memory and OpenClaw long-term design knowledge (Notion DB) for efficient development. Use this skill to guide the 3-phase workflow (Before → During → After implementation) with proper memory management.
metadata:
  short-description: メモリファースト開発（Serena短期＋OpenClaw長期LTM）で効率化。
allowed-tools:
  # Serena memory (short-term)
  - mcp__serena__read_memory
  - mcp__serena__write_memory
  - mcp__serena__list_memories
  - mcp__serena__edit_memory
  # OpenClaw LTM (long-term, via lorairo-mem skill)
  - Bash
dependencies:
  - lorairo-mem
---

# Memory-First Development

Integrates Serena short-term project memory and OpenClaw long-term design knowledge (Notion DB) for efficient development workflow.

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
│ OpenClaw LTM (Long-Term, Notion DB)         │
├─────────────────────────────────────────────┤
│ • Design approaches and rationale           │
│ • Architectural intent and background       │
│ • Performance and maintainability analysis  │
│ • Implementation challenges and solutions   │
│ • Best practices and anti-patterns          │
│ • Technology selection criteria and results │
├─────────────────────────────────────────────┤
│ Characteristics:                            │
│ • Persistent (Notion DB, hash de-duped)     │
│ • Searchable (filter + free-text query)     │
│ • Structured (title, summary, body, type)   │
│ • Shared (accessible from any environment)  │
└─────────────────────────────────────────────┘
```

### Serena Memory (Short-Term)
**Purpose:** Current development progress and temporary notes
**Access:** 0.3-0.5s (fast)
**Lifecycle:** Temporary (archive or delete after task completion)
**Scope:** Project-specific (LoRAIro only)

### OpenClaw LTM (Long-Term)
**Purpose:** Reusable design pattern assets stored in Notion
**Access:** 1-3s (HTTP webhook)
**Lifecycle:** Persistent (Notion DB, hash-based de-duplication)
**Scope:** Shared across environments (Container, WSL, CI)

## Memory-First Development Cycle

### Phase 1: Pre-Implementation (Before)

**Goal:** Leverage past knowledge, avoid duplicate work

**Checklist:**
1. **Check project status (Serena):**
   - `mcp__serena__list_memories()` → Available memories
   - `mcp__serena__read_memory("current-project-status")` → Current branch, latest changes, next priorities

2. **Search past implementations (OpenClaw LTM):**
   ```bash
   python3 .github/skills/lorairo-mem/scripts/ltm_search.py <<'JSON'
   {"limit": 10, "filters": {"type": ["decision", "howto"], "tags": ["implementation-keyword"]}}
   JSON
   ```

3. **Check latest LTM entries:**
   ```bash
   python3 .github/skills/lorairo-mem/scripts/ltm_latest.py <<'JSON'
   {"limit": 5}
   JSON
   ```

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

**Long-Term Storage (OpenClaw LTM):**
- **When:** Feature completion, refactoring completion, after major technical decisions
- **Tool:** `POST /hooks/lorairo-memory` via curl (see lorairo-mem skill)
- **Template:** See [memory-templates.md](./memory-templates.md) for LTM template

**Write example:**
```bash
curl -sS -X POST http://host.docker.internal:18789/hooks/lorairo-memory \
  -H "Authorization: Bearer $HOOK_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "LoRAIro [Feature] Implementation",
    "summary": "Design approach and lessons learned",
    "body": "# Implementation Overview\n\n## Design Approach\n...",
    "type": "decision",
    "importance": "High",
    "tags": ["architecture", "pattern-name"],
    "source": "Container"
  }'
```

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

### OpenClaw LTM (Long-Term)
**Title Format:** "LoRAIro [Feature] [Content] Design/Implementation"

**Examples:**
- "LoRAIro Direct Widget Communication Pattern Adoption"
- "LoRAIro Repository Pattern Database Design"
- "LoRAIro QRunnable Async Processing Implementation"

**Type mapping:**
- `decision` - Architectural decisions, technology selection
- `howto` - Implementation patterns, best practices
- `note` - Implementation records, progress milestones
- `reference` - Technical specifications, API documentation
- `bug` - Issue resolutions, debugging lessons

**Tags:** Technical domain, feature area, technology stack (free-form, lowercased)

## Workflow Integration

### Decision Tree
```
Development Task
├─ Before starting?
│  ├─ list_memories → check available memories (Serena)
│  ├─ read_memory → review current status (Serena)
│  └─ ltm_search.py → find past patterns (OpenClaw)
├─ During implementation?
│  ├─ write_memory → record progress (Serena)
│  ├─ write_memory → record decisions (Serena)
│  └─ edit_memory → update existing notes (Serena)
└─ After completion?
   ├─ POST /hooks/lorairo-memory → store knowledge (OpenClaw)
   └─ write_memory → update project status (Serena)
```

### Memory-First Best Practices

**Efficient Memory Usage:**
1. **Always check memory before implementation** - Leverage past knowledge
2. **Record regularly during implementation** - Easy restart after interruption
3. **Always persist after completion** - Build future development assets

**Recording Timing:**
- **Serena write:** After important decisions, work breakpoints, before interruptions
- **OpenClaw store:** Feature completion, refactoring completion, major technical decisions

**Content Guidelines:**

**Serena (Short-Term):**
- What are you working on now?
- What will you do next?
- What issues exist?
- What decisions were made? (temporary)

**OpenClaw LTM (Long-Term):**
- Why was this design chosen?
- What technology selection was made?
- What results were obtained?
- What lessons were learned?

## LoRAIro-Specific Strategy

### Serena Memory Usage
- **current-project-status**: Check at start of each development session
- **active-development-tasks**: Update every 1-2 hours during implementation
- **Feature implementation notes**: Continuous recording for multi-day implementations

### OpenClaw LTM Usage
- **Architectural decisions**: Repository Pattern, Service Layer, Direct Widget Communication
- **Technology selection**: SQLAlchemy, PySide6, pytest rationale
- **Performance improvements**: Cache unification, async processing, approach
- **Refactoring**: Large-scale change intent, effects, lessons learned

### Search Examples
```bash
# Search by type and tags
python3 .github/skills/lorairo-mem/scripts/ltm_search.py <<'JSON'
{"limit": 10, "filters": {"type": ["decision", "howto"], "tags": ["repository-pattern"]}}
JSON

# Search by importance
python3 .github/skills/lorairo-mem/scripts/ltm_search.py <<'JSON'
{"limit": 5, "filters": {"importance": ["High"]}}
JSON

# Latest entries
python3 .github/skills/lorairo-mem/scripts/ltm_latest.py <<'JSON'
{"limit": 10}
JSON
```

## Plan Mode Integration

### Overview

Claude Code's Plan Mode is integrated with the Memory-First workflow through automatic synchronization to Serena Memory.

**Key Features:**
- **Auto-sync:** Plan Mode plans automatically sync to `.serena/memories/` via PostToolUse hook
- **Manual sync:** `/sync-plan` command for manual synchronization or historical plans
- **Template:** Dedicated `plan_{topic}_{YYYY_MM_DD}` template in memory-templates.md

### Plan Mode vs /planning Command

**Plan Mode** (Quick Task Planning):
- **Use for:** Single-feature implementation, immediate execution tasks
- **Duration:** 5-10 minutes
- **Output:** `.claude/plans/` → Auto-sync to Serena Memory
- **Memory:** Serena + OpenClaw LTM (search required, storage optional)
- **Workflow:** LTM search → Plan creation → Auto-sync on exit → (optional) LTM storage

**/planning Command** (Comprehensive Design):
- **Use for:** Complex architecture decisions, multi-phase features
- **Duration:** 20-40 minutes
- **Output:** OpenClaw LTM (design patterns) + Serena Memory (current status)
- **Memory:** Serena + OpenClaw (shared knowledge)
- **Workflow:** Investigation + Library Research + Solutions agents

### Plan Mode Workflow

```
┌──────────────────┐
│  LTM Search      │ Search past design patterns from OpenClaw LTM
│  (Pre-Planning)  │ ltm_search.py + ltm_latest.py
└────────┬─────────┘
         │
         ↓ Serena Memory check (current-project-status)
┌──────────────────┐
│   Plan Mode      │ Create plan with context from LTM + Serena
│  (Native UI)     │
└────────┬─────────┘
         │
         ↓ Exit Plan Mode (trigger PostToolUse hook)
┌──────────────────┐
│   Auto-Sync      │ hook_post_plan_mode.py executes
│  .claude/plans/  │ → .serena/memories/plan_{topic}_{date}.md
│  → Serena Memory │
└────────┬─────────┘
         │
         ↓ Implementation phase
┌──────────────────┐
│  Update Memory   │ Add implementation notes, progress, challenges
│  During Dev      │ Use mcp__serena__edit_memory to update plan
└────────┬─────────┘
         │
         ↓ After completion
┌──────────────────┐
│ Extract to       │ Important design decisions → OpenClaw LTM
│ OpenClaw LTM     │ ltm_write.py or POST /hooks/lorairo-memory
└──────────────────┘
```

### Memory Naming Convention

Plan Mode files are synced with this naming pattern:

**File name:** `plan_{sanitized_topic}_{YYYY_MM_DD}.md`

**Sanitization rules:**
- Hyphens (-) → Underscores (_)
- Special characters → Removed
- Lowercase conversion

**Examples:**
- Input: `moonlit-munching-yeti.md` (Plan Mode file)
- Output: `plan_moonlit_munching_yeti_2025_12_21.md` (Serena Memory)

### Using Synced Plans

**Reading a plan:**
```javascript
mcp__serena__read_memory("plan_moonlit_munching_yeti_2025_12_21")
```

**Updating during implementation:**
```javascript
mcp__serena__edit_memory(
  "plan_moonlit_munching_yeti_2025_12_21",
  "## Implementation Notes\n- Completed Phase 1\n- Issue encountered in Phase 2: [description]",
  "regex"
)
```

**Listing all plans:**
```javascript
mcp__serena__list_memories() // Look for files starting with "plan_"
```

### Manual Sync with /sync-plan

Use `/sync-plan` command when:
- Auto-sync hook is disabled
- Syncing historical plans from `.claude/plans/`
- Auto-sync failed and needs manual retry

**Usage:**
```bash
/sync-plan                    # Sync latest plan
/sync-plan my-feature.md     # Sync specific plan
```

### Integration with Memory-First Cycle

**Phase 1 (Before) — Required for both Plan Mode and /planning:**
1. Search OpenClaw LTM for past design patterns:
   ```bash
   python3 .github/skills/lorairo-mem/scripts/ltm_search.py <<'JSON'
   {"limit": 5, "filters": {"type": ["decision", "howto"], "tags": ["relevant-tag"]}}
   JSON
   ```
2. Check latest LTM entries:
   ```bash
   python3 .github/skills/lorairo-mem/scripts/ltm_latest.py <<'JSON'
   {"limit": 5}
   JSON
   ```
3. Check Serena Memory: `mcp__serena__list_memories()` → Look for `plan_*` files
4. Review past plans if similar feature was planned before

**Phase 2 (During):**
- Update plan memory with implementation notes
- Record deviations from original plan and rationale
- Track progress against plan phases

**Phase 3 (After):**
- Extract important design decisions to OpenClaw LTM:
  ```bash
  python3 .github/skills/lorairo-mem/scripts/ltm_write.py <<'JSON'
  {
    "title": "LoRAIro [Feature] Design Decision",
    "summary": "Brief summary",
    "body": "# Details\n\n...",
    "type": "decision",
    "importance": "High",
    "tags": ["relevant-tag"],
    "source": "Container"
  }
  JSON
  ```
- Update plan status to "completed"
- Record lessons learned vs original plan

### Best Practices

1. **Use Plan Mode for quick planning**, use `/planning` for comprehensive design
2. **Update plan memories during implementation** to track deviations and challenges
3. **Extract to OpenClaw LTM after completion** if plan contains reusable design patterns
4. **Reference plans from other agents** by reading Serena memory files
5. **Archive completed plans** by prefixing with `archived_` or deleting after LTM extraction

## Reference Files

- [memory-templates.md](./memory-templates.md) - Serena and OpenClaw LTM memory templates
- [examples.md](./examples.md) - Complete implementation workflow examples
- [reference.md](./reference.md) - Full memory operation patterns and workflows
