# 0042. OpenAI Moderation WebAPI Preflight

## Context

WebAPI annotation can send images to downstream provider models before LoRAIro has a usable rating row. Existing refusal and rating filters prevent repeat sends for known refused or `X` / `XXX` images, but unrated images still need a preflight decision before normal WebAPI annotation.

## Decision

Normal GUI and CLI WebAPI annotation paths run `openai/omni-moderation-latest` for DB-registered images whose latest rating is missing, `UNRATED`, or otherwise not usable for a send decision. Moderation results are stored in the existing `ratings` table using the existing OpenAI moderation model row and `openai_moderation_v1` rating scheme. No new schema flag is added.

Known latest ratings remain authoritative:

- `X` / `XXX` skip WebAPI annotation without another moderation call.
- `PG` / `PG-13` / `R` proceed without another moderation call.
- unknown file paths pass through because no `ratings.image_id` target exists.

If moderation cannot run or does not produce a saved rating for an unrated image, LoRAIro fails closed for that image: the image is skipped, an `error_records` row records the reason, and the rest of the batch continues.

## Rationale

This keeps the rating table as the single source of truth for WebAPI send decisions and reuses the existing image-annotator-lib OpenAI moderation converter. A fixed fail-closed policy avoids accidentally sending unrated images when the OpenAI key, network, or moderation API is unavailable.

Provider Batch automatic two-stage orchestration is not included here. The existing manual `rating_preflight` batch task remains available, while this ADR covers the normal GUI/CLI annotation path.

## Consequences

Tests must cover existing-rating skip/allow, unrated moderation allow/block, moderation failure, and no-op local-model selections. The model registry must keep `openai/omni-moderation-latest` mapped to the `ratings` model type, and future moderation model changes must preserve `openai_moderation_v1` mapping compatibility.
