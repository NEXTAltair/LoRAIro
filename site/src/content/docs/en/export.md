---
type: Guide
title: Export a dataset
description: Create training files from staging or explicit image IDs.
sidebar:
  order: 7
---

## Export in the GUI

1. Check staged images and their count.
2. In Export (「エクスポート」), select resolution and format.
3. Review export tag adjustments and run Validate (「検証」).
4. If there are no issues, run Export and inspect the generated images and text.

Resolution choices are 512, 768, 1024 and 1536. Formats include TXT with separate tags (「TXT（タグ分離）」), TXT with merged captions (「TXT（キャプション統合）」), and JSON. Choose the format your training tool expects.

Temporary output exclusions differ from database rejects. See [tag editing](../editing/).

## Specify image IDs in the CLI

The current `export create` does not accept search filters. Search first and check the target IDs. Old examples using `--tags cat` no longer work.

```powershell
uv run --no-sync lorairo-cli export create -p "my-project" --image-ids 42,57 -o ./dataset
uv run --no-sync lorairo-cli export create -p "my-project" --image-ids-file ids.txt -o ./dataset
```

These two lines are alternatives. `--image-ids` and `--image-ids-file` cannot be combined. Direct input supports up to 500 IDs. For bulk export, use `ids.txt` containing newline- or comma-separated IDs. The CLI generates both TXT and JSON.

Use a dedicated empty output directory to avoid mixing with an existing dataset unintentionally. Check file counts, images and tags before passing the dataset to training.

## Separate datasets by tag language

Explicitly request multilingual tag export in the CLI.

```powershell
uv run --no-sync lorairo-cli export create -p "my-project" --image-ids 42,57 -o ./dataset --tag-language canonical --tag-language ja
```

For multiple languages, complete datasets including images are created in directories such as `canonical/` and `ja/`. Allow enough disk space for these copies. A single language uses the output root.

Tags without a registered preferred translation fall back to canonical text. This does not automatically translate captions. It is separate from this guide's four-language support and does not guarantee four translations for every tag. Instructions for multilingual tag export from the GUI are not currently provided.
