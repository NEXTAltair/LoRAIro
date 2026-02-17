"""Dataset export commands.

データセット エクスポート コマンド。
API層（lorairo.api）を経由してService層を利用する。
"""

from pathlib import Path

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn
from rich.table import Table

from lorairo.api.exceptions import (
    ExportFailedError,
    InvalidFormatError,
    ProjectNotFoundError,
)
from lorairo.api.project import get_project as api_get_project
from lorairo.services.service_container import get_service_container
from lorairo.utils.log import logger

# サブコマンドアプリ定義
app = typer.Typer(help="Dataset export commands")

# Rich console（出力用）
console = Console()


@app.command("create")
def create(
    project: str = typer.Option(
        ...,
        "--project",
        "-p",
        help="Project name",
    ),
    output: str = typer.Option(
        ...,
        "--output",
        "-o",
        help="Output directory for exported dataset",
    ),
    format: str = typer.Option(
        "txt",
        "--format",
        "-f",
        help="Export format: txt or json",
    ),
    resolution: int = typer.Option(
        512,
        "--resolution",
        "-r",
        help="Target resolution for processed images",
    ),
) -> None:
    """Create a dataset export from project.

    プロジェクトからデータセットをエクスポートします。
    """
    try:
        # API層経由でプロジェクト確認
        try:
            api_get_project(project)
        except ProjectNotFoundError as e:
            console.print(f"[red]Error:[/red] Project not found: {project}")
            raise typer.Exit(code=1) from e

        # ServiceContainer を取得
        container = get_service_container()
        repository = container.image_repository
        export_service = container.dataset_export_service

        console.print(f"[cyan]Loading project database: {project}[/cyan]")

        # NOTE: Current architecture limitation - LoRAIro initializes database globally
        # through db_core.py. For now, we work with the currently configured database.
        console.print(
            "[yellow]Note:[/yellow] Working with currently configured database. "
            "Ensure config/lorairo.toml points to the correct project."
        )

        # 全画像を取得
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.1f}%"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("画像情報取得中...", total=None)

            # 全画像IDを取得（フィルター条件なしで全画像を取得）
            all_images, _ = repository.get_images_by_filter()
            image_ids = [img["id"] for img in all_images] if all_images else []

            progress.update(task, completed=1)

        if not image_ids:
            console.print(f"[yellow]Warning:[/yellow] No images found in project: {project}")
            raise typer.Exit(code=0)

        console.print(f"[cyan]Found {len(image_ids)} image(s)[/cyan]")
        console.print(f"[cyan]Export format: {format}[/cyan]")
        console.print(f"[cyan]Target resolution: {resolution}px[/cyan]")

        # 出力ディレクトリの作成
        output_path = Path(output)
        output_path.mkdir(parents=True, exist_ok=True)

        # データセット エクスポート実行
        console.print("[cyan]Starting export...[/cyan]")

        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.1f}%"),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("エクスポート中...", total=len(image_ids))

                # エクスポート実行
                result_path = export_service.export_filtered_dataset(
                    image_ids,
                    output_path,
                    format_type=format.lower(),
                    resolution=resolution,
                )

                # 完了時に進捗を100%に
                progress.update(task, completed=len(image_ids))

        except ValueError as e:
            console.print(f"[red]Error:[/red] Invalid export format: {e}")
            logger.error(f"Export format error: {e}", exc_info=True)
            raise typer.Exit(code=1) from e
        except Exception as e:
            console.print(f"[red]Error:[/red] Export failed: {e}")
            logger.error(f"Export error: {e}", exc_info=True)
            raise typer.Exit(code=1) from e

        # 結果サマリー表示
        console.print("\n[bold cyan]Export Summary[/bold cyan]")

        summary_table = Table()
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green")

        summary_table.add_row("Total Images", str(len(image_ids)))
        summary_table.add_row("Export Format", format)
        summary_table.add_row("Resolution", f"{resolution}px")
        summary_table.add_row("Output Path", str(result_path))

        console.print(summary_table)

        console.print("\n[green]Export completed successfully![/green]")

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        logger.error(f"Command error: {e}", exc_info=True)
        raise typer.Exit(code=2) from e
