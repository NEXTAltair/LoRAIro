---
type: Reference
title: CLI export results and retries
status: Accepted
tags: [cli, dataset-export]
---

# Export results and retries

`export create` reports this invocation, including errors after partial file output.
Its terminal JSONL result preserves `total_images` as the requested ID count for
compatibility; use `exported` to decide how many complete image datasets were written.
An image is exported only when all requested languages and both TXT and JSON finish.

| Field | Meaning |
| --- | --- |
| `requested` | Number of unique requested IDs; duplicate CSV IDs are exported once |
| `exported` | Images with complete TXT/JSON output |
| `skipped` | IDs missing from the DB or without a usable processed image |
| `failed` | Images with operational failures, such as DB, copy, or writer errors |
| `exported_ids` | IDs with all requested output complete |
| `failed_ids` | Every incomplete ID, including skipped images; suitable for retry input |
| `error_details` | Per-ID reasons, completed formats, and files whose writers completed |

`requested = exported + skipped + failed`. Any incomplete image produces `ok:false`.
`status` is `success` (exit 0) for complete output, `partial_success` (exit 3) when some
images exported, and `failed` (exit 1) when none exported. Invalid input remains exit 2.
A TXT file can remain after a JSON
write fails; it is listed as partial evidence and does not increment `exported`.
JSON evidence is tracked separately for each language. When an image's later language
fails, an earlier language's completed `metadata.json` can still contain that image
and is listed in its `output_files`. A metadata write failure is attributed to every
image staged in that specific document, including images already failing elsewhere;
the error message identifies the document path. Neither partial staging nor one
successful language makes the image's overall JSON format complete.
Missing IDs (`image_not_found`) and missing processed files (`processed_image_missing`)
are distinct from `export_error` and late `metadata_write_error` failures.
`output_path_collision` means a later selected image would overwrite an earlier
image's output. Flat filenames remain unchanged: different source directories with
the same basename, or different extensions with the same TXT/caption stem, conflict.
The later ID fails before writing any language or format, preserving the earlier
image's files and JSON entry. Correct the source naming or export the conflicting
IDs into separate directories before retrying.

Destination ownership is retained for the entire operation, including across 500-ID
boundaries and between TXT/JSON passes, using O(selected IDs × languages) memory.
All destinations for an ID are checked before reservation; a rejected ID does not
reserve unrelated names. This ownership record is separate from translation caches.

This changes the former exit-0 behavior for incomplete exports. Scripts should inspect
exit status and `ok`, then use `exported`, rather than treating `total_images` as success.
Successful filenames, TXT/caption/JSON contents and single-format service Path return
values remain compatible. Service callers may supply `ExportResult` to collect results.

Existing output files are overwritten, and unrelated or stale files are not deleted.
`metadata.json` is replaced with this invocation's records, rather than merged with a
previous export. Files already present are never taken as proof that a new write
succeeded. Atomic rollback of output files is not provided; an interrupted write can
leave an incomplete file, and `output_files` lists only completed writes. For retries,
correct the reported cause and write `failed_ids` to a new output directory; to rebuild
a complete dataset in the same directory, rerun the original full ID list.
CSV input remains limited to 500 IDs; use `--image-ids-file` for up to 100,000 IDs.

## Shared work for all formats

`export create` uses `DatasetExportService.export_dataset_all_formats` and copies each
processed image once per language destination. For N unique IDs and L languages,
successful copies are NL instead of 2NL. Processed-path resolution, image metadata,
annotations, and canonical tag normalization run once per image; translation runs
once per image and language and is shared by TXT and JSON. Exact/closest processed
resolution selection uses the existing resolver.

Input records are consumed one image at a time. Translation caches reset every 500
images; their size depends on the tags in that window. Final JSON document dictionaries
still grow with the output dataset, as in the existing JSON writer. This change does
not batch SQL queries or claim bounded total memory or a measured speedup factor.

Python callers can use `lorairo.public_api.export.export_images_all_formats` with a
project name, exact image IDs, output path, resolution, and optional languages. It
returns the same service `ExportResult` collector, whose `summary()` exposes the CLI
result fields above. Existing single-format methods remain available. A TXT failure
can leave successful JSON output, and a late JSON failure retains completed TXT files;
both remain incomplete image results and can be retried using `failed_ids`.

## Preview without output writes

Add `--dry-run` to preview the same exact IDs, processed image resolution selection,
tag language directories, TXT/caption names, and filename collisions used by real export:

```sh
lorairo-cli --json export create --project training --image-ids-file ids.txt \
  --output planned-dataset --tag-language canonical --tag-language ja --dry-run
```

The preview emits a `kind:item` JSONL row for each image ready for export, followed by
one `kind:result`. Each item contains `image_id`, `source_path`, and `destinations`.
Each destination contains `language`, `image_path`, `tags_path`, `caption_path`
(`null` when there is no caption), and `metadata_path`. Paths follow the same spelling
and relative/absolute convention as the real export, and language aliases and repeated
language options are normalized by the shared path resolver.

The result sets `dry_run:true`, replaces `exported` with `would_export`, and replaces
`exported_ids` with `ready_ids`. It also lists the planned per-language `metadata_files`.
`requested`, `skipped`, `failed`, `failed_ids`, and `error_details` retain their meanings
for input validation. Preview error details contain reasons without completed-format or
written-file evidence. `requested = would_export + skipped + failed`. Exit 0 means all
requested inputs are ready; exit 3 means some are ready; exit 1 means none are ready.
The manifest and counts describe a plan and do not claim that any files were exported.

Plain `--dry-run` already requires existing compatible project and tag databases and
cached tag data. It never creates output directories, copies images, writes metadata,
initializes user tag databases, downloads base tag data, or migrates the project DB.
Missing preparation returns `PRECONDITION_FAILED`; run the separately authorized
`project prepare` workflow before trying again. `--read-only` can also be combined with
`--dry-run`; `--read-only export create` without `--dry-run` is rejected.
The existing CLI log and SQLite read-only WAL/shared-memory bookkeeping remain in
use; the guarantee covers dataset output and logical database content, not those
runtime bookkeeping files.

The shared planner resolves tags, captions, translations, optional Python overlays,
and output name ownership before returning paths. It does not attempt writes to prove
permissions, available disk space, or future write success. Source changes and races
between preview and real export remain possible, and existing destination files will
be overwritten by a later real export as before.

Python callers can use `lorairo.public_api.export.preview_images_all_formats` with the
same project name, exact IDs, output path, resolution and languages as the real facade.
It returns `ExportPreview`, containing `manifest`, `metadata_files`, and `summary()`.
Service callers can use `DatasetExportService.preview_dataset_all_formats` and supply
the same `tag_format` and `overlay_plan` options as `export_dataset_all_formats`.
