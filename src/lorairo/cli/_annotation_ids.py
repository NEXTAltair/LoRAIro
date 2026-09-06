"""Bounded exact-ID annotation path; outcome rows partition the requested input set."""

from typing import Any

import typer
from loguru import logger

from lorairo.cli._emit import emit_item, emit_result
from lorairo.cli._image_guard import reject_original_image_records
from lorairo.cli._image_ids import BULK_CHUNK_SIZE, validate_candidate_ids
from lorairo.cli._output_mode import is_json_mode
from lorairo.database.filter_criteria import ImageFilterCriteria


def _emit_outcome(image_id: int, status: str, *, reason: str | None = None, saved: bool = False) -> None:
    if is_json_mode():
        emit_item(
            {
                "type": "annotation_outcome",
                "image_id": image_id,
                "status": status,
                "reason": reason,
                "saved": saved,
            }
        )


def _select_ids(
    repo: Any, ids: list[int], criteria: ImageFilterCriteria, offset: int, limit: int | None
) -> list[int]:
    eligible: list[int] = []
    for start in range(0, len(ids), BULK_CHUNK_SIZE):
        eligible.extend(repo.get_candidate_image_ids(ids[start : start + BULK_CHUNK_SIZE], criteria))
    selected = sorted(set(eligible))[offset:]
    return selected if limit is None else selected[:limit]


def _validate_selection(repo: Any, selected: list[int], resolution: int | None) -> dict[int, str] | None:
    """Check originals for the complete selection before opening any inference model."""
    paths: dict[int, str] | None = {} if resolution is not None else None
    for start in range(0, len(selected), BULK_CHUNK_SIZE):
        chunk = selected[start : start + BULK_CHUNK_SIZE]
        if resolution is None:
            reject_original_image_records(repo.get_images_by_ids(chunk), command_name="annotate run")
        else:
            assert paths is not None
            paths.update(repo.get_processed_image_paths_by_resolution(chunk, resolution))
    return paths


def _annotate_chunk(
    container: Any,
    records: list[dict[str, Any]],
    models: list[str],
    preflight: Any,
    statuses: dict[int, str],
    counters: dict[str, int],
) -> None:
    from lorairo.cli.commands.annotate import (
        _annotation_value,
        _apply_moderation_preflight_to_records,
        _emit_annotation_items,
        _load_batch_images,
    )

    original_ids = {int(record["id"]) for record in records}
    if preflight is not None:
        records, _ = _apply_moderation_preflight_to_records(records, preflight)
        remaining = {int(record["id"]) for record in records}
        for image_id in original_ids - remaining:
            statuses[image_id] = "skipped"
            _emit_outcome(image_id, "skipped", reason="moderation preflight")
    images, loaded_records, loaded, failed = _load_batch_images(records)
    counters["loaded"] += loaded
    counters["load_failed"] += failed
    loaded_ids = {int(record["id"]) for record in loaded_records}
    for record in records:
        image_id = int(record["id"])
        if image_id not in loaded_ids:
            statuses[image_id] = "failed"
            _emit_outcome(image_id, "failed", reason="image load failed")
    if not images:
        return
    try:
        results = container.annotator_library.annotate(
            images, litellm_model_ids=models, phash_list=[str(record["phash"]) for record in loaded_records]
        )
        counters["results"] += len(results or {})
        save_result = container.annotation_save_service.save_annotation_results(
            results,
            allowed_image_ids=loaded_ids,
        )
        counters["saved"] += save_result.success_count
        per_id = getattr(save_result, "image_outcomes", {})
        # Compatibility with alternate save adapters returning only aggregate success.
        # Never attribute a partial aggregate success to an arbitrary subset of IDs.
        all_saved = save_result.success_count == len(loaded_ids) and not save_result.error_count
        for record in loaded_records:
            image_id = int(record["id"])
            model_results = (results or {}).get(str(record["phash"]), {})
            errors = [
                str(_annotation_value(value, "error"))
                for value in model_results.values()
                if _annotation_value(value, "error") is not None
            ]
            saved = per_id.get(image_id) == "success" or (not per_id and all_saved)
            status = "completed" if saved and not errors else "failed"
            if per_id.get(image_id) == "skipped" and not errors:
                status = "skipped"
            statuses[image_id] = status
            reason = "; ".join(errors) if errors else (None if saved else "No confirmed saved annotation")
            _emit_outcome(image_id, status, reason=reason, saved=saved)
        _emit_annotation_items(results, loaded_records)
    finally:
        for image in images:
            image.close()


def _make_preflight(container: Any, models: list[str]) -> Any:
    from lorairo.annotation.annotation_runner import AnnotationRunner
    from lorairo.cli.commands.annotate import (
        _get_deprecated_models_best_effort,
        _status_console,
        _validate_required_api_keys,
    )
    from lorairo.services.model_registry_protocol import selection_includes_webapi_model
    from lorairo.services.moderation_preflight_service import (
        ModerationPreflightService,
        build_annotation_runner_runner,
    )

    annotator = container.annotator_library
    config = container.config_service
    _validate_required_api_keys(container.db_manager.model_repo, config, models)
    for model in _get_deprecated_models_best_effort(annotator, models):
        _status_console().print(f"Warning: Model '{model}' is deprecated")
    preflight = None
    try:
        should_preflight = selection_includes_webapi_model(models, annotator)
    except Exception as exc:
        logger.opt(exception=True).warning(
            f"WebAPI model detection failed; moderation preflight skipped: {exc}"
        )
        should_preflight = False
    if should_preflight:
        preflight = ModerationPreflightService(
            image_repo=container.db_manager.image_repo,
            model_repo=container.db_manager.model_repo,
            error_record_repo=container.db_manager.error_record_repo,
            annotation_save_service=container.annotation_save_service,
            config_service=config,
            moderation_runner=build_annotation_runner_runner(
                AnnotationRunner(annotator).execute_annotation
            ),
        )
    return preflight


def _execute_ids(
    container: Any,
    active: list[int],
    paths: dict[int, str] | None,
    batch_size: int,
    models: list[str],
    statuses: dict[int, str],
    counters: dict[str, int],
) -> tuple[bool, str | None]:
    interrupted = False
    failure_reason = None
    current: list[int] = []
    preflight = _make_preflight(container, models)
    try:
        # Both DB metadata and PIL image lists remain bounded even with100,000 IDs.
        for start in range(0, len(active), min(batch_size, BULK_CHUNK_SIZE)):
            current = active[start : start + min(batch_size, BULK_CHUNK_SIZE)]
            records = container.db_manager.image_repo.get_images_by_ids(current)
            if {int(record["id"]) for record in records} != set(current):
                raise RuntimeError("Selected images changed after validation; no replacement images loaded")
            if paths is not None:
                for record in records:
                    record["stored_image_path"] = paths[int(record["id"])]
            _annotate_chunk(container, records, models, preflight, statuses, counters)
    except (Exception, KeyboardInterrupt) as exc:
        interrupted = isinstance(exc, KeyboardInterrupt)
        failure_reason = str(exc) or type(exc).__name__
        for image_id in current:
            if image_id not in statuses:
                statuses[image_id] = "failed"
                _emit_outcome(image_id, "failed", reason=failure_reason)
    return interrupted, failure_reason


def run_id_annotation(
    container: Any,
    *,
    image_ids: list[int],
    file_input: bool,
    project: str,
    criteria: ImageFilterCriteria,
    offset: int,
    limit: int | None,
    resolution: int | None,
    batch_size: int,
    models: list[str],
) -> None:
    from lorairo.cli.commands.annotate import (
        MAX_ANNOTATE_IMAGES,
        AnnotationSelectionError,
        _status_console,
    )
    from lorairo.public_api.exceptions import ResultSetTooLargeError

    repo = container.db_manager.image_repo
    image_ids = validate_candidate_ids(repo, image_ids)
    selected = _select_ids(repo, image_ids, criteria, offset, limit)
    if not file_input and len(selected) > MAX_ANNOTATE_IMAGES:
        raise ResultSetTooLargeError(len(selected), MAX_ANNOTATE_IMAGES)
    if not selected:
        raise AnnotationSelectionError("No images selected for annotation")
    paths = _validate_selection(repo, selected, resolution)
    statuses: dict[int, str] = {}
    selected_set = set(selected)
    for image_id in image_ids:
        reason = (
            "filter or offset/limit"
            if image_id not in selected_set
            else (
                "no processed image at requested resolution"
                if paths is not None and image_id not in paths
                else None
            )
        )
        if reason is not None:
            statuses[image_id] = "skipped"
            _emit_outcome(image_id, "skipped", reason=reason)
    active = [image_id for image_id in selected if image_id not in statuses]
    counters = {"saved": 0, "loaded": 0, "load_failed": 0, "results": 0}
    interrupted = False
    failure_reason = None
    if active:
        interrupted, failure_reason = _execute_ids(
            container, active, paths, batch_size, models, statuses, counters
        )
    for image_id in image_ids:
        if image_id not in statuses:
            statuses[image_id] = "unexecuted"
            _emit_outcome(image_id, "unexecuted", reason=failure_reason)
    counts = {
        status: sum(value == status for value in statuses.values())
        for status in ("completed", "failed", "skipped", "unexecuted")
    }
    unsuccessful = bool(counts["failed"] or counts["unexecuted"] or not active)
    status = "success" if not unsuccessful else "partial_success" if counts["completed"] else "failed"
    if is_json_mode():
        emit_result(
            f"Annotated {counters['saved']} image(s)",
            ok=not unsuccessful,
            status=status,
            project=project,
            total=len(image_ids),
            annotated=counters["saved"],
            skipped=counts["skipped"],
            errors=counts["failed"],
            completed=counts["completed"],
            unexecuted=counts["unexecuted"],
            loaded=counters["loaded"],
            results=counters["results"],
            models=models,
            interrupted=interrupted,
            reason=failure_reason,
        )
    else:
        _status_console().print(f"Annotation {status}: {counts}; saved={counters['saved']}")
    if unsuccessful:
        raise typer.Exit(1)
