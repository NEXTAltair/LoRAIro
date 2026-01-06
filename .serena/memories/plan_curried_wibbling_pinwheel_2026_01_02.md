# Plan: curried-wibbling-pinwheel

**Created**: 2026-01-02 00:00:44
**Source**: plan_mode
**Original File**: curried-wibbling-pinwheel.md
**Status**: planning

---

# CLAUDE.md Resilience Improvement Plan

## Executive Summary

CLAUDE.md has become outdated due to repeated design changes. This plan addresses:
- **30+ critical inaccuracies** (wrong paths, missing services, outdated integrations)
- **Fundamental maintenance problem**: Manual documentation lags behind fast-paced development
- **Solution**: Multi-layered documentation structure with automated validation

## Problem Analysis

### Current Issues (from codebase analysis)

**Critical Path Errors:**
- ❌ `main_workspace_window.py` → Actually `main_window.py`
- ❌ `ai_annotator.py` → Actually `annotator_adapter.py` + `annotation_logic.py`
- ❌ `cleanup_txt.py` → Doesn't exist; integration is in `db_repository.py`

**Service Layer Undercounting:**
- Documented: 5 services (ImageProcessingService, ConfigurationService, etc.)
- Actual: 30+ services including:
  - Business Logic (18+): TagManagementService, ServiceContainer, DataTransformService, etc.
  - GUI Services (12+): ResultHandlerService, PipelineControlService, etc.

**Missing Recent Changes (Dec 2025 - Jan 2026):**
- Qt-free core vs Qt-dependent GUI service separation (2025-12-29)
- Tag Management System Phase 2/2.5 (2025-12-30)
- MainWindow 5-stage initialization (2025-11-19)
- Public API migration for genai-tag-db-tools (2025-12-28)
- pytest-qt best practices
- User DB only strategy for TagManagementService (2026-01-01)

### Root Cause

**Documentation Decay Pattern:**
1. Developer implements feature → updates code
2. Memory files record change → `.serena/memories/plan_*.md`
3. CLAUDE.md update forgotten → documentation lags
4. Cycle repeats → gap widens exponentially

## Recommended Solution: Layered Documentation Architecture

### Design Philosophy

**Principle: Separate Stable from Volatile**
- **Stable content** (changes yearly): Architecture principles, design patterns, workflows
- **Volatile content** (changes monthly): File paths, service lists, API signatures
- **Semi-stable content** (changes quarterly): Integration patterns, testing strategies

### Three-Layer Structure

#### Layer 1: CLAUDE.md (High-Level Guide)
**Purpose:** AI agent orientation + workflow guidance
**Update frequency:** Quarterly or on major architecture changes
**Contents:**
- Core development principles (YAGNI, readability-first)
- Standard workflow (commands, Plan Mode vs /planning)
- Architecture patterns (Repository, Service Layer, Worker)
- How to find detailed information (links to Layer 2/3)

#### Layer 2: docs/ (Technical Specifications)
**Purpose:** Detailed architecture and API documentation
**Update frequency:** On feature completion
**Contents:**
- `docs/architecture.md`: System design, component relationships
- `docs/services.md`: **NEW** - Complete service catalog with responsibilities
- `docs/integrations.md`: **NEW** - External package integration patterns
- `docs/testing.md`: **NEW** - Testing strategies and patterns

#### Layer 3: Code (Source of Truth)
**Purpose:** Always accurate implementation details
**Update frequency:** Real-time (on every commit)
**Contents:**
- Python docstrings (Google style)
- Type hints
- Module-level comments
- Inline implementation notes

### Validation Strategy

**Automated Checks (via pre-commit hook or CI):**
1. Service existence validation: Scan `src/lorairo/services/` and `src/lorairo/gui/services/`
2. File path validation: Check all referenced paths exist
3. Integration point validation: Verify import statements match documentation

**Manual Review Checklist (on major changes):**
- [ ] Update memory files (automatic via Plan Mode)
- [ ] Update Layer 2 docs (architecture.md, services.md)
- [ ] Review CLAUDE.md for obsolete patterns (quarterly)

## Implementation Plan

### Phase 1: Content Audit & Correction (Priority: Critical)

**Task 1.1: Fix Path Errors in CLAUDE.md**
- Line 115: `main_workspace_window.py` → `main_window.py`
- Line 142: Remove reference to `ai_annotator.py`
- Line 146: Remove reference to `cleanup_txt.py`
- Add: Actual integration files (`annotator_adapter.py`, `annotation_logic.py`, `db_repository.py`)

**Task 1.2: Update Service Layer Documentation**
- Replace "5 services" section with reference to comprehensive list
- Add note: "See docs/services.md for complete catalog (30+ services)"
- Keep examples of key patterns: ServiceContainer, 2-tier architecture

**Task 1.3: Document Recent Design Changes**
- Add "Qt-Free Core Pattern" section (composition over inheritance)
- Add "Tag Management System" section (Phase 2/2.5 features)
- Add "External Tag DB Integration" (user DB vs base DB)
- Update "MainWindow" description (5-stage initialization, 688 lines)

### Phase 2: Create Layer 2 Documentation (Priority: High)

**Task 2.1: Create docs/services.md**
Structure:
```markdown
# Service Layer Architecture

## Overview
Two-tier architecture: Business Logic (Qt-free) + GUI Services (Qt-dependent)

## Business Logic Services (src/lorairo/services/)
### Core Services
- **ServiceContainer**: Dependency injection container [file path]
- **ConfigurationService**: Application configuration [file path]
- ... (all 18+ services with one-line descriptions)

## GUI Services (src/lorairo/gui/services/)
- **SearchFilterService**: GUI-focused search operations [file path]
- ... (all 12+ services)

## Design Patterns
### Qt-Free Core Pattern
- Core services: No Qt dependencies
- GUI wrappers: Composition pattern, Signal support
- Example: TagRegisterService (core) + GuiTagRegisterService (wrapper)
```

**Task 2.2: Create docs/integrations.md**
Content:
- genai-tag-db-tools integration points (public API usage)
- image-annotator-lib integration points (multi-provider annotation)
- User DB initialization strategy
- format_id collision avoidance (1000+ reservation)

**Task 2.3: Create docs/testing.md**
Content:
- pytest-qt best practices (waitSignal, waitUntil patterns)
- Coverage targets (75%+)
- Test structure (unit/integration/BDD)
- Mock strategies (external dependencies only)

### Phase 3: Restructure CLAUDE.md (Priority: High)

**Task 3.1: Reduce Volatile Content**
Remove detailed listings, replace with references:
- Service lists → "See docs/services.md"
- Integration details → "See docs/integrations.md"
- Testing patterns → "See docs/testing.md"

**Task 3.2: Keep Essential Patterns**
Retain in CLAUDE.md:
- Virtual environment rules (critical for development)
- Development commands (frequently used)
- Architecture patterns overview (Repository, Service Layer, etc.)
- Problem-solving approach (YAGNI, readability-first)
- Quick reference commands

**Task 3.3: Add Maintenance Guidelines**
New section: "Maintaining This Documentation"
```markdown
## Documentation Maintenance

### When to Update
- **CLAUDE.md**: Quarterly review or major architecture changes
- **docs/*.md**: On feature completion or pattern changes
- **Code docstrings**: On every implementation

### Update Checklist
- [ ] Memory files auto-updated via Plan Mode
- [ ] docs/*.md updated with new patterns/services
- [ ] CLAUDE.md reviewed for obsolete sections
- [ ] Validation script run (if available)

### Validation
Run: `python scripts/validate_docs.py` (to be created)
```

### Phase 4: Create Validation Tooling (Priority: Medium)

**Task 4.1: Create scripts/validate_docs.py**
Features:
- Scan all file paths referenced in CLAUDE.md and docs/*.md
- Verify paths exist
- Check service lists match actual directory contents
- Report mismatches

**Task 4.2: Add Pre-commit Hook (Optional)**
- Run validation on CLAUDE.md/docs changes
- Warn if service count mismatches
- Block commit if critical paths broken

### Phase 5: Migration & Testing (Priority: High)

**Task 5.1: Migrate Content**
1. Extract volatile content from CLAUDE.md
2. Create comprehensive docs/services.md
3. Create docs/integrations.md
4. Create docs/testing.md
5. Update CLAUDE.md with references

**Task 5.2: Validation Pass**
1. Run validation script
2. Manually verify all links work
3. Test AI agent comprehension (run simple task with updated CLAUDE.md)

**Task 5.3: Update Memory**
Create `.serena/memories/claude_md_resilience_architecture_2026_01_01.md`:
- Document new layered structure
- Explain maintenance workflow
- Record design decisions

## Critical Files to Modify

### Direct Edits
1. `CLAUDE.md` - Main refactor
2. `docs/services.md` - NEW FILE - Service catalog
3. `docs/integrations.md` - NEW FILE - Integration patterns
4. `docs/testing.md` - NEW FILE - Testing strategies
5. `scripts/validate_docs.py` - NEW FILE - Validation tool

### Reference Only (verify accuracy)
- `src/lorairo/gui/window/main_window.py`
- `src/lorairo/services/` (entire directory)
- `src/lorairo/gui/services/` (entire directory)
- `src/lorairo/annotations/annotator_adapter.py`
- `src/lorairo/database/db_repository.py`

## Success Criteria

### Immediate (Post-Implementation)
- [ ] All file paths in CLAUDE.md are correct
- [ ] All 30+ services documented in docs/services.md
- [ ] Recent design changes (Dec 2025-Jan 2026) documented
- [ ] Validation script passes 100%

### Long-term (3-6 months)
- [ ] Documentation updates take <10 minutes (vs 1+ hour currently)
- [ ] AI agents reference correct file paths
- [ ] New developers find services via docs/services.md
- [ ] CLAUDE.md remains stable (no major rewrites needed)

## Maintenance Workflow (Post-Implementation)

### On Feature Completion
1. Memory auto-updated (Plan Mode hook)
2. Update docs/services.md if new service added
3. Update docs/integrations.md if integration changed
4. Run `python scripts/validate_docs.py`

### Quarterly Review
1. Read through CLAUDE.md for obsolete patterns
2. Update architecture patterns if needed
3. Verify docs/*.md still accurate
4. Run full validation

### On Major Architecture Change
1. Update affected docs/*.md files first
2. Update CLAUDE.md references if structure changed
3. Create memory file documenting change
4. Run validation

## Risk Mitigation

**Risk: Developers ignore Layer 2 docs**
- Mitigation: Make docs/*.md clearly referenced in CLAUDE.md
- Mitigation: Validation script enforces accuracy

**Risk: Validation script becomes outdated**
- Mitigation: Keep validation logic simple (path existence checks)
- Mitigation: Review validation script quarterly

**Risk: Too much fragmentation**
- Mitigation: Keep CLAUDE.md as primary entry point
- Mitigation: Layer 2 docs are supplements, not replacements

## Timeline Estimate

- Phase 1 (Critical fixes): 1-2 hours
- Phase 2 (Layer 2 docs): 2-3 hours
- Phase 3 (Restructure): 1-2 hours
- Phase 4 (Validation): 1-2 hours
- Phase 5 (Migration): 1 hour
- **Total**: 6-10 hours of focused work

## Next Steps

1. User approval of this plan
2. Execute Phase 1 (critical path fixes)
3. Create Layer 2 documentation files
4. Restructure CLAUDE.md
5. Build validation tooling
6. Final validation pass
