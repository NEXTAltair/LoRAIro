"""Offline generation of processed images for CLI workflows."""

from dataclasses import asdict

import click
import typer

from lorairo.cli._boundary import command_boundary
from lorairo.cli._console import make_console
from lorairo.cli._emit import emit_item, emit_result
from lorairo.cli._image_ids import resolve_image_ids_input
from lorairo.cli._output_mode import is_json_mode
from lorairo.public_api.processing import process_images


def process(
    project: str = typer.Option(..., "--project", "-p", help="Target project name"),
    image_ids_csv: str | None = typer.Option(None, "--image-ids", help="Exact image IDs, CSV (max 500)"),
    image_ids_file: str | None = typer.Option(None, "--image-ids-file", help="ID file (max 100,000)"),
    resolution: int = typer.Option(
        512,
        "--resolution",
        "-r",
        min=32,
        max=8192,
        help="Offline resize long side, multiple of 32; no model downloads",
    ),
    rebuild: bool = typer.Option(
        False, "--rebuild", help="Regenerate existing valid exact-resolution output"
    ),
) -> None:
    """Generate processed images offline while preserving original IDs and files.

    Valid exact-resolution files are skipped; missing/corrupt files are rebuilt.
    Reports one outcome per ID and returns exit 1 if any image fails.
    """
    with command_boundary():
        image_ids, _from_file = resolve_image_ids_input(image_ids_csv, image_ids_file)
        if resolution % 32:
            raise click.UsageError("--resolution must be a multiple of 32 between 32 and 8192")
        outcomes = process_images(project, image_ids, resolution, rebuild=rebuild)
        processed_ids = [item.image_id for item in outcomes if item.status == "success"]
        skipped_ids = [item.image_id for item in outcomes if item.status == "skipped"]
        failed_ids = [item.image_id for item in outcomes if item.status == "failed"]
        status = (
            "success" if not failed_ids else "partial_success" if processed_ids or skipped_ids else "failed"
        )
        message = (
            "Offline processing completed."
            if not failed_ids
            else "Offline processing incomplete; inspect failed IDs."
        )
        if is_json_mode():
            for item in outcomes:
                emit_item(asdict(item))
            emit_result(
                message,
                ok=not failed_ids,
                status=status,
                project=project,
                resolution=resolution,
                total=len(outcomes),
                processed=len(processed_ids),
                skipped=len(skipped_ids),
                failed=len(failed_ids),
                processed_ids=processed_ids,
                skipped_ids=skipped_ids,
                failed_ids=failed_ids,
            )
        else:
            console = make_console()
            for item in outcomes:
                console.print(f"{item.image_id}: {item.status} {item.output_path or item.reason or ''}")
            console.print(message)
        if failed_ids:
            raise typer.Exit(code=1)
