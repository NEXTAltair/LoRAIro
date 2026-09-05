---
type: Guide
title: Search and staging
description: Explicitly choose which search results to process.
sidebar:
  order: 4
---

## Search results are not execution targets

Filter images by tags or other conditions in the GUI, select thumbnails, and use Add selection to staging (「選択をステージングへ」). Appearing in search results or selecting a thumbnail alone does not make an image an execution target.

Annotation and export share the staging set. It holds up to 500 images and does not add the same image twice. Check its contents and count immediately before running a task.

Clear (「クリア」) removes images from the staging set; it does not delete them from the database.

## GUI search

Tag searches support exclusions (`-tag`). After changing conditions, check counts and thumbnails to confirm that the intended images are included. Combine relevant conditions, such as ratings or missing model results.

## CLI search

Create a UTF-8 `query.json` file to avoid quoting problems when embedding JSON directly in PowerShell.

```json
{"tags":["cat"],"excluded_tags":["dog"],"limit":100}
```

```powershell
uv run --no-sync lorairo-cli --json images search -p "my-project" --query-file query.json
uv run --no-sync lorairo-cli images show 42 57 -p "my-project"
```

`include_nsfw` is false by default. Do not confuse exclusion by search conditions with missing registration. Large result sets have a count guard. Explicitly add `"emit_ids":true` to the query when enumerating many IDs.

With `--json`, stdout is JSONL. Some rows carry message types rather than just results, so do not use the entire output directly as an image ID file. See [CLI notes](../cli/).
