"""Read-only duplicate report, registered under the images command group."""

from dataclasses import asdict

import typer

from lorairo.cli._boundary import command_boundary
from lorairo.cli._console import make_console
from lorairo.cli._emit import emit_item, emit_result
from lorairo.cli._output_mode import is_json_mode
from lorairo.public_api.duplicate_report import report_duplicates
from lorairo.services.duplicate_report_service import DEFAULT_MAX_DISTANCE, MAX_REPORT_LIMIT

console = make_console()


def report(
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    max_distance: int = typer.Option(
        DEFAULT_MAX_DISTANCE,
        "--max-distance",
        min=0,
        max=64,
        help="Maximum differing bits in saved 64-bit pHashes (default 4; candidate review only)",
    ),
    limit: int = typer.Option(
        100, "--limit", min=1, max=MAX_REPORT_LIMIT, help="Maximum clusters and members per cluster to show"
    ),
) -> None:
    """Report approximate duplicate candidates from saved pHashes without changing images.

    Scans the whole project, up to 10,000 images. Connected clusters can contain
    endpoints farther apart than the threshold. Missing or invalid hashes are counted.
    """
    with command_boundary():
        result = report_duplicates(project, max_distance=max_distance, limit=limit)
        if is_json_mode():
            for cluster in result.clusters:
                emit_item(asdict(cluster))
            emit_result(
                "Duplicate candidate report complete",
                project=project,
                read_only=True,
                status="success",
                **result.summary(),
            )
        else:
            console.print(
                f"Duplicate candidates: {result.cluster_count} clusters, "
                f"{result.clustered_images} of {result.total_images} images"
            )
            for cluster in result.clusters:
                console.print(str(asdict(cluster)), markup=False)
            console.print(str(result.summary()), markup=False)
            console.print("Candidates only; connected chains may exceed the threshold at their endpoints.")
