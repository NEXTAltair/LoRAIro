"""Project management commands.

プロジェクトの作成、一覧表示、削除などの管理コマンド。
"""

import shutil
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

# サブコマンドアプリ定義
app = typer.Typer(help="Project management commands")

# Rich console（出力用）
console = Console()

# プロジェクトディレクトリのベースパス
PROJECTS_BASE_DIR = Path.home() / ".lorairo" / "projects"


def _get_projects_directory() -> Path:
    """プロジェクトディレクトリを取得。

    Returns:
        Path: プロジェクトディレクトリ
    """
    return PROJECTS_BASE_DIR


def _list_projects() -> list[dict[str, str]]:
    """プロジェクト一覧を取得。

    Returns:
        list[dict[str, str]]: プロジェクト情報リスト
    """
    projects: list[dict[str, str]] = []
    projects_dir = _get_projects_directory()

    if not projects_dir.exists():
        return projects

    for proj_dir in sorted(projects_dir.iterdir()):
        if proj_dir.is_dir() and "_" in proj_dir.name:
            # ディレクトリ名から日付とプロジェクト名を抽出
            db_file = proj_dir / "image_database.db"
            if db_file.exists():
                parts = proj_dir.name.rsplit("_", 1)
                if len(parts) == 2:
                    project_name, date_seq = parts
                    projects.append(
                        {
                            "name": project_name,
                            "created": date_seq,
                            "path": str(proj_dir),
                        }
                    )

    return projects


@app.command("create")
def create(
    name: str = typer.Argument(..., help="Project name"),
    description: str = typer.Option("", "--description", "-d", help="Project description"),
) -> None:
    """Create a new project."""
    try:
        projects_dir = _get_projects_directory()
        projects_dir.mkdir(parents=True, exist_ok=True)

        # プロジェクトディレクトリ名の生成（名前_日付）
        now = datetime.now()
        date_str = now.strftime("%Y%m%d_%H%M%S")
        project_dir = projects_dir / f"{name}_{date_str}"

        # 既に存在する場合はエラー
        if project_dir.exists():
            console.print(f"[red]Error:[/red] Project already exists: {name}")
            raise typer.Exit(code=1)

        # プロジェクトディレクトリの作成
        project_dir.mkdir(parents=True, exist_ok=True)

        # image_dataset ディレクトリの作成
        image_dataset_dir = project_dir / "image_dataset"
        image_dataset_dir.mkdir(exist_ok=True)
        (image_dataset_dir / "original_images").mkdir(exist_ok=True)

        # .lorairo-project ファイル（メタデータ）の作成
        metadata = {
            "name": name,
            "created": date_str,
            "description": description,
        }
        import json

        metadata_file = project_dir / ".lorairo-project"
        metadata_file.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

        console.print(f"[green]✓[/green] Project created: [bold]{name}[/bold]")
        console.print(f"[dim]Location: {project_dir}[/dim]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e


@app.command("list")
def list_projects(
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format: table/json",
    ),
) -> None:
    """List all projects."""
    try:
        import json

        projects = _list_projects()

        if format == "json":
            console.print(json.dumps(projects, indent=2, ensure_ascii=False))
        else:
            # Rich テーブル表示
            if not projects:
                console.print("[yellow]No projects found[/yellow]")
                return

            table = Table(title="Projects")
            table.add_column("Name", style="cyan")
            table.add_column("Created", style="magenta")
            table.add_column("Path", style="dim")

            for proj in projects:
                table.add_row(proj["name"], proj["created"], proj["path"])

            console.print(table)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e


@app.command("delete")
def delete(
    name: str = typer.Argument(..., help="Project name to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Force delete without confirmation"),
) -> None:
    """Delete a project."""
    try:
        projects_dir = _get_projects_directory()
        project_dir = None

        # プロジェクトディレクトリを検索
        if projects_dir.exists():
            for proj_dir in projects_dir.iterdir():
                if proj_dir.is_dir() and proj_dir.name.startswith(name + "_"):
                    project_dir = proj_dir
                    break

        if not project_dir:
            console.print(f"[red]Error:[/red] Project not found: {name}")
            raise typer.Exit(code=1)

        # 確認（--force がない場合）
        if not force:
            confirm = typer.confirm(f"Delete project '{name}' at {project_dir}? This cannot be undone.")
            if not confirm:
                console.print("[yellow]Cancelled[/yellow]")
                raise typer.Exit(code=0)

        # 削除
        shutil.rmtree(project_dir)
        console.print(f"[green]✓[/green] Project deleted: [bold]{name}[/bold]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e
