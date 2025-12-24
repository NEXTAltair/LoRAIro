
To update an existing database to be compatible with the `site_tags` integration, a migration script must be applied. The script, located at `migrations/2025_12_18_add_tag_status_deprecated_and_source_created_at.sql`, adds the `deprecated`, `deprecated_at`, and `source_created_at` columns to the `TAG_STATUS` table. This is a one-time operation required for databases created before this change.
