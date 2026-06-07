# CLI Rating Preflight Workflow

This page shows how to assign image ratings from the CLI with OpenAI Moderation.
Use the synchronous path for small image sets and the Provider Batch path for large sets.

## Prerequisites

- Configure an OpenAI API key in the CLI config.
- Register images in a project.
- Refresh models into the project database before submitting batch jobs.

```bash
lorairo-cli project create main_dataset
lorairo-cli images register /path/to/images --project main_dataset
lorairo-cli models refresh --project main_dataset
lorairo-cli models list --category rating
```

Confirm that `openai/omni-moderation-latest` or another `openai/omni-moderation-*` rating model is listed.

## Synchronous Path

Use this when you want immediate results or only need to process a small set.

```bash
lorairo-cli annotate run \
  --project main_dataset \
  --model openai/omni-moderation-latest
```

The normal annotation save path stores moderation ratings in the `ratings` table.

## Provider Batch Path

Use this for larger sets where asynchronous processing is preferable.

First list images that do not have ratings yet. Read/list commands are
count-first (ADR 0060): by default they return only the count. Pass `--fetch`
to retrieve the curated projection (`image_id` + `file_path`):

```bash
# 件数のみ (count-first の既定)
lorairo-cli images list --project main_dataset --unrated --limit 50

# 実データ (image_id + file_path) を取得
lorairo-cli images list --project main_dataset --unrated --fetch --limit 50
```

`--limit` の上限は 500 (作業集合上限)。これを超える選択は `RESULT_SET_TOO_LARGE`
で弾かれるので、絞り込み条件を足してください。

エージェント駆動でこのワークフローを回す場合は、グローバル `--json` フラグ
(または環境変数 `LORAIRO_CLI_JSON=1`) で機械可読 JSONL モードに切り替えると、
stdout が JSONL のみ (kind は `item` / `result` / `error`) になり parse しやすくなります
(ADR 0057):

```bash
lorairo-cli --json images list --project main_dataset --unrated --fetch --limit 50
```

Submit selected image IDs to OpenAI Moderations:

```bash
lorairo-cli batch submit \
  --project main_dataset \
  --task-type rating_preflight \
  --model openai/omni-moderation-latest \
  --image-ids 2,7,11
```

Check status, fetch normalized results if needed, then import:

```bash
lorairo-cli batch status 1 --project main_dataset
lorairo-cli batch fetch 1 --project main_dataset
lorairo-cli batch import 1 --project main_dataset
```

`rating_preflight` requires direct OpenAI, endpoint `/v1/moderations`, an
`openai/omni-moderation-*` model, and a model registered with `ratings` model type.

## Duplicate Submit and Rating Upsert Behavior

### Why duplicate submission can occur

`images list --unrated` returns images that have no `ratings` row yet. If a batch job has been
submitted but not imported yet, the same images still appear as "unrated" and can be submitted
again in a new job. There is no hard error for this — re-submission is allowed (e.g., after a
failed job).

As a result, the same `image_id` may appear in multiple provider batch jobs.

### How to detect duplicate submissions

Use `batch status --items` to inspect per-image items of a job:

```bash
lorairo-cli batch status <job_id> --project <project> --items
```

In JSON mode each item is emitted as a `ProviderBatchItemRecord` row before the result row:

```bash
lorairo-cli --json batch status <job_id> --project <project> --items
```

Fields: `id`, `job_id`, `custom_id`, `image_id`, `model_id`, `task_type`, `status`,
`error_type`. Compare items across jobs to identify images submitted more than once.

Use `--item-status` to filter by status, and `--limit` / `--offset` for pagination:

```bash
lorairo-cli batch status <job_id> --project <project> --items --item-status failed
```

### Rating upsert semantics on import

When `batch import` runs, ratings are stored in the `ratings` table using an upsert keyed on
`(image_id, model_id)`:

- If a rating row already exists for that image and model, it is **updated** (overwritten).
- If no row exists, it is **inserted**.

Importing a second job for the same image overwrites the rating from the first import.
The **last-imported result wins** as the canonical current value.

The raw moderation response for each job is preserved in `provider_batch_items.raw_response`
for audit and debugging. The `batch import` summary (`imported` / `skipped` / `errors` /
`total`) counts images, not insert/update operations individually. See ADR 0031 Amendment
2026-06-07 for the design rationale.

## Known Limitation

Batch submit image path resolution is tracked separately in issue #528. If that bug is present in
your build, the batch path may fail even when the workflow above is correct.
