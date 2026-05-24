"""WorkerManager ユニットテスト（スレッド不要のシンプルなメソッド中心）。"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from lorairo.gui.workers.manager import WorkerManager


@pytest.fixture
def manager(qapp) -> WorkerManager:
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


class TestWorkerManagerCancellation:
    def test_cancel_worker_wait_success_finalizes_canceled_when_no_terminal_signal(self, manager):
        worker = Mock()
        thread = Mock()
        thread.isRunning.return_value = True
        thread.wait.return_value = True
        manager.active_workers["worker-1"] = {"worker": worker, "thread": thread, "auto_cleanup": True}
        canceled_mock = Mock()
        manager.worker_canceled.connect(canceled_mock)

        result = manager.cancel_worker("worker-1")

        assert result is True
        worker.cancel.assert_called_once()
        thread.quit.assert_called_once()
        thread.wait.assert_called_once_with(2000)
        canceled_mock.assert_called_once_with("worker-1")
        assert "worker-1" not in manager.active_workers

    def test_cancel_worker_wait_success_prefers_queued_finished_signal(self, manager, monkeypatch):
        worker = Mock()
        thread = Mock()
        thread.isRunning.return_value = True
        thread.wait.return_value = True
        manager.active_workers["worker-1"] = {"worker": worker, "thread": thread, "auto_cleanup": True}
        finished_mock = Mock()
        canceled_mock = Mock()
        manager.worker_finished.connect(finished_mock)
        manager.worker_canceled.connect(canceled_mock)
        app = Mock()
        app.processEvents.side_effect = lambda: manager._on_worker_finished("worker-1", {"ok": True})
        monkeypatch.setattr("lorairo.gui.workers.manager.QCoreApplication.instance", Mock(return_value=app))

        result = manager.cancel_worker("worker-1")

        assert result is True
        finished_mock.assert_called_once_with("worker-1", {"ok": True})
        canceled_mock.assert_not_called()
        assert "worker-1" not in manager.active_workers

    def test_cancel_worker_wait_success_prefers_queued_error_signal(self, manager, monkeypatch):
        worker = Mock()
        thread = Mock()
        thread.isRunning.return_value = True
        thread.wait.return_value = True
        manager.active_workers["worker-1"] = {"worker": worker, "thread": thread, "auto_cleanup": True}
        error_mock = Mock()
        canceled_mock = Mock()
        manager.worker_error.connect(error_mock)
        manager.worker_canceled.connect(canceled_mock)
        app = Mock()
        app.processEvents.side_effect = lambda: manager._on_worker_error("worker-1", "boom")
        monkeypatch.setattr("lorairo.gui.workers.manager.QCoreApplication.instance", Mock(return_value=app))

        result = manager.cancel_worker("worker-1")

        assert result is True
        error_mock.assert_called_once_with("worker-1", "boom")
        canceled_mock.assert_not_called()
        assert "worker-1" not in manager.active_workers

    def test_finished_after_cancel_request_wins_over_canceled(self, manager):
        manager.active_workers["worker-1"] = {"worker": Mock(), "thread": Mock(), "auto_cleanup": True}
        finished_mock = Mock()
        canceled_mock = Mock()
        manager.worker_finished.connect(finished_mock)
        manager.worker_canceled.connect(canceled_mock)

        manager._on_worker_finished("worker-1", {"ok": True})
        manager._on_worker_canceled("worker-1")

        finished_mock.assert_called_once_with("worker-1", {"ok": True})
        canceled_mock.assert_not_called()

    def test_error_after_cancel_request_wins_over_canceled(self, manager):
        manager.active_workers["worker-1"] = {"worker": Mock(), "thread": Mock(), "auto_cleanup": True}
        error_mock = Mock()
        canceled_mock = Mock()
        manager.worker_error.connect(error_mock)
        manager.worker_canceled.connect(canceled_mock)

        manager._on_worker_error("worker-1", "boom")
        manager._on_worker_canceled("worker-1")

        error_mock.assert_called_once_with("worker-1", "boom")
        canceled_mock.assert_not_called()

    def test_cancel_worker_timeout_forces_canceled_cleanup(self, manager):
        worker = Mock()
        thread = Mock()
        thread.isRunning.return_value = True
        thread.wait.side_effect = [False, True]
        manager.active_workers["worker-1"] = {"worker": worker, "thread": thread, "auto_cleanup": True}
        canceled_mock = Mock()
        manager.worker_canceled.connect(canceled_mock)

        result = manager.cancel_worker("worker-1")

        assert result is True
        thread.terminate.assert_called_once()
        canceled_mock.assert_called_once_with("worker-1")
        assert "worker-1" not in manager.active_workers

    def test_cancel_worker_timeout_does_not_finalize_when_terminate_wait_fails(self, manager):
        worker = Mock()
        thread = Mock()
        thread.isRunning.return_value = True
        thread.wait.side_effect = [False, False]
        manager.active_workers["worker-1"] = {"worker": worker, "thread": thread, "auto_cleanup": True}
        canceled_mock = Mock()
        manager.worker_canceled.connect(canceled_mock)

        result = manager.cancel_worker("worker-1")

        assert result is True
        thread.terminate.assert_called_once()
        canceled_mock.assert_not_called()
        assert "worker-1" in manager.active_workers

    def test_on_worker_canceled_removes_active_worker_and_emits_terminal_signals(self, manager):
        manager.active_workers["worker-1"] = {"worker": Mock(), "thread": Mock(), "auto_cleanup": True}
        canceled_mock = Mock()
        count_mock = Mock()
        all_finished_mock = Mock()
        manager.worker_canceled.connect(canceled_mock)
        manager.active_worker_count_changed.connect(count_mock)
        manager.all_workers_finished.connect(all_finished_mock)

        manager._on_worker_canceled("worker-1")

        assert manager.active_workers == {}
        canceled_mock.assert_called_once_with("worker-1")
        count_mock.assert_called_once_with(0)
        all_finished_mock.assert_called_once()

    def test_cancel_worker_not_found_returns_false(self, manager: WorkerManager) -> None:
        result = manager.cancel_worker("nonexistent")
        assert result is False

    def test_cancel_all_workers_cancels_each_worker(self, manager: WorkerManager) -> None:
        for wid in ("w1", "w2", "w3"):
            worker = Mock()
            thread = Mock()
            thread.isRunning.return_value = True
            thread.wait.return_value = True
            manager.active_workers[wid] = {"worker": worker, "thread": thread, "auto_cleanup": True}
        canceled_ids: list[str] = []
        manager.worker_canceled.connect(canceled_ids.append)

        manager.cancel_all_workers()

        assert set(canceled_ids) == {"w1", "w2", "w3"}
        assert manager.get_active_worker_count() == 0


def _make_worker_mock() -> Mock:
    """WorkerManager.start_worker() が期待するシグナルを持つ Mock を返す。"""
    worker = Mock()
    worker.finished = Mock()
    worker.finished.connect = Mock()
    worker.error_occurred = Mock()
    worker.error_occurred.connect = Mock()
    worker.canceled = Mock()
    worker.canceled.connect = Mock()
    return worker


def _make_thread_mock() -> MagicMock:
    thread = MagicMock()
    thread.started = Mock()
    thread.started.connect = Mock()
    thread.finished = Mock()
    thread.finished.connect = Mock()
    return thread


@pytest.mark.unit
class TestStartWorker:
    def test_start_worker_registers_and_starts_thread(self, manager: WorkerManager) -> None:
        worker = _make_worker_mock()
        thread = _make_thread_mock()

        with patch("lorairo.gui.workers.manager.QThread", return_value=thread):
            result = manager.start_worker("worker-1", worker)

        assert result is True
        assert "worker-1" in manager.active_workers
        thread.start.assert_called_once()

    def test_start_worker_emits_started_signal(self, manager: WorkerManager, qtbot) -> None:
        worker = _make_worker_mock()
        thread = _make_thread_mock()

        started_ids: list[str] = []
        manager.worker_started.connect(started_ids.append)

        with patch("lorairo.gui.workers.manager.QThread", return_value=thread):
            with qtbot.waitSignal(manager.worker_started, timeout=1000):
                manager.start_worker("worker-1", worker)

        assert started_ids == ["worker-1"]

    def test_start_worker_returns_false_when_already_active(self, manager: WorkerManager) -> None:
        manager.active_workers["worker-1"] = {"worker": Mock(), "thread": Mock(), "auto_cleanup": True}
        worker = Mock()
        result = manager.start_worker("worker-1", worker)
        assert result is False

    def test_start_worker_increments_active_count_signal(self, manager: WorkerManager) -> None:
        worker = _make_worker_mock()
        thread = _make_thread_mock()

        count_values: list[int] = []
        manager.active_worker_count_changed.connect(count_values.append)

        with patch("lorairo.gui.workers.manager.QThread", return_value=thread):
            manager.start_worker("worker-1", worker)

        assert 1 in count_values


@pytest.mark.unit
class TestCleanupWorker:
    def test_cleanup_worker_removes_from_active_workers(self, manager: WorkerManager) -> None:
        thread = Mock()
        thread.isRunning.return_value = False
        worker = Mock()
        manager.active_workers["worker-1"] = {"worker": worker, "thread": thread, "auto_cleanup": True}

        result = manager.cleanup_worker("worker-1")

        assert result is True
        assert "worker-1" not in manager.active_workers

    def test_cleanup_worker_returns_false_when_not_found(self, manager: WorkerManager) -> None:
        result = manager.cleanup_worker("nonexistent")
        assert result is False

    def test_cleanup_worker_quits_running_thread(self, manager: WorkerManager) -> None:
        thread = Mock()
        thread.isRunning.return_value = True
        thread.wait.return_value = True
        worker = Mock()
        manager.active_workers["worker-1"] = {"worker": worker, "thread": thread, "auto_cleanup": True}

        manager.cleanup_worker("worker-1")

        thread.quit.assert_called_once()
        thread.wait.assert_called_once_with(3000)

    def test_cleanup_worker_emits_count_changed_signal(self, manager: WorkerManager) -> None:
        thread = Mock()
        thread.isRunning.return_value = False
        worker = Mock()
        manager.active_workers["worker-1"] = {"worker": worker, "thread": thread, "auto_cleanup": True}

        count_values: list[int] = []
        manager.active_worker_count_changed.connect(count_values.append)

        manager.cleanup_worker("worker-1")

        assert 0 in count_values

    def test_cleanup_all_workers_removes_all(self, manager: WorkerManager) -> None:
        for wid in ("w1", "w2"):
            thread = Mock()
            thread.isRunning.return_value = False
            manager.active_workers[wid] = {"worker": Mock(), "thread": thread, "auto_cleanup": True}

        manager.cleanup_all_workers()

        assert manager.get_active_worker_count() == 0


@pytest.mark.unit
class TestCleanupThread:
    def test_cleanup_thread_does_nothing_when_not_running(self, manager: WorkerManager) -> None:
        thread = Mock()
        thread.isRunning.return_value = False

        # 例外が発生しないことを確認
        manager._cleanup_thread("worker-1", thread)
        thread.wait.assert_not_called()

    def test_cleanup_thread_waits_when_running(self, manager: WorkerManager) -> None:
        thread = Mock()
        thread.isRunning.return_value = True
        thread.wait.return_value = True

        manager._cleanup_thread("worker-1", thread)

        thread.wait.assert_called_once_with(1000)

    def test_cleanup_thread_terminates_on_timeout(self, manager: WorkerManager) -> None:
        thread = Mock()
        thread.isRunning.return_value = True
        thread.wait.side_effect = [False, True]

        manager._cleanup_thread("worker-1", thread)

        thread.terminate.assert_called_once()

    def test_cleanup_thread_handles_exception(self, manager: WorkerManager) -> None:
        thread = Mock()
        thread.isRunning.side_effect = RuntimeError("スレッドエラー")

        # 例外が外部に漏れないことを確認
        manager._cleanup_thread("worker-1", thread)


@pytest.mark.unit
class TestWaitForAllWorkers:
    def test_wait_for_all_workers_empty_returns_true(self, manager: WorkerManager) -> None:
        result = manager.wait_for_all_workers()
        assert result is True

    def test_wait_for_all_workers_running_thread_returns_true_on_success(
        self, manager: WorkerManager
    ) -> None:
        thread = Mock()
        thread.isRunning.return_value = True
        thread.wait.return_value = True
        manager.active_workers["w1"] = {"worker": Mock(), "thread": thread, "auto_cleanup": True}

        result = manager.wait_for_all_workers(timeout_ms=5000)

        assert result is True
        thread.wait.assert_called_once_with(5000)

    def test_wait_for_all_workers_timeout_returns_false(self, manager: WorkerManager) -> None:
        thread = Mock()
        thread.isRunning.return_value = True
        thread.wait.return_value = False
        manager.active_workers["w1"] = {"worker": Mock(), "thread": thread, "auto_cleanup": True}

        result = manager.wait_for_all_workers(timeout_ms=100)

        assert result is False

    def test_wait_for_all_workers_not_running_thread(self, manager: WorkerManager) -> None:
        thread = Mock()
        thread.isRunning.return_value = False
        manager.active_workers["w1"] = {"worker": Mock(), "thread": thread, "auto_cleanup": True}

        result = manager.wait_for_all_workers()

        assert result is True
        thread.wait.assert_not_called()


class AnnotationWorker:
    """get_worker_summary テスト用スタブ。クラス名 "AnnotationWorker" を保持する。"""


@pytest.mark.unit
class TestGetWorkerSummary:
    def test_get_worker_summary_with_active_workers(self, manager: WorkerManager) -> None:
        worker = Mock(spec=AnnotationWorker)
        worker.status = Mock()
        worker.status.value = "running"
        manager.active_workers["w1"] = {"worker": worker, "thread": Mock(), "auto_cleanup": True}

        summary = manager.get_worker_summary()

        assert summary["active_worker_count"] == 1
        assert "w1" in summary["active_worker_ids"]
        assert "w1" in summary["worker_details"]
        assert summary["worker_details"]["w1"]["class_name"] == "AnnotationWorker"
        assert summary["worker_details"]["w1"]["status"] == "running"
        assert summary["worker_details"]["w1"]["auto_cleanup"] is True
