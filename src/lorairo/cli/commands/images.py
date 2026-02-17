"""Image management commands.

画像の登録、メタデータ更新などの画像管理コマンド。
API層（lorairo.api）を経由してService層を利用する。
"""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from lorairo.api.exceptions import ImageRegistrationError, ProjectNotFoundError
from lorairo.api.images import register_images as api_register_images
from lorairo.api.project import get_project as api_get_project
from lorairo.api.types import RegistrationResult

# サブコマンドアプリ定義
app = typer.Typer(help="Image management commands")

# Rich console（出力用）
console = Console()


def _print_registration_summary(result: RegistrationResult, project: str) -> None:
    """画像登録結果のサマリーを表示する。

    Args:
        result: 登録結果
        project: プロジェクト名
    """
    console.print("\n[bold]Registration Summary[/bold]")
    table = Table(show_header=False)
    table.add_row("Total", f"{result.total}")
    table.add_row("Registered", f"[green]{result.successful}[/green]")
    table.add_row("Skipped (duplicates)", f"[yellow]{result.skipped}[/yellow]")
    table.add_row("Errors", f"[red]{result.failed}[/red]")
    console.print(table)

    if result.error_details:
        console.print("\n[yellow]Error details:[/yellow]")
        for err in result.error_details:
            console.print(f"  - {err}")

    if result.successful > 0:
        console.print(f"\n[green]✓[/green] Images registered to project: {project}")


@app.command("register")
def register(
    directory: str = typer.Argument(
        ...,
        help="Image directory path",
    ),
    project: str = typer.Option(
        ...,
        "--project",
        "-p",
        help="Project name",
    ),
    skip_duplicates: bool = typer.Option(
        True,
        "--skip-duplicates/--include-duplicates",
        help="Skip duplicate images (detected by pHash)",
    ),
) -> None:
    """Register images from directory to project.

    画像ディレクトリからプロジェクトへ画像を登録します。
    pHashを計算して重複検出を行います。
    """
    try:
        dir_path = Path(directory).resolve()

        # ディレクトリ存在確認
        if not dir_path.exists():
            console.print(f"[red]Error:[/red] Directory not found: {directory}")
            raise typer.Exit(code=1)

        if not dir_path.is_dir():
            console.print(f"[red]Error:[/red] Not a directory: {directory}")
            raise typer.Exit(code=1)

        # プロジェクト存在確認
        try:
            api_get_project(project)
        except ProjectNotFoundError as e:
            console.print(f"[red]Error:[/red] Project not found: {project}")
            raise typer.Exit(code=1) from e

        # API層経由で画像登録
        result = api_register_images(dir_path, skip_duplicates)

        if result.total == 0:
            console.print(f"[yellow]Warning:[/yellow] No image files found in {directory}")
            raise typer.Exit(code=0)

        _print_registration_summary(result, project)

    except ImageRegistrationError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e


@app.command("list")
def list_images(
    project: str = typer.Option(
        ...,
        "--project",
        "-p",
        help="Project name",
    ),
    limit: int | None = typer.Option(
        None,
        "--limit",
        "-l",
        help="Maximum number of images to display",
    ),
) -> None:
    """List images in a project.

    プロジェクト内の画像一覧を表示します（将来実装）。
    """
    console.print("[yellow]Note:[/yellow] images list is not yet implemented")
    console.print("This will show registered images in the project.")


@app.command("update")
def update(
    project: str = typer.Option(
        ...,
        "--project",
        "-p",
        help="Project name",
    ),
    tags: str | None = typer.Option(
        None,
        "--tags",
        help="Tags to add (comma-separated)",
    ),
) -> None:
    """Update image metadata.

    画像のメタデータを更新します（将来実装）。
    """
    console.print("[yellow]Note:[/yellow] images update is not yet implemented")
    if tags:
        console.print(f"Would add tags: {tags}")
