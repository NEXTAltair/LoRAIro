---
type: Guide
title: Settings, backups and troubleshooting
description: Protect secrets and projects while diagnosing recovery problems.
sidebar:
  order: 8
---

## Settings

Open Settings (「設定」, Ctrl+,) in the GUI. `config/lorairo.toml` contains storage paths and API keys. Do not publish API keys, the full settings file, or screenshots exposing private image paths.

Key settings cover API keys; project, export and Batch result locations; additional prompts; model routes; database wait time; and log level. After restoring, check for absolute paths left over from the original PC.

## Backups

1. Stop processes that write to the database, including the GUI, CLI and Batch imports.
2. Copy the entire project from its actual storage location to another location. It is usually under `lorairo_data/`.
3. Preserve not only `image_database.db`, but also `image_dataset/`, the user tag database (`user_tags.sqlite`) and related files.
4. Store `config/lorairo.toml` and any needed Batch results separately as confidential data.

Avoid copying only a live SQLite database file. During recovery, do not overwrite the original backup. Use a recovery copy to check images, tags and settings.

## Startup and dependency errors

Windows and Linux `.venv` environments are different. Install dependencies on the target OS instead of reusing a copied environment from another OS. Stop apps, tests and agents using the shared environment before rebuilding it.

If the GUI does not appear, check whether Windows has `QT_QPA_PLATFORM=offscreen` set. Offscreen is expected for container tests.

## GPU not detected

```powershell
nvidia-smi
uv run --no-sync python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.version.cuda)"
```

If the result is false when GPU use is intended, check the driver, GPU compatibility and PyTorch environment. Deleting app data will not solve a GPU configuration problem.

## Database conflicts and external connections

For `CONFLICT`, wait for other writes to finish before retrying. Do not write simultaneously from the GUI and CLI. If the initial tag database download fails, check the network and Hugging Face authentication if required.

For WebAPI errors, check authentication, usage limits, model support and submission restrictions. Investigate before repeating the same operation.

## Report a problem

Include the steps, OS, reproduction conditions and a short relevant log excerpt. Main logs are `logs/lorairo.log`, `logs/image-annotator-lib.log` and `logs/lorairo-cli.log`. Redact API keys, personal information and image paths you do not want to disclose.
