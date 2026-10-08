"""Keep independent review history durable and distinguish stale results."""

import hashlib
import json
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from PIL import Image as PILImage
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError, OperationalError

from lorairo.database.repository.annotation_review import AnnotationReviewRepository
from lorairo.database.schema import Image, Tag
from lorairo.services.annotation_review_adoption_service import AnnotationReviewAdoptionService
from lorairo.services.annotation_review_service import (
    AnnotationReviewItem,
    AnnotationReviewResult,
    AnnotationReviewService,
    ReviewCandidateSource,
    ReviewSnapshot,
)
from lorairo.services.annotation_review_store import AnnotationReviewStore
from lorairo.services.configuration_service import ConfigurationService

pytestmark = pytest.mark.unit


@pytest.fixture
def saved_context(test_repository, db_session_factory):
    with db_session_factory() as session:
        session.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
        session.add_all(
            [
                Image(
                    id=image_id,
                    uuid=f"review-{image_id}",
                    phash=f"phash-{image_id}",
                    original_image_path=f"{image_id}.png",
                    stored_image_path=f"{image_id}.png",
                    width=32,
                    height=32,
                    format="PNG",
                    extension=".png",
                )
                for image_id in (7, 8)
            ]
        )
        session.commit()
    db = Mock()
    db.image_repo = test_repository
    service = Mock(spec=AnnotationReviewService)
    service.model_name = "@cf/cloudflare/clef-flash"
    service.warning_threshold = 0.2
    service.prepare_reviews.return_value = {
        image_id: ReviewSnapshot(image_id, Path(f"{image_id}.png"), (), (), "original")
        for image_id in (7, 8)
    }
    review = AnnotationReviewResult(
        7,
        "original",
        service.model_name,
        (
            AnnotationReviewItem("tag_11", "tag", "dog", 0.03, "warning"),
            AnnotationReviewItem("caption_21", "caption", "赤い髪の女性。", 0.9, "ok"),
        ),
        "completed",
    )
    return db, service, review


def test_restart_roundtrip_preserves_candidates_settings_and_time(saved_context):
    db, service, review = saved_context
    AnnotationReviewStore(db).save(review, 0.2)

    loaded = AnnotationReviewStore(db).get_current_result(7, service)

    assert loaded.review == review
    assert loaded.warning_threshold == 0.2
    assert loaded.checked_at is not None
    service.prepare_reviews.assert_called_once_with((7,))
    service.prepare_review.assert_not_called()
    assert db.image_repo.get_image_annotations(7)["tags"] == []
    assert db.image_repo.get_image_annotations(7)["captions"] == []


@pytest.mark.parametrize("change", ["image", "model", "threshold", "missing"])
def test_changed_source_or_settings_stale_only_for_display(saved_context, change):
    db, service, review = saved_context
    store = AnnotationReviewStore(db)
    store.save(review, 0.2)
    if change == "image":
        service.prepare_reviews.return_value[7] = ReviewSnapshot(7, Path("7.png"), (), (), "edited")
    elif change == "model":
        service.model_name = "@cf/cloudflare/clef"
    elif change == "threshold":
        service.warning_threshold = 0.1
    else:
        service.prepare_reviews.return_value = {}

    displayed = store.get_current_result(7, service)

    assert displayed.review.status == "stale"
    assert all(item.probability is None and item.status == "unevaluated" for item in displayed.review.items)
    assert store.get_results()[7].review == review
    assert displayed.checked_at == store.get_results()[7].checked_at


def test_authentication_failure_roundtrip_retains_typed_batch_stop_code(saved_context):
    db, _, review = saved_context
    failed = replace(
        review,
        items=(AnnotationReviewItem("tag_11", "tag", "dog", None, "failed", "Authentication failed"),),
        status="failed",
        error="Authentication failed",
        error_code="authentication",
    )
    store = AnnotationReviewStore(db)
    store.save(failed, 0.2)
    assert store.get_results((7,))[7].review == failed


def test_empty_cancellation_does_not_erase_existing_warning(saved_context):
    db, _, review = saved_context
    store = AnnotationReviewStore(db)
    store.save(review, 0.2)
    previous = store.get_results()[7]
    cancelled = replace(
        review,
        items=(AnnotationReviewItem("tag_11", "tag", "dog", None, "unevaluated"),),
        status="cancelled",
    )
    store.save(cancelled, 0.2)
    assert store.get_results()[7] == previous


def test_cancellation_after_a_completed_chunk_retains_its_probabilities(saved_context):
    db, _, review = saved_context
    partial = replace(
        review,
        items=(*review.items, AnnotationReviewItem("tag_12", "tag", "cat", None, "unevaluated")),
        status="cancelled",
    )
    store = AnnotationReviewStore(db)
    store.save(partial, 0.2)
    assert store.get_results()[7].review == partial


def test_latest_limit_applied_before_batched_freshness_read(saved_context):
    db, service, review = saved_context
    store = AnnotationReviewStore(db)
    store.save(review, 0.2)
    store.save(replace(review, image_id=8), 0.2)

    results = store.get_current_results(service, limit=1)

    assert list(results) == [8]
    service.prepare_reviews.assert_called_once_with((8,))
    assert len(store.get_results()) == 2
    assert store.get_results([]) == {}


@pytest.mark.parametrize(
    "payload",
    [
        "not JSON",
        "[]",
        '{"items":[{"candidate_id":"tag_11","kind":"tag","text":"dog","probability":true,"status":"ok"}]}',
        '{"items":[{"candidate_id":"tag_11","kind":"tag","text":"dog","probability":null,"status":"warning"}]}',
        '{"items":[{"candidate_id":"tag_11","kind":"tag","text":"dog","probability":2,"status":"ok"}]}',
    ],
)
def test_unreadable_stored_result_is_failure_not_clean_success(saved_context, payload):
    db, _, review = saved_context
    repository = AnnotationReviewRepository(db.image_repo.session_factory)
    repository.save_result(
        image_id=7,
        fingerprint=review.fingerprint,
        model_name=review.model_name,
        warning_threshold=0.2,
        status="completed",
        items_json=payload,
        error=None,
    )
    loaded = AnnotationReviewStore(db).get_results()[7]
    assert loaded.review.status == "failed"
    assert loaded.review.items == ()
    assert loaded.review.error


def test_candidates_with_equal_text_preserve_distinct_row_ids(saved_context):
    db, _, review = saved_context
    duplicate_text = replace(
        review,
        items=(*review.items, AnnotationReviewItem("tag_12", "tag", "dog", 0.9, "ok")),
    )
    store = AnnotationReviewStore(db)
    store.save(duplicate_text, 0.2)
    assert store.get_results()[7].review == duplicate_text
    record = AnnotationReviewRepository(db.image_repo.session_factory).get_results()[7]
    assert len(json.loads(record.items_json)["items"]) == 3


def _suggestion_review(review, *, probability=0.8, status="suggestion", text="new_tag"):
    source = ReviewCandidateSource("hair", ("smile",), 12)
    candidate_id = "suggestion_" + hashlib.sha256(text.casefold().encode("utf-8")).hexdigest()
    return replace(
        review,
        items=(
            *review.items,
            AnnotationReviewItem(candidate_id, "suggestion", text, probability, status),
        ),
        candidate_source=source,
        suggestion_threshold=0.8,
    )


def test_suggestion_restart_roundtrip_keeps_scope_threshold_and_actual_source_fingerprint(saved_context):
    db, service, review = saved_context
    service.suggestion_threshold = 0.8
    review = _suggestion_review(review)
    AnnotationReviewStore(db).save(review, 0.2)

    loaded = AnnotationReviewStore(db).get_current_result(7, service)

    assert loaded.review == review
    assert loaded.candidate_source == review.candidate_source
    assert loaded.suggestion_threshold == 0.8
    # Currentness uses the actual annotations, never re-extracts candidate tags.
    service.prepare_reviews.assert_called_once_with((7,))
    assert loaded.review.fingerprint == "original"


def test_suggestion_threshold_change_invalidates_saved_suggestions_only(saved_context):
    db, service, review = saved_context
    service.suggestion_threshold = 0.8
    store = AnnotationReviewStore(db)
    store.save(_suggestion_review(review), 0.2)
    store.save(replace(review, image_id=8), 0.2)
    service.suggestion_threshold = 0.9

    current = store.get_current_results(service)

    assert current[7].review.status == "stale"
    assert all(item.probability is None for item in current[7].review.items)
    assert current[8].review.status == "completed"
    assert store.get_results((7,))[7].review.status == "completed"


def test_old_json_payload_without_candidate_metadata_remains_readable(saved_context):
    from dataclasses import asdict

    db, service, review = saved_context
    repository = AnnotationReviewRepository(db.image_repo.session_factory)
    repository.save_result(
        image_id=7,
        fingerprint=review.fingerprint,
        model_name=review.model_name,
        warning_threshold=0.2,
        status=review.status,
        items_json=json.dumps({"items": [asdict(item) for item in review.items]}),
        error=None,
    )
    restored = AnnotationReviewStore(db).get_current_result(7, service)
    assert restored.review == review
    assert restored.candidate_source is None and restored.suggestion_threshold == 0.8


@pytest.mark.parametrize(
    "corruption",
    [
        "tag_suggestion_status",
        "suggestion_warning_status",
        "high_ok_status",
        "low_suggestion_status",
        "missing_source",
        "invalid_source",
        "invalid_threshold",
    ],
)
def test_restore_rejects_incoherent_suggestion_kind_status_probability_and_metadata(
    saved_context, corruption
):
    db, _, review = saved_context
    store = AnnotationReviewStore(db)
    store.save(_suggestion_review(review), 0.2)
    repository = AnnotationReviewRepository(db.image_repo.session_factory)
    record = repository.get_results((7,))[7]
    payload = json.loads(record.items_json)
    suggestion = payload["items"][-1]
    if corruption == "tag_suggestion_status":
        suggestion["kind"] = "tag"
    elif corruption == "suggestion_warning_status":
        suggestion["status"] = "warning"
        suggestion["probability"] = 0.1
    elif corruption == "high_ok_status":
        suggestion["status"] = "ok"
    elif corruption == "low_suggestion_status":
        suggestion["probability"] = 0.79
    elif corruption == "missing_source":
        payload.pop("candidate_source")
    elif corruption == "invalid_source":
        payload["candidate_source"]["selected_tags"] = "smile"
    else:
        payload["suggestion_threshold"] = True
    repository.save_result(
        image_id=7,
        fingerprint=record.fingerprint,
        model_name=record.model_name,
        warning_threshold=record.warning_threshold,
        status=record.status,
        items_json=json.dumps(payload),
        error=None,
    )
    restored = store.get_results((7,))[7]
    assert restored.review.status == "failed" and restored.review.items == ()


@pytest.mark.parametrize(
    "change", ["image", "model", "warning_threshold", "suggestion_threshold", "newer", "missing"]
)
def test_adoption_rejects_stale_settings_sources_or_obsolete_ui_result(saved_context, change):
    db, service, review = saved_context
    service.suggestion_threshold = 0.8
    review = _suggestion_review(review)
    store = AnnotationReviewStore(db)
    store.save(review, 0.2)
    expected = store.get_results((7,))[7].checked_at
    if change == "image":
        service.prepare_reviews.return_value[7] = ReviewSnapshot(7, Path("7.png"), (), (), "changed")
    elif change == "model":
        service.model_name = "@cf/cloudflare/clef"
    elif change == "warning_threshold":
        service.warning_threshold = 0.1
    elif change == "suggestion_threshold":
        service.suggestion_threshold = 0.9
    elif change == "newer":
        store.save(review, 0.2)
        assert store.get_results((7,))[7].checked_at != expected
    else:
        service.prepare_reviews.return_value = {}

    assert not AnnotationReviewAdoptionService(db, service, store).adopt(
        7, review.items[-1].candidate_id, expected
    )
    db.add_manual_tag.assert_not_called()


@pytest.mark.parametrize("phase", ["read", "write"])
def test_adoption_database_failure_returns_false_without_escaping(saved_context, phase):
    db, service, review = saved_context
    service.suggestion_threshold = 0.8
    review = _suggestion_review(review)
    store = AnnotationReviewStore(db)
    store.save(review, 0.2)
    expected = store.get_results((7,))[7].checked_at
    error = OperationalError("adopt suggestion", {}, RuntimeError("database is locked"))
    if phase == "read":
        store = Mock(spec=AnnotationReviewStore)
        store.get_current_result.side_effect = error
    else:
        db.add_manual_tag.side_effect = error

    assert not AnnotationReviewAdoptionService(db, service, store).adopt(
        7, review.items[-1].candidate_id, expected
    )
    if phase == "read":
        db.add_manual_tag.assert_not_called()
    else:
        db.add_manual_tag.assert_called_once_with(7, review.items[-1].text)


@pytest.mark.parametrize("candidate", ["regular_tag", "missing", "low_probability", "unevaluated"])
def test_adoption_requires_evaluated_high_probability_suggestion(saved_context, candidate):
    db, service, review = saved_context
    service.suggestion_threshold = 0.8
    if candidate == "low_probability":
        review = _suggestion_review(review, probability=0.79, status="ok")
    elif candidate == "unevaluated":
        review = _suggestion_review(review, probability=None, status="unevaluated")
        review = replace(review, status="partial")
    else:
        review = _suggestion_review(review)
    store = AnnotationReviewStore(db)
    store.save(review, 0.2)
    expected = store.get_results((7,))[7].checked_at
    candidate_id = (
        "tag_11"
        if candidate == "regular_tag"
        else ("missing" if candidate == "missing" else review.items[-1].candidate_id)
    )
    assert not AnnotationReviewAdoptionService(db, service, store).adopt(7, candidate_id, expected)
    db.add_manual_tag.assert_not_called()


@pytest.mark.parametrize("text", ["new_tag", "Fate/Grand Order"])
def test_adoption_uses_manual_provenance_no_probability_confidence_and_preserves_reviewed_state(
    saved_context, test_db_manager, db_session_factory, monkeypatch, text
):
    db, service, review = saved_context
    service.suggestion_threshold = 0.8
    review = _suggestion_review(review, text=text)
    store = AnnotationReviewStore(db)
    store.save(review, 0.2)
    expected = store.get_results((7,))[7].checked_at
    reviewed_at = datetime(2026, 10, 1, tzinfo=UTC)
    with db_session_factory() as session:
        session.get(Image, 7).reviewed_at = reviewed_at
        session.commit()
    monkeypatch.setattr(
        test_db_manager.annotation_repo,
        "_resolution_for_batch_add",
        lambda session, tag, resolved: (tag, None),
    )
    adoption = AnnotationReviewAdoptionService(test_db_manager, service, store)
    assert adoption.adopt(7, review.items[-1].candidate_id, expected)
    with db_session_factory() as session:
        tag = session.query(Tag).filter_by(image_id=7, tag=text).one()
        assert tag.is_edited_manually and tag.confidence_score is None
        assert tag.model_id == test_db_manager.get_manual_edit_model_id()
        assert session.get(Image, 7).reviewed_at.replace(tzinfo=UTC) == reviewed_at
    assert not adoption.adopt(7, review.items[-1].candidate_id, expected)
    assert not adoption.adopt(7, review.items[-1].candidate_id, expected - timedelta(seconds=1))
    assert store.get_results((7,))[7].review == review


def test_image_deleted_during_paid_request_does_not_abort_later_fixed_targets(
    saved_context, db_session_factory, tmp_path, monkeypatch
):
    from lorairo.gui.workers.annotation_review_batch_worker import AnnotationReviewBatchWorker

    package = (
        Path(__file__).resolve().parents[3] / "local_packages/image-annotator-lib/src/image_annotator_lib"
    )
    monkeypatch.setattr(sys.modules["image_annotator_lib"], "__path__", [str(package)])
    from image_annotator_lib.decisions import CloudflareDecisionClient

    db, _, _ = saved_context
    path = tmp_path / "image.png"
    PILImage.new("RGB", (32, 32), "red").save(path)
    with db_session_factory() as session:
        for image_id in (7, 8):
            session.get(Image, image_id).stored_image_path = str(path)
            session.add(Tag(image_id=image_id, tag="red_hair"))
        session.commit()
    for name in (
        "get_image_metadata",
        "get_image_annotations",
        "get_images_metadata_batch",
        "get_image_annotations_batch",
    ):
        getattr(db, name).side_effect = getattr(db.image_repo, name)
    requests = []

    def delete_first_image(request):
        payload = json.loads(request.content)
        requests.append(payload)
        if len(requests) == 1:
            with db_session_factory() as session:
                session.execute(delete(Image).where(Image.id == 7))
                session.commit()
        return httpx.Response(
            200,
            json={
                "result": {
                    "model": "clef-flash",
                    "answers": {key: {"type": "noul", "noul": 0.9} for key in payload["questions"]},
                }
            },
        )

    config = ConfigurationService(
        shared_config={"api": {"cloudflare_account_id": "account", "cloudflare_api_token": "token"}}
    )
    service = AnnotationReviewService(
        config,
        db,
        client_factory=partial(CloudflareDecisionClient, transport=httpx.MockTransport(delete_first_image)),
    )
    store = AnnotationReviewStore(db)
    worker = AnnotationReviewBatchWorker(service, store, (7, 8), 1)
    received = []
    worker.per_image_finished.connect(received.append)

    result = worker.execute()

    assert [review.status for review in result.reviews] == ["failed", "completed"]
    assert [payload.saved for payload in received] == [False, True]
    assert list(store.get_results()) == [8]
    assert len(requests) == 2


def test_unrelated_database_integrity_error_still_propagates(saved_context, monkeypatch):
    db, _, review = saved_context
    store = AnnotationReviewStore(db)
    error = IntegrityError("statement", {}, ValueError("unrelated integrity failure"))
    monkeypatch.setattr(store._repository, "save_result", Mock(side_effect=error))
    with pytest.raises(IntegrityError):
        store.save(review, 0.2)


def test_old_batch_finishing_late_cannot_overwrite_newer_single_image_result(saved_context):
    from lorairo.gui.workers.annotation_review_batch_worker import AnnotationReviewBatchWorker
    from lorairo.gui.workers.annotation_review_worker import AnnotationReviewWorker

    db, service, review = saved_context
    old_store = AnnotationReviewStore(db)
    new_store = AnnotationReviewStore(db)
    service.review.return_value = replace(
        review,
        items=(AnnotationReviewItem("tag_11", "tag", "old dog", None, "unevaluated"),),
        status="stale",
    )
    old_batch = AnnotationReviewBatchWorker(service, old_store, (7,), 1)
    emitted = []
    old_batch.per_image_finished.connect(emitted.append)

    new_service = Mock(spec=AnnotationReviewService)
    new_service.warning_threshold = 0.2
    new_service.prepare_review.return_value = ReviewSnapshot(7, Path("7.png"), (), (), "new source")
    newer_review = replace(review, fingerprint="new source")
    new_service.review.return_value = newer_review
    new_worker = AnnotationReviewWorker(new_service, 7, 2, store=new_store)
    new_worker.execute()
    saved_before_late_completion = new_store.get_results()[7]

    result = old_batch.execute()

    assert result.processed_count == 1 and result.reviews == ()
    assert emitted == []
    assert old_store.get_results()[7] == saved_before_late_completion
    assert old_store.get_results()[7].review == newer_review
