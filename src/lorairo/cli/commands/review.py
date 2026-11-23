"""Annotation review commands; results are saved only with --save-results."""

from __future__ import annotations

from typing import TYPE_CHECKING

import typer

from lorairo.cli._boundary import command_boundary
from lorairo.cli._console import make_console
from lorairo.cli._emit import emit_item, emit_result
from lorairo.cli._errors import result_exit_code
from lorairo.cli._image_ids import MAX_IMAGE_IDS_FILE, parse_image_ids, parse_image_ids_file
from lorairo.cli._output_mode import is_json_mode
from lorairo.public_api.review import ReviewSaveOutcome, resolve_crop_child_image_ids, review_annotations

if TYPE_CHECKING:
    from lorairo.services.annotation_review_service import AnnotationReviewResult

app = typer.Typer(help="Review existing tags and captions with local Clef; annotations remain unchanged.")
console = make_console()

_SELECTION_ERROR = "--image-ids / --image-ids-file / --crop-children-of / --crop-children のどれか 1 つを指定してください。"


def _resolve_review_image_ids(
    project: str,
    image_ids: str | None,
    image_ids_file: str | None,
    crop_children_of: int | None = None,
    crop_children: bool = False,
) -> list[int]:
    """Parse explicit input or resolve crop children; the review API caps the deduplicated selection."""
    selections = [bool(image_ids), bool(image_ids_file), crop_children_of is not None, crop_children]
    if sum(selections) != 1:
        raise typer.BadParameter(_SELECTION_ERROR)
    if crop_children_of is not None or crop_children:
        return resolve_crop_child_image_ids(project, crop_children_of)
    if image_ids_file:
        return parse_image_ids_file(image_ids_file)
    selected = parse_image_ids(image_ids or "")
    if not selected:
        raise typer.BadParameter("--image-ids に有効な値がありません。")
    if len(selected) > MAX_IMAGE_IDS_FILE:
        raise typer.BadParameter(f"--image-ids は最大 {MAX_IMAGE_IDS_FILE} 件まで。")
    return selected


def _emit_review(result: AnnotationReviewResult, saved: ReviewSaveOutcome | None = None) -> None:
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
                "save_status": saved.status if saved else None,
                "save_error": saved.error if saved else None,
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
        if saved is not None:
            console.print(f"  Save: {saved.status}" + (f" — {saved.error}" if saved.error else ""))


def _reject_save_under_read_only(save_results: bool) -> None:
    from lorairo.database.access_policy import is_read_only

    if save_results and is_read_only():
        raise typer.BadParameter(
            "--save-results は DB へ書き込むため、ルートの --read-only と併用できません。"
        )


def _run_status(
    operational_failures: int,
    counts: dict[str, int],
    normal_skips: int,
    save_results: bool,
    save_counts: dict[str, int],
) -> str:
    """With --save-results, partial success also requires at least one saved image."""
    if not operational_failures:
        return "success"
    progressed = bool(counts["successful"] or counts["partial"] or normal_skips)
    if save_results:
        progressed = progressed and save_counts["saved"] > 0
    return "partial_success" if progressed else "failed"


def _summary_message(counts: dict[str, int], warnings: int, save_counts: dict[str, int] | None) -> str:
    message = (
        f"Review: {counts['successful']} successful, {counts['partial']} partial, "
        f"{counts['failed']} failed, {counts['stale']} stale, "
        f"{counts['cancelled']} cancelled, {counts['unevaluated']} unevaluated; {warnings} warnings"
    )
    if save_counts is not None:
        message += (
            f"; saved {save_counts['saved']}, save skipped {save_counts['save_skipped']}, "
            f"save failed {save_counts['save_failed']}"
        )
    return message


def _emit_no_targets(project: str, save_results: bool) -> None:
    """Report an empty crop-child selection as a successful run with 0 targets."""
    message = "対象 0 件: no crop child images matched; nothing was reviewed."
    if is_json_mode():
        emit_result(
            message,
            ok=True,
            project=project,
            status="success",
            image_count=0,
            item_count=0,
            warnings=0,
            save_results=save_results,
            **dict.fromkeys(("successful", "partial", "failed", "cancelled", "stale", "unevaluated"), 0),
            **dict.fromkeys(("saved", "save_skipped", "save_failed"), 0),
        )
    else:
        console.print(message)


@app.command("run")
def run(
    project: str = typer.Option(..., "--project", "-p", help="Existing project to review."),
    image_ids: str | None = typer.Option(
        None,
        "--image-ids",
        help=(
            "Explicit comma-separated image IDs (max 500 unique images; reader max 100,000 IDs; "
            "duplicates evaluated once; "
            "mutually exclusive with --image-ids-file and crop selections)."
        ),
    ),
    image_ids_file: str | None = typer.Option(
        None,
        "--image-ids-file",
        help=(
            "UTF-8 newline/comma-separated IDs; review max 500 unique images "
            "(file reader max 100,000 IDs; mutually exclusive with --image-ids and crop selections)."
        ),
    ),
    crop_children_of: int | None = typer.Option(
        None,
        "--crop-children-of",
        help=(
            "Review the crop child images of this parent image ID (crop_relations; parent excluded; "
            "max 500 children; mutually exclusive with other selections)."
        ),
    ),
    crop_children: bool = typer.Option(
        False,
        "--crop-children",
        help=(
            "Review every crop child image in the project (crop_relations; max 500; "
            "mutually exclusive with other selections)."
        ),
    ),
    save_results: bool = typer.Option(
        False,
        "--save-results",
        help=(
            "Save each image result to annotation_review_results (shown as needs-review in the GUI). "
            "Default: no DB writes. Not allowed with root --read-only."
        ),
    ),
) -> None:
    """Evaluate existing annotations with Clef, using the configured model and threshold.

    Requires an explicit selection of at most 500 unique images: IDs, an ID file, or crop children resolved from
    crop_relations. Zero crop children is a successful run with 0 targets. Annotations are never changed. The DB is
    unchanged unless --save-results saves per-image results. Low probability warnings are review decisions, not failures.
    """
    with command_boundary():
        _reject_save_under_read_only(save_results)
        selected = _resolve_review_image_ids(
            project, image_ids, image_ids_file, crop_children_of, crop_children
        )
        if not selected:
            _emit_no_targets(project, save_results)
            return
        counts = dict.fromkeys(("successful", "partial", "failed", "cancelled", "stale", "unevaluated"), 0)
        save_counts = dict.fromkeys(("saved", "save_skipped", "save_failed"), 0)
        save_outcomes: dict[int, ReviewSaveOutcome] = {}
        item_count = 0
        warnings = 0
        blocked = 0
        normal_skips = 0

        def on_saved(outcome: ReviewSaveOutcome) -> None:
            save_outcomes[outcome.image_id] = outcome
            key = "saved" if outcome.status == "saved" else f"save_{outcome.status}"
            save_counts[key] += 1

        def on_result(result: AnnotationReviewResult) -> None:
            nonlocal item_count, warnings, blocked, normal_skips
            _emit_review(result, save_outcomes.pop(result.image_id, None))
            category = "successful" if result.status == "completed" else result.status
            counts[category] += 1
            if result.status == "unevaluated":
                if result.error or result.error_code:
                    blocked += 1
                else:
                    normal_skips += 1
            item_count += len(result.items)
            warnings += sum(item.status == "warning" for item in result.items)

        if save_results:
            review_annotations(
                project,
                selected,
                on_result=on_result,
                collect_results=False,
                save_results=True,
                on_saved=on_saved,
            )
        else:
            review_annotations(project, selected, on_result=on_result, collect_results=False)
        # 保存失敗は画像単位の運用上の失敗として数える (評価済みでも結果が残らないため)。
        operational_failures = (
            blocked
            + sum(counts[name] for name in ("partial", "failed", "cancelled", "stale"))
            + save_counts["save_failed"]
        )
        status = _run_status(operational_failures, counts, normal_skips, save_results, save_counts)
        message = _summary_message(counts, warnings, save_counts if save_results else None)
        if is_json_mode():
            emit_result(
                message,
                ok=not operational_failures,
                project=project,
                status=status,
                image_count=sum(counts.values()),
                item_count=item_count,
                warnings=warnings,
                save_results=save_results,
                **counts,
                **save_counts,
            )
        else:
            console.print(message)
        if operational_failures:
            raise typer.Exit(code=result_exit_code(status))
