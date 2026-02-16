"""Image management commands.

画像の登録、メタデータ更新などの画像管理コマンド。
"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from rich.table import Table

from lorairo.cli.commands import project as project_module

# サブコマンドアプリ定義
app = typer.Typer(help="Image management commands")

# Rich console（出力用）
console = Console()


def _get_image_files(directory: Path) -> list[Path]:
    """ディレクトリから画像ファイルを取得。

    Args:
        directory: 検索対象ディレクトリ

    Returns:
        list[Path]: 画像ファイルのパスリスト
    """
    image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
    image_files = []

    if not directory.exists():
        return image_files

    for ext in image_extensions:
        image_files.extend(directory.glob(f"*{ext}"))
        image_files.extend(directory.glob(f"*{ext.upper()}"))

    return sorted(set(image_files))  # 重複排除


def _calculate_phash(image_path: Path) -> Optional[str]:
    """画像のpHashを計算。

    Args:
        image_path: 画像ファイルパス

    Returns:
        Optional[str]: pHash値（16進数文字列）。計算失敗時はNone
    """
    try:
        from PIL import Image
        import imagehash

        img = Image.open(image_path)
        phash = imagehash.phash(img)
        return str(phash)
    except Exception as e:
        console.print(f"[yellow]Warning:[/yellow] pHash計算失敗 {image_path.name}: {e}")
        return None


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
        import json
        from datetime import datetime

        dir_path = Path(directory).resolve()

        # ディレクトリ存在確認
        if not dir_path.exists():
            console.print(f"[red]Error:[/red] Directory not found: {directory}")
            raise typer.Exit(code=1)

        if not dir_path.is_dir():
            console.print(f"[red]Error:[/red] Not a directory: {directory}")
            raise typer.Exit(code=1)

        # 画像ファイルを取得
        image_files = _get_image_files(dir_path)

        if not image_files:
            console.print(f"[yellow]Warning:[/yellow] No image files found in {directory}")
            raise typer.Exit(code=0)

        console.print(f"[cyan]Found {len(image_files)} image(s)[/cyan]")

        # プロジェクトディレクトリを確認
        projects_base = project_module.PROJECTS_BASE_DIR
        project_dir = None

        if projects_base.exists():
            for proj_dir in projects_base.iterdir():
                if proj_dir.is_dir() and proj_dir.name.startswith(project + "_"):
                    project_dir = proj_dir
                    break

        if not project_dir:
            console.print(f"[red]Error:[/red] Project not found: {project}")
            raise typer.Exit(code=1)

        # 登録処理（Progress バー付き）
        registered = 0
        skipped = 0
        errors = 0
        phashs_in_project: set[str] = set()

        # プロジェクト内の既存pHashを読み込み（将来：DB から取得）
        # 今は簡略化して空集合で初期化
        phashs_in_project = set()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.1f}%"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("画像登録中...", total=len(image_files))

            for image_file in image_files:
                try:
                    # pHashを計算
                    phash = _calculate_phash(image_file)

                    if not phash:
                        errors += 1
                        progress.advance(task)
                        continue

                    # 重複チェック
                    if skip_duplicates and phash in phashs_in_project:
                        skipped += 1
                        progress.advance(task)
                        continue

                    # メタデータ作成
                    metadata = {
                        "filename": image_file.name,
                        "size": image_file.stat().st_size,
                        "phash": phash,
                        "registered_at": datetime.now().isoformat(),
                    }

                    # 登録完了カウント
                    registered += 1
                    phashs_in_project.add(phash)

                    progress.advance(task)

                except Exception as e:
                    console.print(f"[red]Error:[/red] {image_file.name}: {e}")
                    errors += 1
                    progress.advance(task)

        # サマリー表示
        console.print("\n[bold]Registration Summary[/bold]")
        table = Table(show_header=False)
        table.add_row("Registered", f"[green]{registered}[/green]")
        table.add_row("Skipped (duplicates)", f"[yellow]{skipped}[/yellow]")
        table.add_row("Errors", f"[red]{errors}[/red]")
        console.print(table)

        if registered > 0:
            console.print(f"\n[green]✓[/green] Images registered to project: {project}")

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@app.command("list")
def list_images(
    project: str = typer.Option(
        ...,
        "--project",
        "-p",
        help="Project name",
    ),
    limit: Optional[int] = typer.Option(
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
    tags: Optional[str] = typer.Option(
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
