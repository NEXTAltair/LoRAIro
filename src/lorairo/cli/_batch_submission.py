"""Explicit-ID Provider Batch submission with bounded validation and durable job reporting."""

from typing import Any

import click
import typer
from PIL import Image

from lorairo.cli._console import make_console
from lorairo.cli._emit import emit_item, emit_result
from lorairo.cli._image_guard import reject_original_image_records
from lorairo.cli._image_ids import BULK_CHUNK_SIZE, validate_candidate_ids
from lorairo.cli._output_mode import is_json_mode
from lorairo.database.db_core import resolve_stored_path

# Independent provider adapter safety limit (image-annotator-lib openai/anthropic).
# Do not conflate this with the DB exact-set limit even though both currently500.
PROVIDER_JOB_ITEMS = 500


def _validate_image_paths(paths: dict[int, str]) -> None:
    """Validate every selected artifact before any job can be sent; one open image."""
    for image_id, path in paths.items():
        try:
            with Image.open(path) as image:
                image.verify()
        except (OSError, ValueError) as exc:
            raise click.UsageError(f"Cannot submit image {image_id}: {exc}. No jobs submitted.") from exc


def _prevalidate(
    container: Any, image_ids: list[int], resolution: int | None, options: dict[str, Any]
) -> dict[int, str]:
    from lorairo.cli.commands.batch import _resolve_processed_image_paths

    repo = container.db_manager.image_repo
    paths: dict[int, str] = {}
    for start in range(0, len(image_ids), BULK_CHUNK_SIZE):
        chunk = image_ids[start : start + BULK_CHUNK_SIZE]
        if resolution is not None:
            selected = _resolve_processed_image_paths(container, chunk, resolution)
        else:
            records = repo.get_images_by_ids(chunk)
            reject_original_image_records(records, command_name="batch submit")
            selected = {int(record["id"]): record.get("stored_image_path") for record in records}
        for image_id in chunk:
            if not selected.get(image_id):
                raise click.UsageError(f"No stored image path for image_id={image_id}. No jobs submitted.")
            paths[image_id] = str(resolve_stored_path(str(selected[image_id])))
    _validate_image_paths(paths)
    # Validate custom_id metadata, task/model compatibility, and every request before send.
    # Build only one bounded request at a time; no image bytes/request list retained.
    for start in range(0, len(image_ids), PROVIDER_JOB_ITEMS):
        chunk = image_ids[start : start + PROVIDER_JOB_ITEMS]
        container.provider_batch_workflow_service.build_submit_request(
            **options, image_ids=chunk, image_paths={i: paths[i] for i in chunk}
        )
    return paths


def _outcome(status: str, ids: list[int], *, job_id: int | None = None, reason: str | None = None) -> None:
    if is_json_mode():
        emit_item(
            {
                "type": "batch_submission",
                "status": status,
                "image_ids": ids,
                "job_id": job_id,
                "reason": reason,
            }
        )
    else:
        message = (
            f"Provider Batch job submitted: {job_id} ({len(ids)} images)"
            if status == "submitted"
            else f"{status}: {len(ids)} images; job_id={job_id}; {reason or ''}"
        )
        make_console().print(message)


def submit_validated_ids(
    container: Any, *, image_ids: list[int], project: str, resolution: int | None, **options: Any
) -> None:
    """Emit per-job assignments immediately; later errors retain all prior job IDs."""
    image_ids = validate_candidate_ids(container.db_manager.image_repo, image_ids)
    paths = _prevalidate(container, image_ids, resolution, options)
    if resolution is not None and not is_json_mode():
        make_console().print(f"Using processed images at resolution {resolution}px")
    job_ids: list[int] = []
    submitted = 0
    failed = 0
    unsubmitted = 0
    interrupted = False
    first_job = None
    from lorairo.cli.commands.batch import _job_dict

    for start in range(0, len(image_ids), PROVIDER_JOB_ITEMS):
        chunk = image_ids[start : start + PROVIDER_JOB_ITEMS]
        try:
            job_id = container.provider_batch_workflow_service.submit_images(
                **options,
                image_ids=chunk,
                image_paths={i: paths[i] for i in chunk} if resolution is not None else None,
            )
        except (Exception, KeyboardInterrupt) as exc:
            interrupted = isinstance(exc, KeyboardInterrupt)
            failed = len(chunk)
            # A transport/interruption error may have occurred after provider acceptance.
            # Report uncertainty instead of automatically resubmitting this assignment.
            _outcome(
                "failed", chunk, reason=f"Submission not confirmed; inspect provider before retry: {exc}"
            )
            for remaining in range(start + len(chunk), len(image_ids), PROVIDER_JOB_ITEMS):
                pending = image_ids[remaining : remaining + PROVIDER_JOB_ITEMS]
                unsubmitted += len(pending)
                _outcome("unsubmitted", pending, reason="Stopped after prior submission failure")
            break
        job_ids.append(job_id)
        submitted += len(chunk)
        _outcome("submitted", chunk, job_id=job_id)
        if first_job is None:
            try:
                job = container.db_manager.provider_batch_repo.get_provider_batch_job(job_id)
                first_job = _job_dict(job) if job is not None else None
                if first_job and not is_json_mode():
                    make_console().print(str(first_job))
            except Exception:
                # Assignment was already emitted; metadata lookup cannot erase submitted job identity.
                first_job = None
    status = "success" if not failed else "partial_success" if submitted else "failed"
    if is_json_mode():
        emit_result(
            f"Submitted {len(job_ids)} Provider Batch job(s)",
            ok=not failed,
            status=status,
            project=project,
            total=len(image_ids),
            submitted=submitted,
            failed=failed,
            unsubmitted=unsubmitted,
            interrupted=interrupted,
            job_ids=job_ids,
            job_id=job_ids[0] if job_ids else None,
            job=first_job,
        )
    if failed:
        raise typer.Exit(1)
