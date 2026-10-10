"""Execution refresh uses real Qt workers without loading annotation models."""

import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from loguru import logger
from PySide6.QtCore import QThread, QTimer

from lorairo.gui.state.dataset_state import DatasetStateManager
from lorairo.gui.workers.manager import _ABANDONED_WORKERS
from lorairo.gui.workers.terminal import WorkerOutcome, WorkerTerminalEvent


class ControlledRepository:
    """Block each query at a deterministic point while the GUI remains live."""

    def __init__(self):
        self.lookup_started = threading.Event()
        self.lookup_release = threading.Event()
        self.load_started = threading.Event()
        self.load_release = threading.Event()
        self.lookup_release.set()
        self.load_release.set()
        self.lookup_calls = []
        self.load_calls = []
        self.query_threads = []
        self.mapping = {"a": [1, 2, 999], "b": [2, 3]}
        self.annotations = {
            image_id: {
                "tags": [{"tag": f"fresh-{image_id}"}],
                "tags_text": f"fresh-{image_id}",
                "captions": [],
                "ratings": [],
                "manual_rating_value": "",
                "quality_summary": {"tier": "fresh"},
                "stored_image_path": "/original/must-not-replace.webp",
            }
            for image_id in (1, 2, 3)
        }
        self.lookup_error = None
        self.load_error = None
        self.get_images_metadata_batch = Mock(side_effect=AssertionError("Full fetch is forbidden"))
        self.get_image_metadata = Mock(side_effect=AssertionError("Full fetch is forbidden"))

    def find_image_ids_by_phashes_multi(self, phashes):
        self.query_threads.append(threading.get_ident())
        self.lookup_calls.append(phashes.copy())
        self.lookup_started.set()
        assert self.lookup_release.wait(5), "Lookup was not released"
        if self.lookup_error is not None:
            raise self.lookup_error
        return {phash: self.mapping[phash].copy() for phash in phashes if phash in self.mapping}

    def get_image_annotation_metadata(self, image_id):
        self.query_threads.append(threading.get_ident())
        self.load_calls.append(image_id)
        # Read before blocking, allowing another execution/manual edit to race.
        result = self.annotations[image_id].copy()
        self.load_started.set()
        assert self.load_release.wait(5), "Annotation load was not released"
        if self.load_error is not None:
            raise self.load_error
        return result


@pytest.fixture
def refresh_setup(qapp, qtbot):
    repo = ControlledRepository()
    state = DatasetStateManager()
    state.set_db_manager(SimpleNamespace(image_repo=repo))
    state.set_dataset_images(
        [
            {
                "id": image_id,
                "stored_image_path": f"/processed/{image_id}.webp",
                "width": 768,
                "height": 512,
                "long_edge": 768,
                "tags": [{"tag": "old"}],
                "tags_text": "old",
                "ratings": [{"rating": "old"}],
                "manual_rating_value": "old",
                "quality_summary": {"tier": "old"},
                "annotation_review_status": "completed",
                "annotation_review_warning_count": 3,
                "annotation_review_checked_at": "old-check",
                "annotation_review_model": "old-model",
                "annotation_review_threshold": 0.5,
            }
            for image_id in (1, 2, 3, 4)
        ]
    )
    try:
        yield state, repo
    finally:
        repo.lookup_release.set()
        repo.load_release.set()
        state.shutdown_annotation_refresh()
        manager = state._annotation_worker_manager
        if manager is not None:
            qtbot.waitUntil(lambda: manager.get_active_worker_count() == 0, timeout=3000)
            qtbot.waitUntil(lambda: manager.get_pending_thread_release_count() == 0, timeout=3000)
            qtbot.waitUntil(lambda: not _ABANDONED_WORKERS, timeout=3000)
            # Drain thread.finished/deleteLater before state teardown.
            assert_gui_tick(qtbot)


def wait_for_lookup(qtbot, state):
    qtbot.waitUntil(
        lambda: state._annotation_lookup_request is None and not state._annotation_pending_phashes,
        timeout=3000,
    )


def assert_gui_tick(qtbot):
    ticks = []
    QTimer.singleShot(0, lambda: ticks.append(True))
    qtbot.waitUntil(lambda: bool(ticks), timeout=1000)


def test_multiversion_lookup_only_invalidates_unique_cached_annotations(qtbot, refresh_setup):
    state, repo = refresh_setup
    original = {image["id"]: image.copy() for image in state.all_images}
    review_updates = []
    state.execution_annotations_invalidated.connect(review_updates.append)
    state.refresh_annotations_after_execution({"a", "b"})
    wait_for_lookup(qtbot, state)

    assert repo.lookup_calls == [{"a", "b"}]
    assert state._annotation_invalidated_ids == {1, 2, 3}
    for image_id in (1, 2, 3):
        cached = state.get_image_by_id(image_id)
        assert not set(cached).intersection(state._ANNOTATION_CACHE_KEYS)
        assert not set(cached).intersection(state._ANNOTATION_REVIEW_CACHE_KEYS)
        assert cached["stored_image_path"] == original[image_id]["stored_image_path"]
        assert cached["long_edge"] == 768
    assert state.get_image_by_id(4) == original[4]
    assert repo.load_calls == []
    assert len(review_updates) == 1
    assert set(review_updates[0]) == {1, 2, 3}
    assert len(review_updates[0]) == 3
    repo.get_image_metadata.assert_not_called()
    repo.get_images_metadata_batch.assert_not_called()


def test_lookup_and_current_load_keep_gui_live_and_apply_on_gui_thread(qapp, qtbot, refresh_setup):
    state, repo = refresh_setup
    state.set_current_image(1)
    updates = []
    update_threads = []
    state.current_image_data_changed.connect(lambda data: updates.append(data.copy()))
    state.current_image_data_changed.connect(lambda _data: update_threads.append(QThread.currentThread()))
    repo.lookup_release.clear()
    repo.load_release.clear()

    state.refresh_annotations_after_execution({"a"})
    qtbot.waitUntil(repo.lookup_started.is_set)
    assert_gui_tick(qtbot)
    assert updates == []
    repo.lookup_release.set()
    qtbot.waitUntil(repo.load_started.is_set)
    assert_gui_tick(qtbot)
    assert len(updates) == 1
    assert updates[0]["id"] == 1
    assert "tags" not in updates[0]
    assert "ratings" not in updates[0]
    assert updates[0]["stored_image_path"] == "/processed/1.webp"
    repo.load_release.set()
    qtbot.waitUntil(lambda: len(updates) == 2)

    assert updates[-1]["tags_text"] == "fresh-1"
    assert updates[-1]["stored_image_path"] == "/processed/1.webp"
    assert updates[-1]["long_edge"] == 768
    assert repo.load_calls == [1]
    assert all(thread_id != threading.get_ident() for thread_id in repo.query_threads)
    assert update_threads == [qapp.thread(), qapp.thread()]
    assert "tags" not in state.get_image_by_id(2)


@pytest.mark.parametrize("load_result", ["error", None, {}])
def test_current_image_invalidation_clears_display_even_if_reload_fails(qtbot, refresh_setup, load_result):
    state, repo = refresh_setup
    state.set_current_image(1)
    displayed = state.get_current_image_data().copy()
    updates = []

    def display(data):
        displayed.clear()
        displayed.update(data)
        updates.append(data.copy())

    state.current_image_data_changed.connect(display)
    if load_result == "error":
        query = Mock(side_effect=RuntimeError("annotation query failed"))
    else:
        query = Mock(return_value=load_result)
    repo.get_image_annotation_metadata = query

    state.refresh_annotations_after_execution({"a"})
    qtbot.waitUntil(lambda: bool(repo.lookup_calls) and state._annotation_active_worker_id is None)

    query.assert_called_once_with(1)
    assert len(updates) == 1
    assert displayed["id"] == 1
    assert displayed["stored_image_path"] == "/processed/1.webp"
    assert displayed["long_edge"] == 768
    assert not set(displayed).intersection(state._ANNOTATION_CACHE_KEYS)
    assert not set(displayed).intersection(state._ANNOTATION_REVIEW_CACHE_KEYS)
    assert 1 in state._annotation_invalidated_ids


def test_selecting_invalidated_image_loads_async_and_shows_basic_metadata(
    qtbot, refresh_setup, monkeypatch
):
    state, repo = refresh_setup
    state.refresh_annotations_after_execution({"a"})
    wait_for_lookup(qtbot, state)
    state.set_current_image(4)
    updates = []
    state.current_image_data_changed.connect(lambda data: updates.append(data.copy()))
    ensure = Mock(side_effect=AssertionError("Invalidated annotations cannot load on GUI"))
    monkeypatch.setattr(state, "_ensure_annotations_loaded", ensure)
    repo.load_release.clear()

    state.set_current_image(2)
    assert updates == [state.get_image_by_id(2)]
    assert updates[0]["id"] == 2
    assert updates[0]["stored_image_path"] == "/processed/2.webp"
    assert "tags" not in updates[0]
    qtbot.waitUntil(repo.load_started.is_set)
    assert_gui_tick(qtbot)
    repo.load_release.set()
    qtbot.waitUntil(lambda: len(updates) == 2)
    assert updates[-1]["tags_text"] == "fresh-2"
    ensure.assert_not_called()


def test_load_failure_keeps_selected_basic_metadata_without_success_log(qtbot, refresh_setup):
    state, repo = refresh_setup
    state.refresh_annotations_after_execution({"a"})
    wait_for_lookup(qtbot, state)
    state.set_current_image(4)
    updates = []
    state.current_image_data_changed.connect(lambda data: updates.append(data.copy()))
    repo.load_error = RuntimeError("annotation query failed")
    messages = []
    sink = logger.add(lambda message: messages.append(str(message)), level="DEBUG")
    try:
        state.set_current_image(2)
        qtbot.waitUntil(lambda: state._annotation_load_request is None)
    finally:
        logger.remove(sink)

    assert state.current_image_id == 2
    assert len(updates) == 1
    assert updates[0]["id"] == 2
    assert updates[0]["stored_image_path"] == "/processed/2.webp"
    assert "tags" not in updates[0]
    assert any("注釈再取得失敗" in message for message in messages)
    assert not any("反映 1件" in message or "画像キャッシュを更新" in message for message in messages)
    assert repo.load_calls == [2]


@pytest.mark.parametrize("missing_annotations", [None, {}])
def test_missing_annotations_stay_invalidated_without_success_or_retry(
    qtbot, refresh_setup, missing_annotations
):
    state, repo = refresh_setup
    state.refresh_annotations_after_execution({"a"})
    wait_for_lookup(qtbot, state)
    query = Mock(return_value=missing_annotations)
    repo.get_image_annotation_metadata = query
    messages = []
    sink = logger.add(lambda message: messages.append(str(message)), level="DEBUG")
    try:
        state.set_current_image(2)
        qtbot.waitUntil(lambda: state._annotation_active_worker_id is None)
    finally:
        logger.remove(sink)

    query.assert_called_once_with(2)
    assert 2 in state._annotation_invalidated_ids
    assert "tags" not in state.get_image_by_id(2)
    assert any("取得 0件、反映 0件" in message for message in messages)
    assert not any("反映 1件" in message for message in messages)


def test_lookup_failure_does_not_invalidate_or_emit_success(qtbot, refresh_setup):
    state, repo = refresh_setup
    original = state.get_image_by_id(1).copy()
    repo.lookup_error = RuntimeError("lookup failed")
    review_updates = []
    state.execution_annotations_invalidated.connect(review_updates.append)
    messages = []
    sink = logger.add(lambda message: messages.append(str(message)), level="DEBUG")
    try:
        state.refresh_annotations_after_execution({"a"})
        wait_for_lookup(qtbot, state)
    finally:
        logger.remove(sink)

    assert state.get_image_by_id(1) == original
    assert repo.load_calls == []
    assert review_updates == []
    assert any("ID 解決失敗" in message for message in messages)
    assert not any(
        "注釈キャッシュ無効化" in message or "画像キャッシュを更新" in message for message in messages
    )


@pytest.mark.parametrize("select_again", [False, True])
def test_selection_change_discards_delayed_load_even_when_same_id_is_selected_again(
    qtbot, refresh_setup, select_again
):
    state, repo = refresh_setup
    state.set_current_image(1)
    repo.load_release.clear()
    state.refresh_annotations_after_execution({"a"})
    qtbot.waitUntil(repo.load_started.is_set)
    stale_request = state._annotation_load_request
    updates = []
    state.current_image_data_changed.connect(lambda data: updates.append(data.copy()))

    state.set_current_image(4)
    if select_again:
        state.set_current_image(1)
    count_before = len(updates)
    # Simulate a queued success already emitted just before cancellation.
    state._apply_annotation_load(stale_request, {"tags_text": "stale"})
    assert len(updates) == count_before
    assert "tags_text" not in state.get_image_by_id(1)
    repo.load_release.set()
    if select_again:
        qtbot.waitUntil(lambda: state.get_image_by_id(1).get("tags_text") == "fresh-1")
        assert updates[-1]["tags_text"] == "fresh-1"
    else:
        qtbot.waitUntil(lambda: state._annotation_active_worker_id is None)
        assert len(updates) == 1
        assert updates[0]["id"] == 4


@pytest.mark.parametrize("phase", ["lookup", "load", "idle"])
def test_search_replacement_keeps_retained_images_on_asynchronous_refresh(
    qtbot, refresh_setup, monkeypatch, phase
):
    state, repo = refresh_setup
    if phase != "idle":
        state.set_current_image(1)
    repo.load_release.clear()
    if phase == "lookup":
        repo.lookup_release.clear()
    state.refresh_annotations_after_execution({"a"})
    if phase == "lookup":
        qtbot.waitUntil(repo.lookup_started.is_set)
    elif phase == "load":
        qtbot.waitUntil(repo.load_started.is_set)
    else:
        wait_for_lookup(qtbot, state)
    old_load = state._annotation_load_request
    repo.annotations[1]["tags_text"] = "after-search"
    replacement = [
        {"id": image_id, "stored_image_path": f"/search/{image_id}.webp", "long_edge": 512}
        for image_id in (1, 2)
    ]
    updates = []
    state.current_image_data_changed.connect(lambda data: updates.append(data.copy()))
    ensure = Mock(side_effect=AssertionError("Retained invalidations cannot load on GUI"))
    monkeypatch.setattr(state, "_ensure_annotations_loaded", ensure)

    state.update_from_search_results(replacement)
    if phase == "idle":
        state.set_current_image(1)
    assert updates[-1]["id"] == 1
    assert updates[-1]["stored_image_path"] == "/search/1.webp"
    assert "tags" not in updates[-1]
    if old_load is not None:
        state._apply_annotation_load(old_load, {"tags_text": "stale"})
        assert "tags_text" not in state.get_image_by_id(1)
        assert repo.load_calls == [1]
    assert_gui_tick(qtbot)
    repo.lookup_release.set()
    repo.load_release.set()
    qtbot.waitUntil(lambda: state.get_image_by_id(1).get("tags_text") == "after-search")
    assert updates[-1]["stored_image_path"] == "/search/1.webp"
    assert state._annotation_invalidated_ids == {2}

    repo.load_release.clear()
    state.set_current_image(2)
    assert updates[-1]["id"] == 2
    assert "tags" not in updates[-1]
    assert_gui_tick(qtbot)
    repo.load_release.set()
    qtbot.waitUntil(lambda: state.get_image_by_id(2).get("tags_text") == "fresh-2")
    ensure.assert_not_called()
    assert repo.load_calls == ([1, 1, 2] if phase == "load" else [1, 2])


def test_search_replacement_preserves_manual_edit_priority_for_pending_lookup(qtbot, refresh_setup):
    state, repo = refresh_setup
    repo.lookup_release.clear()
    state.refresh_annotations_after_execution({"a"})
    qtbot.waitUntil(repo.lookup_started.is_set)
    manual = {"id": 1, "stored_image_path": "/manual/1.webp", "tags": [], "tags_text": "manual"}
    state.update_image_metadata(1, manual)
    state.update_from_search_results([manual.copy(), {"id": 2, "stored_image_path": "/search/2.webp"}])
    state.set_current_image(1)
    repo.lookup_release.set()
    wait_for_lookup(qtbot, state)

    assert state.get_image_by_id(1)["tags_text"] == "manual"
    assert state._annotation_invalidated_ids == {2}
    assert repo.load_calls == []


@pytest.mark.parametrize("phase", ["lookup", "load"])
def test_shutdown_retires_blocked_worker_without_waiting_or_accepting_results(qtbot, refresh_setup, phase):
    state, repo = refresh_setup
    state.set_current_image(1)
    updates = []
    state.current_image_data_changed.connect(lambda data: updates.append(data.copy()))
    release = repo.lookup_release if phase == "lookup" else repo.load_release
    started = repo.lookup_started if phase == "lookup" else repo.load_started
    release.clear()
    state.refresh_annotations_after_execution({"a"})
    qtbot.waitUntil(started.is_set)
    updates_before_shutdown = updates.copy()
    review_updates = []
    state.execution_annotations_invalidated.connect(review_updates.append)
    worker_manager = state._annotation_worker_manager
    request = state._annotation_lookup_request if phase == "lookup" else state._annotation_load_request
    active_info = worker_manager.active_workers[request.worker_id]
    thread = active_info["thread"]

    state.shutdown_annotation_refresh()
    assert_gui_tick(qtbot)
    assert thread.isRunning()
    assert id(thread) in _ABANDONED_WORKERS
    state.refresh_annotations_after_execution({"b"})
    assert len(repo.lookup_calls) == 1
    state._on_annotation_refresh_terminal(
        WorkerTerminalEvent(
            request.worker_id, "annotation", WorkerOutcome.SUCCEEDED, {"tags_text": "stale"}
        )
    )
    assert updates == updates_before_shutdown
    assert review_updates == []
    release.set()
    qtbot.waitUntil(lambda: worker_manager.get_active_worker_count() == 0)
    assert updates == updates_before_shutdown
    assert review_updates == []
    if phase == "lookup":
        assert repo.load_calls == []


@pytest.mark.parametrize("phase", ["lookup", "load"])
@pytest.mark.parametrize("change", ["search", "dataset", "db", "project", "clear", "selection_clear"])
def test_context_changes_do_not_accept_old_query_results(qtbot, refresh_setup, phase, change):
    state, repo = refresh_setup
    state.set_current_image(1)
    release = repo.lookup_release if phase == "lookup" else repo.load_release
    started = repo.lookup_started if phase == "lookup" else repo.load_started
    release.clear()
    state.refresh_annotations_after_execution({"a"})
    qtbot.waitUntil(started.is_set)
    replacement = [{"id": 1, "stored_image_path": "/new/1.webp", "tags": [], "tags_text": "new"}]
    if change == "search":
        state.update_from_search_results(replacement)
    elif change == "dataset":
        state.set_dataset_images(replacement)
    elif change == "db":
        state.set_db_manager(SimpleNamespace(image_repo=ControlledRepository()))
    elif change == "project":
        state.set_dataset_path(Path("/new/project"))
    elif change == "clear":
        state.clear_dataset()
    else:
        state.clear_current_image()
    updates = []
    state.current_image_data_changed.connect(lambda data: updates.append(data.copy()))
    release.set()
    if change == "search":
        qtbot.waitUntil(lambda: state.get_image_by_id(1).get("tags_text") == "fresh-1")
        assert updates[-1]["stored_image_path"] == "/new/1.webp"
    else:
        qtbot.waitUntil(lambda: state._annotation_worker_manager.get_active_worker_count() == 0)
        assert updates == []
    if change == "dataset":
        assert state.get_image_by_id(1) == replacement[0]
    if phase == "lookup" and change != "search":
        assert repo.load_calls == []


def test_multiple_completions_are_coalesced_without_losing_prior_phashes(qtbot, refresh_setup):
    state, repo = refresh_setup
    state.set_current_image(3)
    repo.lookup_release.clear()
    state.refresh_annotations_after_execution({"a"})
    qtbot.waitUntil(repo.lookup_started.is_set)
    state.refresh_annotations_after_execution({"b"})
    state.refresh_annotations_after_execution({"b"})
    repo.lookup_release.set()
    qtbot.waitUntil(lambda: state.get_image_by_id(3).get("tags_text") == "fresh-3")

    assert repo.lookup_calls == [{"a"}, {"b"}]
    assert repo.load_calls == [3]
    assert state._annotation_invalidated_ids == {1, 2}


def test_new_completion_cancels_old_annotation_read_and_loads_latest(qtbot, refresh_setup):
    state, repo = refresh_setup
    state.set_current_image(1)
    repo.load_release.clear()
    state.refresh_annotations_after_execution({"a"})
    qtbot.waitUntil(repo.load_started.is_set)
    repo.annotations[1]["tags_text"] = "new-execution"
    state.refresh_annotations_after_execution({"a"})
    assert_gui_tick(qtbot)
    assert len(repo.load_calls) == 1
    repo.load_release.set()
    qtbot.waitUntil(lambda: state.get_image_by_id(1).get("tags_text") == "new-execution")

    assert len(repo.load_calls) == 2
    assert state.get_image_by_id(1)["stored_image_path"] == "/processed/1.webp"


def test_rapid_selections_keep_one_physical_read_and_load_only_latest(qtbot, refresh_setup):
    state, repo = refresh_setup
    state.set_current_image(1)
    repo.load_release.clear()
    state.refresh_annotations_after_execution({"a", "b"})
    qtbot.waitUntil(repo.load_started.is_set)
    first_worker_id = state._annotation_active_worker_id
    for image_id in (2, 3, 1, 2, 3):
        state.set_current_image(image_id)
        assert_gui_tick(qtbot)
        assert repo.load_calls == [1]
        assert state._annotation_active_worker_id == first_worker_id
        assert state._annotation_worker_manager.get_active_worker_count() == 1

    repo.load_release.set()
    qtbot.waitUntil(lambda: state.get_image_by_id(3).get("tags_text") == "fresh-3")
    assert repo.load_calls == [1, 3]
    assert "tags" not in state.get_image_by_id(1)
    assert "tags" not in state.get_image_by_id(2)


def test_successive_completions_start_only_after_prior_native_exit(qtbot, refresh_setup, monkeypatch):
    state, repo = refresh_setup
    state.set_current_image(1)
    manager = state._get_annotation_worker_manager()
    original_start = manager.start_worker
    starts = []

    def checked_start(worker_id, worker, **kwargs):
        # This includes deferred QObject destruction, not just the terminal
        # signal or disappearance from active_workers (#1384 native deadlock).
        assert manager.get_pending_thread_release_count() == 0
        assert original_start(worker_id, worker, **kwargs)
        starts.append(worker_id)
        return True

    monkeypatch.setattr(manager, "start_worker", checked_start)
    for iteration in range(30):
        expected = f"execution-{iteration}"
        repo.annotations[1]["tags_text"] = expected
        state.refresh_annotations_after_execution({"a"})
        qtbot.waitUntil(lambda expected=expected: state.get_image_by_id(1).get("tags_text") == expected)
        assert_gui_tick(qtbot)
    assert len(starts) == 60


@pytest.mark.parametrize("phase", ["lookup", "load"])
def test_context_replacement_waits_for_canceled_physical_worker_before_new_lookup(
    qtbot, refresh_setup, phase
):
    state, repo = refresh_setup
    state.set_current_image(1)
    release = repo.lookup_release if phase == "lookup" else repo.load_release
    started = repo.lookup_started if phase == "lookup" else repo.load_started
    release.clear()
    state.refresh_annotations_after_execution({"a"})
    qtbot.waitUntil(started.is_set)
    first_worker_id = state._annotation_active_worker_id

    state.update_from_search_results(
        [{"id": 3, "stored_image_path": "/new/3.webp", "tags": [], "tags_text": "old"}]
    )
    state.set_current_image(3)
    state.refresh_annotations_after_execution({"b"})
    assert_gui_tick(qtbot)
    assert state._annotation_active_worker_id == first_worker_id
    assert repo.lookup_calls == [{"a"}]
    assert state._annotation_worker_manager.get_active_worker_count() == 1

    release.set()
    qtbot.waitUntil(lambda: state.get_image_by_id(3).get("tags_text") == "fresh-3")
    assert repo.lookup_calls == [{"a"}, {"a", "b"} if phase == "lookup" else {"b"}]
    assert state.get_image_by_id(3)["stored_image_path"] == "/new/3.webp"


@pytest.mark.parametrize("phase", ["lookup", "load"])
@pytest.mark.parametrize("edit", ["replace", "annotation_refresh", "invalidate", "add"])
def test_manual_edits_win_over_delayed_results(qtbot, refresh_setup, phase, edit):
    state, repo = refresh_setup
    state.set_current_image(1)
    release = repo.lookup_release if phase == "lookup" else repo.load_release
    started = repo.lookup_started if phase == "lookup" else repo.load_started
    release.clear()
    state.refresh_annotations_after_execution({"a"})
    qtbot.waitUntil(started.is_set)
    request = state._annotation_lookup_request if phase == "lookup" else state._annotation_load_request

    edited = {"id": 1, "stored_image_path": "/processed/edited.webp", "tags": [], "tags_text": "manual"}
    if edit == "replace":
        state.update_image_metadata(1, edited)
    elif edit == "add":
        state.add_image(edited)
    else:
        # The user-triggered existing refresh remains synchronous. Substitute its
        # one read so it can complete while the old worker's query is blocked.
        repo.get_image_annotation_metadata = Mock(return_value={"tags": [], "tags_text": "manual"})
        if edit == "annotation_refresh":
            state.refresh_image_annotations(1)
        else:
            state.invalidate_annotations([1])
    release.set()
    qtbot.waitUntil(lambda: state._annotation_worker_manager.get_active_worker_count() == 0)
    assert state.get_image_by_id(1)["tags_text"] == "manual"
    assert 1 not in state._annotation_invalidated_ids
    if phase == "load":
        state._on_annotation_refresh_terminal(
            WorkerTerminalEvent(
                request.worker_id, "annotation", WorkerOutcome.SUCCEEDED, {"tags_text": "stale"}
            )
        )
        assert state.get_image_by_id(1)["tags_text"] == "manual"
