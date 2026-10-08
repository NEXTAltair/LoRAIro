"""Review a fixed batch in the background and save each finished image."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, ClassVar

from PySide6.QtCore import Signal

from lorairo.services.annotation_review_service import AnnotationReviewItem, AnnotationReviewResult
from lorairo.services.annotation_review_store import AnnotationReviewImageMissingError, StoredReviewResult

from .base import LoRAIroWorkerBase

if TYPE_CHECKING:
    from lorairo.services.annotation_review_service import AnnotationReviewService, ReviewCandidateSource
    from lorairo.services.annotation_review_store import AnnotationReviewStore


@dataclass(frozen=True)
class AnnotationReviewBatchImageResult:
    """Associate one independently persisted result with the GUI generation."""

    generation: int
    review: AnnotationReviewResult
    saved: bool = True
    stored: StoredReviewResult | None = None


@dataclass(frozen=True)
class AnnotationReviewBatchWorkerResult:
    """Report only processed images; unfinished targets never imply success."""

    generation: int
    image_ids: tuple[int, ...]
    reviews: tuple[AnnotationReviewResult, ...]
    cancelled: bool
    processed_count: int | None = None


class AnnotationReviewBatchWorker(LoRAIroWorkerBase[AnnotationReviewBatchWorkerResult]):
    """Freeze target IDs at construction and all source snapshots before HTTP."""

    _OPERATION_TYPE = "annotation_review"
    MAX_IMAGES: ClassVar[int] = 500
    _STOP_ERROR_CODES: ClassVar[frozenset[str]] = frozenset({"configuration", "transport", "timeout"})

    per_image_finished = Signal(AnnotationReviewBatchImageResult)

    def __init__(
        self,
        service: AnnotationReviewService,
        store: AnnotationReviewStore,
        image_ids: Sequence[int],
        generation: int,
        *,
        candidate_source: ReviewCandidateSource | None = None,
    ) -> None:
        super().__init__()
        targets: dict[int, None] = {}
        for image_id in image_ids:
            if isinstance(image_id, bool) or not isinstance(image_id, int) or image_id <= 0:
                raise ValueError("Review targets must be positive image IDs")
            targets[image_id] = None
            if len(targets) > self.MAX_IMAGES:
                raise ValueError(f"At most {self.MAX_IMAGES} images can be reviewed in one batch")
        if not targets:
            raise ValueError("Choose at least one image for annotation review")
        self._service = service
        self._store = store
        self._image_ids = tuple(targets)
        self._generation = generation
        self._candidate_source = candidate_source
        self._requested_at = datetime.now(UTC)

    def execute(self) -> AnnotationReviewBatchWorkerResult:
        """Preflight all images, then evaluate sequentially with cooperative cancellation."""
        reviews: list[AnnotationReviewResult] = []
        processed_count = 0
        self._report_progress(
            0, "確認する画像とアノテーションを準備しています", total_count=len(self._image_ids)
        )
        if self._candidate_source is None:
            snapshots = self._service.prepare_reviews(
                self._image_ids, is_cancelled=self.cancellation.is_canceled
            )
        else:
            snapshots = self._service.prepare_reviews(
                self._image_ids,
                is_cancelled=self.cancellation.is_canceled,
                candidate_source=self._candidate_source,
            )

        blocked_error: AnnotationReviewResult | None = None
        for image_id in self._image_ids:
            if self.cancellation.is_canceled():
                break
            prepared = snapshots[image_id]
            if isinstance(prepared, AnnotationReviewResult):
                review = prepared
            elif blocked_error is not None:
                review = AnnotationReviewResult(
                    image_id=prepared.image_id,
                    fingerprint=prepared.fingerprint,
                    model_name=self._service.model_name,
                    items=tuple(
                        AnnotationReviewItem(item.candidate_id, item.kind, item.text, None, "unevaluated")
                        for item in prepared.tags + prepared.captions + prepared.suggestions
                    ),
                    status="unevaluated",
                    error=blocked_error.error,
                    error_code=blocked_error.error_code,
                    candidate_source=prepared.candidate_source,
                    suggestion_threshold=blocked_error.suggestion_threshold,
                )
            else:
                self._report_progress(
                    int(processed_count / len(self._image_ids) * 100),
                    f"アノテーションチェック {processed_count + 1}/{len(self._image_ids)}画像を確認中",
                    str(image_id),
                    processed_count,
                    len(self._image_ids),
                )
                review = self._service.review(prepared, is_cancelled=self.cancellation.is_canceled)
                if review.error_code in self._STOP_ERROR_CODES:
                    blocked_error = review
            if review.status == "cancelled" and not any(
                item.probability is not None for item in review.items
            ):
                break
            processed_count += 1
            saved = True
            try:
                accepted = self._store.save(
                    review, self._service.warning_threshold, requested_at=self._requested_at
                )
                if not accepted:
                    self._report_processed(processed_count, review.image_id)
                    continue
            except AnnotationReviewImageMissingError:
                saved = False
                message = "Image was removed; annotation review result could not be saved."
                review = replace(
                    review,
                    items=tuple(
                        replace(item, probability=None, status="failed", error=message)
                        for item in review.items
                    ),
                    status="failed",
                    error=message,
                    error_code=None,
                )
            review, stored = self._load_current(review, saved)
            reviews.append(review)
            self.per_image_finished.emit(
                AnnotationReviewBatchImageResult(self._generation, review, saved, stored)
            )
            self._report_processed(processed_count, review.image_id)
        return self._result(reviews, processed_count)

    def _load_current(
        self, review: AnnotationReviewResult, saved: bool
    ) -> tuple[AnnotationReviewResult, StoredReviewResult | None]:
        if saved:
            current = self._store.get_current_result(review.image_id, self._service)
            if isinstance(current, StoredReviewResult):
                return current.review, current
        return review, None

    def _report_processed(self, processed_count: int, image_id: int) -> None:
        self._report_progress(
            int(processed_count / len(self._image_ids) * 100),
            f"アノテーションチェック {processed_count}/{len(self._image_ids)}画像",
            str(image_id),
            processed_count,
            len(self._image_ids),
        )
        self._report_batch_progress(processed_count, len(self._image_ids), str(image_id))

    def _result(
        self, reviews: list[AnnotationReviewResult], processed_count: int = 0
    ) -> AnnotationReviewBatchWorkerResult:
        return AnnotationReviewBatchWorkerResult(
            generation=self._generation,
            image_ids=self._image_ids,
            reviews=tuple(reviews),
            cancelled=self.cancellation.is_canceled(),
            processed_count=processed_count,
        )
