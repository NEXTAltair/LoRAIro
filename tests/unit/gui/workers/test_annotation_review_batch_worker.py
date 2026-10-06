"""Fixed targets, preflight ordering, independent saves and cancellation."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from lorairo.gui.workers.annotation_review_batch_worker import AnnotationReviewBatchWorker
from lorairo.gui.workers.annotation_review_worker import AnnotationReviewWorker
from lorairo.gui.workers.base import WorkerStatus
from lorairo.services.annotation_review_service import (
    AnnotationReviewItem,
    AnnotationReviewResult,
    AnnotationReviewService,
    ReviewCandidate,
    ReviewSnapshot,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def batch_context():
    service = Mock(spec=AnnotationReviewService)
    service.model_name = "@cf/cloudflare/clef-flash"
    service.warning_threshold = 0.2
    snapshots = {
        image_id: ReviewSnapshot(
            image_id,
            Path(f"{image_id}.png"),
            (ReviewCandidate(f"tag_{image_id}", "tag", "dog"),),
            (),
            f"snapshot-{image_id}",
        )
        for image_id in (1, 2, 3)
    }
    service.prepare_reviews.return_value = snapshots

    def review(snapshot, *, is_cancelled):
        return AnnotationReviewResult(
            snapshot.image_id,
            snapshot.fingerprint,
            service.model_name,
            (AnnotationReviewItem(f"tag_{snapshot.image_id}", "tag", "dog", 0.03, "warning"),),
            "completed",
        )

    service.review.side_effect = review
    store = Mock()
    return service, store, snapshots, review


def test_target_list_frozen_ordered_and_deduplicated_before_worker_runs(batch_context):
    service, store, snapshots, _ = batch_context
    targets = [3, 1, 3, 2]
    worker = AnnotationReviewBatchWorker(service, store, targets, 42)
    targets[:] = [999]
    emitted = []
    worker.per_image_finished.connect(emitted.append)

    result = worker.execute()

    assert result.image_ids == (3, 1, 2)
    assert [review.image_id for review in result.reviews] == [3, 1, 2]
    assert [item.review.image_id for item in emitted] == [3, 1, 2]
    assert all(item.generation == 42 for item in emitted)
    service.prepare_reviews.assert_called_once_with((3, 1, 2), is_cancelled=worker.cancellation.is_canceled)
    assert [call.args[0] for call in service.review.call_args_list] == [
        snapshots[3],
        snapshots[1],
        snapshots[2],
    ]
    assert not result.cancelled
    assert store.save.call_count == 3


def test_preflight_finishes_before_first_review_and_save_precedes_signal(batch_context):
    service, store, _, review = batch_context
    events = []
    service.prepare_reviews.side_effect = lambda targets, **kwargs: (
        events.append("all snapshots"),
        service.prepare_reviews.return_value,
    )[1]
    service.review.side_effect = lambda snapshot, **kwargs: (
        events.append(f"review {snapshot.image_id}"),
        review(snapshot, **kwargs),
    )[1]
    store.save.side_effect = lambda result, threshold: events.append(f"save {result.image_id}")
    worker = AnnotationReviewBatchWorker(service, store, (1, 2), 3)
    worker.per_image_finished.connect(lambda payload: events.append(f"signal {payload.review.image_id}"))
    worker.execute()
    assert events == ["all snapshots", "review 1", "save 1", "signal 1", "review 2", "save 2", "signal 2"]


@pytest.mark.parametrize("targets", [[], [True], [0], [-1], ["1"], list(range(1, 502))])
def test_invalid_scope_never_starts_paid_review(batch_context, targets):
    service, store, _, _ = batch_context
    with pytest.raises(ValueError):
        AnnotationReviewBatchWorker(service, store, targets, 1)
    service.review.assert_not_called()
    store.save.assert_not_called()


def test_cancellation_preserves_completed_images_and_leaves_unstarted_targets_alone(batch_context):
    service, store, _, _ = batch_context
    worker = AnnotationReviewBatchWorker(service, store, (1, 2, 3), 1)
    worker.per_image_finished.connect(lambda payload: worker.cancel())
    result = worker.execute()
    assert result.cancelled
    assert [review.image_id for review in result.reviews] == [1]
    assert store.save.call_count == 1
    assert store.save.call_args.args[0].status == "completed"
    assert service.review.call_count == 1


def test_cancelled_run_delivers_per_image_result_before_canceled_terminal(batch_context):
    service, store, _, _ = batch_context
    worker = AnnotationReviewBatchWorker(service, store, (1, 2), 1)
    events = []
    worker.per_image_finished.connect(lambda payload: (events.append("image"), worker.cancel()))
    worker.canceled.connect(lambda: events.append("cancelled"))
    worker.finished.connect(lambda payload: events.append("finished"))
    worker.run()
    assert worker.status == WorkerStatus.CANCELED
    assert events == ["image", "cancelled"]
    assert store.save.call_count == 1


def test_cancellation_during_preflight_sends_nothing(batch_context):
    service, store, _, _ = batch_context
    worker = AnnotationReviewBatchWorker(service, store, (1, 2), 1)

    def cancel_during_preparation(*args, **kwargs):
        worker.cancel()
        return {}

    service.prepare_reviews.side_effect = cancel_during_preparation
    result = worker.execute()
    assert result.cancelled and result.reviews == ()
    service.review.assert_not_called()
    store.save.assert_not_called()


def test_cancellation_while_current_request_pending_does_not_count_unsaved_image(batch_context):
    service, store, _, _ = batch_context
    worker = AnnotationReviewBatchWorker(service, store, (1, 2), 1)
    emitted = []
    worker.per_image_finished.connect(emitted.append)

    def cancel_before_answer(snapshot, **kwargs):
        worker.cancel()
        return AnnotationReviewResult(
            snapshot.image_id,
            snapshot.fingerprint,
            service.model_name,
            (AnnotationReviewItem("tag_1", "tag", "dog", None, "unevaluated"),),
            "cancelled",
        )

    service.review.side_effect = cancel_before_answer
    result = worker.execute()
    assert result.cancelled and result.reviews == ()
    assert emitted == []
    assert service.review.call_count == 1
    store.save.assert_not_called()


def test_missing_image_is_retained_as_failure_while_other_images_are_reviewed(batch_context):
    service, store, snapshots, _ = batch_context
    snapshots[2] = AnnotationReviewResult(2, "", service.model_name, (), "failed", "Image is missing")
    worker = AnnotationReviewBatchWorker(service, store, (1, 2, 3), 1)
    result = worker.execute()
    assert [review.status for review in result.reviews] == ["completed", "failed", "completed"]
    assert service.review.call_count == 2
    assert store.save.call_count == 3


@pytest.mark.parametrize("code", ["configuration", "authentication", "rate_limit"])
def test_global_provider_failure_stops_later_calls_and_retains_explicit_unevaluated_images(
    batch_context, code
):
    service, store, _, _ = batch_context
    service.review.return_value = AnnotationReviewResult(
        1,
        "snapshot-1",
        service.model_name,
        (AnnotationReviewItem("tag_1", "tag", "dog", None, "failed", "Provider failed"),),
        "failed",
        "Provider failed",
        code,
    )
    service.review.side_effect = None
    worker = AnnotationReviewBatchWorker(service, store, (1, 2, 3), 1)
    result = worker.execute()
    assert service.review.call_count == 1
    assert [review.status for review in result.reviews] == ["failed", "unevaluated", "unevaluated"]
    assert all(review.error_code == code for review in result.reviews)
    assert all(item.probability is None for review in result.reviews for item in review.items)
    assert store.save.call_count == 3


def test_single_image_worker_persists_before_completion(batch_context):
    service, store, snapshots, _ = batch_context
    service.prepare_review.return_value = snapshots[1]
    worker = AnnotationReviewWorker(service, 1, 7, store=store)
    result = worker.execute()
    assert result.generation == 7 and result.review.image_id == 1
    store.save.assert_called_once_with(result.review, 0.2)


def test_single_image_worker_keeps_read_only_compatibility_when_no_store(batch_context):
    service, store, snapshots, _ = batch_context
    service.prepare_review.return_value = snapshots[1]
    AnnotationReviewWorker(service, 1, 7).execute()
    store.save.assert_not_called()
