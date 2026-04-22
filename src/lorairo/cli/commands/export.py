"""Dataset export commands.

データセット エクスポート コマンド。
API層（lorairo.api）を経由してService層を利用する。
"""

from pathlib import Path

import click
import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn
from rich.table import Table

from lorairo.api.exceptions import (
    ProjectNotFoundError,
)
from lorairo.api.project import get_project as api_get_project
from lorairo.database.filter_criteria import ImageFilterCriteria
from lorairo.services.service_container import get_service_container
from lorairo.utils.log import logger

# サブコマンドアプリ定義
app = typer.Typer(help="Dataset export commands")

# Rich console（出力用）
console = Console()

# 手動・AI レーティング共通の有効値（Civitai 基準 + UNRATED）
VALID_RATINGS = {"PG", "PG-13", "R", "X", "XXX", "UNRATED"}


def _validate_rating(ctx: click.Context, param: click.Parameter, value: str | None) -> str | None:
    """レーティング値を検証し正規化する。

    Args:
        ctx: Click コンテキスト。
        param: Click パラメーター。
        value: 入力されたレーティング値。

    Returns:
        正規化されたレーティング値（大文字）。

    Raises:
        click.BadParameter: 無効なレーティング値が指定された場合（exit_code=2）。
    """
    if value is None:
        return None
    normalized = value.upper()
    if normalized not in VALID_RATINGS:
        raise click.BadParameter(
            f"有効な値: {', '.join(sorted(VALID_RATINGS))}",
            ctx=ctx,
            param=param,
        )
    return normalized


def _build_filter_criteria(
    tags: str | None,
    excluded_tags: str | None,
    caption: str | None,
    manual_rating: str | None,
    ai_rating: str | None,
    include_nsfw: bool,
    score_min: float | None,
    score_max: float | None,
) -> ImageFilterCriteria:
    """CLI引数から ImageFilterCriteria を生成する。

    Args:
        tags: カンマ区切りのタグ文字列。
        excluded_tags: カンマ区切りの除外タグ文字列。
        caption: キャプションテキストフィルター。
        manual_rating: 手動レーティングフィルター。
        ai_rating: AI評価レーティングフィルター。
        include_nsfw: NSFWコンテンツを含めるかどうか。
        score_min: 最小スコア値。
        score_max: 最大スコア値。

    Returns:
        構築した ImageFilterCriteria。
    """
    tags_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    excluded_tags_list = (
        [t.strip() for t in excluded_tags.split(",") if t.strip()] if excluded_tags else None
    )
    return ImageFilterCriteria(
        tags=tags_list,
        excluded_tags=excluded_tags_list,
        caption=caption,
        manual_rating_filter=manual_rating,
        ai_rating_filter=ai_rating,
        include_nsfw=include_nsfw,
        score_min=score_min,
        score_max=score_max,
    )


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
    tags: str | None = typer.Option(
        None,
        "--tags",
        help="Comma-separated tag filter (e.g. 'cat,dog')",
    ),
    excluded_tags: str | None = typer.Option(
        None,
        "--excluded-tags",
        help="Comma-separated tags to exclude from results",
    ),
    caption: str | None = typer.Option(
        None,
        "--caption",
        help="Caption text filter",
    ),
    manual_rating: str | None = typer.Option(
        None,
        "--manual-rating",
        help="Manual rating filter: PG / PG-13 / R / X / XXX / UNRATED",
        callback=_validate_rating,
    ),
    ai_rating: str | None = typer.Option(
        None,
        "--ai-rating",
        help="AI rating filter: PG / PG-13 / R / X / XXX / UNRATED",
        callback=_validate_rating,
    ),
    include_nsfw: bool = typer.Option(
        False,
        "--include-nsfw",
        help="Include NSFW content in export",
    ),
    score_min: float | None = typer.Option(
        None,
        "--score-min",
        help="Minimum score filter (0.0-10.0)",
    ),
    score_max: float | None = typer.Option(
        None,
        "--score-max",
        help="Maximum score filter (0.0-10.0)",
    ),
) -> None:
    """Create a dataset export from project.

    プロジェクトからデータセットをエクスポートします。
    最低1つのフィルタ条件（--tags, --caption, --manual-rating, --ai-rating,
    --score-min, --score-max）を指定する必要があります。
    """
    try:
        # API層経由でプロジェクト確認
        try:
            api_get_project(project)
        except ProjectNotFoundError as e:
            console.print(f"[red]Error:[/red] Project not found: {project}")
            raise typer.Exit(code=1) from e

        # フィルタ条件バリデーション（フィルタなしは学習用途として無効）
        has_filter = any(
            [
                tags is not None,
                excluded_tags is not None,
                caption is not None,
                manual_rating is not None,
                ai_rating is not None,
                score_min is not None,
                score_max is not None,
            ]
        )
        if not has_filter:
            console.print("[red]Error:[/red] エクスポートには最低1つのフィルタ条件が必要です")
            console.print("例: lorairo-cli export create --project foo --tags cat --output /tmp/out")
            console.print("詳細: lorairo-cli export create --help")
            raise typer.Exit(code=2)

        # フィルタ条件を構築
        criteria = _build_filter_criteria(
            tags=tags,
            excluded_tags=excluded_tags,
            caption=caption,
            manual_rating=manual_rating,
            ai_rating=ai_rating,
            include_nsfw=include_nsfw,
            score_min=score_min,
            score_max=score_max,
        )

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

        # フィルタ条件を適用して画像を取得
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.1f}%"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("画像情報取得中...", total=None)

            all_images, _ = repository.get_images_by_filter(criteria)
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
