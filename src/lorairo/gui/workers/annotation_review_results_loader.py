"""Load bounded saved Clef results and check freshness away from the GUI thread."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .base import LoRAIroWorkerBase

if TYPE_CHECKING:
    from ...services.annotation_review_service import AnnotationReviewService
    from ...services.annotation_review_store import AnnotationReviewStore, StoredReviewResult


@dataclass(frozen=True)
class AnnotationReviewResultsLoaded:
    generation: int
    revision: int
    results: dict[int, StoredReviewResult]


class AnnotationReviewResultsLoader(LoRAIroWorkerBase[AnnotationReviewResultsLoaded]):
    """Freshness only: this worker never calls the Cloudflare review API."""

    _OPERATION_TYPE = "annotation_review_results_load"

    def __init__(
        self,
        service: AnnotationReviewService,
        store: AnnotationReviewStore,
        generation: int,
        revision: int,
        limit: int,
    ) -> None:
        super().__init__()
        self._service = service
        self._store = store
        self._generation = generation
        self._revision = revision
        self._limit = limit

    def execute(self) -> AnnotationReviewResultsLoaded:
        self._check_cancellation()
        results = self._store.get_current_results(self._service, limit=self._limit)
        self._check_cancellation()
        return AnnotationReviewResultsLoaded(self._generation, self._revision, results)
