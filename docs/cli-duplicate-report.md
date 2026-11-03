---
type: Reference
title: Read-only duplicate candidate report
status: Accepted
tags: [cli, phash, image-review]
---

# Duplicate candidates from saved pHashes

```sh
lorairo-cli --json images duplicates --project training --max-distance 4 --limit 100
```

`images duplicates` reads the entire existing project and reports candidate clusters
using its saved 64-bit perceptual hashes. It does not open images, calculate hashes,
register images, delete files, update data, prepare databases, or call model providers.
It always uses the existing strict read-only DB access policy, including when the
global `--read-only` option is omitted. An unprepared or incompatible project returns
`PRECONDITION_FAILED` (exit 1). CLI logging and SQLite WAL/shared-memory bookkeeping
follow the existing read-only runtime policy.

## Distance and clustering

`--max-distance` accepts integers from 0 through 64. It is the maximum Hamming distance
(number of differing bits) for a link between two saved pHashes. Zero groups only equal
hashes; 64 connects all images with valid hashes. The default 4 allows 4 of 64 bits to
differ (6.25%). This is a small initial allowance for review, not a threshold calibrated
to your dataset or a visual similarity percentage. Increase it to include more candidates.

Clusters are **connected components**. If A is close to B and B is close to C, all three
belong to one cluster even when A and C exceed the threshold. Every member is connected
by some sequence of qualifying links; it is not guaranteed to be close to every other
member. Results are deterministic: members are sorted by image ID, clusters are ordered
by their smallest ID, and `cluster_id` is that smallest ID. It identifies this computed
component, not a persistent DB record.

These are suggestions for review. Equal or similar pHashes can include color/grayscale
versions, different resolutions, and unrelated images. Different crops or edits can be
missed. The report does not label candidates as safe to delete or change registration's
duplicate/variant classification described in [ADR 0061](decisions/0061-phash-duplicate-variant-classification.md).

## Complete detection with bounded work and output

The service counts project images before loading hashes. More than **10,000 images**
returns `RESULT_SET_TOO_LARGE` (exit 2) before comparison, with `matched` and `limit`
details. This includes images with missing or invalid hashes. A second size check
guards against project growth between counting and loading. There is no silent partial
project scan, and reducing `--limit` cannot bypass this input cap.

Existing identical hashes are grouped first. For thresholds 1–63, the service compares
every distinct-hash pair with XOR/popcount, equivalent to `ImageHash`'s Hamming metric.
For U unique valid hashes, this requires U(U−1)/2 comparisons, at most **49,995,000**.
Thresholds 0 and 64 need no pair comparisons. `compared_hash_pairs` reports actual
distinct-hash comparisons; equal hashes are connected without comparing every image
pair. The implementation stores component membership rather than a quadratic edge list.

`--limit` accepts 1–500 (default 100). It caps the number of cluster item rows **and**
the members shown inside each cluster. Detection and summary counts still cover every
image in the accepted project. `clusters_truncated` and per-cluster `members_truncated`
explicitly identify omitted output, with full `cluster_count` and `member_count` values.

## JSONL fields

Each `kind:item` contains `cluster_id`, `member_count`, `members`, and
`members_truncated`. Every member includes `image_id`, `stored_image_path`,
`original_image_path`, and normalized lowercase `phash`. Paths are the strings saved
in the DB; their existence and image contents are not checked.

The final `kind:result` has `ok:true`, `status:"success"`, `read_only:true`,
`candidate_only:true`, `project`, and these counts:

| Field | Meaning |
| --- | --- |
| `total_images` | Every image in the accepted project snapshot |
| `valid_phash_images` | Images with a valid 16-digit hexadecimal hash after trimming whitespace |
| `missing_phash_images` | Null or blank stored hashes |
| `invalid_phash_images` | Nonempty values that are not 16 hexadecimal digits |
| `unique_phashes` | Distinct valid hash values |
| `cluster_count` | All components containing at least two images |
| `clustered_images` | Images belonging to those components |
| `unclustered_images` | Valid-hash images that remain singletons |
| `returned_clusters` | Cluster rows actually emitted |
| `compared_hash_pairs` | Distinct-hash pair comparisons actually performed |

`total_images = valid_phash_images + missing_phash_images + invalid_phash_images`, and
`valid_phash_images = clustered_images + unclustered_images`. Missing and invalid hashes
are counted but excluded from detection; the report never invents or recalculates them.
Successful report execution remains exit 0 when those counts are nonzero or no clusters
are found. Invalid arguments return exit 2.

The result also reports `max_distance`, `hash_bits:64`, `distance_metric:"hamming"`,
`clustering:"connected_components"`, `limit`, `max_images:10000`,
`max_pair_comparisons:49995000`, and `clusters_truncated`.

Python callers use `lorairo.public_api.duplicate_report.report_duplicates(project_name,
max_distance=4, limit=100)`. It returns the same `DuplicateReport`, including typed
`clusters` and `summary()`. The pure `analyze_saved_hashes` function accepts synthetic
`SavedImageHash` records for verification without a database or image files.
