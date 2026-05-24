"""WorkerManager ユニットテスト（スレッド不要のシンプルなメソッド中心）。"""

from unittest.mock import Mock

import pytest

from lorairo.gui.workers.manager import WorkerManager
from lorairo.gui.workers.terminal import CancelReason, WorkerOutcome


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


class TestWorkerManagerCancellation:
    def test_cancel_worker_wait_success_finalizes_canceled_when_no_terminal_signal(self, manager):
        worker = Mock()
        thread = Mock()
        thread.isRunning.return_value = True
        thread.wait.return_value = True
        manager.active_workers["worker-1"] = {"worker": worker, "thread": thread, "auto_cleanup": True}
        canceled_mock = Mock()
        terminal_mock = Mock()
        manager.worker_canceled.connect(canceled_mock)
        manager.worker_terminal.connect(terminal_mock)

        result = manager.cancel_worker("worker-1", reason=CancelReason.PIPELINE_CANCEL)

        assert result is True
        worker.cancel.assert_called_once()
        thread.quit.assert_called_once()
        thread.wait.assert_called_once_with(2000)
        canceled_mock.assert_called_once_with("worker-1")
        terminal_mock.assert_called_once()
        event = terminal_mock.call_args.args[0]
        assert event.worker_id == "worker-1"
        assert event.outcome is WorkerOutcome.CANCELED
        assert event.cancel_reason is CancelReason.PIPELINE_CANCEL
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
        terminal_mock = Mock()
        manager.worker_terminal.connect(terminal_mock)
        app = Mock()
        app.processEvents.side_effect = lambda: manager._on_worker_finished("worker-1", {"ok": True})
        monkeypatch.setattr("lorairo.gui.workers.manager.QCoreApplication.instance", Mock(return_value=app))

        result = manager.cancel_worker("worker-1")

        assert result is True
        finished_mock.assert_called_once_with("worker-1", {"ok": True})
        canceled_mock.assert_not_called()
        assert terminal_mock.call_args.args[0].outcome is WorkerOutcome.SUCCEEDED
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
        terminal_mock = Mock()
        manager.worker_terminal.connect(terminal_mock)
        app = Mock()
        app.processEvents.side_effect = lambda: manager._on_worker_error("worker-1", "boom")
        monkeypatch.setattr("lorairo.gui.workers.manager.QCoreApplication.instance", Mock(return_value=app))

        result = manager.cancel_worker("worker-1")

        assert result is True
        error_mock.assert_called_once_with("worker-1", "boom")
        canceled_mock.assert_not_called()
        assert terminal_mock.call_args.args[0].outcome is WorkerOutcome.FAILED
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

    def test_cancel_worker_timeout_terminate_success_emits_terminated(self, manager):
        worker = Mock()
        thread = Mock()
        thread.isRunning.return_value = True
        thread.wait.side_effect = [False, False, True]
        manager.active_workers["worker-1"] = {"worker": worker, "thread": thread, "auto_cleanup": True}
        canceled_mock = Mock()
        error_mock = Mock()
        terminal_mock = Mock()
        manager.worker_canceled.connect(canceled_mock)
        manager.worker_error.connect(error_mock)
        manager.worker_terminal.connect(terminal_mock)

        result = manager.cancel_worker("worker-1")

        assert result is True
        thread.terminate.assert_called_once()
        assert [call.args for call in thread.wait.call_args_list] == [(2000,), (250,), (1000,)]
        canceled_mock.assert_not_called()
        error_mock.assert_called_once()
        event = terminal_mock.call_args.args[0]
        assert event.outcome is WorkerOutcome.TERMINATED
        assert event.cancel_reason is CancelReason.USER_REQUESTED
        assert "worker-1" not in manager.active_workers

    def test_cancel_worker_timeout_extends_cooperative_wait_before_terminate(self, manager):
        worker = Mock()
        thread = Mock()
        thread.isRunning.return_value = True
        thread.wait.side_effect = [False, True]
        manager.active_workers["worker-1"] = {"worker": worker, "thread": thread, "auto_cleanup": True}
        canceled_mock = Mock()
        terminal_mock = Mock()
        manager.worker_canceled.connect(canceled_mock)
        manager.worker_terminal.connect(terminal_mock)

        result = manager.cancel_worker("worker-1")

        assert result is True
        assert [call.args for call in thread.wait.call_args_list] == [(2000,), (250,)]
        thread.terminate.assert_not_called()
        canceled_mock.assert_called_once_with("worker-1")
        assert terminal_mock.call_args.args[0].outcome is WorkerOutcome.CANCELED
        assert "worker-1" not in manager.active_workers

    def test_worker_terminal_precedes_derived_compat_signal(self, manager):
        manager.active_workers["worker-1"] = {"worker": Mock(), "thread": Mock(), "auto_cleanup": True}
        calls = []
        manager.worker_terminal.connect(lambda event: calls.append(("terminal", event.outcome)))
        manager.worker_error.connect(
            lambda worker_id, error: calls.append(("compat_error", worker_id, error))
        )

        manager._on_worker_error("worker-1", "boom")

        assert calls == [
            ("terminal", WorkerOutcome.FAILED),
            ("compat_error", "worker-1", "boom"),
        ]

    def test_cancel_worker_timeout_terminate_wait_failure_emits_unresponsive(self, manager):
        worker = Mock()
        thread = Mock()
        thread.isRunning.return_value = True
        thread.wait.side_effect = [False, False, False]
        manager.active_workers["worker-1"] = {"worker": worker, "thread": thread, "auto_cleanup": True}
        canceled_mock = Mock()
        error_mock = Mock()
        terminal_mock = Mock()
        count_mock = Mock()
        all_finished_mock = Mock()
        manager.worker_canceled.connect(canceled_mock)
        manager.worker_error.connect(error_mock)
        manager.worker_terminal.connect(terminal_mock)
        manager.active_worker_count_changed.connect(count_mock)
        manager.all_workers_finished.connect(all_finished_mock)

        result = manager.cancel_worker("worker-1")

        assert result is True
        thread.terminate.assert_called_once()
        assert [call.args for call in thread.wait.call_args_list] == [(2000,), (250,), (1000,)]
        canceled_mock.assert_not_called()
        error_mock.assert_called_once()
        assert terminal_mock.call_args.args[0].outcome is WorkerOutcome.UNRESPONSIVE
        assert "worker-1" in manager.active_workers
        assert manager.active_workers["worker-1"]["unresponsive"] is True
        count_mock.assert_not_called()
        all_finished_mock.assert_not_called()

    def test_late_terminal_after_unresponsive_removes_active_worker_without_duplicate_event(self, manager):
        manager.active_workers["worker-1"] = {
            "worker": Mock(),
            "thread": Mock(),
            "auto_cleanup": True,
            "terminal_emitted": True,
            "unresponsive": True,
        }
        terminal_mock = Mock()
        count_mock = Mock()
        all_finished_mock = Mock()
        manager.worker_terminal.connect(terminal_mock)
        manager.active_worker_count_changed.connect(count_mock)
        manager.all_workers_finished.connect(all_finished_mock)

        manager._on_worker_finished("worker-1", {"ok": True})

        terminal_mock.assert_not_called()
        assert "worker-1" not in manager.active_workers
        count_mock.assert_called_once_with(0)
        all_finished_mock.assert_called_once()

    def test_on_worker_canceled_removes_active_worker_and_emits_terminal_signals(self, manager):
        manager.active_workers["worker-1"] = {"worker": Mock(), "thread": Mock(), "auto_cleanup": True}
        canceled_mock = Mock()
        count_mock = Mock()
        all_finished_mock = Mock()
        manager.worker_canceled.connect(canceled_mock)
        terminal_mock = Mock()
        manager.worker_terminal.connect(terminal_mock)
        manager.active_worker_count_changed.connect(count_mock)
        manager.all_workers_finished.connect(all_finished_mock)

        manager._on_worker_canceled("worker-1")

        assert manager.active_workers == {}
        canceled_mock.assert_called_once_with("worker-1")
        assert terminal_mock.call_args.args[0].outcome is WorkerOutcome.CANCELED
        count_mock.assert_called_once_with(0)
        all_finished_mock.assert_called_once()
