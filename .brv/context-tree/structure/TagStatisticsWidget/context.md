
統計結果はDATABASE_METADATA.version（複数DBなら最新）でキャッシュ無効化。

---

Statistics results are cached, and the cache is invalidated using the `DATABASE_METADATA.version`. If multiple databases are used, the most recent version determines the cache validity.

---

The `TagStatisticsService` in `genai_tag_db_tools/services/app_services.py` implements the caching logic. The `_ensure_cache` method checks the database version to decide whether to refresh the cache.

---

The `_get_cache_version` method in `TagStatisticsService` retrieves the database version. It uses `MergedTagReader.get_database_version()` from `genai_tag_db_tools/db/repository.py` to get the latest version when multiple databases are configured.
