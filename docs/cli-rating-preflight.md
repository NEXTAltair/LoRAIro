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

First list images that do not have ratings yet:

```bash
lorairo-cli images list --project main_dataset --unrated --limit 50
```

Submit selected image IDs to OpenAI Moderations:

```bash
lorairo-cli batch submit \
  --project main_dataset \
  --task-type rating_preflight \
  --model openai/omni-moderation-latest \
  --image-id 2 \
  --image-id 7 \
  --image-id 11
```

Check status, fetch normalized results if needed, then import:

```bash
lorairo-cli batch status 1 --project main_dataset
lorairo-cli batch fetch 1 --project main_dataset
lorairo-cli batch import 1 --project main_dataset
```

`rating_preflight` requires direct OpenAI, endpoint `/v1/moderations`, an
`openai/omni-moderation-*` model, and a model registered with `ratings` model type.

## Known Limitation

Batch submit image path resolution is tracked separately in issue #528. If that bug is present in
your build, the batch path may fail even when the workflow above is correct.
