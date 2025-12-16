# Source Priority and Conflict Resolution Specification

## Document Information

- **Version**: 1.1.0
- **Date**: 2025-12-14
- **Status**: Draft (Serena-managed)
- **Related**: Phase 2 Data Loss Fix, Phase 2.5 Input Normalization Enhancement

## Update Notes (Project Decisions)

- This document is managed under `.serena/memories/` (not `local_packages/.../docs`).
- **No global priority across posting sites** (different `format_id` are treated as different namespaces; danbooru/e621/derpibooru are "equal value").
- Conflicts are handled primarily **within the same `format_id`** (e.g., `e621_tags_jsonl.csv` vs `e621.csv`), and any semantic conflict must be **reported for manual resolution** (no silent auto-fix).
- `source_tag` representative rule: baseline `tags_v4.db` is imported first; `source_tag` is stored **lowercased** (case-only variants are treated as noise).

## Purpose

This specification defines how tag data sources are processed and how conflicts are detected and handled when building the unified tag database.

## Source Processing Model

### 1) Baseline import (tags_v4.db)

`tags_v4.db` is imported first as the baseline taxonomy.

### 2) Posting site imports (CSV/JSON/Parquet)

Posting sites are separated by `format_id`, so cross-site conflicts are generally not meaningful (they are different namespaces).

### 3) Same-format multi-source rule (internal priority)

When multiple sources exist for the **same format_id** (example: e621 has both JSONL export and CSV export), the build must:

- Prefer the higher quality source for *non-semantic* conflicts if needed (e.g., JSONL over CSV for e621), **but**
- Still emit a conflict report for any semantic mismatch (type/alias/preferred mismatch) so the user can decide.

## Same-Format Priority Order (Only When Applicable)

This is **not** a site-to-site priority; it applies only when sources share the same `format_id`.

| Priority | Source | Format ID | Rationale |
|----------|--------|-----------|-----------
|
| 1 (Highest) | tags_v4.db | N/A | Baseline taxonomy (imported first) |
| 2 | e621_tags_jsonl.csv | 2 | Higher quality export than CSV |
| 3 | e621.csv | 2 | Lower-quality export (fallback) |

For other posting sites (e.g., danbooru=1, derpibooru=3), there is no comparable internal priority unless multiple sources for the same format are added later.

### Build Order in builder.py (Current)

The sources are processed in the following phases:

1. **Phase 2: Import tags_v4.db baseline**
   - Establishes initial tag taxonomy
   - Subject to deduplication (see below)

2. **Phase 3: Import CSV sources (Two-Pass Processing)**
   - Pass 1: Collect all tags (source_tag + deprecated_tags)
   - Pass 2: Create TAG_STATUS records with complete tags_mapping

3. **Phase 4: Import HuggingFace datasets** (Future)
   - External data sources (e.g., deepghs/site_tags)

## tags_v4.db Deduplication Strategy

### Background

The existing tags_v4.db database does **not** have a `UNIQUE(tag)` constraint. Actual data contains duplicate tag entries (e.g., multiple rows for "witch" with different tag_id values).

The new unified database **requires** a `UNIQUE(tag)` constraint to ensure data integrity.

### Deduplication Algorithm

When importing tags_v4.db, duplicate tags are merged using the following strategy:

```python
def _deduplicate_tags(df: pl.DataFrame) -> pl.DataFrame:
    """
    Merge duplicate tags by keeping the entry with the minimum tag_id.

    Strategy:
    1. Sort by tag_id (ascending)
    2. Apply unique(subset=["tag"], keep="first")
    3. Result: Minimum tag_id preserved, first source_tag selected
    """
    return df.sort("tag_id").unique(subset=["tag"], keep="first")
```

**Example**:
```
Input (tags_v4.db):
  tag_id | tag   | source_tag
  -------|-------|------------
  5      | witch | sorceress
  12     | witch | witch
  18     | witch | mage

Output (deduplicated):
  tag_id | tag   | source_tag
  -------|-------|------------
  5      | witch | sorceress  # Minimum tag_id preserved
```

### TAG_STATUS Conflict Detection

After deduplication, TAG_STATUS records may have conflicts for the same (tag, format_id) combination. The system detects and reports these conflicts but does **not** automatically resolve them.

```python
def _detect_tag_status_conflicts(df: pl.DataFrame) -> list[dict]:
    """
    Detect TAG_STATUS records with different metadata for the same (tag, format_id).

    Conflicts occur when:
    - Different alias values (True vs False)
    - Different type_id values (e.g., 1 vs 4)
    - Different preferred_tag_id values
    """
    # JOIN TAGS + TAG_STATUS, group by (tag, format_id)
    # Report rows where count > 1 (multiple metadata versions)
```

**Conflict Handling**:
- **Detection**: Logged as WARNING with full details
- **Resolution**: Manual review required (CSV export for human inspection)
- **Rationale**: Preserves human decision-making for ambiguous cases

## Conflict Resolution Rules

When multiple sources provide metadata for the same tag, conflicts are resolved using the following rules:

### Rule 1: type_id Conflicts

**Scenario**: Different sources assign different type_id values to the same tag.

**Resolution**:
1. Prefer the higher-quality source only if needed for automatic selection
2. Always log the conflict to CSV for manual review

### Rule 2: alias Changes

**Scenario**: Different sources provide conflicting alias relationships.

**Resolution**:
1. Do not auto-resolve semantic alias conflicts
2. Log the conflict to CSV for manual review

### Rule 3: New Tag Insertion

**Scenario**: A tag exists in an input source but not in TAGS yet.

**Resolution**:
1. Add the new tag to TAGS table
2. Assign tag_id deterministically (see `dataset_builder_build_reproducibility_guarantee_spec_2025_12_14`)
3. Create TAG_STATUS records with metadata from the source

### Rule 4: Duplicate Tag Merging (tags_v4.db only)

**Scenario**: tags_v4.db contains multiple entries for the same tag.

**Resolution**:
1. Keep the entry with the **minimum tag_id**
2. Discard other entries
3. Detect TAG_STATUS conflicts and report for manual review

## Implementation References

### Code Locations

- **Deduplication**: `tags_v4_adapter.py` (`_deduplicate_tags()`)
- **Conflict Detection**: `tags_v4_adapter.py` (`_detect_tag_status_conflicts()`)
- **Two-Pass Processing**: `builder.py` (Pass 1 collect, Pass 2 create)

### Test Coverage

- **Unit Test**: `test_tags_v4_adapter.py::test_deduplicate_tags_removes_duplicates`
- **Integration Test**: `test_two_pass_alias_registration.py::test_two_pass_prevents_data_loss`

## Version History

- **1.1.0 (2025-12-14)**: Move to Serena memories; clarify "no site-to-site priority"; manual conflict resolution.
- **1.0.0 (2025-12-14)**: Initial specification with tags_v4.db deduplication strategy
