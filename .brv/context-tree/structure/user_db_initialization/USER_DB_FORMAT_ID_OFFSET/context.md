
USER_DB_FORMAT_ID_OFFSET=1000 is defined in genai_tag_db_tools to reserve user format_id range (1000+), used when allocating new TagFormat IDs. This ensures that user-defined formats do not conflict with base database formats, which use the 1-999 range.

---

LoRAIro's tag database initialization process calls `init_user_db()` from `genai_tag_db_tools` and then proceeds to create its own format mappings, specifically using `format_id=1000`. This is handled in `src/lorairo/database/db_core.py` within the `_initialize_lorairo_format_mappings` function.
