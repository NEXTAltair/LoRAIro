
TagStatisticsService now serves cached general/usage/type/translation stats keyed by DATABASE_METADATA.version (latest across merged DBs) to avoid recomputation until DB updates.

---

class TagStatisticsService(GuiServiceBase):
    """統計取得用のGUIサービス"""

    def __init__(
        self,
        parent: QObject | None = None,
        session: Session | None = None,
        merged_reader: "MergedTagReader | None" = None,
    ):
        super().__init__(parent)
        self._stats = TagStatistics(session=session)
        # Store merged_reader, will be lazy-initialized on first use if None
        self._merged_reader = merged_reader
        self._merged_reader_initialized = merged_reader is not None
        self._cache_version: str | None = None
        self._cache_general_stats: dict[str, Any] | None = None
        self._cache_usage_df: pl.DataFrame | None = None
        self._cache_type_dist_df: pl.DataFrame | None = None
        self._cache_translation_df: pl.DataFrame | None = None

    def _get_cache_version(self) -> str | None:
        try:
            if hasattr(self._stats.repo, "get_database_version"):
                return self._stats.repo.get_database_version()
        except Exception as e:
            self.logger.warning("Failed to read database version for cache: %s", e)
        return None

    def _refresh_cache(self, version: str | None) -> None:
        self._cache_version = version
        self._cache_general_stats = self._compute_general_stats()
        self._cache_usage_df = self._stats.get_usage_stats()
        self._cache_type_dist_df = self._stats.get_type_distribution()
        self._cache_translation_df = self._stats.get_translation_stats()

    def _ensure_cache(self) -> None:
        version = self._get_cache_version()
        if self._cache_general_stats is None:
            self._refresh_cache(version)
            return
        if version is None and self._cache_version is None:
            return
        if version != self._cache_version:
            self._refresh_cache(version)
