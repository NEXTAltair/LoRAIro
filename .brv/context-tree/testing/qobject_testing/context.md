
DbInitializationService tests no longer call qtbot.addWidget(service) since service is QObject; tests rely on waitSignal/wait only.

---

class TestDbInitializationService:
    """Tests for DbInitializationService."""

    def test_service_initialization_default_cache(self, qtbot):
        """Service should initialize with default cache directory."""
        service = DbInitializationService()
        assert service.cache_dir is not None
        assert isinstance(service.cache_dir, Path)
        assert service.thread_pool is not None
