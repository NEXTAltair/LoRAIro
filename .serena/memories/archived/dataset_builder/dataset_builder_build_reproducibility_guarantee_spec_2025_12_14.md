# Build Reproducibility Guarantee Specification

## Document Information

- **Version**: 1.1.0
- **Date**: 2025-12-14
- **Status**: Draft (Serena-managed)
- **Related**: Phase 2 Data Loss Fix, Phase 2.5 Input Normalization Enhancement

## Purpose

This specification defines the requirements and implementation strategies to ensure that the dataset build process is deterministic and reproducible.

## Definition of Reproducibility (Project Decision)

**Reproducibility**: Given identical input sources and build configuration, the build must produce the same **database content** (table rows), even if the SQLite database file bytes are not necessarily bit-for-bit identical.

Rationale:
- SQLite output bytes can vary due to page layout / VACUUM / SQLite version differences.
- The project primarily cares about stable tag taxonomy and relationships, not exact file bytes.

### Scope

**In Scope**:
- Tag ID assignment determinism
- Source processing order determinism
- Deduplication determinism (tags_v4.db)
- TAG_STATUS record creation determinism
- Content-level verification (sorted table export hash)

**Out of Scope**:
- Build performance (execution time may vary)
- Temporary file creation during build
- Log output formatting (content should be consistent, formatting may vary)
- SQLite file byte identity

## Deterministic Tag ID Assignment

### Requirement

All tag IDs in the TAGS table must be assigned in a deterministic, reproducible manner.

### Algorithm

```python
def merge_tags(
    existing_df: pl.DataFrame,
    new_df: pl.DataFrame,
    next_tag_id: int = 1
) -> pl.DataFrame:
    """
    Merge new tags with existing tags, assigning deterministic tag IDs.

    Determinism Strategy:
    1. unique() to remove duplicates within new_df
    2. sort("tag") to establish consistent ordering
    3. with_row_index(name="tag_id", offset=next_tag_id) to assign IDs
    """
    unique_new = new_df.unique(subset=["source_tag"])
    sorted_new = unique_new.sort("tag")
    tagged_new = sorted_new.with_row_index(name="tag_id", offset=next_tag_id)
    return pl.concat([existing_df, tagged_new])
```

## tags_v4.db Deduplication Determinism

### Requirement

When deduplicating tags from tags_v4.db, the same duplicate tags must always result in the same merged tag ID.

### Algorithm

```python
def _deduplicate_tags(df: pl.DataFrame) -> pl.DataFrame:
    """
    Deterministic deduplication by keeping minimum tag_id.

    Determinism Strategy:
    1. sort("tag_id") to establish consistent ordering
    2. unique(subset=["tag"], keep="first") to keep minimum tag_id
    """
    return df.sort("tag_id").unique(subset=["tag"], keep="first")
```

## Source Processing Order Determinism

### Requirement

Sources must be processed in a consistent, deterministic order.

### Key Design Decisions

1. **Explicit ordering**: input lists are defined explicitly (no filesystem glob iteration)
2. **No filesystem dependency**: avoid non-deterministic directory iteration order
3. **Sort before assigning IDs**: ensure stable ordering before `with_row_index`

## Verification (Content-Level)

### Content Hash Calculation

Compute a content hash from sorted exports of key tables.

Example approach:
- Export `TAGS` as rows sorted by `(tag_id)`
- Export `TAG_STATUS` as rows sorted by `(tag_id, format_id)`
- Concatenate as text and hash with SHA256

The exact mechanism may evolve, but the key requirement is:
- The hash is stable across runs with identical inputs.

## Version History

- **1.1.0 (2025-12-14)**: Move to Serena memories; redefine reproducibility as content-level, not byte-level.
- **1.0.0 (2025-12-14)**: Initial specification (byte-identical wording).
