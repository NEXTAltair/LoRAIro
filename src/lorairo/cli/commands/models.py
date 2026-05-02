"""Model registry commands."""

from __future__ import annotations

from enum import StrEnum

import typer
from rich.console import Console
from rich.table import Table

from lorairo.services.service_container import get_service_container
from lorairo.utils.log import logger

app = typer.Typer(help="Model registry commands")
console = Console()


class ModelTypeFilter(StrEnum):
    """`models list` の `--type` フィルタ値。"""

    all = "all"
    webapi = "webapi"
    local = "local"


class ModelCategoryFilter(StrEnum):
    """`models list` の `--category` フィルタ値 (AnnotatorInfo.model_type に対応)。"""

    all = "all"
    tagger = "tagger"
    scorer = "scorer"
    captioner = "captioner"
    vision = "vision"


@app.command("refresh")
def refresh(
    project: str | None = typer.Option(
        None,
        "--project",
        "-p",
        help="Project to sync model metadata into. Uses default DB when omitted.",
    ),
) -> None:
    """Refresh available WebAPI models."""
    try:
        container = get_service_container()
        if project is not None:
            container.set_active_project(project)
        console.print("[cyan]Refreshing model registry...[/cyan]")
        models = container.annotator_library.refresh_available_models(force_refresh=True)
        sync_result = container.model_sync_service.sync_available_models()

        if sync_result.errors:
            console.print("[red]Error:[/red] Model registry refreshed but DB sync failed.")
            console.print(sync_result.summary)
            for error in sync_result.errors:
                console.print(f"[red]Sync error:[/red] {error}")
            raise typer.Exit(code=1)

        console.print(f"[green]Model registry refreshed.[/green] {len(models)} model(s) discovered.")
        console.print(sync_result.summary)
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error:[/red] Failed to refresh models: {e}")
        logger.error(f"Model refresh command failed: {e}", exc_info=True)
        raise typer.Exit(code=1) from e


@app.command("list")
def list_models(
    include_deprecated: bool = typer.Option(
        False,
        "--include-deprecated",
        help="Include deprecated WebAPI models",
    ),
    type_filter: ModelTypeFilter = typer.Option(
        ModelTypeFilter.all,
        "--type",
        case_sensitive=False,
        help="Filter by execution type (all / webapi / local)",
    ),
    category: ModelCategoryFilter = typer.Option(
        ModelCategoryFilter.all,
        "--category",
        case_sensitive=False,
        help="Filter by model category (all / tagger / scorer / captioner / vision)",
    ),
) -> None:
    """List available annotator models (WebAPI + local)."""
    try:
        container = get_service_container()
        annotator = container.annotator_library
        infos = annotator.list_annotator_info()

        rows: list[tuple[str, str, str, bool]] = []
        for info in infos:
            if type_filter is ModelTypeFilter.webapi and not info.is_api:
                continue
            if type_filter is ModelTypeFilter.local and not info.is_local:
                continue
            if category is not ModelCategoryFilter.all and info.model_type != category.value:
                continue

            try:
                deprecated = annotator.is_model_deprecated(info.name)
            except Exception as e:
                logger.warning(f"Deprecated check failed for {info.name}: {e}")
                deprecated = False

            if deprecated and not include_deprecated:
                continue

            type_label = "webapi" if info.is_api else "local"
            rows.append((info.name, type_label, info.model_type, deprecated))

        table = Table(title="Available Models")
        table.add_column("Model", style="cyan", no_wrap=True)
        table.add_column("Type", style="magenta")
        table.add_column("Category", style="blue")
        table.add_column("Status", style="green")

        for name, type_label, model_category, deprecated in rows:
            table.add_row(
                name,
                type_label,
                model_category,
                "[yellow]deprecated[/yellow]" if deprecated else "active",
            )

        console.print(table)
        console.print(f"[dim]{len(rows)} model(s)[/dim]")
    except Exception as e:
        console.print(f"[red]Error:[/red] Failed to list models: {e}")
        logger.error(f"Model list command failed: {e}", exc_info=True)
        raise typer.Exit(code=1) from e
