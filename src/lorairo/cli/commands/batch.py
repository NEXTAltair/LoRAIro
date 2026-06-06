"""Provider Batch commands.

出力は ADR 0057/0058 に従う: ``--json`` 時は stdout に JSONL (item/result)、
それ以外は rich 人間向け。エラー整形は :func:`lorairo.cli._boundary.command_boundary`
に集約し、検証エラーは ``click.UsageError`` (INVALID_INPUT / exit 2) で送出する。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import click
import typer
from rich.table import Table

from lorairo.cli._boundary import command_boundary
from lorairo.cli._console import make_console
from lorairo.cli._emit import emit_item, emit_result
from lorairo.cli._output_mode import is_json_mode
from lorairo.services.service_container import get_service_container

app = typer.Typer(help="Provider Batch API job commands")
console = make_console()

_SUPPORTED_SUBMIT_PROVIDERS = {"openai", "anthropic"}
_SUPPORTED_TASK_TYPES = {"annotation", "rating_preflight"}
_TASK_TYPE_ENDPOINTS = {
    "annotation": {
        "openai": "/v1/chat/completions",
        "anthropic": "/v1/messages",
    },
    "rating_preflight": {
        "openai": "/v1/moderations",
    },
}

# _print_job_detail / json 出力共通の job フィールド。
_JOB_DETAIL_FIELDS = (
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
)


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
        raise click.UsageError(
            f"Ambiguous model '{identifier}':\n{candidates}\nUse the full LiteLLM model ID."
        )

    raise click.UsageError(f"Unknown model '{identifier}'. Run `lorairo-cli models list`.")


def _infer_provider(model: Any, explicit_provider: str | None) -> str:
    if explicit_provider:
        return explicit_provider.lower()

    model_provider = str(getattr(model, "provider", "") or "").lower()
    litellm_model_id = str(getattr(model, "litellm_model_id", "") or "")
    route_prefix = litellm_model_id.split("/", 1)[0].lower() if "/" in litellm_model_id else ""

    provider = model_provider if model_provider in {"openai", "anthropic", "google"} else route_prefix
    if provider in {"openai", "anthropic", "google"}:
        return provider

    raise click.UsageError(
        f"Could not infer a direct Provider Batch provider for {litellm_model_id!r}. "
        "Use a direct openai/... or anthropic/... model."
    )


def _validate_submit_provider(provider: str) -> None:
    if provider == "google":
        raise click.UsageError("Google Provider Batch submit is disabled until Phase 3.")
    if provider not in _SUPPORTED_SUBMIT_PROVIDERS:
        raise click.UsageError(
            f"Unsupported Provider Batch provider '{provider}'. Supported providers: openai, anthropic."
        )


def _model_has_model_type(model: Any, model_type: str) -> bool:
    model_types = getattr(model, "model_types", ())
    return any(getattr(item, "name", None) == model_type for item in model_types)


def _resolve_submit_endpoint(provider: str, task_type: str, endpoint: str | None) -> str:
    provider_endpoints = _TASK_TYPE_ENDPOINTS.get(task_type, _TASK_TYPE_ENDPOINTS["annotation"])
    expected_endpoint = provider_endpoints.get(provider)
    if expected_endpoint is None:
        raise click.UsageError(f"Task type '{task_type}' is not supported for provider '{provider}'.")
    if endpoint is None:
        return expected_endpoint
    if task_type == "rating_preflight":
        normalized_endpoint = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        if normalized_endpoint.rstrip("/") != expected_endpoint:
            raise click.UsageError("rating_preflight submit requires endpoint /v1/moderations.")
        return expected_endpoint
    return endpoint


def _job_value(job: Any, name: str, default: Any = None) -> Any:
    if isinstance(job, dict):
        return job.get(name, default)
    return getattr(job, name, default)


def _format_dt(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return "" if value is None else str(value)


def _job_dict(job: Any) -> dict[str, Any]:
    """job を JSONL item/result 用の dict に変換する (datetime は emit が文字列化)。"""
    return {field: _job_value(job, field) for field in _JOB_DETAIL_FIELDS}


def _result_item_status(item: Any) -> str:
    if isinstance(item, Mapping):
        return str(item.get("status", ""))
    return str(getattr(item, "status", ""))


def _summarize_fetch_counts(result: Any) -> tuple[int, int]:
    items = list(getattr(result, "items", ()) or ())
    succeeded_count = getattr(result, "succeeded_count", None)
    failed_count = getattr(result, "failed_count", None)
    if succeeded_count is None:
        succeeded_count = sum(1 for item in items if _result_item_status(item).lower() == "succeeded")
    if failed_count is None:
        failed_count = sum(1 for item in items if _result_item_status(item).lower() == "failed")
    return int(succeeded_count or 0), int(failed_count or 0)


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

    for field in _JOB_DETAIL_FIELDS:
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


def _artifact_dicts(fetch_result: Any) -> list[dict[str, Any]]:
    """artifacts を JSONL result 用の dict リストに変換する。"""
    artifacts = list(getattr(fetch_result, "artifacts", ()) or ())
    return [
        {
            "artifact_type": str(getattr(artifact, "artifact_type", "")),
            "local_path": str(getattr(artifact, "local_path", "")),
            "provider_file_id": getattr(artifact, "provider_file_id", None),
        }
        for artifact in artifacts
    ]


@app.command("submit")
def submit(
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    model: str = typer.Option(..., "--model", "-m", help="LiteLLM model ID or unique display name"),
    image_ids: list[int] = typer.Option(..., "--image-id", help="Image ID to submit; repeatable"),
    provider: str | None = typer.Option(None, "--provider", help="Provider override: openai/anthropic"),
    endpoint: str | None = typer.Option(None, "--endpoint", help="Provider endpoint override"),
    prompt_profile: str = typer.Option("default", "--prompt-profile", help="Prompt profile name"),
    description: str | None = typer.Option(None, "--description", help="Provider job description"),
    task_type: str = typer.Option(
        "annotation",
        "--task-type",
        help=(
            "Task type: annotation or rating_preflight. rating_preflight requires direct openai, "
            "endpoint /v1/moderations, an openai/omni-moderation-* model, and ratings model_type."
        ),
    ),
) -> None:
    """Submit registered images to a Provider Batch API job."""
    with command_boundary():
        container = _activate_project(project)
        model_repo = container.db_manager.model_repo
        provider_batch_repo = container.db_manager.provider_batch_repo
        db_model = _resolve_model(model_repo, model)
        resolved_provider = _infer_provider(db_model, provider)
        _validate_submit_provider(resolved_provider)
        normalized_task_type = task_type.strip().lower()
        if normalized_task_type not in _SUPPORTED_TASK_TYPES:
            raise click.UsageError(f"Unsupported task type '{task_type}'.")
        if normalized_task_type == "rating_preflight":
            if resolved_provider != "openai":
                raise click.UsageError(
                    "rating_preflight submit is only supported for direct openai models "
                    "such as openai/omni-moderation-latest."
                )
            if not _model_has_model_type(db_model, "ratings"):
                raise click.UsageError(
                    "rating_preflight submit requires a ratings model_type using openai/omni-moderation-*."
                )

        resolved_endpoint = _resolve_submit_endpoint(resolved_provider, normalized_task_type, endpoint)

        job_id = container.provider_batch_workflow_service.submit_images(
            provider=resolved_provider,
            endpoint=resolved_endpoint,
            litellm_model_id=db_model.litellm_model_id,
            prompt_profile=prompt_profile,
            image_ids=image_ids,
            model_id=db_model.id,
            description=description,
            task_type=normalized_task_type,
        )
        job = provider_batch_repo.get_provider_batch_job(job_id)
        if is_json_mode():
            emit_result(
                f"Provider Batch job submitted: {job_id}",
                job_id=job_id,
                job=_job_dict(job) if job is not None else None,
            )
        else:
            console.print(f"[green]Provider Batch job submitted:[/green] {job_id}")
            if job is not None:
                _print_job_detail(job)


@app.command("list")
def list_jobs(
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    provider: str | None = typer.Option(None, "--provider", help="Filter by provider"),
    status: str | None = typer.Option(None, "--status", help="Filter by common job status"),
    limit: int = typer.Option(100, "--limit", min=1, max=1000, help="Maximum rows"),
    offset: int = typer.Option(0, "--offset", min=0, help="Rows to skip"),
) -> None:
    """List persisted Provider Batch jobs."""
    with command_boundary():
        container = _activate_project(project)
        jobs = container.db_manager.provider_batch_repo.list_provider_batch_jobs(
            provider=provider,
            status=status,
            limit=limit,
            offset=offset,
        )
        if is_json_mode():
            for job in jobs:
                emit_item(_job_dict(job))
            emit_result(f"{len(jobs)} job(s)", count=len(jobs))
        else:
            _print_jobs_table(jobs)


@app.command("status")
def status(
    job_id: int = typer.Argument(..., help="Provider Batch job ID"),
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    refresh: bool = typer.Option(True, "--refresh/--no-refresh", help="Refresh provider status first"),
) -> None:
    """Show Provider Batch job status."""
    with command_boundary():
        container = _activate_project(project)
        job = (
            container.provider_batch_workflow_service.refresh(job_id)
            if refresh
            else container.db_manager.provider_batch_repo.get_provider_batch_job(job_id)
        )
        if job is None:
            raise click.UsageError(f"Provider Batch job not found: {job_id}")
        if is_json_mode():
            emit_result(f"Provider Batch job {job_id}", job=_job_dict(job))
        else:
            _print_job_detail(job)


@app.command("cancel")
def cancel(
    job_id: int = typer.Argument(..., help="Provider Batch job ID"),
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
) -> None:
    """Cancel a Provider Batch job."""
    with command_boundary():
        container = _activate_project(project)
        job = container.provider_batch_workflow_service.cancel(job_id)
        if is_json_mode():
            emit_result(
                f"Provider Batch job cancel requested: {job_id}",
                job_id=job_id,
                job=_job_dict(job) if job is not None else None,
            )
        else:
            console.print(f"[green]Provider Batch job cancel requested:[/green] {job_id}")
            _print_job_detail(job)


@app.command("fetch")
def fetch(
    job_id: int = typer.Argument(..., help="Provider Batch job ID"),
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    output_dir: Path | None = typer.Option(None, "--output-dir", "-o", help="Artifact output directory"),
) -> None:
    """Fetch normalized Provider Batch results and artifacts."""
    with command_boundary():
        container = _activate_project(project)
        result = container.provider_batch_workflow_service.fetch_results(job_id, output_dir)
        succeeded_count, failed_count = _summarize_fetch_counts(result)
        if is_json_mode():
            emit_result(
                f"Provider Batch results fetched: {job_id}",
                job_id=job_id,
                provider_status=result.provider_status,
                items=len(result.items),
                succeeded=succeeded_count,
                failed=failed_count,
                artifacts=_artifact_dicts(result),
            )
        else:
            console.print(f"[green]Provider Batch results fetched:[/green] {job_id}")
            console.print(
                f"[dim]provider_status={result.provider_status}, items={len(result.items)}, "
                f"succeeded={succeeded_count}, failed={failed_count}[/dim]"
            )
            _print_artifacts(result)


@app.command("import")
def import_results(
    job_id: int = typer.Argument(..., help="Provider Batch job ID"),
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    output_dir: Path | None = typer.Option(None, "--output-dir", "-o", help="Artifact output directory"),
) -> None:
    """Fetch and import Provider Batch results into annotations."""
    with command_boundary():
        container = _activate_project(project)
        result = container.provider_batch_workflow_service.import_results(
            job_id, destination_dir=output_dir
        )
        if is_json_mode():
            emit_result(
                f"Provider Batch results imported: {job_id}",
                job_id=job_id,
                imported=result.imported_count,
                skipped=result.skipped_count,
                errors=result.error_count,
                total=result.total_count,
                job_imported=result.job_imported,
            )
        else:
            table = Table(title="Provider Batch Import Summary")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")
            table.add_row("Imported", str(result.imported_count))
            table.add_row("Skipped", str(result.skipped_count))
            table.add_row("Errors", str(result.error_count))
            table.add_row("Total", str(result.total_count))
            table.add_row("Job Imported", "yes" if result.job_imported else "no")
            console.print(table)
