"""Clef scope, durable warning navigation, and background history loading."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QListWidget, QWidget

from lorairo.gui.widgets.annotation_review_batch_widget import AnnotationReviewBatchWidget
from lorairo.gui.workers.annotation_review_batch_worker import (
    AnnotationReviewBatchImageResult,
    AnnotationReviewBatchWorker,
    AnnotationReviewBatchWorkerResult,
)
from lorairo.gui.workers.annotation_review_results_loader import AnnotationReviewResultsLoader
from lorairo.gui.workers.base import CancellationError, WorkerProgress
from lorairo.gui.workers.terminal import CancelReason, WorkerOutcome, WorkerTerminalEvent
from lorairo.services.annotation_review_service import (
    AnnotationReviewItem,
    AnnotationReviewResult,
    ReviewCandidateSource,
    ReviewSnapshot,
)
from lorairo.services.annotation_review_store import StoredReviewResult

pytestmark = pytest.mark.gui


class FakeManager(QObject):
    worker_terminal = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.started: list[tuple[str, object]] = []
        self.cancel_requests: list[tuple[str, CancelReason]] = []
        self.shutdown_calls = 0

    def start_worker(self, worker_id, worker, auto_cleanup=True):
        self.started.append((worker_id, worker))
        return True

    def request_cancel_worker(self, worker_id, reason):
        self.cancel_requests.append((worker_id, reason))
        return True

    def cancel_all_workers(self, **kwargs):
        self.shutdown_calls += 1


def saved_result(image_id: int = 5, *, status="completed") -> StoredReviewResult:
    return StoredReviewResult(
        review=AnnotationReviewResult(
            image_id,
            "original",
            "clef-flash",
            (
                AnnotationReviewItem("tag_1", "tag", "blue_eyes", 0.08, "warning"),
                AnnotationReviewItem("caption_2", "caption", "A smiling person.", 0.81, "ok"),
            ),
            status,
        ),
        warning_threshold=0.2,
        checked_at=datetime(2026, 10, 6, 16, 30, tzinfo=UTC),
    )


def complete_load(widget: AnnotationReviewBatchWidget, manager: FakeManager) -> None:
    worker_id, loader = next(
        (worker_id, worker)
        for worker_id, worker in reversed(manager.started)
        if isinstance(worker, AnnotationReviewResultsLoader)
    )
    manager.worker_terminal.emit(
        WorkerTerminalEvent(
            worker_id, "annotation_review_results_load", WorkerOutcome.SUCCEEDED, result=loader.execute()
        )
    )


@pytest.fixture
def wired(qtbot):
    widget = AnnotationReviewBatchWidget()
    qtbot.addWidget(widget)
    service = Mock()
    service.model_name = "clef-flash"
    service.warning_threshold = 0.2
    store = Mock()
    store.get_current_results.return_value = {}
    store.get_current_result.return_value = saved_result()
    manager = FakeManager()
    widget.set_services(service, store, manager)
    complete_load(widget, manager)
    yield widget, service, store, manager
    widget.shutdown()


@pytest.fixture
def selected(qtbot, monkeypatch):
    widget = AnnotationReviewBatchWidget(selection_mode=True)
    qtbot.addWidget(widget)
    service = Mock()
    service.model_name = "clef-flash"
    service.warning_threshold = 0.2
    store = Mock()
    manager = FakeManager()
    widget.set_services(service, store, manager)
    monkeypatch.setattr(widget, "_confirm_scope", lambda *args: True)
    yield widget, service, store, manager
    widget.shutdown()


def test_selection_mode_has_compact_controls_and_never_loads_a_duplicate_ledger(selected):
    widget, service, store, manager = selected
    assert widget.start_button.text() == "選択画像をチェック（0枚）"
    assert not widget.start_button.isEnabled()
    for control in (
        widget.instructions_label,
        widget.notice_label,
        widget.select_targets_button,
        widget.target_list_button,
        widget.candidate_options_widget,
        widget.history_label,
        widget.results_table,
        widget.details_table,
        widget.detail_label,
        widget.manual_review_button,
    ):
        assert control.isHidden()
    widget.set_image_ids([5, 7, 5])
    widget.set_image_names({5: "portrait.jpg", 7: "garden.jpg"})
    assert widget.start_button.text() == "選択画像をチェック（2枚）"
    assert widget.start_button.isEnabled()
    assert "portrait.jpg" in widget.target_names_label.text()
    assert "選択画像 2 枚" in widget.scope_label.text()
    widget.refresh()
    assert manager.started == []
    store.get_current_results.assert_not_called()
    service.review.assert_not_called()
    widget.candidate_checkbox.setChecked(True)
    assert not widget.candidate_options_widget.isHidden()


def test_search_selection_and_names_freeze_before_confirmation_returns(selected, monkeypatch):
    widget, service, _, manager = selected
    widget.set_image_ids([5, 7])
    widget.set_image_names({5: "portrait.jpg", 7: "garden.jpg"})
    widget.candidate_checkbox.setChecked(True)
    widget.candidate_keyword_edit.setText("hair")
    confirmations = []

    def confirm(image_ids, image_names, candidate_source):
        confirmations.append((image_ids, image_names.copy(), candidate_source))
        assert not widget.start_button.isEnabled()
        widget.set_image_ids([99])
        widget.set_image_names({99: "changed.jpg"})
        widget.candidate_keyword_edit.setText("eyes")
        widget._on_start_requested()  # Nested request cannot open another dialog.
        return True

    monkeypatch.setattr(widget, "_confirm_scope", confirm)
    widget._on_start_requested()
    _, worker = manager.started[-1]
    assert isinstance(worker, AnnotationReviewBatchWorker)
    assert confirmations == [((5, 7), {5: "portrait.jpg", 7: "garden.jpg"}, ReviewCandidateSource("hair"))]
    assert worker._image_ids == (5, 7)
    assert worker._service is service
    assert worker._candidate_source == ReviewCandidateSource("hair")
    assert widget._running_image_names == {5: "portrait.jpg", 7: "garden.jpg"}
    assert "現在の選択 1 枚" in widget.scope_label.text()
    assert "portrait.jpg" in widget.target_names_label.text()
    assert "changed.jpg" not in widget.target_names_label.text()
    assert "準備中" in widget.status_label.text()
    assert manager.cancel_requests == []


def test_confirmation_return_and_changed_configuration_never_launch_a_review(selected, monkeypatch):
    widget, service, store, manager = selected
    widget.set_image_ids([5])
    monkeypatch.setattr(widget, "_confirm_scope", lambda *args: False)
    widget._on_start_requested()
    assert manager.started == []
    assert widget.start_button.isEnabled()

    def update_config(*args):
        widget.set_services(service, store)
        return True

    monkeypatch.setattr(widget, "_confirm_scope", update_config)
    widget._on_start_requested()
    assert manager.started == []
    assert widget.start_button.isEnabled()


@pytest.mark.parametrize("accept", [True, False])
def test_search_confirmation_lists_all_targets_and_requires_explicit_choice(qtbot, accept):
    widget = AnnotationReviewBatchWidget(selection_mode=True)
    qtbot.addWidget(widget)
    observed = []

    def inspect_dialog():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, QDialog)
        targets = dialog.findChild(QListWidget, "listAnnotationReviewConfirmedTargets")
        observed.extend(targets.item(index).text() for index in range(targets.count()))
        buttons = dialog.findChild(QDialogButtonBox)
        button = QDialogButtonBox.StandardButton.Ok if accept else QDialogButtonBox.StandardButton.Cancel
        buttons.button(button).click()

    QTimer.singleShot(0, inspect_dialog)
    assert (
        widget._confirm_scope(
            (5, 7, 9, 11), {5: "portrait.jpg", 7: "garden.jpg"}, ReviewCandidateSource("hair")
        )
        is accept
    )
    assert observed == ["portrait.jpg (ID: 5)", "garden.jpg (ID: 7)", "画像 9", "画像 11"]


def test_search_single_image_saved_result_is_forwarded_without_showing_tables(selected):
    widget, _, _, manager = selected
    widget.set_image_ids([5])
    assert widget.start_button.text() == "選択画像をチェック（1枚）"
    saved = QSignalSpy(widget.review_result_saved)
    widget._on_start_requested()
    worker_id, worker = manager.started[-1]
    worker.per_image_finished.emit(
        AnnotationReviewBatchImageResult(widget._generation, saved_result().review, True, saved_result())
    )
    result = AnnotationReviewBatchWorkerResult(widget._generation, (5,), (saved_result().review,), False)
    manager.worker_terminal.emit(
        WorkerTerminalEvent(worker_id, "annotation_review", WorkerOutcome.SUCCEEDED, result=result)
    )
    assert saved.count() == 1 and saved.at(0) == [5]
    assert "終了" in widget.status_label.text()
    assert "保存済み 1 枚" in widget.status_label.text()
    assert "保存失敗" not in widget.status_label.text()
    assert len(manager.started) == 1
    assert widget.results_table.rowCount() == 0
    assert widget.results_table.isHidden() and widget.details_table.isHidden()


def test_search_cancel_reports_saved_and_unsaved_images_separately(selected):
    widget, _, _, manager = selected
    widget.set_image_ids([5, 7, 9])
    saved = QSignalSpy(widget.review_result_saved)
    widget._on_start_requested()
    worker_id, worker = manager.started[-1]
    worker.per_image_finished.emit(
        AnnotationReviewBatchImageResult(widget._generation, saved_result().review, True, saved_result())
    )
    worker.per_image_finished.emit(
        AnnotationReviewBatchImageResult(
            widget._generation, saved_result(7).review, False, save_error="DBへの保存に失敗しました。"
        )
    )
    assert "保存失敗 1 枚（未保存）" in widget.status_label.text()
    widget._on_cancel_requested()
    manager.worker_terminal.emit(
        WorkerTerminalEvent(worker_id, "annotation_review", WorkerOutcome.CANCELED)
    )
    assert saved.count() == 1 and saved.at(0) == [5]
    assert "中止" in widget.status_label.text()
    assert "2 / 3 枚" in widget.status_label.text()
    assert "保存済み 1 枚" in widget.status_label.text()
    assert "保存失敗 1 枚（未保存）" in widget.status_label.text()
    assert "未処理の画像は今回チェックしていません" in widget.status_label.text()


def test_search_save_failure_is_preserved_in_successful_terminal_summary(selected):
    widget, _, _, manager = selected
    widget.set_image_ids([5, 7])
    widget._on_start_requested()
    worker_id, worker = manager.started[-1]
    worker.per_image_finished.emit(
        AnnotationReviewBatchImageResult(widget._generation, saved_result().review, True, saved_result())
    )
    worker.per_image_finished.emit(
        AnnotationReviewBatchImageResult(widget._generation, saved_result(7).review, False)
    )
    result = AnnotationReviewBatchWorkerResult(
        widget._generation, (5, 7), (saved_result().review, saved_result(7).review), False
    )
    manager.worker_terminal.emit(
        WorkerTerminalEvent(worker_id, "annotation_review", WorkerOutcome.SUCCEEDED, result=result)
    )
    assert "終了" in widget.status_label.text()
    assert "保存済み 1 枚" in widget.status_label.text()
    assert "保存失敗 1 枚（未保存）" in widget.status_label.text()
    assert "完了" not in widget.status_label.text()


def test_search_post_save_read_failure_stays_saved_and_reports_currentness_failure(selected):
    widget, _, _, manager = selected
    widget.set_image_ids([5])
    saved = QSignalSpy(widget.review_result_saved)
    widget._on_start_requested()
    _, worker = manager.started[-1]
    worker.per_image_finished.emit(
        AnnotationReviewBatchImageResult(
            widget._generation,
            saved_result().review,
            currentness_error="結果は保存済みですが、照合に失敗しました。",
        )
    )
    assert saved.count() == 1
    assert "保存済み 1 枚" in widget.status_label.text()
    assert "保存後の照合失敗 1 枚" in widget.status_label.text()
    assert "保存失敗" not in widget.status_label.text()


def test_search_reinjection_cancels_frozen_worker_and_forwards_old_generation_saves(selected):
    widget, old_service, store, manager = selected
    widget.set_image_ids([5, 7])
    widget._on_start_requested()
    worker_id, worker = manager.started[-1]
    generation = widget._generation
    saved = QSignalSpy(widget.review_result_saved)
    current_service = Mock()
    current_service.warning_threshold = 0.5
    widget.set_services(current_service, store)
    assert worker._service is old_service
    assert worker._image_ids == (5, 7)
    assert manager.cancel_requests == [(worker_id, CancelReason.USER_REQUESTED)]
    worker.per_image_finished.emit(
        AnnotationReviewBatchImageResult(generation, saved_result().review, True, saved_result())
    )
    assert saved.count() == 1 and saved.at(0) == [5]
    assert widget._saved_results == {}
    manager.worker_terminal.emit(
        WorkerTerminalEvent(worker_id, "annotation_review", WorkerOutcome.CANCELED)
    )
    assert "設定を更新" in widget.status_label.text()
    assert "保存された結果は保持" in widget.status_label.text()
    assert widget.start_button.isEnabled()
    assert len(manager.started) == 1


def test_search_terminal_failure_preserves_and_counts_already_saved_images(selected):
    widget, _, _, manager = selected
    widget.set_image_ids([5, 7])
    widget._on_start_requested()
    worker_id, worker = manager.started[-1]
    worker.per_image_finished.emit(
        AnnotationReviewBatchImageResult(widget._generation, saved_result().review, True, saved_result())
    )
    manager.worker_terminal.emit(
        WorkerTerminalEvent(worker_id, "annotation_review", WorkerOutcome.FAILED, error="prepare failed")
    )
    assert "失敗しました" in widget.status_label.text()
    assert "prepare failed" in widget.status_label.text()
    assert "保存済み 1 枚" in widget.status_label.text()
    assert "保持" in widget.status_label.text()
    assert widget.start_button.isEnabled()


def test_search_saved_failed_and_unevaluated_reviews_do_not_claim_checks_succeeded(selected):
    widget, _, _, manager = selected
    widget.set_image_ids([5, 7])
    widget._on_start_requested()
    _, worker = manager.started[-1]
    for image_id, status in ((5, "failed"), (7, "unevaluated")):
        stored = saved_result(image_id, status=status)
        worker.per_image_finished.emit(
            AnnotationReviewBatchImageResult(widget._generation, stored.review, True, stored)
        )
    assert "保存済み 2 枚" in widget.status_label.text()
    assert "チェック失敗 1 枚" in widget.status_label.text()
    assert "未評価・一部未評価 1 枚" in widget.status_label.text()


@pytest.mark.parametrize("shutdown", [False, True])
def test_post_commit_cancel_notifies_saved_without_unverified_warning_or_shutdown_updates(wired, shutdown):
    widget, service, store, manager = wired
    widget.set_image_ids([5, 7])
    widget._on_start_requested()
    worker_id, worker = manager.started[-1]
    service.prepare_reviews.return_value = {5: Mock(), 7: Mock()}
    service.review.return_value = saved_result().review
    store.save.return_value = True
    store.get_current_result.side_effect = CancellationError("read cancelled")
    saved = QSignalSpy(widget.review_result_saved)
    if shutdown:
        widget.shutdown()
    before = widget.status_label.text()

    worker.run()
    manager.worker_terminal.emit(
        WorkerTerminalEvent(worker_id, "annotation_review", WorkerOutcome.CANCELED)
    )

    if shutdown:
        assert saved.count() == 0
        assert widget.status_label.text() == before
        assert widget._saved_results == {}
    else:
        assert saved.count() == 1 and saved.at(0) == [5]
        assert "保存済み 1 枚" in widget.status_label.text()
        assert "保存失敗" not in widget.status_label.text()
        assert "中止" in widget.status_label.text()
        cached = widget._saved_results[5].review
        assert cached.status == "stale"
        assert all(item.probability is None and item.status != "warning" for item in cached.items)


def test_service_injection_loads_bounded_history_without_starting_review(wired) -> None:
    widget, service, store, manager = wired
    store.get_current_results.assert_called_once_with(service, limit=500)
    service.review.assert_not_called()
    assert not widget.start_button.isEnabled()
    assert all(isinstance(worker, AnnotationReviewResultsLoader) for _, worker in manager.started)
    assert "ローカルの Clef" in widget.notice_label.text()
    assert "初回のモデル読み込み" in widget.notice_label.text()
    assert "Clef（ローカル）" in widget.notice_label.text()
    assert "Cloudflare" not in widget.notice_label.text()


def test_start_freezes_scope_despite_source_list_and_staging_changes(qtbot, wired) -> None:
    widget, service, store, manager = wired
    ids = [5, 7, 5]
    widget.set_image_ids(ids)
    widget._on_start_requested()
    worker_id, worker = manager.started[-1]
    assert isinstance(worker, AnnotationReviewBatchWorker)

    ids.append(99)
    widget.set_image_ids([99])
    worker.per_image_finished.emit(
        AnnotationReviewBatchImageResult(widget._generation, saved_result().review, True, saved_result())
    )
    qtbot.waitUntil(lambda: widget.results_table.rowCount() == 1)

    assert widget._running_image_ids == (5, 7)
    assert "チェック対象 2 枚" in widget.scope_label.text()
    assert "現在のステージ 1 枚" in widget.scope_label.text()
    assert manager.cancel_requests == []
    assert widget.results_table.item(0, 0).text() == "画像 5"
    assert widget.progress_bar.value() == 1
    assert not widget.start_button.isEnabled()
    service.review.assert_not_called()
    store.get_current_result.assert_not_called()
    assert worker_id == widget._inflight_id


def test_target_navigation_is_available_before_staging_and_never_starts_review(qtbot, wired) -> None:
    widget, service, _, manager = wired
    started = len(manager.started)
    assert not widget.start_button.isEnabled()
    assert not widget.target_list_button.isEnabled()
    assert "選択画像" in widget.target_names_label.text()
    with qtbot.waitSignal(widget.target_selection_requested):
        qtbot.mouseClick(widget.select_targets_button, Qt.MouseButton.LeftButton)

    widget.set_image_ids([5, 7])
    assert widget.start_button.isEnabled()
    assert widget.start_button.text() == "チェックを実行"
    with qtbot.waitSignal(widget.target_list_requested):
        qtbot.mouseClick(widget.target_list_button, Qt.MouseButton.LeftButton)

    assert len(manager.started) == started
    service.review.assert_not_called()


def test_displayed_filenames_freeze_with_the_running_target(wired) -> None:
    widget, _, _, _ = wired
    names = {5: "portrait.jpg", 7: "garden.jpg"}
    widget.set_image_names(names)
    widget.set_image_ids([5, 7])
    widget._on_start_requested()

    names[5] = "changed.jpg"
    widget.set_image_names({99: "next.jpg"})
    widget.set_image_ids([99])

    assert "portrait.jpg" in widget.target_names_label.text()
    assert "garden.jpg" in widget.target_names_label.text()
    assert "next.jpg" not in widget.target_names_label.text()
    assert widget._running_image_ids == (5, 7)
    assert "次回" in widget.target_list_button.text()


def test_candidate_options_require_explicit_conditions_and_have_bounded_defaults(wired) -> None:
    widget, service, _, manager = wired
    widget.set_image_ids([5])
    assert widget._candidate_source() is None
    assert widget.candidate_limit_spin.minimum() == 1
    assert widget.candidate_limit_spin.maximum() == 64
    assert widget.candidate_limit_spin.value() == 32
    assert not widget.candidate_keyword_edit.isEnabled()

    widget.candidate_checkbox.setChecked(True)
    widget.candidate_tags_edit.setText(" , , ")
    assert not widget.start_button.isEnabled()
    assert "キーワードまたは関連タグ" in widget.status_label.text()
    started = len(manager.started)
    widget._on_start_requested()
    assert len(manager.started) == started
    service.review.assert_not_called()

    widget.candidate_tags_edit.setText("1girl, portrait")
    assert widget.start_button.isEnabled()
    assert widget._candidate_source() == ReviewCandidateSource("", ("1girl", "portrait"), 32)


def test_run_freezes_candidate_conditions_and_disables_edits_until_terminal(wired) -> None:
    widget, _, _, manager = wired
    widget.set_image_ids([5, 7])
    widget.candidate_checkbox.setChecked(True)
    widget.candidate_keyword_edit.setText(" hair ")
    widget.candidate_tags_edit.setText("1girl, portrait, 1girl, ")
    widget.candidate_limit_spin.setValue(16)
    expected = ReviewCandidateSource("hair", ("1girl", "portrait"), 16)
    widget._on_start_requested()
    worker_id, worker = manager.started[-1]

    assert widget._running_candidate_source == expected
    assert worker._candidate_source == expected
    for control in (
        widget.candidate_checkbox,
        widget.candidate_keyword_edit,
        widget.candidate_tags_edit,
        widget.candidate_limit_spin,
    ):
        assert not control.isEnabled()

    # Even programmatic edits and staging changes affect only the next run.
    widget.candidate_keyword_edit.setText("eyes")
    widget.candidate_tags_edit.setText("landscape")
    widget.candidate_limit_spin.setValue(64)
    widget.set_image_ids([99])
    assert worker._candidate_source == expected
    assert widget._running_image_ids == (5, 7)
    manager.worker_terminal.emit(
        WorkerTerminalEvent(worker_id, "annotation_review_batch", WorkerOutcome.CANCELED)
    )
    assert widget.candidate_checkbox.isEnabled()
    assert widget.candidate_keyword_edit.isEnabled()
    assert widget._candidate_source() == ReviewCandidateSource("eyes", ("landscape",), 64)


def test_preparing_status_is_published_before_worker_launch_and_survives_hidden_tab(wired) -> None:
    widget, _, _, manager = wired
    widget.set_image_ids([5, 7])
    statuses = QSignalSpy(widget.running_status_changed)
    observed_at_launch = []
    launch = manager.start_worker

    def inspect_launch(worker_id, worker, auto_cleanup=True):
        observed_at_launch.append((widget.status_label.text(), statuses.count()))
        return launch(worker_id, worker, auto_cleanup)

    manager.start_worker = inspect_launch
    widget._on_start_requested()
    worker_id, worker = manager.started[-1]
    assert observed_at_launch == [(widget.status_label.text(), 1)]
    assert "準備中" in statuses.at(0)[0]
    assert "対象 2 枚" in statuses.at(0)[0]
    assert "バックグラウンド" in widget.notice_label.text()
    assert "時間がかかります" in widget.notice_label.text()

    widget.hide()
    worker.progress_updated.emit(
        WorkerProgress(50, "チェック中 1 / 2 枚", processed_count=1, total_count=2)
    )
    assert widget.progress_bar.value() == 1
    assert "1 / 2" in statuses.at(statuses.count() - 1)[0]
    manager.worker_terminal.emit(
        WorkerTerminalEvent(worker_id, "annotation_review_batch", WorkerOutcome.CANCELED)
    )
    assert statuses.at(statuses.count() - 1)[0] == ""


def test_failed_worker_launch_clears_published_running_status(wired) -> None:
    widget, _, _, manager = wired
    widget.set_image_ids([5])
    statuses = QSignalSpy(widget.running_status_changed)
    manager.start_worker = lambda *args, **kwargs: False
    widget._on_start_requested()

    assert statuses.count() == 2
    assert "準備中" in statuses.at(0)[0]
    assert statuses.at(1)[0] == ""
    assert widget._inflight_id is None
    assert widget.start_button.isEnabled()


def test_saved_result_signal_includes_persisted_old_generations_but_excludes_unsaved_images(wired) -> None:
    widget, _, _, manager = wired
    widget.set_image_ids([5, 7])
    saved = QSignalSpy(widget.review_result_saved)
    widget._on_start_requested()
    _, worker = manager.started[-1]
    worker.per_image_finished.emit(
        AnnotationReviewBatchImageResult(widget._generation, saved_result().review, True, saved_result())
    )
    worker.per_image_finished.emit(
        AnnotationReviewBatchImageResult(widget._generation, saved_result(7).review, False)
    )
    worker.per_image_finished.emit(
        AnnotationReviewBatchImageResult(widget._generation, saved_result(99).review)
    )
    worker.per_image_finished.emit(
        AnnotationReviewBatchImageResult(widget._generation - 1, saved_result().review)
    )

    assert [saved.at(index) for index in range(saved.count())] == [[5], [99], [5]]
    assert set(widget._saved_results) == {5, 7}


def test_suggestions_are_distinct_from_warnings_and_open_for_manual_adoption(qtbot, wired) -> None:
    widget, _, store, manager = wired
    stored = saved_result()
    suggestion = AnnotationReviewItem("suggestion_1", "suggestion", "long_hair", 0.88, "suggestion")
    stored = replace(stored, review=replace(stored.review, items=(stored.review.items[1], suggestion)))
    store.get_current_results.return_value = {5: stored}
    widget.refresh()
    complete_load(widget, manager)
    widget.results_table.selectRow(0)

    assert widget.results_table.item(0, 1).text() == "追加候補あり"
    assert widget.results_table.item(0, 2).text() == "0"
    assert widget.results_table.item(0, 3).text() == "1"
    assert widget.results_table.item(0, 4).text() == "0"
    assert widget.details_table.item(1, 0).text() == "追加候補"
    assert widget.details_table.item(1, 2).text() == "追加候補"
    assert widget.details_table.item(1, 3).text() == "88.0%"
    with qtbot.waitSignal(widget.manual_review_requested) as emission:
        widget.manual_review_button.click()
    assert emission.args == [5]
    store.save.assert_not_called()


def test_candidate_help_and_saved_details_use_configured_suggestion_threshold(wired) -> None:
    widget, service, store, manager = wired
    service.suggestion_threshold = 0.9
    widget.set_services(service, store)
    complete_load(widget, manager)
    assert "一致確率 90% 以上" in widget.candidate_help_label.text()
    stored = saved_result()
    candidate = AnnotationReviewItem("suggestion_1", "suggestion", "long_hair", 0.88, "ok")
    stored = replace(
        stored,
        review=replace(stored.review, items=(candidate,), suggestion_threshold=0.9),
        suggestion_threshold=0.9,
    )
    store.get_current_results.return_value = {5: stored}
    widget.refresh()
    complete_load(widget, manager)
    widget.results_table.selectRow(0)

    assert widget.results_table.item(0, 2).text() == "0"
    assert widget.results_table.item(0, 3).text() == "0"
    assert "追加候補: 一致確率 90% 以上" in widget.detail_label.text()
    assert widget.details_table.item(0, 0).text() == "候補タグ"
    assert widget.details_table.item(0, 2).text() == "採用候補外"


def test_saved_warning_opens_original_image_and_keeps_candidate_text(qtbot, wired) -> None:
    widget, service, store, manager = wired
    store.get_current_results.return_value = {5: saved_result()}
    widget.refresh()
    complete_load(widget, manager)
    widget.results_table.selectRow(0)

    assert widget.results_table.item(0, 1).text() == "⚠ 要確認"
    assert widget.details_table.item(0, 1).text() == "blue_eyes"
    assert widget.details_table.item(0, 3).text() == "8.0%"
    with qtbot.waitSignal(widget.manual_review_requested) as emission:
        qtbot.mouseClick(widget.manual_review_button, Qt.MouseButton.LeftButton)
    assert emission.args == [5]
    with qtbot.waitSignal(widget.manual_review_requested) as emission:
        widget.results_table.cellDoubleClicked.emit(0, 1)
    assert emission.args == [5]
    service.review.assert_not_called()
    store.save.assert_not_called()


def test_history_survives_staging_clear_and_reopening_widget(qtbot, wired) -> None:
    widget, service, store, manager = wired
    store.get_current_results.return_value = {5: saved_result()}
    widget.set_image_ids([5])
    widget.refresh()
    complete_load(widget, manager)
    widget.set_image_ids([])

    assert widget.results_table.rowCount() == 1
    assert not widget.start_button.isEnabled()
    reopened = AnnotationReviewBatchWidget()
    qtbot.addWidget(reopened)
    reopened_manager = FakeManager()
    reopened.set_services(service, store, reopened_manager)
    complete_load(reopened, reopened_manager)
    assert reopened.results_table.item(0, 0).text() == "画像 5"
    reopened.shutdown()


def test_stale_history_retains_text_and_manual_navigation_without_probabilities(wired) -> None:
    widget, _, store, manager = wired
    stored = saved_result()
    stale = replace(
        stored,
        review=replace(
            stored.review,
            status="stale",
            items=tuple(
                replace(item, probability=None, status="unevaluated") for item in stored.review.items
            ),
        ),
    )
    store.get_current_results.return_value = {5: stale}
    widget.refresh()
    complete_load(widget, manager)
    widget.results_table.selectRow(0)

    assert "再チェックが必要" in widget.results_table.item(0, 1).text()
    assert widget.results_table.item(0, 2).text() == "—"
    assert widget.details_table.item(0, 1).text() == "blue_eyes"
    assert widget.details_table.item(0, 3).text() == "—"
    assert widget.manual_review_button.isEnabled()


def test_refresh_hides_cached_probabilities_until_currentness_is_checked(wired) -> None:
    widget, _, store, manager = wired
    store.get_current_results.return_value = {5: saved_result()}
    widget.refresh()
    complete_load(widget, manager)
    widget.results_table.selectRow(0)
    assert widget.details_table.item(0, 3).text() == "8.0%"

    widget.refresh()

    assert "照合中" in widget.results_table.item(0, 1).text()
    assert widget.details_table.item(0, 3).text() == "—"
    assert widget.manual_review_button.isEnabled()
    complete_load(widget, manager)
    assert widget.details_table.item(0, 3).text() == "8.0%"


def test_settings_reload_rejects_old_image_event_and_reloads_history(wired) -> None:
    widget, _, store, manager = wired
    widget.set_image_ids([5])
    widget._on_start_requested()
    worker_id, worker = manager.started[-1]
    old_generation = widget._generation
    refreshed_service = Mock()
    widget.set_services(refreshed_service, store)
    complete_load(widget, manager)
    worker.per_image_finished.emit(AnnotationReviewBatchImageResult(old_generation, saved_result().review))

    assert manager.cancel_requests == [(worker_id, CancelReason.USER_REQUESTED)]
    assert widget.results_table.rowCount() == 0
    assert not widget.start_button.isEnabled()
    manager.worker_terminal.emit(
        WorkerTerminalEvent(worker_id, "annotation_review_batch", WorkerOutcome.CANCELED)
    )
    assert widget.start_button.isEnabled()
    assert "設定を更新" in widget.status_label.text()


def test_old_history_load_cannot_overwrite_live_image_result(wired) -> None:
    widget, _, store, manager = wired
    widget.set_image_ids([5])
    widget._on_start_requested()
    _, worker = manager.started[-1]
    widget.refresh()
    # Simulate the loader observing an older image row before a review finishes.
    store.get_current_results.return_value = {5: saved_result(status="failed")}
    worker.per_image_finished.emit(
        AnnotationReviewBatchImageResult(widget._generation, saved_result().review, True, saved_result())
    )
    complete_load(widget, manager)

    assert widget.results_table.item(0, 1).text() == "⚠ 要確認"


def test_cancel_preserves_completed_image_and_distinguishes_unfinished_scope(wired) -> None:
    widget, _, store, manager = wired
    widget.set_image_ids([5, 7])
    widget._on_start_requested()
    worker_id, worker = manager.started[-1]
    worker.per_image_finished.emit(
        AnnotationReviewBatchImageResult(widget._generation, saved_result().review, True, saved_result())
    )
    store.get_current_results.return_value = {5: saved_result()}
    widget._on_cancel_requested()
    manager.worker_terminal.emit(
        WorkerTerminalEvent(worker_id, "annotation_review_batch", WorkerOutcome.CANCELED)
    )
    complete_load(widget, manager)

    assert "中止" in widget.status_label.text()
    assert widget.results_table.item(0, 1).text() == "⚠ 要確認"
    assert widget.results_table.rowCount() == 1
    assert widget.progress_bar.value() == 1
    assert widget.start_button.isEnabled()


def test_worker_progress_counts_processed_images_and_keeps_stop_message(wired) -> None:
    widget, _, _, manager = wired
    widget.set_image_ids([5, 7])
    widget._on_start_requested()
    _, worker = manager.started[-1]
    worker.progress_updated.emit(
        WorkerProgress(50, "ローカルの Clef で確認中…", processed_count=1, total_count=2)
    )

    assert "ローカルの Clef" in widget.status_label.text()
    assert widget.progress_bar.value() == 1
    widget._on_cancel_requested()
    worker.progress_updated.emit(WorkerProgress(100, "完了", processed_count=2, total_count=2))
    assert "停止" in widget.status_label.text()
    assert widget.progress_bar.value() == 2


def test_finished_job_refreshes_history_and_shows_manual_review_message(wired) -> None:
    widget, _, store, manager = wired
    widget.set_image_ids([5])
    widget._on_start_requested()
    worker_id, _ = manager.started[-1]
    store.get_current_results.return_value = {5: saved_result()}
    result = AnnotationReviewBatchWorkerResult(widget._generation, (5,), (saved_result().review,), False)
    manager.worker_terminal.emit(
        WorkerTerminalEvent(worker_id, "annotation_review_batch", WorkerOutcome.SUCCEEDED, result=result)
    )
    complete_load(widget, manager)

    assert "警告・失敗・未評価" in widget.status_label.text()
    assert widget.results_table.rowCount() == 1
    assert widget.progress_bar.value() == 1


def test_final_processed_count_includes_superseded_images_without_claiming_they_were_saved(wired) -> None:
    widget, _, _, manager = wired
    widget.set_image_ids([5, 7])
    widget._on_start_requested()
    worker_id, _ = manager.started[-1]
    result = AnnotationReviewBatchWorkerResult(widget._generation, (5, 7), (), True, 2)
    manager.worker_terminal.emit(
        WorkerTerminalEvent(worker_id, "annotation_review", WorkerOutcome.SUCCEEDED, result=result)
    )

    assert widget.progress_bar.value() == 2
    assert "2 枚を処理しました" in widget.status_label.text()
    assert "保存済みの結果は保持" in widget.status_label.text()
    assert "2 枚の結果を保持" not in widget.status_label.text()


def test_deleted_image_failure_is_visible_without_a_saved_result_or_navigation(qtbot, wired) -> None:
    widget, _, store, manager = wired
    widget.set_image_ids([5, 7])
    widget._on_start_requested()
    _, worker = manager.started[-1]
    failed = replace(saved_result().review, status="failed", error="Image 5 was deleted.")
    worker.per_image_finished.emit(AnnotationReviewBatchImageResult(widget._generation, failed, False))
    qtbot.waitUntil(lambda: widget.results_table.rowCount() == 1)
    widget.results_table.selectRow(0)

    store.get_current_result.assert_not_called()
    assert "保存できません" in widget.results_table.item(0, 1).text()
    assert widget.details_table.item(0, 3).text() == "—"
    assert not widget.manual_review_button.isEnabled()
    assert "処理しました" in widget.status_label.text()
    widget.refresh()
    complete_load(widget, manager)
    assert widget.results_table.rowCount() == 1


def test_naive_database_timestamps_can_be_mixed_with_live_error_timestamps(qtbot, wired) -> None:
    widget, _, store, manager = wired
    naive = replace(saved_result(7), checked_at=datetime(2026, 10, 5, 16, 30))
    store.get_current_results.return_value = {7: naive}
    widget.refresh()
    complete_load(widget, manager)
    widget.set_image_ids([5])
    widget._on_start_requested()
    _, worker = manager.started[-1]
    worker.per_image_finished.emit(
        AnnotationReviewBatchImageResult(widget._generation, saved_result(status="failed").review, False)
    )
    qtbot.waitUntil(lambda: widget.results_table.rowCount() == 2)

    assert widget.results_table.rowCount() == 2
    assert widget.results_table.item(0, 0).text() == "画像 5"


def test_large_result_burst_updates_progress_and_renders_once_without_blocking_ui(qtbot, wired) -> None:
    widget, _, store, manager = wired
    draws = QSignalSpy(widget._render_timer.timeout)
    ids = list(range(1, 501))
    widget.set_image_ids(ids)
    widget._on_start_requested()
    _, worker = manager.started[-1]
    heartbeat = []
    QTimer.singleShot(0, lambda: heartbeat.append(True))

    for image_id in ids:
        worker.per_image_finished.emit(
            AnnotationReviewBatchImageResult(
                widget._generation, saved_result(image_id).review, True, saved_result(image_id)
            )
        )

    assert widget.progress_bar.value() == 500
    assert draws.count() == 0
    assert widget.results_table.rowCount() == 0
    qtbot.waitUntil(lambda: widget.results_table.rowCount() == 500)
    assert heartbeat == [True]
    assert draws.count() == 1
    store.get_current_result.assert_not_called()


def test_missing_stream_wrapper_hides_unverified_probability_without_gui_database_read(
    qtbot, wired
) -> None:
    widget, _, store, manager = wired
    widget.set_image_ids([5])
    widget._on_start_requested()
    _, worker = manager.started[-1]
    worker.per_image_finished.emit(
        AnnotationReviewBatchImageResult(widget._generation, saved_result().review)
    )
    qtbot.waitUntil(lambda: widget.results_table.rowCount() == 1)
    widget.results_table.selectRow(0)

    assert "再チェックが必要" in widget.results_table.item(0, 1).text()
    assert widget.details_table.item(0, 3).text() == "—"
    store.get_current_result.assert_not_called()


def test_invalid_settings_keep_saved_text_but_hide_probabilities_and_disable_start(wired) -> None:
    widget, _, store, manager = wired
    store.get_current_results.return_value = {5: saved_result()}
    widget.refresh()
    complete_load(widget, manager)
    widget.results_table.selectRow(0)
    widget.set_image_ids([5])
    widget.set_unavailable_reason("warning_threshold is invalid")

    assert not widget.start_button.isEnabled()
    assert widget.details_table.item(0, 1).text() == "blue_eyes"
    assert widget.details_table.item(0, 3).text() == "—"
    assert widget.manual_review_button.isEnabled()
    assert "設定を確認" in widget.status_label.text()


def test_slow_history_load_does_not_block_staging_or_cloud_review(qtbot) -> None:
    widget = AnnotationReviewBatchWidget()
    qtbot.addWidget(widget)
    entered, released = Event(), Event()
    service = Mock()
    store = Mock()

    def load(*args, **kwargs):
        entered.set()
        released.wait(3)
        return {5: saved_result()}

    store.get_current_results.side_effect = load
    try:
        widget.set_services(service, store)
        qtbot.waitUntil(entered.is_set, timeout=2000)
        widget.set_image_ids([5, 7])
        assert "ステージ済み 2 枚" in widget.scope_label.text()
        assert widget.start_button.isEnabled()
        service.review.assert_not_called()
        released.set()
        qtbot.waitUntil(lambda: widget.results_table.rowCount() == 1, timeout=2000)
    finally:
        released.set()
        widget.shutdown()


def test_parent_destruction_cancels_child_history_worker(qtbot) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)
    widget = AnnotationReviewBatchWidget(parent)
    service, store = Mock(), Mock()
    entered, released = Event(), Event()

    def load(*args, **kwargs):
        entered.set()
        while not released.wait(0.01):
            worker = next(iter(widget._manager.active_workers.values()))["worker"]
            if worker.cancellation.is_canceled():
                break
        return {}

    store.get_current_results.side_effect = load
    widget.set_services(service, store)
    manager = widget._manager
    try:
        qtbot.waitUntil(entered.is_set, timeout=2000)
        parent.deleteLater()
        qtbot.waitUntil(lambda: not manager.active_workers, timeout=2000)
        assert widget._closing
    finally:
        released.set()


def test_parent_destruction_cancels_active_batch_without_restarting_a_history_loader(qtbot) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)
    widget = AnnotationReviewBatchWidget(parent)
    service, store = Mock(), Mock()
    service.warning_threshold = 0.2
    service.prepare_reviews.return_value = {
        5: ReviewSnapshot(5, Path("/tmp/image.png"), (), (), "original")
    }
    store.get_current_results.return_value = {}
    entered, released = Event(), Event()

    def review(snapshot, *, is_cancelled):
        entered.set()
        while not released.wait(0.01):
            if is_cancelled():
                return AnnotationReviewResult(5, "original", "clef-flash", (), "cancelled")
        return saved_result().review

    service.review.side_effect = review
    widget.set_services(service, store)
    widget.set_image_ids([5])
    widget._on_start_requested()
    manager = widget._manager
    try:
        qtbot.waitUntil(entered.is_set, timeout=2000)
        parent.deleteLater()
        qtbot.waitUntil(lambda: not manager.active_workers, timeout=2000)
        assert widget._closing
    finally:
        released.set()
