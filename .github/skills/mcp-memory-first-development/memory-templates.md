# Memory Templates for Memory-First Development

This file provides ready-to-use templates for Serena short-term memory and Moltbot LTM (long-term memory via Notion) operations.

## Serena Memory Templates (Short-Term)

### Template 1: active-development-tasks

```markdown
# Current Implementation Status - YYYY-MM-DD

## In Progress
- [Current task being worked on]
  - [Specific subtask or component]
  - [Another aspect of the work]

## Completed
✅ [Completed item 1]
✅ [Completed item 2]
✅ [Completed item 3]

## Next Steps
1. [Next task to implement]
2. [Following task]
3. [Future task]

## Technical Decisions
- **Decision 1**: [What was decided]
  - **Rationale**: [Why this decision was made]
  - **Trade-offs**: [Advantages and disadvantages considered]

- **Decision 2**: [What was decided]
  - **Rationale**: [Why this decision was made]
  - **Alternatives**: [Other options considered]

## Issues & Blockers
- **Issue 1**: [Problem description]
  - **Status**: [Investigating / Workaround found / Blocked]
  - **Solution candidates**: [Possible solutions]

- **Issue 2**: [Problem description]
  - **Impact**: [How this affects development]
  - **Next action**: [What to try next]

## Notes
- [Any important observations or reminders]
```

### Template 2: {feature}_wip_{YYYY_MM_DD}

```markdown
# {Feature Name} Work in Progress - YYYY-MM-DD

## Feature Overview
[Brief description of the feature being implemented]

## Current Status
**Progress**: [X]% complete
**Started**: YYYY-MM-DD
**Target**: YYYY-MM-DD (if applicable)

## Implementation Plan
- [ ] Component 1: [Name]
- [ ] Component 2: [Name]
- [ ] Component 3: [Name]
- [ ] Testing
- [ ] Documentation

## Today's Work
**Goal**: [What you're trying to accomplish today]

**Progress**:
- ✅ [Completed today]
- 🔄 [In progress]
- ⏸️ [Paused/blocked]

## Code Changes
**Files Modified**:
- `path/to/file1.py` - [Brief description of changes]
- `path/to/file2.py` - [Brief description of changes]

**New Files**:
- `path/to/new_file.py` - [Purpose]

## Technical Notes
- [Important implementation details]
- [Design decisions for this feature]
- [Dependencies or integration points]

## Testing Notes
- [Test cases to write]
- [Edge cases to consider]
- [Manual testing steps]

## Questions / Uncertainties
- [Question 1 about implementation approach]
- [Question 2 about requirements]
```

### Template 3: debug_{issue}_{YYYY_MM_DD}

```markdown
# Debug: {Issue Name} - YYYY-MM-DD

## Problem Description
[Clear description of the issue]

## Reproduction Steps
1. [Step 1]
2. [Step 2]
3. [Step 3]
**Result**: [What happens]
**Expected**: [What should happen]

## Error Messages
```
[Full error message or stack trace]
```

## Investigation
**Hypothesis 1**: [Possible cause]
- **Test**: [How to verify]
- **Result**: [What happened]

**Hypothesis 2**: [Possible cause]
- **Test**: [How to verify]
- **Result**: [What happened]

## Root Cause
[Identified root cause of the issue]

## Solution
**Approach**: [How the issue was fixed]

**Code Changes**:
- `file1.py` line X: [Change description]
- `file2.py` line Y: [Change description]

**Verification**:
- [Test 1]: ✅ Pass
- [Test 2]: ✅ Pass

## Lessons Learned
- [What was learned from this debugging session]
- [How to prevent similar issues in the future]
```

### Template 4: current-project-status

```markdown
# LoRAIro Project Status - YYYY-MM-DD

## Current Branch
**Branch**: `feature/branch-name`
**Base**: `main` or `develop`
**Status**: [In development / Ready for review / Blocked]

## Latest Changes
**Completed** (last 7 days):
- ✅ [Feature/fix 1] - YYYY-MM-DD
- ✅ [Feature/fix 2] - YYYY-MM-DD

**In Progress**:
- 🔄 [Current work item 1]
- 🔄 [Current work item 2]

## Next Priorities
1. **[Priority 1]** - [Brief description]
2. **[Priority 2]** - [Brief description]
3. **[Priority 3]** - [Brief description]

## Dependencies
- [Dependency 1]: [Status]
- [Dependency 2]: [Status]

## Blockers
- [Blocker 1]: [Description and workaround if any]

## Notes
- [Important reminders or context for next session]
```

### Template 5: plan_{topic}_{YYYY_MM_DD} (Plan Mode Sync)

```markdown
# Plan: {topic}

**Created**: YYYY-MM-DD HH:MM:SS
**Source**: plan_mode | manual_sync
**Original File**: {plan-file}.md
**Status**: planning | implementing | completed

---

{original plan content from .claude/plans/}

## Implementation Notes
[Updates made during implementation - add as work progresses]

**Progress**:
- [ ] Phase 1: [Name]
- [ ] Phase 2: [Name]
- [ ] Phase 3: [Name]

**Deviations from Plan**:
- [Any changes made from original plan and rationale]

**Challenges Encountered**:
- [Challenge 1]: [How it was addressed]
- [Challenge 2]: [Current status]

## Outcome
[To be filled after implementation completion]

**Results**:
- [Result 1]
- [Result 2]

**Success Criteria Met**:
- ✅ [Criterion 1]
- ✅ [Criterion 2]
- ⚠️ [Criterion 3 - partially met]: [Explanation]

**Next Steps**:
- [Follow-up task 1]
- [Follow-up task 2]

**Extract to Moltbot LTM**:
- [ ] Important design decisions extracted to Moltbot LTM
- [ ] Reusable patterns documented
- [ ] Lessons learned captured
```

## Moltbot LTM Templates (Long-Term, Notion DB)

### Payload Structure

All Moltbot LTM writes use the following JSON structure via `POST /hooks/lorairo-memory`:

```json
{
  "title": "LoRAIro [Feature] [Content]",
  "summary": "[1-2 sentence summary]",
  "body": "[Markdown body - see templates below]",
  "type": "decision|howto|bug|note|reference",
  "importance": "High|Medium|Low",
  "tags": ["tag1", "tag2"],
  "source": "Container"
}
```

### Template 1: Feature Implementation Knowledge

**type**: `decision` | **importance**: `High`

**body template**:
```markdown
# Implementation Overview
[Concise description of what was implemented - 1-2 sentences]

## Background & Motivation
**Problem**: [What problem needed solving]
**Goal**: [What the implementation aimed to achieve]
**Context**: [LoRAIro project context, related features]

## Design Approach
**Architecture Pattern**: [Pattern used - e.g., Repository Pattern, Service Layer, MVC]

**Key Design Decisions**:
1. **Decision**: [Design choice made]
   - **Rationale**: [Why this approach was chosen]
   - **Alternatives considered**: [Other options and why they weren't chosen]
   - **Trade-offs**: [Benefits and drawbacks]

**Design Principles Applied**:
- [Principle 1 - e.g., SOLID, DRY, KISS]
- [Principle 2]

## Technology Selection
**Technologies Used**:
- **[Technology 1]**: [Purpose and selection rationale]
- **[Technology 2]**: [Purpose and selection rationale]

## Implementation Details
**Key Patterns**:
```python
# Pattern: [Pattern name]
class ExampleClass:
    """[Purpose of this pattern]"""
    def key_method(self) -> ReturnType:
        pass
```

## Results & Effects
**Metrics** (before → after):
- Performance: [e.g., 500ms → 50ms]
- Code reduction: [e.g., 300 lines → 100 lines]
- Test coverage: [e.g., 60% → 85%]

## Challenges & Solutions
**Challenge 1**: [Problem encountered]
- **Solution**: [How it was solved]

## Lessons Learned & Best Practices
**What Worked Well**:
- ✅ [Practice 1]

**What to Avoid**:
- ❌ [Anti-pattern 1]

**Reusable Patterns**:
- [Pattern 1]: Use when [scenario]
```

**tags example**: `["architecture", "repository-pattern", "database"]`

### Template 2: Refactoring Knowledge

**type**: `decision` | **importance**: `High`

**body template**:
```markdown
# Refactoring Overview
[What was refactored and why - 1-2 sentences]

## Motivation
**Pain Points** (before refactoring):
- [Problem 1]
- [Problem 2]

## Refactoring Approach
**Strategy**: [e.g., Incremental, Big Bang, Strangler Pattern]

**Steps Taken**:
1. [Step 1]
2. [Step 2]

## Before vs After
**Key Changes**:
- [Change 1]: [Impact]
- [Change 2]: [Impact]

## Impact Analysis
**Code Metrics** (before → after):
- Lines of code: [X → Y]
- Cyclomatic complexity: [A → B]

## Lessons Learned
**Success Factors**:
- ✅ [What made the refactoring successful]

**Challenges**:
- ⚠️ [Challenge encountered and solution]
```

**tags example**: `["refactoring", "performance", "state-management"]`

### Template 3: Architecture Decision Record (ADR)

**type**: `decision` | **importance**: `High`

**body template**:
```markdown
# Architecture Decision: [Decision Title]

## Status
**Status**: [Accepted / Deprecated / Superseded]
**Date**: YYYY-MM-DD

## Context
[Describe the issue or situation requiring a decision]

## Decision
[The decision that was made - clear and concise]

## Alternatives Considered
**Option 1**: [Alternative approach]
- **Pros**: [Advantages]
- **Cons**: [Disadvantages]
- **Reason not chosen**: [Why rejected]

## Consequences
**Positive**: ✅ [Benefit 1], ✅ [Benefit 2]
**Negative**: ⚠️ [Trade-off 1]

## Validation
**Success Criteria**: [How success will be measured]
```

**tags example**: `["architecture", "adr", "design-pattern"]`

## Usage Guidelines

### When to Use Each Template

**Serena Templates** (use during implementation):
- **active-development-tasks**: Daily development tracking
- **{feature}_wip_{YYYY_MM_DD}**: Multi-day feature implementation
- **debug_{issue}_{YYYY_MM_DD}**: Bug investigation and resolution
- **current-project-status**: Overall project state tracking
- **plan_{topic}_{YYYY_MM_DD}**: Plan Mode sync (auto/manual from `.claude/plans/`)

**Moltbot LTM Templates** (use after completion):
- **Feature Implementation**: After completing a feature or component
- **Refactoring Knowledge**: After major code refactoring
- **Architecture Decision Record**: After making architectural decisions

### Template Adaptation
- Modify templates to fit specific needs
- Add/remove sections as appropriate
- Maintain consistent structure for searchability
- Use clear, descriptive titles for LTM search

### Moltbot LTM Metadata

**Type selection guide**:
| Scenario | type | importance |
|----------|------|-----------|
| Architectural decision | `decision` | `High` |
| Implementation pattern | `howto` | `Medium` |
| Bug resolution | `bug` | `Medium` |
| Progress milestone | `note` | `Low` |
| API/tech specification | `reference` | `Medium` |

**Tags** (free-form, will be lowercased):
- Technical domain: `gui`, `database`, `testing`, `ai-integration`
- Technology: `pyside6`, `sqlalchemy`, `pytest`
- Pattern: `repository-pattern`, `service-layer`, `async-worker`
- Feature area: `annotation`, `search`, `filtering`
