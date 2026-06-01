# ADR 0049: Apply CLI Image List Limit in the Repository Query

## Status

Accepted

## Context

`lorairo-cli images list --limit N` previously fetched every matching image record and then sliced
the Python list in the CLI layer. On large projects this made a small listing pay the metadata cost
for the whole dataset.

The CLI still needs the total matching count so it can print `Showing N of M images.`

## Decision

Add `limit` and `offset` to `ImageFilterCriteria`.

`ImageRepository.get_images_by_filter()` now:

1. Builds the existing filtered ID query.
2. Counts the full filtered result from a subquery.
3. Applies stable `Image.id` ordering plus `offset` / `limit` to the ID query.
4. Fetches annotation metadata only for the paged IDs.

`lorairo-cli images list` passes its `--limit` value through `ImageFilterCriteria` instead of
slicing after the repository call.

## Consequences

`get_images_by_filter()` keeps returning `(records, total_count)`. Without `limit`, behavior is
unchanged. With `limit`, `records` contains the requested page while `total_count` remains the full
filtered count.

The query now has deterministic ID ordering for paged results.
