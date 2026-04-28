"""Model registry commands."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from lorairo.services.service_container import get_service_container
from lorairo.utils.log import logger

app = typer.Typer(help="Model registry commands")
console = Console()


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
        help="Include deprecated models",
    ),
) -> None:
    """List available WebAPI models."""
    try:
        container = get_service_container()
        annotator = container.annotator_library
        models = annotator.list_available_models(include_deprecated=include_deprecated)

        table = Table(title="Available API Models")
        table.add_column("Model", style="cyan")
        table.add_column("Status", style="green")

        for model in models:
            try:
                deprecated = annotator.is_model_deprecated(model)
            except Exception as e:
                logger.warning(f"Deprecated check failed for {model}: {e}")
                deprecated = False
            if deprecated and not include_deprecated:
                continue
            table.add_row(model, "[yellow]deprecated[/yellow]" if deprecated else "active")

        console.print(table)
        console.print(f"[dim]{len(models)} model(s)[/dim]")
    except Exception as e:
        console.print(f"[red]Error:[/red] Failed to list models: {e}")
        logger.error(f"Model list command failed: {e}", exc_info=True)
        raise typer.Exit(code=1) from e
