"""Saved Clef review metadata used by search, without invoking inference."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .annotation_review_service import AnnotationReviewService
    from .annotation_review_store import AnnotationReviewStore, StoredReviewResult


def review_metadata(saved: StoredReviewResult | None) -> dict[str, Any]:
    """Keep stale and incomplete reviews distinct from a completed clean review."""
    if saved is None:
        return {"annotation_review_status": "unchecked", "annotation_review_warning_count": 0}
    review = saved.review
    warnings = (
        sum(
            item.kind in ("tag", "caption") and item.status == "warning" and item.probability is not None
            for item in review.items
        )
        if review.status != "stale"
        else 0
    )
    return {
        "annotation_review_status": review.status,
        "annotation_review_warning_count": warnings,
        "annotation_review_checked_at": saved.checked_at.isoformat(),
        "annotation_review_model": review.model_name,
        "annotation_review_threshold": saved.warning_threshold,
    }


def load_review_metadata(
    image_ids: Sequence[int],
    service: AnnotationReviewService,
    store: AnnotationReviewStore,
    check_cancellation: Callable[[], None] | None = None,
) -> dict[int, dict[str, Any]]:
    """Check only matching images, in cancellable batches, on a worker thread."""
    metadata: dict[int, dict[str, Any]] = {}
    for start in range(0, len(image_ids), 128):
        if check_cancellation is not None:
            check_cancellation()
        batch = image_ids[start : start + 128]
        saved_results = store.get_current_results(service, batch)
        metadata.update({image_id: review_metadata(saved_results.get(image_id)) for image_id in batch})
    if check_cancellation is not None:
        check_cancellation()
    return metadata


def apply_review_filter(
    images: list[dict[str, Any]],
    service: AnnotationReviewService,
    store: AnnotationReviewStore,
    *,
    warnings_only: bool,
    check_cancellation: Callable[[], None] | None = None,
) -> list[dict[str, Any]]:
    """Annotate the entire candidate set before thumbnail pagination."""
    metadata = load_review_metadata([image["id"] for image in images], service, store, check_cancellation)
    enriched = [{**image, **metadata[image["id"]]} for image in images]
    if warnings_only:
        return [image for image in enriched if image["annotation_review_warning_count"] > 0]
    return enriched
