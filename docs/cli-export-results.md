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

`requested = exported + skipped + failed`. Any incomplete image produces `ok:false`
and exit 1. `status` is `success` for complete output, `partial_success` when some
images exported, and `failed` when none exported. A TXT file can remain after a JSON
write fails; it is listed as partial evidence and does not increment `exported`.
Missing IDs (`image_not_found`) and missing processed files (`processed_image_missing`)
are distinct from `export_error` and late `metadata_write_error` failures.

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
