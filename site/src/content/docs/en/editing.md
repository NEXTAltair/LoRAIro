---
type: Guide
title: Edit tags and review captions
description: Distinguish database edits from export-only adjustments.
sidebar:
  order: 6
---

## Review generated results first

Select an image and inspect tags, captions and evaluations in the details panel. AI output may be wrong. Look for unnecessary training tags or wording that contradicts the image.

The current caption display is read-only. Do not assume there is a free-text caption editor. A tag menu provides the operation for moving a tag into the caption.

## Persistent changes and export adjustments

- Adding, replacing or rejecting tags affects database contents.
- Exclude from output (「出力除外」) in the export overlay is a temporary export adjustment.
- `reject(DB)` is not temporary exclusion. Check the stated scope and do not assume it can be undone.

Models may not return individual confidence values for AI tags. Automatic noise removal based on confidence is not always available.

## Preview CLI changes before applying them

Tag changes default to dry-run. First inspect the target without `--apply`.

```powershell
uv run --no-sync lorairo-cli tags add -p "my-project" --image-ids 42,57 --tags "cat,outdoor"
uv run --no-sync lorairo-cli tags add -p "my-project" --image-ids 42,57 --tags "cat,outdoor" --apply
uv run --no-sync lorairo-cli tags remove -p "my-project" --image-ids 42 --tags "bad_tag" --apply
uv run --no-sync lorairo-cli tags replace -p "my-project" --image-ids 42 --from "bad tag" --to "good_tag" --apply
```

Removal is handled as soft-reject, but this does not guarantee a general Undo operation. Back up before bulk changes. After CLI edits, search again or reload the GUI to check the latest state.
