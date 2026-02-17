"""Project management commands.

プロジェクトの作成、一覧表示、削除などの管理コマンド。
API層（lorairo.api）を経由してService層を利用する。
"""

import typer
from rich.console import Console
from rich.table import Table

from lorairo.api.exceptions import (
    ProjectAlreadyExistsError,
    ProjectNotFoundError,
    ProjectOperationError,
)
from lorairo.api.project import (
    create_project as api_create_project,
)
from lorairo.api.project import (
    delete_project as api_delete_project,
)
from lorairo.api.project import (
    list_projects as api_list_projects,
)
from lorairo.api.types import ProjectCreateRequest

# サブコマンドアプリ定義
app = typer.Typer(help="Project management commands")

# Rich console（出力用）
console = Console()


@app.command("create")
def create(
    name: str = typer.Argument(..., help="Project name"),
    description: str = typer.Option("", "--description", "-d", help="Project description"),
) -> None:
    """Create a new project."""
    try:
        request = ProjectCreateRequest(name=name, description=description or None)
        project = api_create_project(request)
        console.print(f"[green]✓[/green] Project created: [bold]{project.name}[/bold]")
        console.print(f"[dim]Location: {project.path}[/dim]")

    except ProjectAlreadyExistsError as e:
        console.print(f"[red]Error:[/red] Project already exists: {name}")
        raise typer.Exit(code=1) from e
    except (ProjectOperationError, ValueError) as e:
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

        projects = api_list_projects()

        if format == "json":
            projects_data = [
                {
                    "name": p.name,
                    "created": p.created.strftime("%Y%m%d_%H%M%S") if p.created else "",
                    "path": str(p.path),
                }
                for p in projects
            ]
            console.print(json.dumps(projects_data, indent=2, ensure_ascii=False), soft_wrap=True)
        else:
            if not projects:
                console.print("[yellow]No projects found[/yellow]")
                return

            table = Table(title="Projects")
            table.add_column("Name", style="cyan")
            table.add_column("Created", style="magenta")
            table.add_column("Path", style="dim")

            for proj in projects:
                created_str = proj.created.strftime("%Y%m%d_%H%M%S") if proj.created else ""
                table.add_row(proj.name, created_str, str(proj.path))

            console.print(table)

    except ProjectOperationError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e


@app.command("delete")
def delete(
    name: str = typer.Argument(..., help="Project name to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Force delete without confirmation"),
) -> None:
    """Delete a project."""
    try:
        if not force:
            confirm = typer.confirm(f"Delete project '{name}'? This cannot be undone.")
            if not confirm:
                console.print("[yellow]Cancelled[/yellow]")
                raise typer.Exit(code=0)

        api_delete_project(name)
        console.print(f"[green]✓[/green] Project deleted: [bold]{name}[/bold]")

    except ProjectNotFoundError as e:
        console.print(f"[red]Error:[/red] Project not found: {name}")
        raise typer.Exit(code=1) from e
    except ProjectOperationError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e
