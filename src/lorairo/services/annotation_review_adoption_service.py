"""Explicitly adopt a current saved suggestion through the manual-tag path."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lorairo.database.db_manager import ImageDatabaseManager
    from lorairo.services.annotation_review_service import AnnotationReviewService
    from lorairo.services.annotation_review_store import AnnotationReviewStore


class AnnotationReviewAdoptionService:
    """Validate the latest durable review before any annotation mutation."""

    def __init__(
        self,
        db_manager: ImageDatabaseManager,
        review_service: AnnotationReviewService,
        store: AnnotationReviewStore,
    ) -> None:
        self._db_manager = db_manager
        self._review_service = review_service
        self._store = store

    def adopt(self, image_id: int, candidate_id: str, expected_checked_at: datetime) -> bool:
        """Add an eligible suggestion; obsolete UI results can never select a newer row."""
        if (
            isinstance(image_id, bool)
            or not isinstance(image_id, int)
            or image_id <= 0
            or not isinstance(candidate_id, str)
            or not isinstance(expected_checked_at, datetime)
            or expected_checked_at.tzinfo is None
            or expected_checked_at.utcoffset() is None
        ):
            return False
        stored = self._store.get_current_result(image_id, self._review_service)
        if stored is None or stored.checked_at != expected_checked_at:
            return False
        review = stored.review
        source = stored.candidate_source
        if (
            review.image_id != image_id
            or review.status not in ("completed", "partial", "cancelled")
            or not review.fingerprint
            or review.model_name != self._review_service.model_name
            or stored.warning_threshold != self._review_service.warning_threshold
            or stored.suggestion_threshold != self._review_service.suggestion_threshold
            or source is None
            or not (source.keyword or source.selected_tags)
        ):
            return False
        candidate = next((item for item in review.items if item.candidate_id == candidate_id), None)
        if (
            candidate is None
            or candidate.kind != "suggestion"
            or candidate.status != "suggestion"
            or candidate.probability is None
            or not stored.suggestion_threshold <= candidate.probability <= 1
        ):
            return False
        tag = candidate.text.strip().lower()
        if (
            not tag
            or candidate.candidate_id != "suggestion_" + hashlib.sha256(tag.encode("utf-8")).hexdigest()
        ):
            return False
        # This centralized path supplies manual provenance and handles duplicates.
        # Clef probability is deliberately never copied into tag confidence.
        return self._db_manager.add_manual_tag(image_id, tag)
