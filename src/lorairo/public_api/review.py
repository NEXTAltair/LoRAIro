"""Clef evaluation of existing project annotations; results are saved only on request."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from sqlalchemy.exc import SQLAlchemyError

from lorairo.public_api.exceptions import ImageNotFoundError, InvalidInputError, ResultSetTooLargeError

if TYPE_CHECKING:
    from lorairo.services.annotation_review_service import AnnotationReviewResult, ReviewSnapshot
    from lorairo.services.annotation_review_store import AnnotationReviewStore
    from lorairo.services.service_container import ServiceContainer

MAX_REVIEW_IMAGES = 500
_VALIDATION_CHUNK_SIZE = 500
_STOP_REVIEW_ERROR_CODES = frozenset({"configuration", "transport", "timeout"})

ReviewSaveStatus = Literal["saved", "skipped", "failed"]


@dataclass(frozen=True)
class ReviewSaveOutcome:
    """Per-image persistence outcome of ``review_annotations(save_results=True)``.

    ``skipped`` means the store kept a newer result or an empty cancellation had
    nothing to save; it is not a failure. ``failed`` carries a safe message.
    """

    image_id: int
    status: ReviewSaveStatus
    error: str | None = None


@contextmanager
def _project_context(project_name: str, *, read_only: bool = True) -> Iterator[ServiceContainer]:
    """Open only an existing project; read-only mode never prepares or changes it.

    ``read_only=False`` is used only for explicit result saving (#1603) and opens
    the project like other write commands.
    """
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
        Path.cwd(), DEFAULT_CONFIG_PATH, get_config()
    )
    with ExitStack() as stack:
        stack.enter_context(runtime_configuration_scope(configuration))
        if read_only:
            stack.enter_context(read_only_scope())
        container = stack.enter_context(service_container_scope())
        container.set_active_project(project_name)
        yield container


def _validate_image_ids(image_ids: list[int]) -> list[int]:
    if not image_ids or any(type(image_id) is not int or image_id <= 0 for image_id in image_ids):
        raise InvalidInputError("image_ids", "Specify a nonempty set of positive integer image IDs.")
    unique_ids = list(dict.fromkeys(image_ids))
    if len(unique_ids) > MAX_REVIEW_IMAGES:
        raise ResultSetTooLargeError(len(unique_ids), MAX_REVIEW_IMAGES)
    return unique_ids


def resolve_crop_child_image_ids(project_name: str, parent_image_id: int | None = None) -> list[int]:
    """Resolve crop child image IDs from ``crop_relations`` without changing the DB.

    ``parent_image_id=None`` selects every crop child. The working-set cap is
    left to ``review_annotations`` so the resolved set is reviewed unchanged.

    Raises:
        InvalidInputError: ``parent_image_id`` is not a positive integer.
        ImageNotFoundError: The parent image does not exist.
    """
    if parent_image_id is not None and (type(parent_image_id) is not int or parent_image_id <= 0):
        raise InvalidInputError("parent_image_id", "Specify a positive integer parent image ID.")
    from lorairo.services.crop_review_targets import resolve_crop_child_image_ids as resolve

    with _project_context(project_name) as container:
        return resolve(container.db_manager, parent_image_id)


def review_annotations(
    project_name: str,
    image_ids: list[int],
    *,
    on_result: Callable[[AnnotationReviewResult], None] | None = None,
    collect_results: bool = True,
    is_cancelled: Callable[[], bool] | None = None,
    save_results: bool = False,
    on_saved: Callable[[ReviewSaveOutcome], None] | None = None,
) -> list[AnnotationReviewResult]:
    """Evaluate saved tags and captions, without modifying annotations.

    The DB is unchanged unless ``save_results=True``. Then each image result is
    saved independently to ``annotation_review_results`` with the GUI's store
    (fingerprint, atomic upsert by request time), and ``on_saved`` receives the
    outcome before ``on_result``. A save failure is image-scoped and does not stop
    the run; tags, captions, images and reject state are never changed.

    At most 500 unique images may be reviewed per call; this cap is checked before
    opening the project. The complete explicit ID selection is validated before
    starting local inference.
    Duplicate IDs are reviewed once, in first-occurrence order. Empty active
    annotations retain the service's ``unevaluated`` result and make no request.
    Per-image failures do not discard successful results from other images.
    Fatal runtime failures stop inference; remaining images are reported unevaluated.

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
    requested_at = datetime.now(UTC)
    context = (
        _project_context(project_name, read_only=False) if save_results else _project_context(project_name)
    )
    with context as container:
        _require_existing_images(container, selected)
        service = AnnotationReviewService(container.config_service, container.db_manager)
        store = _open_review_store(container) if save_results else None
        blocked_error: AnnotationReviewResult | None = None
        for image_id in selected:
            snapshot: ReviewSnapshot | None = None
            try:
                snapshot = service.prepare_review(image_id)
                if blocked_error is not None:
                    result = AnnotationReviewResult(
                        image_id=image_id,
                        fingerprint=snapshot.fingerprint,
                        model_name=service.model_name,
                        items=tuple(
                            AnnotationReviewItem(
                                item.candidate_id, item.kind, item.text, None, "unevaluated"
                            )
                            for item in snapshot.tags + snapshot.captions + snapshot.suggestions
                        ),
                        status="unevaluated",
                        error=blocked_error.error,
                        error_code=blocked_error.error_code,
                        candidate_source=snapshot.candidate_source,
                        suggestion_threshold=blocked_error.suggestion_threshold,
                    )
                else:
                    result = service.review(snapshot, is_cancelled=is_cancelled)
                    if result.error_code in _STOP_REVIEW_ERROR_CODES:
                        blocked_error = result
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
            if store is not None:
                _save_review(store, result, service.warning_threshold, requested_at, on_saved)
            if collect_results:
                results.append(result)
            if on_result is not None:
                on_result(result)
    return results


def _require_existing_images(container: ServiceContainer, selected: list[int]) -> None:
    """Validate the complete selection before any inference starts."""
    repository = container.db_manager.image_repo
    for start in range(0, len(selected), _VALIDATION_CHUNK_SIZE):
        chunk = selected[start : start + _VALIDATION_CHUNK_SIZE]
        existing = set(repository.get_candidate_image_ids(chunk))
        missing = [image_id for image_id in chunk if image_id not in existing]
        if missing:
            raise ImageNotFoundError(missing[0])


def _open_review_store(container: ServiceContainer) -> AnnotationReviewStore:
    from lorairo.services.annotation_review_store import AnnotationReviewStore

    return AnnotationReviewStore(container.db_manager)


def _save_review(
    store: AnnotationReviewStore,
    review: AnnotationReviewResult,
    warning_threshold: float,
    requested_at: datetime,
    on_saved: Callable[[ReviewSaveOutcome], None] | None,
) -> None:
    """Save one image like the GUI batch worker and report it; failures stay image-scoped."""
    outcome = _store_review(store, review, warning_threshold, requested_at)
    if on_saved is not None:
        on_saved(outcome)


def _store_review(
    store: AnnotationReviewStore,
    review: AnnotationReviewResult,
    warning_threshold: float,
    requested_at: datetime,
) -> ReviewSaveOutcome:
    from lorairo.services.annotation_review_store import AnnotationReviewImageMissingError
    from lorairo.utils.log import logger

    try:
        saved = store.save(review, warning_threshold, requested_at=requested_at)
    except AnnotationReviewImageMissingError:
        return ReviewSaveOutcome(
            review.image_id, "failed", "The image was removed before its review result could be saved."
        )
    except (SQLAlchemyError, OSError, ValueError, TypeError) as error:
        # DB ロック等の詳細はログのみに残し、利用者向けの文言には含めない。
        logger.warning("Annotation review save failed for image {}: {}", review.image_id, error)
        return ReviewSaveOutcome(
            review.image_id, "failed", f"Could not save the review result ({type(error).__name__})."
        )
    return ReviewSaveOutcome(review.image_id, "saved" if saved else "skipped")
