"""Reload saved thumbnail review statuses away from the GUI thread."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ...services.search_review_status import load_review_metadata
from .base import LoRAIroWorkerBase

if TYPE_CHECKING:
    from ...services.annotation_review_service import AnnotationReviewService
    from ...services.annotation_review_store import AnnotationReviewStore


@dataclass(frozen=True)
class SearchReviewMetadataLoaded:
    generation: int
    revisions: dict[int, int]
    metadata: dict[int, dict[str, Any]]


class SearchReviewLoader(LoRAIroWorkerBase[SearchReviewMetadataLoaded]):
    """Read durable results and local fingerprints; never call the Clef API."""

    _OPERATION_TYPE = "search_review_load"

    def __init__(
        self,
        service: AnnotationReviewService,
        store: AnnotationReviewStore,
        generation: int,
        revisions: dict[int, int],
    ) -> None:
        super().__init__()
        self._service = service
        self._store = store
        self._generation = generation
        self._revisions = revisions.copy()

    def execute(self) -> SearchReviewMetadataLoaded:
        metadata = load_review_metadata(
            tuple(self._revisions), self._service, self._store, self._check_cancellation
        )
        return SearchReviewMetadataLoaded(self._generation, self._revisions, metadata)
