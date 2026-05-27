"""Provider Batch commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from rich.table import Table

from lorairo.cli._console import make_console
from lorairo.services.provider_batch_service import ProviderBatchError
from lorairo.services.service_container import get_service_container
from lorairo.utils.log import logger

app = typer.Typer(help="Provider Batch API job commands")
console = make_console()

_SUPPORTED_SUBMIT_PROVIDERS = {"openai", "anthropic"}
_DEFAULT_ENDPOINTS = {
    "openai": "/v1/chat/completions",
    "anthropic": "/v1/messages",
}


def _activate_project(project: str) -> Any:
    container = get_service_container()
    container.set_active_project(project)
    return container


def _resolve_model(repository: Any, identifier: str) -> Any:
    by_litellm = repository.get_model_by_litellm_id(identifier)
    if by_litellm is not None:
        return by_litellm

    by_name = repository.get_models_by_name(identifier)
    if len(by_name) == 1:
        return by_name[0]
    if len(by_name) > 1:
        candidates = "\n".join(
            f"  - {model.litellm_model_id} (provider: {model.provider or 'unknown'})" for model in by_name
        )
        console.print(
            f"[red]Error:[/red] Ambiguous model '{identifier}':\n"
            f"{candidates}\nUse the full LiteLLM model ID."
        )
        raise typer.Exit(code=1)

    console.print(f"[red]Error:[/red] Unknown model '{identifier}'. Run `lorairo-cli models list`.")
    raise typer.Exit(code=1)


def _infer_provider(model: Any, explicit_provider: str | None) -> str:
    if explicit_provider:
        return explicit_provider.lower()

    model_provider = str(getattr(model, "provider", "") or "").lower()
    litellm_model_id = str(getattr(model, "litellm_model_id", "") or "")
    route_prefix = litellm_model_id.split("/", 1)[0].lower() if "/" in litellm_model_id else ""

    provider = model_provider if model_provider in {"openai", "anthropic", "google"} else route_prefix
    if provider in {"openai", "anthropic", "google"}:
        return provider

    console.print(
        f"[red]Error:[/red] Could not infer a direct Provider Batch provider for "
        f"{litellm_model_id!r}. Use a direct openai/... or anthropic/... model."
    )
    raise typer.Exit(code=1)


def _validate_submit_provider(provider: str) -> None:
    if provider == "google":
        console.print("[red]Error:[/red] Google Provider Batch submit is disabled until Phase 3.")
        raise typer.Exit(code=1)
    if provider not in _SUPPORTED_SUBMIT_PROVIDERS:
        console.print(
            f"[red]Error:[/red] Unsupported Provider Batch provider '{provider}'. "
            "Supported providers: openai, anthropic."
        )
        raise typer.Exit(code=1)


def _job_value(job: Any, name: str, default: Any = None) -> Any:
    if isinstance(job, dict):
        return job.get(name, default)
    return getattr(job, name, default)


def _format_dt(value: Any) -> str:
    return "" if value is None else str(value)


def _print_jobs_table(jobs: list[Any]) -> None:
    table = Table(title="Provider Batch Jobs")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Provider", style="magenta", no_wrap=True)
    table.add_column("Status", style="green", no_wrap=True)
    table.add_column("Provider Status", style="yellow")
    table.add_column("Requests", justify="right")
    table.add_column("Created", style="dim")

    for job in jobs:
        table.add_row(
            str(_job_value(job, "id", "")),
            str(_job_value(job, "provider", "")),
            str(_job_value(job, "status", "")),
            str(_job_value(job, "provider_status", "") or ""),
            str(_job_value(job, "request_count", 0)),
            _format_dt(_job_value(job, "created_at")),
        )
    console.print(table)
    console.print(f"[dim]{len(jobs)} job(s)[/dim]")


def _print_job_detail(job: Any) -> None:
    table = Table(title=f"Provider Batch Job {_job_value(job, 'id', '')}")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")

    for field in (
        "id",
        "provider",
        "provider_job_id",
        "status",
        "provider_status",
        "endpoint",
        "model_id",
        "request_count",
        "succeeded_count",
        "failed_count",
        "canceled_count",
        "expired_count",
        "submitted_at",
        "completed_at",
        "canceled_at",
        "expires_at",
        "imported_at",
    ):
        table.add_row(field, _format_dt(_job_value(job, field)))
    console.print(table)


def _print_artifacts(fetch_result: Any) -> None:
    artifacts = list(getattr(fetch_result, "artifacts", ()) or ())
    if not artifacts:
        console.print("[yellow]No artifacts downloaded.[/yellow]")
        return

    table = Table(title="Downloaded Artifacts")
    table.add_column("Type", style="cyan")
    table.add_column("Path", style="green")
    table.add_column("Provider File ID", style="dim")
    for artifact in artifacts:
        table.add_row(
            str(getattr(artifact, "artifact_type", "")),
            str(getattr(artifact, "local_path", "")),
            str(getattr(artifact, "provider_file_id", "") or ""),
        )
    console.print(table)


@app.command("submit")
def submit(
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    model: str = typer.Option(..., "--model", "-m", help="LiteLLM model ID or unique display name"),
    image_ids: list[int] = typer.Option(..., "--image-id", help="Image ID to submit; repeatable"),
    provider: str | None = typer.Option(None, "--provider", help="Provider override: openai/anthropic"),
    endpoint: str | None = typer.Option(None, "--endpoint", help="Provider endpoint override"),
    prompt_profile: str = typer.Option("default", "--prompt-profile", help="Prompt profile name"),
    description: str | None = typer.Option(None, "--description", help="Provider job description"),
) -> None:
    """Submit registered images to a Provider Batch API job."""
    try:
        container = _activate_project(project)
        model_repo = container.db_manager.model_repo
        provider_batch_repo = container.db_manager.provider_batch_repo
        db_model = _resolve_model(model_repo, model)
        resolved_provider = _infer_provider(db_model, provider)
        _validate_submit_provider(resolved_provider)
        resolved_endpoint = endpoint or _DEFAULT_ENDPOINTS[resolved_provider]

        job_id = container.provider_batch_workflow_service.submit_images(
            provider=resolved_provider,
            endpoint=resolved_endpoint,
            litellm_model_id=db_model.litellm_model_id,
            prompt_profile=prompt_profile,
            image_ids=image_ids,
            model_id=db_model.id,
            description=description,
        )
        job = provider_batch_repo.get_provider_batch_job(job_id)
        console.print(f"[green]Provider Batch job submitted:[/green] {job_id}")
        if job is not None:
            _print_job_detail(job)
    except typer.Exit:
        raise
    except ProviderBatchError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        logger.error(f"Provider Batch submit failed: {e}", exc_info=True)
        raise typer.Exit(code=2) from e


@app.command("list")
def list_jobs(
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    provider: str | None = typer.Option(None, "--provider", help="Filter by provider"),
    status: str | None = typer.Option(None, "--status", help="Filter by common job status"),
    limit: int = typer.Option(100, "--limit", min=1, max=1000, help="Maximum rows"),
    offset: int = typer.Option(0, "--offset", min=0, help="Rows to skip"),
) -> None:
    """List persisted Provider Batch jobs."""
    try:
        container = _activate_project(project)
        jobs = container.db_manager.provider_batch_repo.list_provider_batch_jobs(
            provider=provider,
            status=status,
            limit=limit,
            offset=offset,
        )
        _print_jobs_table(jobs)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        logger.error(f"Provider Batch list failed: {e}", exc_info=True)
        raise typer.Exit(code=2) from e


@app.command("status")
def status(
    job_id: int = typer.Argument(..., help="Provider Batch job ID"),
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    refresh: bool = typer.Option(True, "--refresh/--no-refresh", help="Refresh provider status first"),
) -> None:
    """Show Provider Batch job status."""
    try:
        container = _activate_project(project)
        job = (
            container.provider_batch_workflow_service.refresh(job_id)
            if refresh
            else container.db_manager.provider_batch_repo.get_provider_batch_job(job_id)
        )
        if job is None:
            console.print(f"[red]Error:[/red] Provider Batch job not found: {job_id}")
            raise typer.Exit(code=1)
        _print_job_detail(job)
    except typer.Exit:
        raise
    except ProviderBatchError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        logger.error(f"Provider Batch status failed: {e}", exc_info=True)
        raise typer.Exit(code=2) from e


@app.command("cancel")
def cancel(
    job_id: int = typer.Argument(..., help="Provider Batch job ID"),
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
) -> None:
    """Cancel a Provider Batch job."""
    try:
        container = _activate_project(project)
        job = container.provider_batch_workflow_service.cancel(job_id)
        console.print(f"[green]Provider Batch job cancel requested:[/green] {job_id}")
        _print_job_detail(job)
    except ProviderBatchError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        logger.error(f"Provider Batch cancel failed: {e}", exc_info=True)
        raise typer.Exit(code=2) from e


@app.command("fetch")
def fetch(
    job_id: int = typer.Argument(..., help="Provider Batch job ID"),
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    output_dir: Path | None = typer.Option(None, "--output-dir", "-o", help="Artifact output directory"),
) -> None:
    """Fetch normalized Provider Batch results and artifacts."""
    try:
        container = _activate_project(project)
        result = container.provider_batch_workflow_service.fetch_results(job_id, output_dir)
        console.print(f"[green]Provider Batch results fetched:[/green] {job_id}")
        console.print(
            f"[dim]provider_status={result.provider_status}, items={len(result.items)}, "
            f"succeeded={result.succeeded_count or 0}, failed={result.failed_count or 0}[/dim]"
        )
        _print_artifacts(result)
    except ProviderBatchError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        logger.error(f"Provider Batch fetch failed: {e}", exc_info=True)
        raise typer.Exit(code=2) from e


@app.command("import")
def import_results(
    job_id: int = typer.Argument(..., help="Provider Batch job ID"),
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    output_dir: Path | None = typer.Option(None, "--output-dir", "-o", help="Artifact output directory"),
) -> None:
    """Fetch and import Provider Batch results into annotations."""
    try:
        container = _activate_project(project)
        result = container.provider_batch_workflow_service.import_results(
            job_id, destination_dir=output_dir
        )
        table = Table(title="Provider Batch Import Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Imported", str(result.imported_count))
        table.add_row("Skipped", str(result.skipped_count))
        table.add_row("Errors", str(result.error_count))
        table.add_row("Total", str(result.total_count))
        table.add_row("Job Imported", "yes" if result.job_imported else "no")
        console.print(table)
    except ProviderBatchError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        logger.error(f"Provider Batch import failed: {e}", exc_info=True)
        raise typer.Exit(code=2) from e
