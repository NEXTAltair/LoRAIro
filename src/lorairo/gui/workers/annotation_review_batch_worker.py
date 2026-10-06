"""Review a fixed batch in the background and save each finished image."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, ClassVar

from PySide6.QtCore import Signal

from lorairo.services.annotation_review_service import AnnotationReviewItem, AnnotationReviewResult
from lorairo.services.annotation_review_store import AnnotationReviewImageMissingError

from .base import LoRAIroWorkerBase

if TYPE_CHECKING:
    from lorairo.services.annotation_review_service import AnnotationReviewService
    from lorairo.services.annotation_review_store import AnnotationReviewStore


@dataclass(frozen=True)
class AnnotationReviewBatchImageResult:
    """Associate one independently persisted result with the GUI generation."""

    generation: int
    review: AnnotationReviewResult
    saved: bool = True


@dataclass(frozen=True)
class AnnotationReviewBatchWorkerResult:
    """Report only processed images; unfinished targets never imply success."""

    generation: int
    image_ids: tuple[int, ...]
    reviews: tuple[AnnotationReviewResult, ...]
    cancelled: bool


class AnnotationReviewBatchWorker(LoRAIroWorkerBase[AnnotationReviewBatchWorkerResult]):
    """Freeze target IDs at construction and all source snapshots before HTTP."""

    _OPERATION_TYPE = "annotation_review"
    MAX_IMAGES: ClassVar[int] = 500
    _STOP_ERROR_CODES: ClassVar[frozenset[str]] = frozenset(
        {"configuration", "authentication", "rate_limit"}
    )

    per_image_finished = Signal(AnnotationReviewBatchImageResult)

    def __init__(
        self,
        service: AnnotationReviewService,
        store: AnnotationReviewStore,
        image_ids: Sequence[int],
        generation: int,
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

    def execute(self) -> AnnotationReviewBatchWorkerResult:
        """Preflight all images, then evaluate sequentially with cooperative cancellation."""
        reviews: list[AnnotationReviewResult] = []
        self._report_progress(
            0, "確認する画像とアノテーションを準備しています", total_count=len(self._image_ids)
        )
        snapshots = self._service.prepare_reviews(
            self._image_ids, is_cancelled=self.cancellation.is_canceled
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
                        for item in prepared.tags + prepared.captions
                    ),
                    status="unevaluated",
                    error=blocked_error.error,
                    error_code=blocked_error.error_code,
                )
            else:
                review = self._service.review(prepared, is_cancelled=self.cancellation.is_canceled)
                if review.error_code in self._STOP_ERROR_CODES:
                    blocked_error = review
            if review.status == "cancelled" and not any(
                item.probability is not None for item in review.items
            ):
                break
            saved = True
            try:
                self._store.save(review, self._service.warning_threshold)
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
            reviews.append(review)
            self.per_image_finished.emit(AnnotationReviewBatchImageResult(self._generation, review, saved))
            completed = len(reviews)
            self._report_progress(
                int(completed / len(self._image_ids) * 100),
                f"アノテーション確認 {completed}/{len(self._image_ids)}画像",
                str(review.image_id),
                completed,
                len(self._image_ids),
            )
            self._report_batch_progress(completed, len(self._image_ids), str(review.image_id))
        return self._result(reviews)

    def _result(self, reviews: list[AnnotationReviewResult]) -> AnnotationReviewBatchWorkerResult:
        return AnnotationReviewBatchWorkerResult(
            generation=self._generation,
            image_ids=self._image_ids,
            reviews=tuple(reviews),
            cancelled=self.cancellation.is_canceled(),
        )
