"""Explicit annotation review without blocking the image details panel."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .base import LoRAIroWorkerBase

if TYPE_CHECKING:
    from ...services.annotation_review_service import AnnotationReviewResult, AnnotationReviewService
    from ...services.annotation_review_store import AnnotationReviewStore


@dataclass(frozen=True)
class AnnotationReviewWorkerResult:
    """Carry the GUI generation with the service's immutable review result."""

    generation: int
    review: AnnotationReviewResult


class AnnotationReviewWorker(LoRAIroWorkerBase[AnnotationReviewWorkerResult]):
    """Read a snapshot and evaluate it only after an explicit user request."""

    _OPERATION_TYPE = "annotation_review"

    def __init__(
        self,
        service: AnnotationReviewService,
        image_id: int,
        generation: int,
        *,
        store: AnnotationReviewStore | None = None,
    ) -> None:
        super().__init__()
        self._service = service
        self._image_id = image_id
        self._generation = generation
        self._store = store

    def execute(self) -> AnnotationReviewWorkerResult:
        self._check_cancellation()
        snapshot = self._service.prepare_review(self._image_id)
        self._check_cancellation()
        review = self._service.review(snapshot, is_cancelled=self.cancellation.is_canceled)
        if self._store is not None:
            self._store.save(review, self._service.warning_threshold)
        return AnnotationReviewWorkerResult(generation=self._generation, review=review)
