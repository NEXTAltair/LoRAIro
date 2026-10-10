"""Annotation waiting, persistence and terminals without real models or DB queries."""

from dataclasses import replace
from threading import Event
from time import monotonic
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QObject, QThread, QTimer, Slot
from PySide6.QtWidgets import QStatusBar, QTabWidget, QWidget

from lorairo.gui.services.progress_state_service import ProgressStateService
from lorairo.gui.services.worker_service import WorkerService
from lorairo.gui.widgets.annotation_progress_widget import AnnotationProgressWidget
from lorairo.gui.widgets.sync_job_ledger_widget import SyncJobLedgerWidget
from lorairo.gui.workers.annotation_worker import AnnotationWorker
from lorairo.gui.workers.base import WorkerProgress
from lorairo.gui.workers.terminal import WorkerOutcome, WorkerTerminalEvent
from lorairo.services.annotation_progress import AnnotationPhase, AnnotationProgress
from lorairo.services.job_ledger_service import JobEntry, JobStatus, StageProgress


@pytest.fixture
def progress():
    return AnnotationProgress(AnnotationPhase.RUNNING, 500, 12, monotonic() - 754)


def test_elapsed_updates_during_api_wait_and_saving(qtbot, monkeypatch):
    """A blocked API emits no fake updates; the GUI timer runs and saving stays active."""
    entered = Event()
    release_api = Event()
    saving = Event()
    release_save = Event()
    runner = Mock()
    registry = Mock()
    registry.get_available_models.return_value = []

    def execute_annotation(**kwargs):
        assert len(kwargs["image_paths"]) == 500
        assert len(kwargs["litellm_model_ids"]) == 12
        entered.set()
        assert release_api.wait(10)
        return {}

    runner.execute_annotation.side_effect = execute_annotation
    worker = AnnotationWorker(
        runner, ["/image.jpg"] * 500, [f"model-{i}" for i in range(12)], Mock(), registry
    )
    monkeypatch.setattr(worker, "_refresh_input_phash_cache", lambda: None)
    monkeypatch.setattr(worker, "_apply_refusal_prefilter", lambda: [])

    def save_results(results):
        saving.set()
        assert release_save.wait(10)
        return 0, 0, [], {}

    monkeypatch.setattr(worker, "_save_results_to_database", save_results)
    widget = AnnotationProgressWidget()
    qtbot.addWidget(widget)
    phases = []
    stages = []

    class ProgressReceiver(QObject):
        @Slot(object)
        def show_progress(self, event):
            phases.append(event.annotation_progress.phase)
            widget.set_progress(event.annotation_progress)

    receiver = ProgressReceiver()
    worker.progress_updated.connect(receiver.show_progress)
    worker.stage_progress_updated.connect(stages.append)
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    worker.error_occurred.connect(thread.quit)
    ticks = []
    timer = QTimer(widget)
    timer.setInterval(20)
    timer.timeout.connect(lambda: ticks.append(True))
    timer.start()
    thread.start()
    try:
        qtbot.waitUntil(lambda: entered.is_set() and widget._progress is not None)
        qtbot.waitUntil(lambda: phases[-1] is AnnotationPhase.RUNNING)
        assert widget.progress_bar.maximum() == 0
        assert "対象 500枚 / 12モデル" in widget.context_label.text()
        assert "%" not in widget.phase_label.text()
        assert "0件" not in widget.context_label.text()
        assert all(stage.percentage is None for stage in stages[0])
        before = widget.context_label.text()
        qtbot.waitUntil(lambda: widget.context_label.text() != before, timeout=2500)
        assert len(ticks) > 5
        assert phases == [AnnotationPhase.PREPARING, AnnotationPhase.RUNNING]
        release_api.set()
        qtbot.waitUntil(lambda: saving.is_set() and phases[-1] is AnnotationPhase.SAVING)
        assert widget.progress_bar.maximum() == 0
        assert widget._elapsed_timer.isActive()
        assert AnnotationPhase.COMPLETED not in phases
        release_save.set()
        qtbot.waitUntil(lambda: phases[-1] is AnnotationPhase.COMPLETED)
        assert widget.progress_bar.value() == 100
        assert not widget._elapsed_timer.isActive()
        runner.execute_annotation.assert_called_once()
    finally:
        release_api.set()
        release_save.set()
        thread.quit()
        assert thread.wait(5000)


@pytest.mark.parametrize(
    "phase", [AnnotationPhase.COMPLETED, AnnotationPhase.FAILED, AnnotationPhase.CANCELED]
)
def test_terminal_stops_timer_and_indeterminate_bar(qtbot, progress, phase):
    widget = AnnotationProgressWidget()
    qtbot.addWidget(widget)
    widget.set_progress(progress)
    assert widget._elapsed_timer.isActive()
    terminal = replace(progress, phase=phase, stopped_at=monotonic())
    widget.set_progress(terminal)
    assert widget.progress_bar.maximum() == 100
    assert not widget._elapsed_timer.isActive()
    assert widget.progress_bar.value() == (100 if phase is AnnotationPhase.COMPLETED else 0)


def test_cancel_request_waits_for_worker_stop(qtbot, monkeypatch):
    runner = Mock()
    registry = Mock()
    registry.get_available_models.return_value = []
    worker = AnnotationWorker(runner, ["/image.jpg"], ["model"], Mock(), registry)
    monkeypatch.setattr(worker, "_refresh_input_phash_cache", lambda: None)
    monkeypatch.setattr(worker, "_apply_refusal_prefilter", lambda: [])
    save = Mock()
    monkeypatch.setattr(worker, "_save_results_to_database", save)
    widget = AnnotationProgressWidget()
    qtbot.addWidget(widget)
    states = []
    worker.progress_updated.connect(lambda event: widget.set_progress(event.annotation_progress))
    worker.progress_updated.connect(lambda event: states.append(event.annotation_progress.phase))
    canceled = []
    worker.canceled.connect(lambda: canceled.append(True))

    def request_cancel(**kwargs):
        worker.cancel()
        assert states[-1] is AnnotationPhase.CANCELING
        assert widget.progress_bar.maximum() == 0
        assert widget._elapsed_timer.isActive()
        assert not canceled
        return {}

    runner.execute_annotation.side_effect = request_cancel
    worker.run()
    assert states[-1] is AnnotationPhase.CANCELED
    assert canceled == [True]
    assert not widget._elapsed_timer.isActive()
    save.assert_not_called()


def test_gui_cancel_of_blocked_api_delivers_pending_then_terminal(qtbot, monkeypatch):
    entered = Event()
    release = Event()
    runner = Mock()
    registry = Mock()
    registry.get_available_models.return_value = []

    def blocked_api(**kwargs):
        entered.set()
        assert release.wait(10)
        return {}

    runner.execute_annotation.side_effect = blocked_api
    worker = AnnotationWorker(runner, ["/image.jpg"], ["model"], Mock(), registry)
    monkeypatch.setattr(worker, "_refresh_input_phash_cache", lambda: None)
    monkeypatch.setattr(worker, "_apply_refusal_prefilter", lambda: [])
    save = Mock()
    monkeypatch.setattr(worker, "_save_results_to_database", save)
    widget = AnnotationProgressWidget()
    qtbot.addWidget(widget)
    phases = []

    class Receiver(QObject):
        @Slot(object)
        def update(self, event):
            phases.append(event.annotation_progress.phase)
            widget.set_progress(event.annotation_progress)

    receiver = Receiver()
    worker.progress_updated.connect(receiver.update)
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.canceled.connect(thread.quit)
    thread.start()
    try:
        qtbot.waitUntil(lambda: entered.is_set() and phases and phases[-1] is AnnotationPhase.RUNNING)
        worker.cancel()  # GUI thread, while the worker's event loop is blocked by the API.
        qtbot.waitUntil(lambda: phases[-1] is AnnotationPhase.CANCELING)
        assert widget._elapsed_timer.isActive()
        assert widget.progress_bar.maximum() == 0
        assert thread.isRunning()
        release.set()
        qtbot.waitUntil(lambda: phases[-1] is AnnotationPhase.CANCELED)
        qtbot.waitUntil(lambda: not thread.isRunning())
        assert phases == [
            AnnotationPhase.PREPARING,
            AnnotationPhase.RUNNING,
            AnnotationPhase.CANCELING,
            AnnotationPhase.CANCELED,
        ]
        assert not widget._elapsed_timer.isActive()
        assert widget.progress_bar.maximum() == 100
        save.assert_not_called()
    finally:
        release.set()
        thread.quit()
        assert thread.wait(5000)


def test_save_failure_never_reports_success(qtbot, monkeypatch):
    runner = Mock()
    runner.execute_annotation.return_value = {}
    registry = Mock()
    registry.get_available_models.return_value = []
    worker = AnnotationWorker(runner, ["/image.jpg"], ["model"], Mock(), registry)
    monkeypatch.setattr(worker, "_refresh_input_phash_cache", lambda: None)
    monkeypatch.setattr(worker, "_apply_refusal_prefilter", lambda: [])
    monkeypatch.setattr(worker, "_save_results_to_database", Mock(side_effect=RuntimeError("save failed")))
    phases = []
    worker.progress_updated.connect(lambda event: phases.append(event.annotation_progress.phase))
    worker.run()
    assert phases == [
        AnnotationPhase.PREPARING,
        AnnotationPhase.RUNNING,
        AnnotationPhase.SAVING,
        AnnotationPhase.FAILED,
    ]


def test_statusbar_progress_survives_short_messages_and_tab_switch(qtbot, progress):
    statusbar = QStatusBar()
    qtbot.addWidget(statusbar)
    service = ProgressStateService(statusbar)
    service.on_worker_progress_updated("annotation_1", WorkerProgress(0, "", annotation_progress=progress))
    statusbar.showMessage("別の操作", 1)
    widget = service._annotation_widget
    assert "対象 500枚 / 12モデル" in widget.context_label.text()
    assert widget._progress.started_at == progress.started_at
    assert widget.progress_bar.maximum() == 0

    tabs = QTabWidget()
    qtbot.addWidget(tabs)
    jobs = SyncJobLedgerWidget()
    tabs.addTab(jobs, "Jobs")
    tabs.addTab(QWidget(), "Other")
    entry = JobEntry(
        "annotation_1",
        "annotation",
        "画像アノテーション",
        annotation_progress=progress,
        stage_progress=[StageProgress("TAGS", "model", "local", None, "実行状況不明", "info")],
    )
    jobs.set_entries([entry])
    old_widget = jobs.findChild(AnnotationProgressWidget)
    tabs.setCurrentIndex(1)
    tabs.setCurrentIndex(0)
    jobs.set_entries([entry])
    new_widget = jobs.findChild(AnnotationProgressWidget)
    assert not old_widget._elapsed_timer.isActive()
    assert new_widget._progress.started_at == progress.started_at
    assert "12分" in new_widget.context_label.text()
    assert new_widget.progress_bar.maximum() == 0
    entry.status = JobStatus.CANCELING
    entry.annotation_progress = replace(progress, phase=AnnotationPhase.CANCELING)
    jobs.set_entries([entry])
    assert jobs.tableSyncJobs.cellWidget(0, 2).text() == "停止待ち"
    assert not jobs.tableSyncJobs.cellWidget(0, 6).isEnabled()
    entry.status = JobStatus.CANCELED
    jobs.set_entries([entry])
    assert jobs.findChild(AnnotationProgressWidget) is None


def test_global_progress_ignores_older_job_terminals(qtbot, progress):
    statusbar = QStatusBar()
    qtbot.addWidget(statusbar)
    service = ProgressStateService(statusbar)
    service.on_worker_progress_updated("annotation_a", WorkerProgress(0, "", annotation_progress=progress))
    newer = replace(progress, started_at=progress.started_at + 1)
    service.on_worker_progress_updated("annotation_b", WorkerProgress(0, "", annotation_progress=newer))
    old_terminal = replace(progress, phase=AnnotationPhase.COMPLETED, stopped_at=monotonic())
    service.on_worker_progress_updated(
        "annotation_a", WorkerProgress(100, "", annotation_progress=old_terminal)
    )
    assert service._annotation_worker_id == "annotation_b"
    assert service._annotation_widget._progress == newer
    assert service._annotation_widget._elapsed_timer.isActive()
    own_terminal = replace(newer, phase=AnnotationPhase.FAILED, stopped_at=monotonic())
    service.on_worker_progress_updated(
        "annotation_b", WorkerProgress(0, "", annotation_progress=own_terminal)
    )
    assert not service._annotation_widget._elapsed_timer.isActive()


@pytest.mark.parametrize(
    "terminal", [AnnotationPhase.COMPLETED, AnnotationPhase.FAILED, AnnotationPhase.CANCELED]
)
def test_global_progress_returns_to_older_active_job(qtbot, progress, terminal):
    statusbar = QStatusBar()
    qtbot.addWidget(statusbar)
    service = ProgressStateService(statusbar)
    service.on_worker_progress_updated("annotation_a", WorkerProgress(0, "", annotation_progress=progress))
    newer = replace(progress, started_at=progress.started_at + 1)
    service.on_worker_progress_updated("annotation_b", WorkerProgress(0, "", annotation_progress=newer))
    b_terminal = replace(newer, phase=terminal, stopped_at=monotonic())
    service.on_worker_progress_updated(
        "annotation_b", WorkerProgress(0, "", annotation_progress=b_terminal)
    )
    widget = service._annotation_widget
    assert service._annotation_worker_id == "annotation_a"
    assert widget._progress == progress
    assert widget._progress.started_at == progress.started_at
    assert widget._elapsed_timer.isActive()
    assert widget.progress_bar.maximum() == 0
    # Duplicate terminal delivery must not take the display back from the active job.
    service.on_worker_progress_updated(
        "annotation_b", WorkerProgress(0, "", annotation_progress=b_terminal)
    )
    assert widget._progress == progress
    a_terminal = replace(progress, phase=terminal, stopped_at=monotonic())
    service.on_worker_progress_updated(
        "annotation_a", WorkerProgress(0, "", annotation_progress=a_terminal)
    )
    assert widget._progress == a_terminal
    assert not widget._elapsed_timer.isActive()
    assert not service._active_annotation_progress


def test_first_progress_accepts_negative_synthetic_start_time(qtbot, progress):
    """A fresh CI VM may have an uptime shorter than the simulated elapsed time."""
    statusbar = QStatusBar()
    qtbot.addWidget(statusbar)
    service = ProgressStateService(statusbar)
    synthetic = replace(progress, started_at=-261.30653696)
    service.on_worker_progress_updated("annotation_a", WorkerProgress(0, "", annotation_progress=synthetic))
    assert service._annotation_widget is not None
    assert service._annotation_widget._progress == synthetic
    assert service._annotation_widget._elapsed_timer.isActive()


def test_cancel_during_save_preserves_committed_result_and_finished_signal(qtbot, monkeypatch):
    saving = Event()
    release_save = Event()
    committed = {}
    annotations = {"phash": {"model": {"tags": ["cat"], "error": None}}}
    runner = Mock()
    runner.execute_annotation.return_value = annotations
    registry = Mock()
    registry.get_available_models.return_value = []
    worker = AnnotationWorker(runner, ["/image.jpg"], ["model"], Mock(), registry)
    monkeypatch.setattr(worker, "_refresh_input_phash_cache", lambda: None)
    monkeypatch.setattr(worker, "_apply_refusal_prefilter", lambda: [])

    def save_results(results):
        saving.set()
        assert release_save.wait(10)
        committed.update(results)
        return 1, 0, [], {"phash": "image.jpg"}

    monkeypatch.setattr(worker, "_save_results_to_database", save_results)
    service = WorkerService(Mock(), Mock())
    service.worker_manager = Mock()
    service.worker_manager.request_cancel_worker.side_effect = lambda wid: worker.cancel() or True
    worker_id = "annotation_save_cancel"
    service._on_worker_started(worker_id)
    worker.progress_updated.connect(
        lambda event: service._annotation_progress_received.emit(worker_id, event)
    )
    received = []
    canceled = []
    service.enhanced_annotation_finished.connect(received.append)

    class Caller(QObject):
        @Slot(object)
        def finished(self, result):
            service._on_worker_terminal(
                WorkerTerminalEvent(worker_id, "annotation", WorkerOutcome.SUCCEEDED, result=result)
            )

        @Slot()
        def canceled(self):
            canceled.append(True)

    caller = Caller()
    worker.finished.connect(caller.finished)
    worker.canceled.connect(caller.canceled)
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    worker.canceled.connect(thread.quit)
    worker.error_occurred.connect(thread.quit)
    thread.start()
    try:
        entry = service.job_ledger.get(worker_id)
        qtbot.waitUntil(
            lambda: (
                saving.is_set()
                and entry.annotation_progress is not None
                and entry.annotation_progress.phase is AnnotationPhase.SAVING
            )
        )
        assert service.cancel_job(worker_id)
        assert entry.status is JobStatus.CANCELING
        assert not received and not committed
        release_save.set()
        qtbot.waitUntil(lambda: bool(received))
        result = received[0]
        assert committed == annotations == result.results
        assert result.db_save_success == 1
        assert result.phash_to_filename == {"phash": "image.jpg"}
        assert not canceled
        assert entry.status is JobStatus.FINISHED
        assert entry.annotation_progress.phase is AnnotationPhase.COMPLETED
        assert "保存 1件" in entry.summary
    finally:
        release_save.set()
        thread.quit()
        assert thread.wait(5000)


@pytest.mark.parametrize(
    "outcome, phase",
    [
        (WorkerOutcome.SUCCEEDED, AnnotationPhase.COMPLETED),
        (WorkerOutcome.FAILED, AnnotationPhase.FAILED),
        (WorkerOutcome.CANCELED, AnnotationPhase.CANCELED),
        (WorkerOutcome.UNRESPONSIVE, AnnotationPhase.FAILED),
    ],
)
def test_service_preserves_context_and_publishes_terminals(qtbot, progress, outcome, phase):
    service = WorkerService(Mock(), Mock())
    worker_id = "annotation_test"
    service._on_annotation_progress(worker_id, WorkerProgress(0, "", annotation_progress=progress))
    service._on_worker_started(worker_id)
    entry = service.job_ledger.get(worker_id)
    assert entry.annotation_progress.started_at == progress.started_at
    service.worker_manager = Mock()
    service.worker_manager.request_cancel_worker.return_value = True
    assert service.cancel_job(worker_id)
    assert entry.status is JobStatus.CANCELING
    assert entry.annotation_progress.phase is AnnotationPhase.CANCELING
    assert entry.finished_at is None
    service.worker_manager.cancel_worker.assert_not_called()
    captured = []
    service.worker_progress_updated.connect(lambda wid, event: captured.append(event))
    # Older GUI-queued API snapshots cannot undo an already accepted cancellation request.
    service._on_annotation_progress(worker_id, WorkerProgress(0, "", annotation_progress=progress))
    assert entry.annotation_progress.phase is AnnotationPhase.CANCELING
    assert captured[-1].annotation_progress.phase is AnnotationPhase.CANCELING
    service._on_worker_terminal(WorkerTerminalEvent(worker_id, "annotation", outcome, error="boom"))
    assert entry.annotation_progress.phase is phase
    assert entry.annotation_progress.stopped_at is not None
    assert captured[-1].annotation_progress.phase is phase
    # A late API snapshot cannot resurrect the terminated job or its global timer.
    before = len(captured)
    service._on_annotation_progress(worker_id, WorkerProgress(0, "", annotation_progress=progress))
    assert len(captured) == before
