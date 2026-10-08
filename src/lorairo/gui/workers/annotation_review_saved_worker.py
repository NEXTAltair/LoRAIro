"""Read a selected image's saved check and freshness outside the GUI thread."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .base import LoRAIroWorkerBase

if TYPE_CHECKING:
    from ...services.annotation_review_service import AnnotationReviewService
    from ...services.annotation_review_store import AnnotationReviewStore, StoredReviewResult


@dataclass(frozen=True)
class SavedImageReview:
    generation: int
    image_id: int
    saved: StoredReviewResult | None


class SavedImageReviewWorker(LoRAIroWorkerBase[SavedImageReview]):
    _OPERATION_TYPE = "annotation_review_results_load"

    def __init__(
        self, service: AnnotationReviewService, store: AnnotationReviewStore, image_id: int, generation: int
    ) -> None:
        super().__init__()
        self._service = service
        self._store = store
        self._image_id = image_id
        self._generation = generation

    def execute(self) -> SavedImageReview:
        self._check_cancellation()
        saved = self._store.get_current_result(self._image_id, self._service)
        self._check_cancellation()
        return SavedImageReview(self._generation, self._image_id, saved)
