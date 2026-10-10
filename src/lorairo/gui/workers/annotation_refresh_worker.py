"""Annotation cache refresh queries, without GUI state or shared DB sessions."""

from typing import Any, Protocol

from .base import LoRAIroWorkerBase


class AnnotationRefreshRepository(Protocol):
    """The repository owns each query's session in the calling worker thread."""

    def find_image_ids_by_phashes_multi(self, phashes: set[str]) -> dict[str, list[int]]: ...

    def get_image_annotation_metadata(self, image_id: int) -> dict[str, Any] | None: ...


class AnnotationRefreshLookupWorker(LoRAIroWorkerBase[dict[str, list[int]]]):
    """Resolve every image version for the completed execution's pHashes."""

    def __init__(self, repository: AnnotationRefreshRepository, phashes: set[str]) -> None:
        super().__init__()
        self._repository = repository
        self._phashes = phashes.copy()

    def execute(self) -> dict[str, list[int]]:
        self._check_cancellation()
        result = self._repository.find_image_ids_by_phashes_multi(self._phashes)
        self._check_cancellation()
        return result


class AnnotationRefreshLoadWorker(LoRAIroWorkerBase[dict[str, Any] | None]):
    """Fetch annotations for one displayed, invalidated image only."""

    def __init__(self, repository: AnnotationRefreshRepository, image_id: int) -> None:
        super().__init__()
        self._repository = repository
        self._image_id = image_id

    def execute(self) -> dict[str, Any] | None:
        self._check_cancellation()
        result = self._repository.get_image_annotation_metadata(self._image_id)
        self._check_cancellation()
        return result
