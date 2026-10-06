"""Clef review is explicit, read-only, and cannot apply outdated probabilities."""

from __future__ import annotations

from pathlib import Path
from threading import Event
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QAbstractItemView

from lorairo.gui.widgets.annotation_review_widget import AnnotationReviewWidget
from lorairo.gui.widgets.selected_image_details_widget import SelectedImageDetailsWidget
from lorairo.gui.workers.annotation_review_worker import AnnotationReviewWorkerResult
from lorairo.gui.workers.terminal import CancelReason, WorkerOutcome, WorkerTerminalEvent
from lorairo.services.annotation_review_service import (
    AnnotationReviewItem,
    AnnotationReviewResult,
    ReviewCandidate,
    ReviewSnapshot,
)

pytestmark = pytest.mark.gui


class FakeWorkerManager(QObject):
    worker_terminal = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.started: list[tuple[str, object]] = []
        self.cancel_requests: list[tuple[str, CancelReason]] = []
        self.shutdown_calls = 0
        self.start_success = True

    def start_worker(self, worker_id, worker, auto_cleanup=True):
        self.started.append((worker_id, worker))
        return self.start_success

    def request_cancel_worker(self, worker_id, reason):
        self.cancel_requests.append((worker_id, reason))
        return True

    def cancel_all_workers(self, **kwargs):
        self.shutdown_calls += 1


def make_snapshot(image_id: int = 5, fingerprint: str = "original") -> ReviewSnapshot:
    return ReviewSnapshot(
        image_id=image_id,
        image_path=Path("/tmp/image.png"),
        tags=(ReviewCandidate("tag:1", "tag", "blue_eyes"),),
        captions=(ReviewCandidate("caption:2", "caption", "A smiling person."),),
        fingerprint=fingerprint,
    )


def make_result(*, status="completed", fingerprint="original", image_id=5) -> AnnotationReviewResult:
    return AnnotationReviewResult(
        image_id=image_id,
        fingerprint=fingerprint,
        model_name="@cf/cloudflare/clef-flash",
        items=(
            AnnotationReviewItem("tag:1", "tag", "blue_eyes", 0.08, "warning", None),
            AnnotationReviewItem("caption:2", "caption", "A smiling person.", 0.81, "ok", None),
        ),
        status=status,
        error=None,
    )


@pytest.fixture
def wired_widget(qtbot):
    widget = AnnotationReviewWidget()
    qtbot.addWidget(widget)
    service = Mock()
    service.warning_threshold = 0.2
    service.prepare_review.return_value = make_snapshot()
    service.review.return_value = make_result()
    manager = FakeWorkerManager()
    widget.set_service(service, worker_manager=manager)
    widget.set_image(5)
    yield widget, service, manager
    widget.shutdown()


def finish(widget, manager, result=None, outcome=WorkerOutcome.SUCCEEDED, error=None):
    worker_id, _worker = manager.started[-1]
    envelope = AnnotationReviewWorkerResult(widget._generation, result or make_result())
    manager.worker_terminal.emit(
        WorkerTerminalEvent(worker_id, "annotation_review", outcome, result=envelope, error=error)
    )


def test_selection_and_service_injection_do_not_request_cloud_review(wired_widget) -> None:
    widget, service, manager = wired_widget
    widget.set_image(9)
    widget.set_image(5)

    service.prepare_review.assert_not_called()
    service.review.assert_not_called()
    assert manager.started == []
    assert "未評価" in widget.status_label.text()
    assert widget.evaluate_button.isEnabled()


def test_click_shows_running_then_item_probabilities_without_edit_controls(qtbot, wired_widget) -> None:
    widget, service, manager = wired_widget
    qtbot.mouseClick(widget.evaluate_button, Qt.MouseButton.LeftButton)

    assert len(manager.started) == 1
    assert "評価中" in widget.status_label.text()
    assert not widget.evaluate_button.isEnabled()
    assert not widget.cancel_button.isHidden()
    # The real worker calls exactly the snapshot API, with cancellation checks.
    envelope = manager.started[0][1].execute()
    service.review.assert_called_once()
    finish(widget, manager, envelope.review)

    assert widget.results_table.rowCount() == 2
    assert widget.results_table.item(0, 1).text() == "blue_eyes"
    assert widget.results_table.item(0, 2).text() == "⚠ 要確認"
    assert widget.results_table.item(0, 3).text() == "8.0%"
    assert widget.results_table.item(1, 0).text() == "キャプション"
    assert widget.results_table.item(1, 3).text() == "81.0%"
    assert widget.results_table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
    assert "20% 未満" in widget.model_label.text()
    assert "cloudflare/clef-flash" in widget.model_label.text()
    assert widget.evaluate_button.isEnabled()


@pytest.mark.parametrize("next_image", [9, 5, None])
def test_selection_or_same_image_edit_cancels_and_discards_inflight_result(
    wired_widget, next_image
) -> None:
    widget, _service, manager = wired_widget
    widget._on_evaluate_requested()
    old_generation = widget._generation
    worker_id = manager.started[0][0]
    widget.set_image(next_image)
    # Old image data returns after the selection/edit, including an A -> B -> A race.
    if next_image == 9:
        widget.set_image(5)
    manager.worker_terminal.emit(
        WorkerTerminalEvent(
            worker_id,
            "annotation_review",
            WorkerOutcome.SUCCEEDED,
            result=AnnotationReviewWorkerResult(old_generation, make_result()),
        )
    )

    assert manager.cancel_requests[0][0] == worker_id
    assert widget.results_table.rowCount() == 0
    assert widget.results_table.isHidden()
    assert "未評価" in widget.status_label.text()


def test_completed_results_are_cleared_on_annotation_reload(wired_widget) -> None:
    widget, _service, manager = wired_widget
    widget._on_evaluate_requested()
    finish(widget, manager)
    assert widget.results_table.rowCount() == 2

    widget.set_image(5)

    assert widget.results_table.rowCount() == 0
    assert widget.model_label.isHidden()
    assert "未評価" in widget.status_label.text()


def test_service_reinjection_cancels_inflight_and_uses_refreshed_service_on_next_click(
    wired_widget,
) -> None:
    widget, original_service, manager = wired_widget
    widget._on_evaluate_requested()
    generation = widget._generation
    worker_id = manager.started[0][0]
    refreshed_service = Mock()
    refreshed_service.warning_threshold = 0.2
    refreshed_service.prepare_review.return_value = make_snapshot()

    widget.set_service(refreshed_service)

    assert widget._manager is manager
    assert len(manager.started) == 1
    assert manager.cancel_requests == [(worker_id, CancelReason.USER_REQUESTED)]
    assert widget.results_table.rowCount() == 0
    assert not widget.evaluate_button.isEnabled()
    original_service.review.assert_not_called()
    refreshed_service.review.assert_not_called()
    manager.worker_terminal.emit(
        WorkerTerminalEvent(
            worker_id,
            "annotation_review",
            WorkerOutcome.SUCCEEDED,
            result=AnnotationReviewWorkerResult(generation, make_result()),
        )
    )
    assert widget.results_table.rowCount() == 0
    assert widget.evaluate_button.isEnabled()

    widget._on_evaluate_requested()
    assert manager.started[-1][1]._service is refreshed_service


def test_external_edit_fingerprint_rejects_old_result(wired_widget) -> None:
    widget, service, manager = wired_widget
    widget._on_evaluate_requested()
    service.prepare_review.return_value = make_snapshot(fingerprint="edited")

    finish(widget, manager)

    assert widget.results_table.rowCount() == 0
    assert "内容が変更" in widget.status_label.text()
    assert widget.evaluate_button.isEnabled()


def test_failed_worker_is_distinct_from_a_warning_free_result(wired_widget) -> None:
    widget, _service, manager = wired_widget
    widget._on_evaluate_requested()
    finish(widget, manager, outcome=WorkerOutcome.FAILED, error="Cloudflare credentials are missing")

    assert "失敗" in widget.status_label.text()
    assert "credentials" in widget.status_label.text()
    assert widget.results_table.rowCount() == 0
    assert widget.evaluate_button.isEnabled()


def test_partial_result_keeps_failures_and_unevaluated_items_visible(wired_widget) -> None:
    widget, _service, manager = wired_widget
    widget._on_evaluate_requested()
    result = AnnotationReviewResult(
        image_id=5,
        fingerprint="original",
        model_name="@cf/cloudflare/clef-flash",
        items=(
            AnnotationReviewItem("tag:1", "tag", "blue_eyes", None, "failed", "timeout"),
            AnnotationReviewItem("caption:2", "caption", "A smiling person.", None, "unevaluated", None),
        ),
        status="partial",
        error="timeout",
    )
    finish(widget, manager, result)

    assert "一部を評価できません" in widget.status_label.text()
    assert widget.results_table.item(0, 2).text() == "評価失敗"
    assert widget.results_table.item(0, 3).text() == "—"
    assert widget.results_table.item(0, 2).toolTip() == "timeout"
    assert widget.results_table.item(1, 2).text() == "未評価"


@pytest.mark.parametrize("status", ["unevaluated", "stale"])
def test_empty_or_stale_service_result_never_claims_no_warnings(wired_widget, status) -> None:
    widget, _service, manager = wired_widget
    widget._on_evaluate_requested()
    result = AnnotationReviewResult(5, "original", "@cf/cloudflare/clef-flash", (), status, None)

    finish(widget, manager, result)

    assert "未評価" in widget.status_label.text()
    assert "評価完了" not in widget.status_label.text()
    assert widget.results_table.rowCount() == 0


def test_worker_start_failure_and_shutdown_release_ui_without_restarting(wired_widget) -> None:
    widget, _service, manager = wired_widget
    manager.start_success = False
    widget._on_evaluate_requested()
    assert widget.evaluate_button.isEnabled()
    assert "失敗" in widget.status_label.text()

    widget.shutdown()
    widget._on_evaluate_requested()

    assert len(manager.started) == 1
    assert manager.shutdown_calls == 1
    assert not widget.evaluate_button.isEnabled()


def test_cancel_is_cooperative_and_cannot_show_returned_result(wired_widget) -> None:
    widget, _service, manager = wired_widget
    widget._on_evaluate_requested()
    generation = widget._generation
    worker_id = manager.started[0][0]

    widget._on_cancel_requested()
    assert "停止" in widget.status_label.text()
    assert manager.cancel_requests == [(worker_id, CancelReason.USER_REQUESTED)]
    manager.worker_terminal.emit(
        WorkerTerminalEvent(
            worker_id,
            "annotation_review",
            WorkerOutcome.SUCCEEDED,
            result=AnnotationReviewWorkerResult(generation, make_result()),
        )
    )

    assert widget.results_table.rowCount() == 0
    assert "未評価" in widget.status_label.text()
    assert widget.evaluate_button.isEnabled()


def test_real_worker_does_not_block_event_loop_and_shutdown_cancels(qtbot) -> None:
    widget = AnnotationReviewWidget()
    qtbot.addWidget(widget)
    entered = Event()
    released = Event()
    service = Mock()
    service.warning_threshold = 0.2
    service.prepare_review.return_value = make_snapshot()

    def blocked_review(snapshot, *, is_cancelled):
        entered.set()
        while not released.wait(0.01):
            if is_cancelled():
                return make_result(status="cancelled")
        return make_result()

    service.review.side_effect = blocked_review
    widget.set_service(service)
    widget.set_image(5)
    try:
        widget._on_evaluate_requested()
        qtbot.waitUntil(entered.is_set, timeout=2000)
        # Switching remains synchronous and interactive while the service waits.
        widget.set_image(9)
        assert widget._image_id == 9
        assert "未評価" in widget.status_label.text()
        widget.shutdown()
        assert not widget._manager.active_workers
    finally:
        released.set()
        widget.shutdown()


def test_real_worker_success_delivers_results_to_the_widget(qtbot) -> None:
    widget = AnnotationReviewWidget()
    qtbot.addWidget(widget)
    service = Mock()
    service.warning_threshold = 0.2
    service.prepare_review.return_value = make_snapshot()
    service.review.return_value = make_result()
    widget.set_service(service)
    widget.set_image(5)
    try:
        widget._on_evaluate_requested()
        qtbot.waitUntil(lambda: widget.results_table.rowCount() == 2, timeout=2000)
        assert "評価完了" in widget.status_label.text()
        assert widget.evaluate_button.isEnabled()
        service.review.assert_called_once()
    finally:
        widget.shutdown()


def test_selected_details_forwards_edits_clear_and_shutdown(qtbot) -> None:
    details = SelectedImageDetailsWidget()
    qtbot.addWidget(details)
    service = Mock()
    service.warning_threshold = 0.2
    details.set_annotation_review_service(service)
    try:
        details._on_image_data_received({"id": 5, "tags": [], "caption_text": "original"})
        assert details.annotation_review_widget._image_id == 5
        generation = details.annotation_review_widget._generation
        details._on_image_data_received({"id": 5, "tags": [], "caption_text": "edited"})
        assert details.annotation_review_widget._generation > generation
        details._on_image_data_received({})
        assert details.annotation_review_widget._image_id is None
        service.review.assert_not_called()
    finally:
        details.shutdown()
    assert details.annotation_review_widget._closing
