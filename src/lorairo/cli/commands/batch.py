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
from lorairo.cli._image_guard import reject_original_image_records
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

# _print_items_table / json 出力共通の item フィールド。
_ITEM_DETAIL_FIELDS = (
    "id",
    "job_id",
    "custom_id",
    "image_id",
    "model_id",
    "task_type",
    "status",
    "error_type",
    "error_message",
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


def _item_value(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _format_dt(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return "" if value is None else str(value)


def _job_dict(job: Any) -> dict[str, Any]:
    """job を JSONL item/result 用の dict に変換する。

    datetime は raw のまま載せ、``_emit`` の ``_json_default`` が ISO 8601 (isoformat) へ
    正規化する (#669)。rich 表示の ``_format_dt`` とは別経路だが双方 isoformat で一致する。
    """
    return {field: _job_value(job, field) for field in _JOB_DETAIL_FIELDS}


def _item_dict(item: Any) -> dict[str, Any]:
    """provider batch item を JSONL item 用の dict に変換する。"""
    return {field: _item_value(item, field) for field in _ITEM_DETAIL_FIELDS}


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


def _parse_image_ids_csv(value: str) -> list[int]:
    """Parse the canonical ``--image-ids`` CSV option into integer IDs."""
    image_ids: list[int] = []
    invalid_tokens: list[str] = []
    empty_tokens = 0

    for token in value.split(","):
        normalized = token.strip()
        if not normalized:
            empty_tokens += 1
            continue
        try:
            image_ids.append(int(normalized))
        except ValueError:
            invalid_tokens.append(normalized)

    if invalid_tokens or empty_tokens or not image_ids:
        details: list[str] = []
        if invalid_tokens:
            details.append(f"invalid token(s): {', '.join(invalid_tokens)}")
        if empty_tokens:
            details.append("empty item(s)")
        if not image_ids:
            details.append("no image IDs")
        raise click.UsageError(
            "--image-ids must be a comma-separated list of integer image IDs "
            f"(example: --image-ids 2,7,11): {'; '.join(details)}"
        )

    return image_ids


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


def _print_items_table(items: list[Any], job_id: int) -> None:
    table = Table(title=f"Provider Batch Items (job {job_id})")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("custom_id", style="dim")
    table.add_column("image_id", justify="right")
    table.add_column("model_id", justify="right")
    table.add_column("task_type", style="magenta")
    table.add_column("status", style="green")
    table.add_column("error_type", style="red")

    for item in items:
        table.add_row(
            str(_item_value(item, "id", "")),
            str(_item_value(item, "custom_id", "")),
            str(_item_value(item, "image_id", "") or ""),
            str(_item_value(item, "model_id", "") or ""),
            str(_item_value(item, "task_type", "") or ""),
            str(_item_value(item, "status", "")),
            str(_item_value(item, "error_type", "") or ""),
        )
    console.print(table)
    console.print(f"[dim]{len(items)} item(s)[/dim]")


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
    image_ids_csv: str = typer.Option(
        ...,
        "--image-ids",
        help="Comma-separated image IDs to submit (example: 2,7,11)",
    ),
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
        image_ids = _parse_image_ids_csv(image_ids_csv)
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
        image_repo = container.db_manager.image_repo
        reject_original_image_records(
            image_repo.get_images_by_ids(image_ids),
            command_name="batch submit",
        )

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
    show_items: bool = typer.Option(
        False,
        "--items/--no-items",
        help=(
            "Show provider batch items (custom_id, image_id, model_id, task_type, status, error_type). "
            "rating_preflight の重複 submit 確認に使用できる。"
        ),
    ),
    items_limit: int = typer.Option(500, "--limit", min=1, max=500, help="Item page size (--items 時)"),
    items_offset: int = typer.Option(0, "--offset", min=0, help="Item rows to skip (--items 時)"),
    item_status: str | None = typer.Option(
        None, "--item-status", help="Filter items by status (--items 時)"
    ),
) -> None:
    """Show Provider Batch job status.

    --items を付けると provider batch items (job 配下の per-image item) を表示する。
    rating_preflight で同一 image_id が別 job に重複投入されていないかの確認にも使える。
    """
    with command_boundary():
        container = _activate_project(project)
        job = (
            container.provider_batch_workflow_service.refresh(job_id)
            if refresh
            else container.db_manager.provider_batch_repo.get_provider_batch_job(job_id)
        )
        if job is None:
            raise click.UsageError(f"Provider Batch job not found: {job_id}")

        fetched_items: list[Any] = []
        if show_items:
            fetched_items = container.db_manager.provider_batch_repo.list_provider_batch_items(
                job_id,
                status=item_status,
                limit=items_limit,
                offset=items_offset,
            )

        if is_json_mode():
            if show_items:
                for item in fetched_items:
                    emit_item(_item_dict(item))
            has_more = len(fetched_items) >= items_limit if show_items else None
            emit_result(
                f"Provider Batch job {job_id}",
                job=_job_dict(job),
                items_count=len(fetched_items) if show_items else None,
                items_limit=items_limit if show_items else None,
                items_offset=items_offset if show_items else None,
                items_has_more=has_more,
            )
        else:
            _print_job_detail(job)
            if show_items:
                _print_items_table(fetched_items, job_id)


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


def _get_rating_breakdown(container: Any, job_id: int) -> dict[str, int]:
    """rating_preflight job の image_id セットに対する normalized_rating 別件数を返す。

    job の items を最大 500 件取得し、task_type が rating_preflight の image_id を抽出する。
    500 件超の job では最初の 500 件で近似する（CLI 上限 = 500）。
    """
    items = container.db_manager.provider_batch_repo.list_provider_batch_items(job_id, limit=500)
    task_types = {_item_value(item, "task_type") for item in items}
    if "rating_preflight" not in task_types:
        return {}

    image_ids = [
        _item_value(item, "image_id") for item in items if _item_value(item, "image_id") is not None
    ]
    if not image_ids:
        return {}

    return container.db_manager.annotation_repo.get_rating_breakdown_for_images(image_ids)


def _print_rating_breakdown(breakdown: dict[str, int], total: int) -> None:
    table = Table(title="Rating Breakdown")
    table.add_column("Rating", style="cyan")
    table.add_column("Count", justify="right", style="green")
    rating_order = ["PG", "PG-13", "R", "X", "XXX"]
    shown: set[str] = set()
    for rating in rating_order:
        if rating in breakdown:
            table.add_row(rating, str(breakdown[rating]))
            shown.add(rating)
    for rating in sorted(breakdown):
        if rating not in shown:
            table.add_row(rating, str(breakdown[rating]))
    console.print(table)
    console.print(f"[dim]Ratings saved: {total}[/dim]")


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
        rating_breakdown = _get_rating_breakdown(container, job_id)
        ratings_saved = sum(rating_breakdown.values())

        if is_json_mode():
            emit_result(
                f"Provider Batch results imported: {job_id}",
                job_id=job_id,
                imported=result.imported_count,
                skipped=result.skipped_count,
                errors=result.error_count,
                total=result.total_count,
                job_imported=result.job_imported,
                ratings_saved=ratings_saved if rating_breakdown else None,
                rating_breakdown=rating_breakdown if rating_breakdown else None,
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
            if rating_breakdown:
                _print_rating_breakdown(rating_breakdown, ratings_saved)
