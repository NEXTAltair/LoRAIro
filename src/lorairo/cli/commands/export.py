"""Dataset export commands.

データセット エクスポート コマンド。
"""

from pathlib import Path

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn
from rich.table import Table

from lorairo.cli.commands import project as project_module
from lorairo.services.service_container import get_service_container
from lorairo.utils.log import logger

# サブコマンドアプリ定義
app = typer.Typer(help="Dataset export commands")

# Rich console（出力用）
console = Console()


def _validate_project_and_db(
    project_name: str,
) -> Path:
    """プロジェクトとデータベースを確認して、プロジェクトディレクトリを返す。

    Args:
        project_name: プロジェクト名

    Returns:
        Path: プロジェクトディレクトリパス

    Raises:
        typer.Exit: プロジェクトまたはDBが見つからない場合
    """
    projects_base = project_module.PROJECTS_BASE_DIR
    project_dir = None

    if projects_base.exists():
        for proj_dir in projects_base.iterdir():
            if proj_dir.is_dir() and proj_dir.name.startswith(project_name + "_"):
                project_dir = proj_dir
                break

    if not project_dir:
        console.print(f"[red]Error:[/red] Project not found: {project_name}")
        raise typer.Exit(code=1)

    db_file = project_dir / "image_database.db"
    if not db_file.exists():
        console.print(
            f"[yellow]Warning:[/yellow] Database not found for project: {project_name}"
        )
        raise typer.Exit(code=1)

    return project_dir


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
        # プロジェクトディレクトリを確認
        _validate_project_and_db(project)

        # ServiceContainer を取得
        container = get_service_container()
        repository = container.image_repository
        export_service = container.dataset_export_service

        console.print(f"[cyan]Loading project database: {project}[/cyan]")

        # NOTE: Current architecture limitation - LoRAIro initializes database globally
        # through db_core.py. For now, we work with the currently configured database.
        # TODO: Future enhancement - support dynamic database switching for multi-project CLI
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
            console.print(
                f"[yellow]Warning:[/yellow] No images found in project: {project}"
            )
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
                task = progress.add_task(
                    "エクスポート中...", total=len(image_ids)
                )

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

        console.print(
            "\n[green]Export completed successfully![/green]"
        )

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        logger.error(f"Command error: {e}", exc_info=True)
        raise typer.Exit(code=2) from e
