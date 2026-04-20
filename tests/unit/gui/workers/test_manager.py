"""WorkerManager ユニットテスト（スレッド不要のシンプルなメソッド中心）。"""

import pytest

from lorairo.gui.workers.manager import WorkerManager


@pytest.fixture
def manager(qapp):
    return WorkerManager()


class TestWorkerManagerInit:
    def test_init_creates_empty_active_workers(self, manager):
        assert manager.active_workers == {}

    def test_active_worker_count_initially_zero(self, manager):
        assert manager.get_active_worker_count() == 0

    def test_active_worker_ids_initially_empty(self, manager):
        assert manager.get_active_worker_ids() == []


class TestWorkerManagerAccessors:
    def test_is_worker_active_false_when_empty(self, manager):
        assert manager.is_worker_active("nonexistent") is False

    def test_get_worker_returns_none_when_empty(self, manager):
        assert manager.get_worker("nonexistent") is None

    def test_get_worker_summary_empty(self, manager):
        summary = manager.get_worker_summary()
        assert summary["active_worker_count"] == 0
        assert summary["active_worker_ids"] == []
        assert summary["worker_details"] == {}


class TestWorkerManagerEmptyOperations:
    def test_cancel_all_workers_when_empty(self, manager):
        manager.cancel_all_workers()
        assert manager.get_active_worker_count() == 0

    def test_cleanup_all_workers_when_empty(self, manager):
        manager.cleanup_all_workers()
        assert manager.get_active_worker_count() == 0

    def test_wait_for_all_workers_when_empty(self, manager):
        result = manager.wait_for_all_workers()
        assert result is True
