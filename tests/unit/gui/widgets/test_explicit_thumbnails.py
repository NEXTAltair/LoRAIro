"""Regression coverage for staging diffs, background scaling and stale deliveries (#1385)."""

from pathlib import Path
from threading import Event
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QSize, Qt, QThread
from PySide6.QtGui import QImage

from lorairo.gui.state.dataset_state import DatasetStateManager
from lorairo.gui.state.staging_state import StagingStateManager
from lorairo.gui.widgets.staging_widget import StagingWidget
from lorairo.gui.widgets.thumbnail_selector_widget import ThumbnailSelectorWidget
from lorairo.gui.workers.explicit_thumbnail_worker import (
    ExplicitThumbnailRequest,
    ExplicitThumbnailResult,
    ExplicitThumbnailWorker,
)

pytestmark = pytest.mark.gui


@pytest.fixture
def widget(qtbot):
    view = ThumbnailSelectorWidget()
    qtbot.addWidget(view)
    return view


@pytest.fixture
def paused_pool(monkeypatch):
    """Capture real requests so tests can deterministically reorder deliveries."""
    pool = Mock()
    monkeypatch.setattr(
        "lorairo.gui.widgets.thumbnail_selector_widget.QThreadPool.globalInstance", lambda: pool
    )
    return pool


def colored_image(color=Qt.GlobalColor.red):
    image = QImage(48, 24, QImage.Format.Format_RGB32)
    image.fill(color)
    return image


def deliver(widget, requests, color=Qt.GlobalColor.red):
    widget._on_explicit_thumbnails_loaded(
        [ExplicitThumbnailResult(request, colored_image(color)) for request in requests]
    )


def test_incremental_hundreds_reuse_items_and_decode_only_new_paths(widget, qtbot, tmp_path, monkeypatch):
    """100 -> 500 must perform 500 background decodes/scales rather than 1500."""
    paths = []
    for image_id in range(500):
        path = tmp_path / f"{image_id}.png"
        assert colored_image().save(str(path))
        paths.append((str(path), image_id))
    calls = []
    original = ExplicitThumbnailWorker.load_image

    def counted_load(key):
        calls.append((key, QThread.currentThread()))
        return original(key)

    monkeypatch.setattr(ExplicitThumbnailWorker, "load_image", staticmethod(counted_load))
    previous = []
    for count in range(100, 501, 100):
        widget.load_thumbnails_from_paths(paths[:count])
        qtbot.waitUntil(lambda: not widget._explicit_pending, timeout=5000)
        assert widget.thumbnail_items[: len(previous)] == previous
        previous = widget.thumbnail_items.copy()
        assert len(calls) == count
        assert len(widget._explicit_thumbnail_cache) == count
    assert all(thread != widget.thread() for _, thread in calls)
    assert [item.image_id for item in widget.thumbnail_items] == list(range(500))


def test_append_preserves_inflight_requests_and_out_of_order_results(widget, paused_pool):
    widget.load_thumbnails_from_paths([("a.png", 1)])
    first = widget._explicit_pending[1]
    item = widget.thumbnail_items[0]
    widget.load_thumbnails_from_paths([("a.png", 1), ("b.png", 2)])
    assert widget._explicit_pending[1] == first
    assert paused_pool.start.call_count == 2
    deliver(widget, [widget._explicit_pending[2]])
    deliver(widget, [first])
    assert not widget._explicit_pending
    assert widget.thumbnail_items[0] is item
    assert [item.image_id for item in widget.thumbnail_items] == [1, 2]


def test_width_only_repositions_and_updates_scene_and_recommended_height(widget, paused_pool):
    widget.enable_content_height()
    widget.load_thumbnails_from_paths([(f"{i}.png", i) for i in range(6)])
    deliver(widget, list(widget._explicit_pending.values()))
    original = widget.thumbnail_items.copy()
    pixmaps = [item.pixmap.cacheKey() for item in original]
    viewport = widget.scrollAreaThumbnails.viewport()
    viewport.resize(6 * 128, 300)
    widget.update_thumbnail_layout()
    wide_height = widget.sizeHint().height()
    assert widget.scene.sceneRect().height() == 128
    viewport.resize(2 * 128, 300)
    widget.update_thumbnail_layout()
    assert widget.scene.sceneRect().height() == 384
    assert widget.sizeHint().height() == wide_height + 256
    assert [(item.x(), item.y()) for item in original] == [
        (0, 0),
        (128, 0),
        (0, 128),
        (128, 128),
        (0, 256),
        (128, 256),
    ]
    assert widget.thumbnail_items == original
    assert [item.pixmap.cacheKey() for item in original] == pixmaps
    assert paused_pool.start.call_count == 1


@pytest.mark.parametrize("clear_method", ["empty", "clear_thumbnails", "clear_cache"])
def test_clear_readd_rejects_old_result_even_for_same_id_and_path(widget, paused_pool, clear_method):
    paths = [("a.png", 1)]
    widget.load_thumbnails_from_paths(paths)
    old_request = widget._explicit_pending[1]
    old_task = paused_pool.start.call_args.args[0]
    if clear_method == "empty":
        widget.load_thumbnails_from_paths([])
    else:
        getattr(widget, clear_method)()
    widget.load_thumbnails_from_paths(paths)
    new_request = widget._explicit_pending[1]
    assert new_request != old_request
    assert old_task.canceled.is_set()
    deliver(widget, [old_request])
    assert widget._explicit_pending[1] == new_request
    assert not widget._explicit_thumbnail_cache
    deliver(widget, [new_request], Qt.GlobalColor.blue)
    assert widget.thumbnail_items[0].pixmap.toImage().pixelColor(0, 0).blue() == 255


def test_removed_image_cannot_return_and_readdition_uses_new_token(widget, paused_pool):
    widget.load_thumbnails_from_paths([("a.png", 1), ("b.png", 2)])
    old = widget._explicit_pending[1]
    survivor = widget.thumbnail_items[1]
    widget.last_selected_item = widget.thumbnail_items[0]
    widget.load_thumbnails_from_paths([("b.png", 2)])
    deliver(widget, [old])
    assert widget.thumbnail_items == [survivor]
    assert widget.last_selected_item is None
    assert len(widget.scene.items()) == 1
    widget.load_thumbnails_from_paths([("b.png", 2), ("a.png", 1)])
    new = widget._explicit_pending[1]
    deliver(widget, [old])
    assert widget._explicit_pending[1] == new
    deliver(widget, list(widget._explicit_pending.values()))
    assert [item.image_id for item in widget.thumbnail_items] == [2, 1]


def test_path_change_invalidates_only_changed_image(widget, paused_pool):
    widget.load_thumbnails_from_paths([("a.png", 1), ("b.png", 2)])
    old_requests = list(widget._explicit_pending.values())
    deliver(widget, old_requests)
    survivor = widget.thumbnail_items[1]
    survivor_key = survivor.pixmap.cacheKey()
    widget.load_thumbnails_from_paths([("new.png", 1), ("b.png", 2)])
    assert set(widget._explicit_pending) == {1}
    assert (Path("a.png"), 128, 128) not in widget._explicit_thumbnail_cache
    deliver(widget, old_requests)
    assert set(widget._explicit_pending) == {1}
    assert survivor.pixmap.cacheKey() == survivor_key
    deliver(widget, list(widget._explicit_pending.values()), Qt.GlobalColor.blue)
    assert widget.thumbnail_items[0].image_path == Path("new.png")


def test_size_change_reuses_items_but_regenerates_and_ignores_old_size(widget, paused_pool):
    widget.load_thumbnails_from_paths([("a.png", 1)])
    original_item = widget.thumbnail_items[0]
    old = widget._explicit_pending[1]
    widget.thumbnail_size = QSize(96, 96)
    widget.update_thumbnail_layout()
    request = widget._explicit_pending[1]
    assert request.key == (Path("a.png"), 96, 96)
    assert widget.thumbnail_items[0] is original_item
    deliver(widget, [old])
    assert widget._explicit_pending[1] == request
    deliver(widget, [request])
    assert len(widget._explicit_thumbnail_cache) == 1


def test_lru_cache_is_bounded_and_reuses_removed_thumbnail(widget, paused_pool):
    widget._explicit_cache_limit = 2
    widget.load_thumbnails_from_paths([("a.png", 1), ("b.png", 2)])
    deliver(widget, list(widget._explicit_pending.values()))
    widget.load_thumbnails_from_paths([("b.png", 2)])
    widget.load_thumbnails_from_paths([("b.png", 2), ("a.png", 1)])
    assert paused_pool.start.call_count == 1
    widget.load_thumbnails_from_paths([("b.png", 2), ("a.png", 1), ("c.png", 3)])
    deliver(widget, list(widget._explicit_pending.values()))
    assert len(widget._explicit_thumbnail_cache) == 2
    assert len(widget.thumbnail_items) == 3


def test_shared_staging_clear_and_limit_preserve_selection(qtbot, paused_pool):
    state = DatasetStateManager()
    state.update_from_search_results([{"id": i, "stored_image_path": f"{i}.png"} for i in range(510)])
    state.set_selected_images([3, 1])
    manager = StagingStateManager()
    manager.set_dataset_state_manager(state)
    views = [StagingWidget(), StagingWidget()]
    for view in views:
        qtbot.addWidget(view)
        view.set_staging_state_manager(manager)
    views[0].add_image_ids(list(range(510)))
    for view in views:
        assert view.count() == 500
        thumb = view._staging_thumbnail_widget
        assert [item.image_id for item in thumb.thumbnail_items] == list(range(500))
    old = list(views[0]._staging_thumbnail_widget._explicit_pending.values())
    views[1].clear()
    deliver(views[0]._staging_thumbnail_widget, old)
    assert all(view._staging_thumbnail_widget.thumbnail_items == [] for view in views)
    assert state.selected_image_ids == [3, 1]
    views[0].add_image_ids([3, 1])
    assert all(view.get_image_ids() == [3, 1] for view in views)


def test_worker_batches_cancellation_and_failed_path(qapp, tmp_path):
    requests = [ExplicitThumbnailRequest(i, (tmp_path / f"{i}.png", 96, 96), i) for i in range(20)]
    worker = ExplicitThumbnailWorker("batch", requests, Event())
    batches, finished = [], []
    worker.signals.loaded.connect(batches.append)
    worker.signals.finished.connect(finished.append)
    worker.run()
    assert [len(batch) for batch in batches] == [16, 4]
    assert all(result.image.isNull() for batch in batches for result in batch)
    assert finished == ["batch"]
    worker.canceled.set()
    batches.clear()
    worker.run()
    assert batches == []


def test_deleting_view_cancels_work_without_waiting_for_pool(paused_pool, qtbot):
    widget = ThumbnailSelectorWidget()
    widget.load_thumbnails_from_paths([("a.png", 1)])
    task = paused_pool.start.call_args.args[0]
    widget.deleteLater()
    qtbot.waitUntil(task.shutdown.is_set)
