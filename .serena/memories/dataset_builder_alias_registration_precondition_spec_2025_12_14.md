# Alias Registration Precondition Specification

## Document Information

- **Version**: 1.0.1
- **Date**: 2025-12-14
- **Status**: Draft (Serena-managed)
- **Related**: Phase 2 Data Loss Fix Implementation

## Purpose

This specification defines the **preconditions** required for successful alias registration in TAG_STATUS records. It ensures that all deprecated tags (aliases) are properly registered in the TAGS table before creating TAG_STATUS relationships, preventing data loss.

## Problem Statement

### Critical Data Loss Scenario

**Original Implementation (Single-Pass)**:
```python
# ⚠️ DATA LOSS: Tags not yet in TAGS table
for row in csv_df.iter_rows():
    source_tag = row["source_tag"]
    deprecated_tags = row["deprecated_tags"]  # e.g., "alias1,alias2,alias3"

    # Register source_tag in TAGS
    tag_id = register_tag(source_tag)

    # Create TAG_STATUS for aliases
    for alias in deprecated_tags.split(","):
        alias_id = tags_mapping.get(alias)  # ⚠️ alias_id may be None if alias not in TAGS
        if alias_id:
            create_tag_status(alias_id, tag_id, format_id)
        else:
            # ⚠️ SILENT DATA LOSS: Alias relationship permanently lost
            pass
```

**Consequence**: If `alias1` is not yet in the TAGS table (e.g., it will be registered in a later CSV row), the TAG_STATUS record is silently skipped, and the alias relationship is **permanently lost**.

### Root Cause

**Violation of Precondition**: `process_deprecated_tags()` requires that **all tags in deprecated_tags are already registered in TAGS**. Single-pass processing cannot guarantee this precondition.

## Precondition Requirements

### Formal Precondition

**Function**: `process_deprecated_tags(canonical_tag, deprecated_tags, format_id, tags_mapping)`

**Precondition**:
```
∀ alias ∈ deprecated_tags.split(","):
    normalize_tag(alias) ∈ tags_mapping.keys()
```

**In English**: Every tag in the `deprecated_tags` string must have a corresponding entry in the `tags_mapping` dictionary (i.e., must be registered in the TAGS table).

## Two-Pass Algorithm

### Overview

The **Two-Pass Processing** algorithm ensures the precondition is met by separating tag collection from relationship creation.

**Pass 1: Tag Collection**
1. Read all CSV files
2. Extract all tags (source_tag + deprecated_tags)
3. Merge all tags into TAGS table
4. Build complete tags_mapping dictionary

**Pass 2: Relationship Creation**
1. Re-read CSV files
2. Create TAG_STATUS records using complete tags_mapping
3. Precondition guaranteed: All tags are now in tags_mapping

## Related Specifications (Serena)

- `dataset_builder_source_priority_and_conflict_resolution_spec_2025_12_14.md`
- `dataset_builder_build_reproducibility_guarantee_spec_2025_12_14.md`

## Version History

- **1.0.1 (2025-12-14)**: Move to Serena memories; update related-spec references.
- **1.0.0 (2025-12-14)**: Initial specification with two-pass algorithm.
