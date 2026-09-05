---
type: Guide
title: AI annotation and Jobs
description: Choose between local inference, WebAPI and Provider Batch.
sidebar:
  order: 5
---

## Before running

Check the staged images and count, selected model, and output types (tags, caption, score, rating). Available models vary by environment and provider.

| Method | Processing location and precautions |
| --- | --- |
| Local model | Runs inference locally. Initial model or tag database downloads may require network access. |
| Synchronous WebAPI | Sends target images and prompts to an external provider. Check charges and permission to send. |
| Provider Batch | Processes external submissions as asynchronous jobs. It is neither free processing nor local inference. |

Before sending confidential or third-party images, confirm that you may send them. The app does not enforce API spending limits. Reruns and retries may create additional requests.

## Run in the GUI

1. Select a model and check the target count.
2. Choose Synchronous run (「同期実行」) or Batch API run (「Batch API 実行」). Batch eligibility depends on the model.
3. Check progress, completion and failures in Jobs.
4. Review tags and captions after completion. Read the cause of a failure before retrying.

There is no automatic fallback between providers. Canceling a Batch does not necessarily undo processing or charges already incurred.

## Run synchronously in the CLI

```powershell
uv run --no-sync lorairo-cli models list
uv run --no-sync lorairo-cli annotate run -p "my-project" --model "MODEL_ID" --image-id 42 --image-id 57
```

Replace `MODEL_ID` with a model ID from the listing. Repeat `--image-id` to select images. `--batch-size` controls synchronous processing chunks; it does not submit a Provider Batch.

## Manage Provider Batch

The CLI provides `batch submit/list/status/fetch/import/cancel`. Check arguments with `uv run --no-sync lorairo-cli batch --help` and each subcommand's `--help`. Fetching results and importing them into the database are separate operations. `import` updates the project database.

Batch support is not universal across providers. Do not publish result files containing API keys or images.
