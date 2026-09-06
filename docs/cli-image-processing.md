---
type: Reference
title: CLI offline image processing
status: Accepted
tags: [cli, images, processing]
---

# Offline processed-image generation

`images process` connects registered originals to the processed-image paths used by
annotation, Provider Batch, and export. It preserves the original file and image ID.

```bash
lorairo-cli --json images process --project dataset --image-ids-file ids.txt --resolution 512
lorairo-cli --json annotate run --project dataset --image-id 1 --model local-model --resolution 512
lorairo-cli --json batch submit --project dataset --image-ids 1 --model provider/model --resolution 512
lorairo-cli --json export create --project dataset --image-ids-file ids.txt --resolution 512 --output exported
```

Choose exactly one of `--image-ids` (CSV, maximum 500) and `--image-ids-file`
(newline/comma-separated, maximum 100,000). Empty input is INVALID_INPUT/exit 2.
Repeated IDs are processed once. No image outside the selected ID set is registered
or processed. Missing IDs and corrupt/missing originals produce individual failures.

The resolution is the target long side, a multiple of 32 between 32 and 8192.
The existing CPU pipeline performs automatic cropping, color normalization and
Lanczos resize; dimensions align to multiples of 32. Extremely narrow images that
would yield a zero dimension fail with a per-image error. Preferred-resolution buckets
and configured upscalers do not override the explicit size. No model is loaded or
downloaded, no inference API is called, and GPU is not required. A small original can
be enlarged with ordinary Lanczos interpolation; this does not invoke a learned model.

A valid, decodable exact-resolution output whose dimensions, mode and alpha match
its DB record is skipped. When multiple exact-resolution rows exist, a valid file is preferred over
missing/corrupt candidates. A nearby resolution does not substitute for the requested size. Missing or
corrupt exact output is rebuilt at its existing processed path; `--rebuild` also
regenerates a valid file. Replacement uses a temporary file in the same directory and
an atomic rename, without changing the original image row or processed-image ID.
If regenerated dimensions differ from existing DB metadata, the command reports
`processed_metadata_mismatch` instead of replacing the file with inconsistent data.
An existing nonempty `upscaler_used`, or a mode/alpha mismatch, rejects offline rebuild
with `processed_provenance_mismatch`, preserving the previous file and row. Choose a
different resolution to create a separate offline output, or restore the old processed
file. A valid upscaled file can still be skipped without `--rebuild`; its provenance
is retained because the file is unchanged.
Paths outside the project's image dataset or inside original-image storage are never
replaced. New resolutions create a processed file and associate it with the original
ID through the existing DB registration service. A DB registration failure reports
the unlinked output path; generated files are not silently deleted.

Each JSONL `item` contains `image_id`, `status` (`success`, `skipped`, `failed`),
`resolution`, `output_path`, `processed_image_id`, and `reason`. The terminal result
contains total/processed/skipped/failed counts and their ID sets. Valid skips retain
`ok:true`, status `success`, and exit 0. Any failure gives `ok:false`, exit 1, and
status `partial_success` when another selected ID is usable, otherwise `failed`.
Input validation errors exit 2 before processing.

The original-image guard for annotate and Batch remains active: specify
`--resolution` to select generated processed paths. Generation does not rewrite an
original DB path to bypass this guard.

The implementation reuses `ImageProcessingManager`, `FileSystemManager`, and
`ImageDatabaseManager`; CLI-specific work is exact-ID selection, offline policy,
validated re-use, and per-ID reporting. Existing GUI processing remains unchanged.
