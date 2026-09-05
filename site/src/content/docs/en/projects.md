---
type: Guide
title: Projects and image registration
description: Understand project storage and register images safely.
sidebar:
  order: 3
---

## What is stored

Image information, annotations and edits are managed per project. The usual location is `lorairo_data/<project>_YYYYMMDD_NNN/`, containing a SQLite database, `image_dataset/` and other files. Custom settings can change this location.

Distinguish the original image folder from LoRAIro project storage. Back up the entire project, not just the image database.

## Register images in the GUI

1. Open the Search tab (「検索」).
2. Under Dataset (「データセット」), choose Select (「選択」) and select the image folder.
3. Wait for registration to finish, then check search results and counts.

Select chooses the source folder for registration. It is not a button for opening an existing project. Start with a small test folder to avoid registering an unintended directory tree.

## Specify the project in the CLI

```powershell
uv run --no-sync lorairo-cli project create "my-project"
uv run --no-sync lorairo-cli project list
uv run --no-sync lorairo-cli images register ./images --project "my-project"
uv run --no-sync lorairo-cli images list --project "my-project" --fetch
```

Replace `my-project` with your project name. Check image IDs in the post-registration listing; do not use the sample IDs unchanged.

CLI registration skips images with identical pHash values by default. Use `--include-duplicates` only when duplicate registration is intentional.

## After registration

Registration alone does not run annotation or export. Choose targets in [search and staging](../search/) before continuing. Do not perform writes such as registration or editing simultaneously in the GUI and CLI.
