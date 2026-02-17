"""Annotation commands.

アノテーション実行コマンド。
API層（lorairo.api）を経由してService層を利用する。
"""

from pathlib import Path

import typer
from PIL import Image
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from lorairo.api.exceptions import (
    AnnotationFailedError,
    APIKeyNotConfiguredError,
    ProjectNotFoundError,
)
from lorairo.api.project import get_project as api_get_project
from lorairo.services.service_container import get_service_container
from lorairo.utils.log import logger

# サブコマンドアプリ定義
app = typer.Typer(help="Annotation commands")

# Rich console（出力用）
console = Console()


def _load_images(image_dataset_dir: Path) -> tuple[list[Image.Image], int, int]:
    """画像ファイルをロード。

    Args:
        image_dataset_dir: 画像ディレクトリ

    Returns:
        tuple: (PIL画像リスト, ロード成功数, ロード失敗数)
    """
    pil_images: list[Image.Image] = []
    loaded_count = 0
    failed_count = 0

    # 画像ファイルを取得
    image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
    image_files: list[Path] = []
    for ext in image_extensions:
        image_files.extend(image_dataset_dir.glob(f"*{ext}"))
        image_files.extend(image_dataset_dir.glob(f"*{ext.upper()}"))

    image_files = sorted(set(image_files))

    if not image_files:
        return [], 0, 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.1f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("画像ロード中...", total=len(image_files))

        for image_file in image_files:
            try:
                img = Image.open(image_file)
                img.load()
                pil_images.append(img)
                loaded_count += 1
            except Exception as e:
                console.print(f"[yellow]Warning:[/yellow] Failed to load {image_file.name}: {e}")
                failed_count += 1
            progress.advance(task)

    return pil_images, loaded_count, failed_count


@app.command("run")
def run(
    project: str = typer.Option(
        ...,
        "--project",
        "-p",
        help="Project name",
    ),
    model: list[str] = typer.Option(
        ...,
        "--model",
        "-m",
        help="Model name(s) to use for annotation",
    ),
    output: str | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory for annotation results (optional)",
    ),
    batch_size: int = typer.Option(
        10,
        "--batch-size",
        "-b",
        help="Batch size for processing",
    ),
) -> None:
    """Run annotation on project images.

    プロジェクトの画像に対してアノテーションを実行します。
    """
    try:
        # API層経由でプロジェクト確認
        try:
            project_info = api_get_project(project)
        except ProjectNotFoundError as e:
            console.print(f"[red]Error:[/red] Project not found: {project}")
            raise typer.Exit(code=1) from e

        project_dir = project_info.path

        # プロジェクトの画像ディレクトリ
        image_dataset_dir = project_dir / "image_dataset" / "original_images"
        if not image_dataset_dir.exists():
            console.print(f"[red]Error:[/red] Image directory not found: {image_dataset_dir}")
            raise typer.Exit(code=1)

        # 画像をロード
        pil_images, loaded_count, failed_count = _load_images(image_dataset_dir)

        if not pil_images and loaded_count == 0:
            console.print(f"[yellow]Warning:[/yellow] No image files found in {image_dataset_dir}")
            raise typer.Exit(code=0)

        console.print(f"[cyan]Found {loaded_count + failed_count} image(s)[/cyan]")
        console.print(f"[cyan]Using model(s): {', '.join(model)}[/cyan]")
        console.print(f"[green]Loaded {loaded_count} image(s) ({failed_count} failed)[/green]")

        if not pil_images:
            console.print("[red]Error:[/red] No images could be loaded for annotation")
            raise typer.Exit(code=1)

        # ServiceContainer を取得
        container = get_service_container()
        annotator = container.annotator_library
        config = container.config_service

        # APIキー確認
        api_keys = {
            "openai": config.get_setting("api", "openai_key", ""),
            "anthropic": config.get_setting("api", "claude_key", ""),
            "google": config.get_setting("api", "google_key", ""),
        }
        api_keys = {k: v for k, v in api_keys.items() if v and v.strip()}

        if not api_keys:
            console.print(
                "[yellow]Warning:[/yellow] No API keys configured. "
                "Consider setting API keys in config/lorairo.toml"
            )

        # アノテーション実行
        console.print("[cyan]Starting annotation...[/cyan]")

        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.1f}%"),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("アノテーション実行中...", total=len(pil_images))

                results = annotator.annotate(pil_images, model)

                progress.update(task, completed=len(pil_images))

        except Exception as e:
            console.print(f"[red]Error:[/red] Annotation failed: {e}")
            logger.error(f"Annotation error: {e}", exc_info=True)
            raise typer.Exit(code=1) from e

        # 結果サマリー表示
        console.print("\n[bold cyan]Annotation Summary[/bold cyan]")

        summary_table = Table()
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green")

        summary_table.add_row("Total Images", str(len(pil_images)))
        summary_table.add_row("Models Used", ", ".join(model))
        summary_table.add_row("Results", str(len(results)))

        console.print(summary_table)

        console.print("\n[green]Annotation completed successfully![/green]")

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        logger.error(f"Command error: {e}", exc_info=True)
        raise typer.Exit(code=2) from e
