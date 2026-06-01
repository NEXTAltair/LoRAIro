# 0050. CLI tag DB lazy initialization

## Status

Accepted

## Context

`ServiceContainer` initialized genai-tag-db-tools databases during container construction.
That made read-only CLI commands such as `lorairo-cli status`, `project list`, and
`images list --limit 5` contact Hugging Face before doing any command-specific work.
Without `HF_TOKEN`, startup could spend a long time in tag DB initialization even when the
command did not need tag management.

## Decision

`ServiceContainer` construction must stay side-effect-light. It should not initialize
genai-tag-db-tools databases by default.

Tag DB initialization is deferred to the first service path that actually needs external tag DB
access:

- `ServiceContainer.tag_management_service`, before constructing `TagManagementService`.
- `AnnotationRepository` tag ID resolution/registration, before creating a `MergedTagReader`.

`ensure_tag_db_initialized()` must not rewrite the selected image database path. Project selection
owns `db_core.IMG_DB_PATH` / `DATABASE_URL`; tag DB initialization only prepares genai-tag-db-tools
base/user databases.

## Consequences

- Read-only CLI commands no longer block on tag DB initialization.
- `lorairo-cli --help` and `version` continue avoiding service initialization side effects.
- Tag management still initializes the external tag DB before using genai-tag-db-tools user DB
  APIs.
- Annotation repository construction remains cheap, but annotation tag ID resolution still
  initializes external tag DB support when needed and continues graceful degradation if unavailable.
- Opening tag management after `set_active_project()` no longer resets project-root resolution back
  to the default image database.
