"""Search uses current saved warnings across every thumbnail page."""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import OperationalError

from lorairo.database.schema import Image
from lorairo.gui.workers.base import CancellationError
from lorairo.gui.workers.search_worker import SearchWorker
from lorairo.services.annotation_review_service import (
    AnnotationReviewItem,
    AnnotationReviewResult,
    AnnotationReviewService,
    ReviewSnapshot,
)
from lorairo.services.annotation_review_store import AnnotationReviewStore, StoredReviewResult
from lorairo.services.search_models import SearchConditions
from lorairo.services.search_review_status import load_review_metadata, review_metadata

pytestmark = pytest.mark.unit


@pytest.fixture
def review_search_context(test_repository, db_session_factory):
    """Persist one warning on the second page and one stale warning on the first."""
    images = [
        {"id": image_id, "stored_image_path": f"{image_id}.png", "source": f"source-{image_id}"}
        for image_id in range(1, 205)
    ]
    with db_session_factory() as session:
        session.add_all(
            Image(
                id=image_id,
                uuid=f"search-{image_id}",
                phash=f"phash-{image_id}",
                original_image_path=f"{image_id}.png",
                stored_image_path=f"{image_id}.png",
                width=32,
                height=32,
                format="PNG",
                extension=".png",
            )
            for image_id in (7, 201)
        )
        session.commit()
    db = Mock()
    db.image_repo = test_repository
    db.get_images_by_filter.return_value = (images, len(images))
    service = Mock(spec=AnnotationReviewService)
    service.model_name = "clef-flash"
    service.warning_threshold = 0.2
    service.prepare_reviews.side_effect = lambda image_ids: {
        image_id: ReviewSnapshot(
            image_id, Path(f"{image_id}.png"), (), (), "edited" if image_id == 7 else "original"
        )
        for image_id in image_ids
    }
    store = AnnotationReviewStore(db)
    for image_id in (7, 201):
        store.save(
            AnnotationReviewResult(
                image_id,
                "original",
                service.model_name,
                (AnnotationReviewItem("tag_1", "tag", "dog", 0.03, "warning"),),
                "completed",
            ),
            0.2,
        )
    return db, service, store, images


def test_warning_filter_checks_all_pages_and_preserves_source_metadata(review_search_context):
    db, service, store, original = review_search_context
    worker = SearchWorker(
        db,
        SearchConditions("tags", [], "and", annotation_review_warnings_only=True),
        review_service=service,
        review_store=store,
    )
    result = worker.execute()
    assert result.total_count == 1
    assert [image["id"] for image in result.image_metadata] == [201]
    assert result.image_metadata[0]["source"] == "source-201"
    assert result.image_metadata[0]["annotation_review_warning_count"] == 1
    assert "annotation_review_status" not in original[-4]
    service.review.assert_not_called()
    assert store.get_results((7,))[7].review.status == "completed"


def test_search_badges_distinguish_stale_and_unchecked_without_http(review_search_context):
    db, service, store, _ = review_search_context
    result = SearchWorker(
        db, SearchConditions("tags", [], "and"), review_service=service, review_store=store
    ).execute()
    metadata = {image["id"]: image for image in result.image_metadata}
    assert result.total_count == 204
    assert metadata[1]["annotation_review_status"] == "unchecked"
    assert metadata[7]["annotation_review_status"] == "stale"
    assert metadata[7]["annotation_review_warning_count"] == 0
    assert metadata[201]["annotation_review_warning_count"] == 1
    service.review.assert_not_called()


def test_background_count_estimate_matches_warning_filtered_search(review_search_context):
    from lorairo.gui.services.search_filter_service import SearchFilterService

    db, service, store, _ = review_search_context
    search_service = SearchFilterService(db, Mock())
    search_service.set_review_context(service, store)
    assert (
        search_service.get_estimated_count(
            SearchConditions("tags", [], "and", annotation_review_warnings_only=True)
        )
        == 1
    )
    service.review.assert_not_called()


@pytest.mark.parametrize("phase", ["saved", "fingerprint"])
@pytest.mark.parametrize("warnings_only", [False, True])
def test_failed_auxiliary_review_read_preserves_only_ordinary_search(
    review_search_context, monkeypatch, phase, warnings_only
):
    db, service, store, original = review_search_context
    error = OperationalError("read review", {}, RuntimeError("database is locked"))
    if phase == "saved":
        monkeypatch.setattr(store, "get_results", Mock(side_effect=error))
    else:
        service.prepare_reviews.side_effect = error
    worker = SearchWorker(
        db,
        SearchConditions("tags", [], "and", annotation_review_warnings_only=warnings_only),
        review_service=service,
        review_store=store,
    )
    if warnings_only:
        with pytest.raises(OperationalError):
            worker.execute()
        db.save_error_record.assert_called_once()
    else:
        result = worker.execute()
        assert result.total_count == 204
        assert [image["id"] for image in result.image_metadata] == [image["id"] for image in original]
        assert all(image["annotation_review_status"] == "load_failed" for image in result.image_metadata)
        assert all(image["annotation_review_warning_count"] == 0 for image in result.image_metadata)
        assert result.image_metadata[-1]["source"] == original[-1]["source"]
        db.save_error_record.assert_not_called()
    assert all("annotation_review_status" not in image for image in original)
    service.review.assert_not_called()


def test_cancellation_during_optional_review_read_still_cancels_search(review_search_context, monkeypatch):
    db, service, store, _ = review_search_context
    monkeypatch.setattr(store, "get_results", Mock(side_effect=CancellationError()))
    worker = SearchWorker(
        db, SearchConditions("tags", [], "and"), review_service=service, review_store=store
    )
    with pytest.raises(CancellationError):
        worker.execute()
    db.save_error_record.assert_not_called()


def test_suggestions_are_not_warnings():
    # New backend candidates have their own kind/status and never imply that
    # an existing annotation contradicts the image.
    items = (
        AnnotationReviewItem("tag_1", "tag", "dog", 0.03, "warning"),
        SimpleNamespace(kind="suggestion", status="warning", probability=0.03),
        SimpleNamespace(kind="suggestion", status="suggestion", probability=0.95),
    )
    saved = StoredReviewResult(
        AnnotationReviewResult(1, "fp", "model", items, "completed"), 0.2, datetime.now(UTC)
    )
    assert review_metadata(saved)["annotation_review_warning_count"] == 1
    stale = replace(saved, review=replace(saved.review, status="stale"))
    assert review_metadata(stale)["annotation_review_warning_count"] == 0


def test_batch_freshness_stops_on_cancellation():
    store, service = Mock(), Mock()
    store.get_current_results.return_value = {}
    calls = 0

    def check_cancel():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise CancellationError()

    with pytest.raises(CancellationError):
        load_review_metadata(tuple(range(1, 301)), service, store, check_cancel)
    assert store.get_current_results.call_count == 1
    assert len(store.get_current_results.call_args.args[1]) == 128
