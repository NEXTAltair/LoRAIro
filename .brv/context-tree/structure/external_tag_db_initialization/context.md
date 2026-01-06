
## Relations
@bug_fixes/external_tag_db_initialization_failure

The external tag database is a critical component of LoRAIro. Its initialization is handled in `db_core.py`. The process involves ensuring the database is present, setting up paths, and initializing the SQLAlchemy engine. If this process fails, the application will not start. This is a change from previous behavior where a failure would only disable tag-related features.

---

The initialization of the `genai-tag-db-tools` databases is a multi-step process that includes:
1. Downloading the base DB from HuggingFace.
2. Setting the base DB paths.
3. Initializing the SQLAlchemy engine.
4. Creating a user DB in the project directory.
5. Creating default type_name mappings for LoRAIro.
