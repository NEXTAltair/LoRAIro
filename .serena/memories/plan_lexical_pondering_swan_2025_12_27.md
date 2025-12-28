## Update: decisions and clarifications

- Approved: remove `_get_default_database_path()`; `get_database_path()` fallback can be simplified because core init sets explicit paths.
- init_engine() call sites are limited: hf_downloader, gui db_initialization, db_maintenance_tool (plus tests). No other runtime usage.
- Policy confirmed: HF-downloaded base DBs should use HF Hub standard cache (CAS); custom cache_dir for base DB is deprecated.
- User DB should be stored in user-specified directory (CLI/GUI), separate from HF cache. Compatibility with old `--cache-dir` is NOT required.
- Testing: CLI tests should not require real HF downloads (use mocks/local_files_only).
- Open decision: GUI initialization should be consolidated through core_api (same path as CLI) to avoid multiple init entrypoints; approved to proceed with that consolidation.
- cache_metadata.json purpose still unclear; revisit whether it is needed or can be omitted.
