"""Provider Batch job management commands."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.table import Table

from lorairo.cli._console import make_console
from lorairo.services.provider_batch_service import ProviderBatchError
from lorairo.services.service_container import get_service_container

if TYPE_CHECKING:
    from lorairo.database.schema import ProviderBatchJob
    from lorairo.services.provider_batch_service import ProviderBatchArtifactRef, ProviderBatchFetchResult
    from lorairo.services.provider_batch_workflow_service import ProviderBatchImportResult
    from lorairo.services.service_container import ServiceContainer


app = typer.Typer(help="Provider Batch job management commands")
console = make_console()


def _active_container(project: str) -> ServiceContainer:
    container = get_service_container()
    container.set_active_project(project)
    return container


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _format_count(value: int | None) -> str:
    return "-" if value is None else str(value)


def _job_counts(job: ProviderBatchJob) -> str:
    return (
        f"{job.succeeded_count}/{job.request_count} ok; "
        f"{job.failed_count} failed; {job.canceled_count} canceled; {job.expired_count} expired"
    )


def _imported_state(job: ProviderBatchJob) -> str:
    return "yes" if job.imported_at is not None or job.status == "imported" else "no"


def _job_table(jobs: Sequence[ProviderBatchJob], *, title: str) -> Table:
    table = Table(title=title)
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Provider", no_wrap=True)
    table.add_column("Provider Job ID", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Counts", no_wrap=True)
    table.add_column("Submitted", no_wrap=True)
    table.add_column("Completed", no_wrap=True)
    table.add_column("Imported", no_wrap=True)

    for job in jobs:
        table.add_row(
            str(job.id),
            job.provider,
            job.provider_job_id or "-",
            job.status,
            _job_counts(job),
            _format_datetime(job.submitted_at),
            _format_datetime(job.completed_at),
            _imported_state(job),
        )
    return table


def _job_summary(job: ProviderBatchJob) -> str:
    return (
        f"Job {job.id}: provider={job.provider}, provider_job_id={job.provider_job_id or '-'}, "
        f"status={job.status}, counts={_job_counts(job)}, submitted={_format_datetime(job.submitted_at)}, "
        f"completed={_format_datetime(job.completed_at)}, imported={_imported_state(job)}"
    )


def _print_job(job: ProviderBatchJob, *, title: str = "Provider Batch Job") -> None:
    console.print(_job_summary(job))
    console.print(_job_table([job], title=title))


def _print_artifacts(artifacts: Sequence[ProviderBatchArtifactRef]) -> None:
    if not artifacts:
        console.print("Artifacts: 0")
        return

    table = Table(title="Artifacts")
    table.add_column("Type")
    table.add_column("Path")
    table.add_column("Provider File ID")
    table.add_column("SHA-256")
    for artifact in artifacts:
        table.add_row(
            artifact.artifact_type,
            str(artifact.local_path),
            artifact.provider_file_id or "-",
            artifact.sha256 or "-",
        )
    console.print(table)


def _handle_error(error: Exception) -> None:
    console.print(f"[red]Error:[/red] {error}")
    raise typer.Exit(code=1) from error


def _validate_submit_provider(provider: str) -> str:
    provider_key = provider.strip().lower()
    if provider_key == "google":
        raise ProviderBatchError("Google Provider Batch is disabled / not configured until Phase 3.")
    return provider_key


@app.command("submit")
def submit(
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    provider: str = typer.Option(..., "--provider", help="Provider name"),
    model: str = typer.Option(..., "--model", help="LiteLLM model ID"),
    endpoint: str = typer.Option("responses", "--endpoint", help="Provider batch endpoint"),
    prompt_profile: str = typer.Option(
        "default",
        "--prompt-profile",
        help="Prompt profile name",
    ),
    image_ids: list[int] | None = typer.Option(
        None,
        "--image-id",
        help="Image ID to submit. Repeat for multiple images.",
    ),
    description: str | None = typer.Option(None, "--description", help="Job description"),
    model_id: int | None = typer.Option(None, "--model-id", help="LoRAIro model database ID"),
) -> None:
    """Submit images to a Provider Batch job."""
    try:
        container = _active_container(project)
        provider_key = _validate_submit_provider(provider)
        job_id = container.provider_batch_workflow_service.submit_images(
            provider=provider_key,
            endpoint=endpoint,
            litellm_model_id=model,
            prompt_profile=prompt_profile,
            image_ids=image_ids or [],
            model_id=model_id,
            description=description,
        )
        console.print(f"Provider batch job submitted: {job_id}")
    except Exception as e:
        _handle_error(e)


@app.command("list")
def list_jobs(
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    provider: str | None = typer.Option(None, "--provider", help="Filter by provider"),
    status: str | None = typer.Option(None, "--status", help="Filter by common job status"),
    limit: int = typer.Option(100, "--limit", min=1, help="Maximum jobs to show"),
) -> None:
    """List Provider Batch jobs."""
    try:
        container = _active_container(project)
        jobs = container.image_repository.list_provider_batch_jobs(
            provider=provider,
            status=status,
            limit=limit,
        )
        if not jobs:
            console.print("No provider batch jobs found.")
            return
        for job in jobs:
            console.print(_job_summary(job))
        console.print(_job_table(jobs, title="Provider Batch Jobs"))
    except Exception as e:
        _handle_error(e)


@app.command("status")
def status(
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    job_id: int = typer.Argument(..., help="Provider Batch job ID"),
    refresh: bool = typer.Option(
        True,
        "--refresh/--no-refresh",
        help="Refresh from provider before showing status",
    ),
) -> None:
    """Show Provider Batch job status."""
    try:
        container = _active_container(project)
        if refresh:
            job = container.provider_batch_workflow_service.refresh(job_id)
        else:
            db_job = container.image_repository.get_provider_batch_job(job_id)
            if db_job is None:
                raise ProviderBatchError(f"Provider batch job が見つかりません: job_id={job_id}")
            job = db_job
        _print_job(job)
    except Exception as e:
        _handle_error(e)


@app.command("cancel")
def cancel(
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    job_id: int = typer.Argument(..., help="Provider Batch job ID"),
) -> None:
    """Cancel a Provider Batch job."""
    try:
        container = _active_container(project)
        job = container.provider_batch_workflow_service.cancel(job_id)
        console.print(f"Provider batch job canceled: {job.id} ({job.status})")
    except Exception as e:
        _handle_error(e)


@app.command("fetch")
def fetch(
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    job_id: int = typer.Argument(..., help="Provider Batch job ID"),
    destination_dir: Path | None = typer.Option(
        None,
        "--destination-dir",
        help="Directory for downloaded provider result artifacts",
    ),
) -> None:
    """Fetch Provider Batch results and artifacts."""
    try:
        container = _active_container(project)
        result: ProviderBatchFetchResult = container.provider_batch_workflow_service.fetch_results(
            job_id,
            destination_dir,
        )
        console.print(
            "Provider batch results fetched: "
            f"provider_job_id={result.provider_job_id}, "
            f"items={len(result.items)}, artifacts={len(result.artifacts)}"
        )
        _print_artifacts(result.artifacts)
    except Exception as e:
        _handle_error(e)


@app.command("import")
def import_results(
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    job_id: int = typer.Argument(..., help="Provider Batch job ID"),
    destination_dir: Path | None = typer.Option(
        None,
        "--destination-dir",
        help="Directory for downloaded provider result artifacts",
    ),
) -> None:
    """Import Provider Batch results into annotations."""
    try:
        container = _active_container(project)
        result: ProviderBatchImportResult = container.provider_batch_workflow_service.import_results(
            job_id,
            destination_dir=destination_dir,
        )
        console.print(
            "Provider batch results imported: "
            f"imported={_format_count(result.imported_count)}, "
            f"skipped={_format_count(result.skipped_count)}, "
            f"errors={_format_count(result.error_count)}, "
            f"total={_format_count(result.total_count)}, "
            f"job_imported={result.job_imported}"
        )
        if result.missing_custom_ids:
            console.print(f"Missing custom IDs: {', '.join(result.missing_custom_ids)}")
    except Exception as e:
        _handle_error(e)
