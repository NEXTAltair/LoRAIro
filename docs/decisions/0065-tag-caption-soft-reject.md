---
type: ADR
title: Tag/Caption Soft-Reject And Export Resolution
status: Accepted
timestamp: 2026-06-11
tags: []
---
# ADR 0065: Tag/Caption Soft-Reject And Export Resolution

## Context

Tag and caption annotations can be produced by multiple models for the same image. Tags were exported by concatenating every row, so identical strings from different models appeared more than once. Captions were also concatenated into one `.caption` file, which creates invalid training text when several models remain.

Physical deletion is not a durable reject operation. A rejected tag or caption can be inserted again by a later annotation run, and GUI triage cannot undo the decision.

## Decision

`tags` and `captions` have a nullable `rejected_at` timestamp.

- `NULL` means the row is adopted.
- Non-`NULL` means the row is soft-rejected and excluded from adopted reads and export.
- `rejected_at` only means "this tag or caption is excluded for this image" (= *when* it was excluded). It is target-independent.
- Export-target vocabulary differences are not represented with `rejected_at`.
- No per-row by export-target adoption matrix is introduced.
- Annotation upsert does not revive a rejected row for the same image/model/content identity.
- Existing tag removal operations mark rows rejected instead of deleting them.
- Export resolves adopted tags by string union with duplicate removal. Manually edited tags win when the same string appears multiple times.
- Export resolves adopted captions to one row. Manually edited captions win; otherwise the newest adopted row wins.

### Amendment (Issue #1003): `reject_reason` — *why* a row was rejected

`tags` and `captions` also have a nullable `reject_reason` string column. It is orthogonal to
`rejected_at` (`rejected_at` = *when*, `reject_reason` = *why*) and only carries meaning when
`rejected_at` is non-`NULL`.

| Kind | `rejected_at` | `reject_reason` | Display | Restore path |
|---|---|---|---|---|
| adopted | `NULL` | `NULL` | normal chip | — |
| disabled | set | `not_needed` | strike-through grey chip (kept inline) | click dashed chip |
| excluded | set | `incorrect` | hidden | none (kept in DB, no UI path) |
| replaced | set | `replaced` | hidden | none (migrated to the replacement tag) |

- **Export reads are unchanged**: adopted extraction still filters `rejected_at IS NULL`, so all
  three `reject_reason` values are excluded from export. `reject_reason` never influences export;
  it exists only for display reconstruction (disabled vs hidden) and to record intent.
- **Write paths** set `reject_reason` alongside `rejected_at`: single chip disable → `not_needed`;
  `remove_tag_from_images_batch` (✕ batch) → `incorrect` (default); `replace_tag_for_images_batch`
  (source tag) → `replaced`; restore → both back to `NULL`. Captions get the column and a default
  of `incorrect` for symmetry (caption chip UI is not implemented yet).
- **Display reconstruction** is the regression fix: `TagPanelWidget` rebuilds its disabled/hidden
  display state from DB `reject_reason` on every reload instead of relying on in-memory sets, so the
  disabled-vs-excluded distinction survives navigating to another image and back.
- **Migration**: existing `rejected_at IS NOT NULL` rows are backfilled to `not_needed` so the
  post-migration display is unchanged (all previously-rejected tags currently render as struck-through).

## Rationale

Soft-reject preserves user judgement across model reruns and keeps reject operations undoable for later GUI workflows. A nullable timestamp matches the existing `ErrorRecord.resolved_at` vocabulary while avoiding a second active state such as explicit accept.

Target-specific Danbooru/Pony vocabulary and style choices should be derived from tag DB format/alias conversion and export rules. Encoding those choices into `rejected_at` would duplicate derivable information and create an N by M state matrix.

Manual edits should be canonical when they collide with AI output because they represent direct user intent. Caption UI selection is still expected to grow in the results triage design, so the export fallback is deterministic without pretending to be the final UX policy.

## Consequences

Queries that present adopted tags or captions should filter `rejected_at IS NULL` by default. Code that needs audit/history rows must opt into rejected rows explicitly. Future caption selection UI should update `rejected_at` rather than physically deleting rows.

Future export profiles may add target-specific format selection, category exclusion, or generated quality tags, but those profiles must not reinterpret `rejected_at` as a target-specific adoption state.

`reject_reason` (Issue #1003) may later feed analytics (e.g. extract `incorrect` vs `replaced` rows for review), but it must remain export-neutral: adopted extraction stays `rejected_at IS NULL` and never branches on `reject_reason`.