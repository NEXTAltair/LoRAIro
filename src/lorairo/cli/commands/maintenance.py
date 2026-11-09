"""Read-only DB maintenance commands (ADR 0099)."""

from dataclasses import asdict
from enum import StrEnum

import typer

from lorairo.cli._boundary import command_boundary
from lorairo.cli._console import make_console
from lorairo.cli._emit import emit_item, emit_result
from lorairo.cli._errors import result_exit_code
from lorairo.cli._output_mode import is_json_mode

app = typer.Typer(help="Read-only DB maintenance commands")
console = make_console()


class MaintenanceScope(StrEnum):
    """`--scope` で選べる点検範囲。"""

    BATCH = "batch"
    FILES = "files"
    PROVIDER = "provider"


@app.command("check")
def check(
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    scope: list[MaintenanceScope] | None = typer.Option(
        None,
        "--scope",
        help="Check scope; repeat for several (batch, files, provider). Default: batch, files.",
        case_sensitive=False,
    ),
    limit: int = typer.Option(100, "--limit", min=1, max=500, help="Maximum IDs reported per check"),
) -> None:
    """Report provider batch DB inconsistencies and missing image files without repairing.

    Uses only the project DB and local files by default (`batch`, `files`); pass
    `--scope provider` to query remote provider batch status in read-only mode.
    Counts cover the whole project; IDs per check are capped by --limit. Findings
    still exit 0: inspect issues_found / issue_count in the result.
    """
    from lorairo.public_api.maintenance import check_database

    with command_boundary():
        scopes = [item.value for item in scope or ()]
        report = check_database(project, scopes, limit=limit)
        summary = report.summary()
        status = str(summary.pop("status", report.status))
        if is_json_mode():
            for finding in report.checks:
                emit_item(asdict(finding))
            emit_result(
                "DB maintenance check complete",
                ok=status == "success",
                project=project,
                read_only=True,
                status=status,
                **summary,
            )
        else:
            console.print(
                f"DB maintenance check: {report.issue_count} issues in {len(report.checks)} checks "
                f"(scopes: {', '.join(report.scopes)})"
            )
            for finding in report.checks:
                more = " ..." if finding.ids_truncated else ""
                console.print(
                    f"{finding.check}: {finding.count} {finding.id_type}s {finding.ids}{more}", markup=False
                )
            console.print(str(report.summary()), markup=False)
            if report.provider_queried:
                console.print("Report only; nothing was repaired (provider API queried in read-only mode).")
            else:
                console.print("Report only; nothing was repaired and no provider API was called.")
        if status != "success":
            raise typer.Exit(result_exit_code(status))
