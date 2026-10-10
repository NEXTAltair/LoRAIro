"""The refresh release barrier waits for native cleanup without blocking GUI."""

import threading
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QTimer

from lorairo.gui.workers.base import LoRAIroWorkerBase
from lorairo.gui.workers.manager import _ABANDONED_WORKERS, WorkerManager


class ImmediateWorker(LoRAIroWorkerBase[None]):
    def execute(self):
        return None


def test_worker_id_cannot_be_reused_before_native_release(qapp):
    manager = WorkerManager()
    manager._deferred_thread_workers["retiring"] = {"thread": Mock(), "worker": Mock()}
    replacement = Mock()
    assert not manager.start_worker("retiring", replacement, defer_thread_release=True)
    replacement.moveToThread.assert_not_called()
    assert manager.get_pending_thread_release_count() == 1


def test_release_signal_waits_for_native_exit_after_deferred_worker_destruction(qapp, qtbot):
    manager = WorkerManager()
    worker = ImmediateWorker()
    destruction_entered = threading.Event()
    destruction_release = threading.Event()
    released = []

    def hold_native_destruction():
        destruction_entered.set()
        assert destruction_release.wait(5), "Native destruction was not released"

    worker.destroyed.connect(hold_native_destruction)
    manager.worker_thread_released.connect(released.append)
    assert manager.start_worker("annotation_refresh_test", worker, defer_thread_release=True)
    thread = manager.active_workers["annotation_refresh_test"]["thread"]
    try:
        qtbot.waitUntil(destruction_entered.is_set)
        qtbot.waitUntil(lambda: manager.get_active_worker_count() == 0)
        assert manager.get_pending_thread_release_count() == 1
        assert not thread.wait(0)
        ticks = []
        QTimer.singleShot(0, lambda: ticks.append(True))
        qtbot.waitUntil(lambda: bool(ticks))
        assert released == []

        # Terminal has already removed this worker from active_workers. Window
        # teardown must nevertheless park its still-running native thread.
        manager.cancel_all_workers(total_grace_ms=0)
        assert id(thread) in _ABANDONED_WORKERS
        assert released == []
        destruction_release.set()
        qtbot.waitUntil(lambda: released == ["annotation_refresh_test"])
        assert manager.get_pending_thread_release_count() == 0
        assert id(thread) not in _ABANDONED_WORKERS
    finally:
        destruction_release.set()
        qtbot.waitUntil(lambda: manager.get_pending_thread_release_count() == 0)


def test_finished_observation_does_not_release_or_delete_thread_before_wait_zero(qapp):
    manager = WorkerManager()
    thread = Mock()
    thread.wait.return_value = False
    worker = Mock()
    manager._deferred_thread_workers["worker"] = {"thread": thread, "worker": worker}
    released = Mock()
    manager.worker_thread_released.connect(released)

    manager._poll_deferred_thread_release()
    thread.wait.assert_called_once_with(0)
    thread.deleteLater.assert_not_called()
    released.assert_not_called()
    assert manager.get_pending_thread_release_count() == 1

    thread.wait.return_value = True
    manager._poll_deferred_thread_release()
    thread.deleteLater.assert_called_once()
    released.assert_called_once_with("worker")
    assert manager.get_pending_thread_release_count() == 0


@pytest.mark.parametrize("terminal_already_observed", [False, True])
def test_shutdown_retains_deferred_thread_until_native_exit(qapp, terminal_already_observed):
    manager = WorkerManager()
    thread = Mock()
    thread.wait.return_value = False
    thread.isRunning.return_value = True
    worker = Mock()
    info = {
        "thread": thread,
        "worker": worker,
        "auto_cleanup": True,
        "terminal_emitted": False,
    }
    manager._deferred_thread_workers["worker"] = info
    if not terminal_already_observed:
        manager.active_workers["worker"] = info
    try:
        manager.cancel_all_workers(total_grace_ms=0)
        assert _ABANDONED_WORKERS[id(thread)] == (thread, worker)
        # No finished callback may release ownership ahead of native exit.
        thread.finished.connect.assert_not_called()
        thread.terminate.assert_not_called()
        thread.deleteLater.assert_not_called()
        thread.wait.return_value = True
        manager._poll_deferred_thread_release()
        assert id(thread) not in _ABANDONED_WORKERS
    finally:
        _ABANDONED_WORKERS.pop(id(thread), None)
