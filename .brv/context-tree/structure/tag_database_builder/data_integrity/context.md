# DB Integrity & Data Damage Handling

This note documents how we verify database integrity and how we handle “damaged” upstream data (e.g., mojibake / wildcard tags) for the tag database builder outputs (CC0/MIT/CC4).

## Integrity checks (SQLite-level)

Recommended minimum checks after every build:

- `PRAGMA quick_check;` must return `ok`
- `PRAGMA foreign_key_check;` must return **0 rows**
- Orphan checks should be **0 rows**:
  - `TAG_STATUS` rows pointing to missing `TAGS` / missing `TAG_TYPE_FORMAT_MAPPING`
  - `TAG_USAGE_COUNTS` rows pointing to missing `TAGS`
  - `TAG_TRANSLATIONS` rows pointing to missing `TAGS`
- Duplicate checks should be **0 rows** (depending on constraints):
  - `TAGS.tag` unique
  - `TAG_STATUS(tag_id, format_id)` unique
  - `TAG_USAGE_COUNTS(tag_id, format_id)` unique

The builder already emits TSV reports under `out_db_*/db_health/` (foreign_key_check / orphan_* / duplicate_* / summary) which are the “human review” surface.

## “Damaged data” policy (upstream quality issues)

We distinguish between:

1. **DB corruption** (broken FK/constraints) — must be fixed before upload.
2. **Upstream content quality issues** — acceptable to upload if they are *contained* and do not break lookup behavior.

### Mojibake / broken Unicode (U+FFFD “�”)

Observed: some upstream sources (e.g. `deepghs/site_tags`) contain tags with unrecoverable replacement characters.

Policy:
- Keep the row for traceability, but **do not treat it as canonical**.
- Mark it as alias/redirect:
  - `TAG_STATUS.alias=1`
  - `TAG_STATUS.preferred_tag_id` points to the canonical tag
  - `TAG_STATUS.deprecated=1` and `deprecated_at=NULL` (if no date known)
- For `TAG_USAGE_COUNTS`, **avoid double counting**:
  - If both alias-tag and canonical-tag have counts for the same `format_id`, keep the canonical row’s count as `max(alias_count, canonical_count)` and delete the alias-tag’s count row.

Note: even after aliasing, `bad_unicode_tags.tsv` will still list those tags because `TAGS.tag` contains “�”. This is expected; the key guarantee is that they are not used as canonical (`alias=0` should be 0 for those rows).

### Search wildcards copied into tag strings (e.g. `*`)

Observed: some sites/users appear to have registered search patterns as tags and later exported them (e.g. `yuki*mami`).

Policy:
- Prefer redirecting wildcard tags into a canonical non-wildcard tag via alias/redirect (same as above).
- If a wildcard tag is actually canonical on that platform, keep it as canonical, and redirect the non-wildcard variant to it.

Operational note: when querying such tags in SQLite, avoid accidental wildcard matching:
- Use equality (`=`) for exact match.
- If using `LIKE`, remember `%` and `_` are wildcards; `*` is not a SQL wildcard but can still confuse external tooling/search UI.

## “Source timestamps” handling

We only store timestamps that are meaningful for operations:
- `TAG_USAGE_COUNTS.created_at/updated_at`: treated as “observation time of that count value” when a source provides it; otherwise keep existing/base values.
- `TAG_STATUS.source_created_at`: optional; represents the source-side timestamp for that tag on that platform (if available). If not available, keep `NULL`.
- `deprecated_at`: keep `NULL` if the source does not provide a reliable timestamp.

## When to do manual repairs vs. rebuild

Prefer **rebuild** if:
- The issue is systematic (same bug affects many rows).
- The fix can be expressed as deterministic logic in the importer.

Prefer **manual repairs** if:
- The issue is rare and requires human judgment (e.g. a small set of garbled tags with unclear intended canonical form).

In both cases, keep a report/TSV of what was changed (before/after tag strings and IDs) so future rebuilds can reproduce the repair logic.

