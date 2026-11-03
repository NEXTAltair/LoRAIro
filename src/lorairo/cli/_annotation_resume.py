"""Opt-in durable annotation execution using fixed IDs and conservative retry semantics."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click
import typer

from lorairo.cli._annotation_ids import _emit_outcome, _make_preflight, _select_ids, _validate_selection
from lorairo.cli._emit import emit_result
from lorairo.cli._errors import result_exit_code
from lorairo.cli._image_ids import BULK_CHUNK_SIZE, validate_candidate_ids
from lorairo.cli._output_mode import is_json_mode
from lorairo.database.db_core import resolve_stored_path
from lorairo.database.filter_criteria import ImageFilterCriteria
from lorairo.services.annotation_run_ledger import (
    AnnotationRunLedger,
    configuration_digest,
    database_identity,
    image_identity,
)


def _configuration_binding(container: Any, models: list[str]) -> str:
    from image_annotator_lib.core.config import config_registry

    from lorairo.services.moderation_preflight_service import MODERATION_LITELLM_MODEL_ID

    library_settings = config_registry.get_all_config()
    if not isinstance(library_settings, dict):
        raise ValueError("Cannot read annotation model settings for durable run validation")
    # Include implicit moderation configuration, but not unrelated model cache entries.
    selected_settings = {
        model: library_settings.get(model, {}) for model in [*models, MODERATION_LITELLM_MODEL_ID]
    }
    return configuration_digest(
        {"application": container.config_service.get_all_settings(), "models": selected_settings}
    )


def _records_with_identity(
    repo: Any, selected: list[int], resolution: int | None
) -> tuple[list[dict[str, Any]], dict[int, str]]:
    paths = _validate_selection(repo, selected, resolution)
    snapshots = []
    for start in range(0, len(selected), BULK_CHUNK_SIZE):
        ids = selected[start : start + BULK_CHUNK_SIZE]
        records = repo.get_images_by_ids(ids)
        if {int(record["id"]) for record in records} != set(ids):
            raise ValueError("Run images are missing from this project; refusing to change the selection")
        for record in records:
            image_id = int(record["id"])
            skipped = paths is not None and image_id not in paths
            if paths is not None and not skipped:
                record = {**record, "stored_image_path": paths[image_id]}
            path = None if skipped else resolve_stored_path(record["stored_image_path"])
            snapshots.append(
                {
                    "image_id": image_id,
                    "identity": image_identity(record, path),
                    "state": "skipped" if skipped else "pending",
                    "reason": "no processed image at requested resolution" if skipped else None,
                }
            )
    return snapshots, paths or {}


def _select_new_run(
    repo: Any,
    image_ids: list[int] | None,
    criteria: ImageFilterCriteria,
    offset: int,
    limit: int | None,
    *,
    file_input: bool,
) -> list[int]:
    from lorairo.cli.commands.annotate import MAX_ANNOTATE_IMAGES, _select_image_records
    from lorairo.public_api.exceptions import ResultSetTooLargeError

    if image_ids:
        selected = _select_ids(repo, validate_candidate_ids(repo, image_ids), criteria, offset, limit)
    else:
        records, _ = repo.get_images_by_filter(criteria)
        selected = [
            int(row["id"])
            for row in _select_image_records(records, limit=limit, offset=offset, image_ids=None)
        ]
    if not selected:
        raise click.UsageError("No images selected for this annotation run")
    if not file_input and len(selected) > MAX_ANNOTATE_IMAGES:
        raise ResultSetTooLargeError(len(selected), MAX_ANNOTATE_IMAGES)
    return selected


def _execute_one(
    container: Any, record: dict[str, Any], models: list[str], preflight: Any, counters: dict[str, int]
) -> tuple[str, str | None, bool]:
    """Called only after in_flight is durable; exceptions deliberately keep that state."""
    from lorairo.cli.commands.annotate import _annotation_value, _emit_annotation_items, _load_batch_images

    if preflight is not None:
        path = str(resolve_stored_path(record["stored_image_path"]))
        result = preflight.apply([path])
        if path not in result.allowed_paths:
            state = "failed" if result.failure_count else "skipped"
            return (
                state,
                "moderation preflight failed" if result.failure_count else "moderation preflight",
                False,
            )
    images, records, _, _ = _load_batch_images([record])
    counters["loaded"] += len(images)
    if not images:
        return "failed", "image load failed", False
    try:
        results = container.annotator_library.annotate(
            images, litellm_model_ids=models, phash_list=[str(record["phash"])]
        )
        counters["results"] += len(results or {})
        model_results = (results or {}).get(str(record["phash"]), {})
        all_models_ok = all(
            model in model_results and _annotation_value(model_results[model], "error") is None
            for model in models
        )
        confirmed: dict[int, str] = {}
        save_result = container.annotation_save_service.save_annotation_results(
            results, allowed_image_ids={int(record["id"])}, confirmed_outcomes=confirmed
        )
        saved = save_result.image_outcomes.get(int(record["id"])) == "success"
        state = "completed" if saved and all_models_ok else "failed"
        # Do not persist provider exception payloads, prompts, or credential-bearing URLs.
        reason = (
            None if state == "completed" else "Not all requested models produced confirmed saved results"
        )
        _emit_annotation_items(results, records)
        return state, reason, saved
    finally:
        for image in images:
            image.close()


def _execute_pending(
    container: Any,
    ledger: AnnotationRunLedger,
    models: list[str],
    paths: dict[int, str],
    counters: dict[str, int],
) -> tuple[bool, str | None]:
    pending = [row for row in ledger.images() if row["state"] == "pending"]
    if not pending:
        return False, None
    # This creates adapters/validates keys, but performs no provider invocation.
    preflight = _make_preflight(container, models, strict=True)
    for row in pending:
        try:
            records = container.db_manager.image_repo.get_images_by_ids([row["image_id"]])
            if len(records) != 1:
                raise ValueError("Selected image disappeared after validation")
            record = dict(records[0])
            if row["image_id"] in paths:
                record["stored_image_path"] = paths[row["image_id"]]
            if image_identity(record, resolve_stored_path(record["stored_image_path"])) != row["identity"]:
                raise ValueError("Selected image changed after validation")
            ledger.transition(row["image_id"], "in_flight")
            state, reason, saved = _execute_one(container, record, models, preflight, counters)
            ledger.transition(row["image_id"], state, reason=reason, saved=saved)
        except (Exception, KeyboardInterrupt) as exc:
            # Even a save-commit/ledger-commit gap stays in_flight. Never infer
            # successful delivery or retryability from the exception type.
            return isinstance(
                exc, KeyboardInterrupt
            ), f"Execution stopped ({type(exc).__name__}); inspect run states before any manual retry"
    return False, None


def _emit_summary(
    ledger: AnnotationRunLedger,
    *,
    project: str,
    models: list[str],
    resumed: bool,
    interrupted: bool,
    reason: str | None,
    counters: dict[str, int],
) -> None:
    from lorairo.cli.commands.annotate import _status_console

    rows = ledger.images()
    counts = {
        state: sum(row["state"] == state for row in rows)
        for state in ("completed", "failed", "skipped", "pending", "in_flight")
    }
    for row in rows:
        _emit_outcome(row["image_id"], row["state"], reason=row["reason"], saved=bool(row["saved"]))
    resolution_skipped = sum(row["reason"] == "no processed image at requested resolution" for row in rows)
    unsuccessful = bool(
        counts["failed"] + counts["pending"] + counts["in_flight"]
    ) or resolution_skipped == len(rows)
    saved = sum(bool(row["saved"]) for row in rows)
    status = "success" if not unsuccessful else "partial_success" if saved else "failed"
    if is_json_mode():
        emit_result(
            f"Annotation run '{ledger.run_id}': {counts['completed']} completed",
            ok=not unsuccessful,
            status=status,
            project=project,
            models=models,
            total=len(rows),
            annotated=saved,
            completed=counts["completed"],
            errors=counts["failed"],
            skipped=counts["skipped"],
            resolution_skipped=resolution_skipped,
            loaded=counters["loaded"],
            results=counters["results"],
            unexecuted=counts["pending"],
            pending=counts["pending"],
            in_flight=counts["in_flight"],
            run_id=ledger.run_id,
            resumed=resumed,
            state_path=str(ledger.path),
            interrupted=interrupted,
            reason=reason,
        )
    else:
        _status_console().print(f"Annotation run {ledger.run_id}: {status}; {counts}")
        _status_console().print(f"State: {ledger.path}")
    if unsuccessful:
        raise typer.Exit(result_exit_code(status))


def run_durable_annotation(
    container: Any,
    *,
    project_path: Path,
    project: str,
    run_id: str,
    resume: bool,
    models: list[str],
    image_ids: list[int] | None,
    file_input: bool,
    criteria: ImageFilterCriteria,
    offset: int,
    limit: int | None,
    resolution: int | None,
) -> None:
    ledger = AnnotationRunLedger(project_path, run_id)
    repo = container.db_manager.image_repo
    with ledger.locked(resume=resume):
        identity = database_identity(project_path / "image_database.db")
        settings = _configuration_binding(container, models)
        if resume:
            binding = ledger.binding()
            if any(
                binding.get(key) != value
                for key, value in {
                    "project": project,
                    "database": identity,
                    "models": models,
                    "settings": settings,
                }.items()
            ):
                raise click.UsageError(
                    "Run project/database/model/configuration differs; resume refused before provider calls"
                )
            stored = ledger.images()
            selected = [row["image_id"] for row in stored]
            resolution = binding.get("resolution")
            snapshots, paths = _records_with_identity(repo, selected, resolution)
            if {row["image_id"]: row["identity"] for row in stored} != {
                row["image_id"]: row["identity"] for row in snapshots
            }:
                raise click.UsageError(
                    "Run image identity/content changed; resume refused before provider calls"
                )
        else:
            selected = _select_new_run(repo, image_ids, criteria, offset, limit, file_input=file_input)
            snapshots, paths = _records_with_identity(repo, selected, resolution)
            binding = {
                "project": project,
                "database": identity,
                "models": models,
                "settings": settings,
                "resolution": resolution,
            }
            ledger.initialize(binding, snapshots)
        counters = {"loaded": 0, "results": 0}
        interrupted, reason = _execute_pending(container, ledger, models, paths, counters)
        _emit_summary(
            ledger,
            project=project,
            models=models,
            resumed=resume,
            interrupted=interrupted,
            reason=reason,
            counters=counters,
        )
