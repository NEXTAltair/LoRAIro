"""Read-only annotation review commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

import click
import typer

from lorairo.cli._boundary import command_boundary
from lorairo.cli._console import make_console
from lorairo.cli._emit import emit_item, emit_result
from lorairo.cli._image_ids import MAX_IMAGE_IDS_FILE, parse_image_ids, parse_image_ids_file
from lorairo.cli._output_mode import is_json_mode
from lorairo.public_api.review import review_annotations

if TYPE_CHECKING:
    from lorairo.services.annotation_review_service import AnnotationReviewResult

app = typer.Typer(
    help="Review existing tags and captions with Cloudflare Clef; annotations remain unchanged."
)
console = make_console()


def _resolve_review_image_ids(image_ids: str | None, image_ids_file: str | None) -> list[int]:
    """Parse explicit input; the review API caps the deduplicated selection."""
    if bool(image_ids) == bool(image_ids_file):
        raise click.UsageError("--image-ids か --image-ids-file のどちらか一方を指定してください。")
    if image_ids_file:
        return parse_image_ids_file(image_ids_file)
    selected = parse_image_ids(image_ids or "")
    if not selected:
        raise click.UsageError("--image-ids に有効な値がありません。")
    if len(selected) > MAX_IMAGE_IDS_FILE:
        raise click.UsageError(f"--image-ids は最大 {MAX_IMAGE_IDS_FILE} 件まで。")
    return selected


def _emit_review(result: AnnotationReviewResult) -> None:
    if is_json_mode():
        for item in result.items:
            emit_item(
                {
                    "type": "annotation_review",
                    "image_id": result.image_id,
                    "fingerprint": result.fingerprint,
                    "model_name": result.model_name,
                    "candidate_id": item.candidate_id,
                    "candidate_kind": item.kind,
                    "text": item.text,
                    "probability": item.probability,
                    "status": item.status,
                    "error": item.error,
                }
            )
        emit_item(
            {
                "type": "annotation_review_outcome",
                "image_id": result.image_id,
                "fingerprint": result.fingerprint,
                "model_name": result.model_name,
                "status": result.status,
                "item_count": len(result.items),
                "error": result.error,
            }
        )
    else:
        console.print(f"Image {result.image_id}: {result.status}")
        for item in result.items:
            probability = f"{item.probability:.4f}" if item.probability is not None else "unevaluated"
            console.print(f"  {item.kind}: {item.text} — {probability} ({item.status})")
            if item.error:
                console.print(f"    {item.error}")
        if result.error:
            console.print(f"  {result.error}")


@app.command("run")
def run(
    project: str = typer.Option(..., "--project", "-p", help="Existing project to review."),
    image_ids: str | None = typer.Option(
        None,
        "--image-ids",
        help=(
            "Explicit comma-separated image IDs (max 500 unique images; reader max 100,000 IDs; "
            "duplicates evaluated once; "
            "mutually exclusive with --image-ids-file)."
        ),
    ),
    image_ids_file: str | None = typer.Option(
        None,
        "--image-ids-file",
        help=(
            "UTF-8 newline/comma-separated IDs; review max 500 unique images "
            "(file reader max 100,000 IDs; mutually exclusive with --image-ids)."
        ),
    ),
) -> None:
    """Evaluate existing annotations with Clef, using the configured model and threshold.

    Requires an explicit selection of at most 500 unique images. This command sends selected images
    and their existing annotation candidates to Cloudflare and leaves the DB
    unchanged. Low probability warnings are review decisions, not failures.
    """
    with command_boundary():
        selected = _resolve_review_image_ids(image_ids, image_ids_file)
        counts = dict.fromkeys(("successful", "partial", "failed", "cancelled", "stale", "unevaluated"), 0)
        item_count = 0
        warnings = 0

        def on_result(result: AnnotationReviewResult) -> None:
            nonlocal item_count, warnings
            _emit_review(result)
            category = "successful" if result.status == "completed" else result.status
            counts[category] += 1
            item_count += len(result.items)
            warnings += sum(item.status == "warning" for item in result.items)

        review_annotations(project, selected, on_result=on_result, collect_results=False)
        operational_failures = sum(counts[name] for name in ("partial", "failed", "cancelled", "stale"))
        status = "success"
        if operational_failures:
            status = (
                "partial_success"
                if counts["successful"] or counts["partial"] or counts["unevaluated"]
                else "failed"
            )
        message = (
            f"Review: {counts['successful']} successful, {counts['partial']} partial, "
            f"{counts['failed']} failed, {counts['stale']} stale, "
            f"{counts['cancelled']} cancelled, {counts['unevaluated']} unevaluated; {warnings} warnings"
        )
        if is_json_mode():
            emit_result(
                message,
                ok=not operational_failures,
                project=project,
                status=status,
                image_count=sum(counts.values()),
                item_count=item_count,
                warnings=warnings,
                **counts,
            )
        else:
            console.print(message)
        if operational_failures:
            raise typer.Exit(code=1)
