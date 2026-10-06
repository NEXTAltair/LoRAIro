"""Read-only Clef evaluation of existing project annotations."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.exc import SQLAlchemyError

from lorairo.public_api.exceptions import ImageNotFoundError, InvalidInputError

if TYPE_CHECKING:
    from lorairo.services.annotation_review_service import AnnotationReviewResult, ReviewSnapshot
    from lorairo.services.service_container import ServiceContainer

_MAX_REVIEW_IMAGES = 100_000
_VALIDATION_CHUNK_SIZE = 500


@contextmanager
def _project_context(project_name: str) -> Iterator[ServiceContainer]:
    """Open only an existing compatible project, without preparing or changing it."""
    from lorairo.database.access_policy import read_only_scope
    from lorairo.services.service_container import service_container_scope
    from lorairo.utils.config import (
        DEFAULT_CONFIG_PATH,
        RuntimeConfiguration,
        get_config,
        get_runtime_configuration,
        runtime_configuration_scope,
    )

    configuration = get_runtime_configuration() or RuntimeConfiguration(
        Path.cwd(), DEFAULT_CONFIG_PATH, get_config(DEFAULT_CONFIG_PATH)
    )
    with (
        runtime_configuration_scope(configuration),
        read_only_scope(),
        service_container_scope() as container,
    ):
        container.set_active_project(project_name)
        yield container


def _validate_image_ids(image_ids: list[int]) -> list[int]:
    if not image_ids or any(type(image_id) is not int or image_id <= 0 for image_id in image_ids):
        raise InvalidInputError("image_ids", "Specify a nonempty set of positive integer image IDs.")
    unique_ids = list(dict.fromkeys(image_ids))
    if len(unique_ids) > _MAX_REVIEW_IMAGES:
        raise InvalidInputError("image_ids", f"At most {_MAX_REVIEW_IMAGES:,} images may be reviewed.")
    return unique_ids


def review_annotations(
    project_name: str,
    image_ids: list[int],
    *,
    on_result: Callable[[AnnotationReviewResult], None] | None = None,
    collect_results: bool = True,
    is_cancelled: Callable[[], bool] | None = None,
) -> list[AnnotationReviewResult]:
    """Evaluate saved tags and captions, without modifying annotations or the DB.

    The complete explicit image selection is checked before any paid request.
    Duplicate IDs are reviewed once, in first-occurrence order. Empty active
    annotations retain the service's ``unevaluated`` result and make no request.
    Per-image failures do not discard successful results from other images.

    ``on_result`` receives each result immediately. Set ``collect_results=False``
    to stream large selections without retaining their complete candidate output.
    Cancellation is passed to the service and preserves per-image outcome rows.
    """
    selected = _validate_image_ids(image_ids)
    from lorairo.services.annotation_review_service import (
        AnnotationReviewItem,
        AnnotationReviewResult,
        AnnotationReviewService,
    )

    results: list[AnnotationReviewResult] = []
    with _project_context(project_name) as container:
        repository = container.db_manager.image_repo
        for start in range(0, len(selected), _VALIDATION_CHUNK_SIZE):
            chunk = selected[start : start + _VALIDATION_CHUNK_SIZE]
            existing = set(repository.get_candidate_image_ids(chunk))
            missing = [image_id for image_id in chunk if image_id not in existing]
            if missing:
                raise ImageNotFoundError(missing[0])

        service = AnnotationReviewService(container.config_service, container.db_manager)
        for image_id in selected:
            snapshot: ReviewSnapshot | None = None
            try:
                snapshot = service.prepare_review(image_id)
                result = service.review(snapshot, is_cancelled=is_cancelled)
            except (ValueError, OSError, SQLAlchemyError) as exc:
                # Snapshot errors (missing files, concurrently removed images)
                # remain image-scoped instead of hiding preceding results.
                message = f"Could not prepare or evaluate this image ({type(exc).__name__})."
                candidates = snapshot.tags + snapshot.captions if snapshot is not None else ()
                result = AnnotationReviewResult(
                    image_id=image_id,
                    fingerprint=snapshot.fingerprint if snapshot is not None else "",
                    model_name=service.model_name,
                    items=tuple(
                        AnnotationReviewItem(
                            candidate.candidate_id, candidate.kind, candidate.text, None, "failed", message
                        )
                        for candidate in candidates
                    ),
                    status="failed",
                    error=message,
                )
            if collect_results:
                results.append(result)
            if on_result is not None:
                on_result(result)
    return results
