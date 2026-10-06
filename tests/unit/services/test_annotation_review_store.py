"""Keep independent review history durable and distinguish stale results."""

import json
import sys
from dataclasses import replace
from functools import partial
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from PIL import Image as PILImage
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from lorairo.database.repository.annotation_review import AnnotationReviewRepository
from lorairo.database.schema import Image, Tag
from lorairo.services.annotation_review_service import (
    AnnotationReviewItem,
    AnnotationReviewResult,
    AnnotationReviewService,
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
