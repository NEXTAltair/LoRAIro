
The database schema is defined in `genai_tag_db_dataset_builder.core.database`. To support the integration of `site_tags`, the `TAG_STATUS` table has been extended with three new columns: `deprecated` (BOOLEAN), `deprecated_at` (DATETIME), and `source_created_at` (DATETIME). When inserting or updating data, the builder uses an upsert strategy that only modifies a row if its values have actually changed. This prevents unnecessary database writes and keeps the `updated_at` timestamp meaningful.

---

ALTER TABLE TAG_STATUS ADD COLUMN deprecated BOOLEAN NOT NULL DEFAULT 0;
ALTER TABLE TAG_STATUS ADD COLUMN deprecated_at DATETIME NULL;
ALTER TABLE TAG_STATUS ADD COLUMN source_created_at DATETIME NULL;
