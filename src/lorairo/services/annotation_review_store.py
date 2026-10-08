"""Persist per-image annotation review results separately from annotations."""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from typing import TYPE_CHECKING, cast

from sqlalchemy.exc import IntegrityError

from lorairo.database.repository.annotation_review import AnnotationReviewRepository, StoredAnnotationReview
from lorairo.services.annotation_review_service import (
    AnnotationReviewItem,
    AnnotationReviewResult,
    AnnotationReviewService,
    ReviewCandidateSource,
    ReviewSnapshot,
    ReviewStatus,
)

if TYPE_CHECKING:
    from lorairo.database.db_manager import ImageDatabaseManager


@dataclass(frozen=True)
class StoredReviewResult:
    """Retain the review settings and date used for a saved result."""

    review: AnnotationReviewResult
    warning_threshold: float
    checked_at: datetime
    suggestion_threshold: float = 0.8
    candidate_source: ReviewCandidateSource | None = None


class AnnotationReviewImageMissingError(ValueError):
    """An image was removed before its independently saved review could commit."""


class AnnotationReviewStore:
    """Save latest per-image reviews without editing tags, captions or ratings."""

    def __init__(self, db_manager: ImageDatabaseManager) -> None:
        self._repository = AnnotationReviewRepository(db_manager.image_repo.session_factory)

    def save(
        self,
        review: AnnotationReviewResult,
        warning_threshold: float,
        *,
        requested_at: datetime | None = None,
    ) -> bool:
        """Commit one image independently; empty cancellation preserves earlier results."""
        if review.status == "cancelled" and not any(item.probability is not None for item in review.items):
            return False
        try:
            return self._repository.save_result(
                image_id=review.image_id,
                fingerprint=review.fingerprint,
                model_name=review.model_name,
                warning_threshold=warning_threshold,
                status=review.status,
                items_json=json.dumps(
                    {
                        "items": [asdict(item) for item in review.items],
                        "error_code": review.error_code,
                        "candidate_source": asdict(review.candidate_source)
                        if review.candidate_source
                        else None,
                        "suggestion_threshold": review.suggestion_threshold,
                    },
                    ensure_ascii=False,
                    allow_nan=False,
                ),
                error=review.error,
                requested_at=requested_at,
            )
        except IntegrityError as error:
            if getattr(error.orig, "sqlite_errorname", None) == "SQLITE_CONSTRAINT_FOREIGNKEY":
                raise AnnotationReviewImageMissingError("The reviewed image no longer exists") from error
            raise

    def get_results(
        self, image_ids: Sequence[int] | None = None, *, limit: int | None = None
    ) -> dict[int, StoredReviewResult]:
        """Load durable results, retaining their original warning threshold."""
        return {
            image_id: self._restore(record)
            for image_id, record in self._repository.get_results(image_ids, limit=limit).items()
        }

    def get_current_result(
        self, image_id: int, service: AnnotationReviewService
    ) -> StoredReviewResult | None:
        """Return the stored image result with currentness checked for display."""
        return self.get_current_results(service, (image_id,)).get(image_id)

    def get_current_results(
        self,
        service: AnnotationReviewService,
        image_ids: Sequence[int] | None = None,
        *,
        limit: int | None = None,
    ) -> dict[int, StoredReviewResult]:
        """Mark changed sources or review settings stale without rewriting history."""
        results = self.get_results(image_ids, limit=limit)
        snapshots = service.prepare_reviews(
            tuple(image_id for image_id, stored in results.items() if stored.review.fingerprint)
        )
        for image_id, stored in results.items():
            review = stored.review
            current = (
                review.model_name == service.model_name
                and stored.warning_threshold == service.warning_threshold
            )
            if any(item.kind == "suggestion" for item in review.items):
                current = current and stored.suggestion_threshold == service.suggestion_threshold
            # Preparation failures have no source fingerprint to compare. Keep
            # their actionable error rather than disguising it as a stale score.
            if current and not review.fingerprint and review.status == "failed":
                continue
            if current:
                snapshot = snapshots.get(image_id)
                current = (
                    isinstance(snapshot, ReviewSnapshot) and snapshot.fingerprint == review.fingerprint
                )
            if not current:
                items = tuple(
                    replace(item, probability=None, status="unevaluated", error=None)
                    for item in review.items
                )
                results[image_id] = replace(
                    stored,
                    review=replace(
                        review,
                        items=items,
                        status="stale",
                        error="Image, annotations or review settings changed; run review again.",
                        error_code=None,
                    ),
                )
        return results

    @staticmethod
    def _restore(record: StoredAnnotationReview) -> StoredReviewResult:
        suggestion_threshold = 0.8
        candidate_source = None
        try:
            payload = json.loads(record.items_json)
            if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
                raise ValueError("Invalid review payload")
            error_code = payload.get("error_code")
            if error_code is not None and not isinstance(error_code, str):
                raise ValueError("Invalid review error code")
            statuses = {"completed", "partial", "failed", "cancelled", "unevaluated", "stale"}
            if record.status not in statuses:
                raise ValueError("Invalid review status")
            suggestion_threshold = AnnotationReviewStore._restore_threshold(
                payload.get("suggestion_threshold", 0.8)
            )
            warning_threshold = AnnotationReviewStore._restore_threshold(record.warning_threshold)
            source = payload.get("candidate_source")
            if source is not None:
                if not isinstance(source, dict):
                    raise ValueError("Invalid candidate source")
                candidate_source = ReviewCandidateSource(**source)
            items = tuple(
                AnnotationReviewStore._restore_item(item, warning_threshold, suggestion_threshold)
                for item in payload["items"]
            )
            if any(item.kind == "suggestion" for item in items) and (
                candidate_source is None or not (candidate_source.keyword or candidate_source.selected_tags)
            ):
                raise ValueError("Suggestions require an explicit candidate source")
            if len({item.candidate_id for item in items}) != len(items):
                raise ValueError("Duplicate review candidate")
            review = AnnotationReviewResult(
                image_id=record.image_id,
                fingerprint=record.fingerprint,
                model_name=record.model_name,
                items=items,
                status=cast(ReviewStatus, record.status),
                error=record.error,
                error_code=error_code,
                candidate_source=candidate_source,
                suggestion_threshold=suggestion_threshold,
            )
        except (TypeError, ValueError, RecursionError):
            review = AnnotationReviewResult(
                image_id=record.image_id,
                fingerprint=record.fingerprint,
                model_name=record.model_name,
                items=(),
                status="failed",
                error="Saved annotation review result could not be read; run review again.",
            )
        return StoredReviewResult(
            review, record.warning_threshold, record.checked_at, suggestion_threshold, candidate_source
        )

    @staticmethod
    def _restore_threshold(value: object) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Invalid saved review threshold")
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("Invalid saved review threshold")
        return float(value)

    @staticmethod
    def _restore_item(
        value: object, warning_threshold: float = 0.2, suggestion_threshold: float = 0.8
    ) -> AnnotationReviewItem:
        if not isinstance(value, dict):
            raise ValueError("Invalid review item")
        candidate_id = value.get("candidate_id")
        kind = value.get("kind")
        text = value.get("text")
        probability = value.get("probability")
        status = value.get("status")
        error = value.get("error")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise ValueError("Invalid review candidate ID")
        if kind not in ("tag", "caption", "suggestion") or not isinstance(text, str) or not text.strip():
            raise ValueError("Invalid review candidate")
        if status not in ("ok", "warning", "suggestion", "failed", "unevaluated"):
            raise ValueError("Invalid review item status")
        if probability is not None:
            probability = AnnotationReviewStore._restore_threshold(probability)
        if (status in ("ok", "warning", "suggestion")) != (probability is not None):
            raise ValueError("Review item status contradicts probability")
        if probability is not None:
            expected_status = (
                ("suggestion" if probability >= suggestion_threshold else "ok")
                if kind == "suggestion"
                else ("warning" if probability < warning_threshold else "ok")
            )
            if status != expected_status:
                raise ValueError("Review item kind, threshold and probability contradict status")
        if error is not None and not isinstance(error, str):
            raise ValueError("Invalid review item error")
        return AnnotationReviewItem(candidate_id, kind, text, probability, status, error)
