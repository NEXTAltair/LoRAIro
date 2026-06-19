---
type: ADR
title: CLI Original Image Annotation Guard
status: Accepted
timestamp: 2026-06-07
tags: []
---
# ADR 0064: CLI Original Image Annotation Guard

- **Related Issue**: #686
- **Related ADRs**: [0053](0053-cli-streaming-annotation-memory-bounded-contract.md), [0057](0057-cli-jsonl-output-and-error-contract.md), [0063](0063-cli-batch-submit-image-ids-csv.md)

## Context

The GUI route does not let users directly annotate original stored images. CLI routes still accepted image records whose
`stored_image_path` points under `image_dataset/original_images/`, so `annotate run` and `batch submit` could bypass the
GUI safety policy.

This surfaced during a rating preflight batch: image IDs selected for OpenAI moderation were submitted from
`image_dataset/original_images/...`, including very large originals. That is the wrong CLI surface. CLI should operate on
the same processed/resized image records that the GUI workflow is designed to use.

## Decision

CLI annotation entry points reject image records whose `stored_image_path` is under `image_dataset/original_images/`.

The guard is enforced before expensive or external work:

- `annotate run` rejects after filter/image-id selection and before image loading, moderation preflight, or annotation.
- `batch submit` resolves the supplied `--image-ids` to image records and rejects before provider batch submission.

The failure is treated as input validation (`click.UsageError`), preserving the CLI JSONL error contract through
`INVALID_INPUT` / exit code 2.

## Rationale

The storage path is the only stable discriminator currently present on the selected image records. Adding a new schema
field would be heavier than this safety fix and would not change the immediate behavior needed at the CLI boundary.

Mixed selections fail as a whole. Silently dropping originals would make the submitted set differ from the user's exact
ID selection and could hide mistakes in automated agent workflows.

## Consequences

- CLI users must select processed/resized image records for annotation and provider batch submission.
- Original image records selected by exact ID or filters produce a clear validation error that includes sample image IDs
  and stored paths.
- Future explicit override, if needed, must be designed as a separate policy change rather than falling through by
  default.