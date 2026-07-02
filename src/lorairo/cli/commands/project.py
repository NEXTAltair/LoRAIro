"""Project management commands.

プロジェクトの作成、一覧表示、削除などの管理コマンド。
API層（lorairo.public_api）を経由してService層を利用する。

出力は ADR 0057/0058 に従う: ``--json`` 時は stdout に JSONL (item/result)、
それ以外は rich 人間向け。エラー整形は :func:`lorairo.cli._boundary.command_boundary`
に集約し、本モジュールは型付き例外を伝播するだけにする。
"""

import click
import typer
from rich.table import Table

from lorairo.cli._boundary import command_boundary
from lorairo.cli._console import make_console
from lorairo.cli._emit import emit_item, emit_result
from lorairo.cli._glyphs import OK
from lorairo.cli._output_mode import is_json_mode
from lorairo.public_api.project import (
    create_project as api_create_project,
)
from lorairo.public_api.project import (
    delete_project as api_delete_project,
)
from lorairo.public_api.project import (
    list_projects as api_list_projects,
)
from lorairo.public_api.types import ProjectCreateRequest

# サブコマンドアプリ定義
app = typer.Typer(help="Project management commands")

# Rich console (Issue #254: Windows では safe_box=True で ASCII 罫線)
console = make_console()


@app.command("create")
def create(
    name: str = typer.Argument(..., help="Project name"),
    description: str = typer.Option("", "--description", "-d", help="Project description"),
) -> None:
    """Create a new project."""
    with command_boundary():
        request = ProjectCreateRequest(name=name, description=description or None)
        project = api_create_project(request)
        if is_json_mode():
            emit_result(
                f"Project created: {project.name}",
                name=project.name,
                path=str(project.path),
            )
        else:
            console.print(f"[green]{OK}[/green] Project created: [bold]{project.name}[/bold]")
            console.print(f"[dim]Location: {project.path}[/dim]")


@app.command("list")
def list_projects(
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Human-readable format (table)。機械可読出力はグローバル --json を使う (ADR 0057/0058)。",
    ),
) -> None:
    """List all projects.

    人間向けは rich テーブル (``--format table``、既定)。機械可読出力は
    グローバル ``--json`` フラグで JSONL (item/result) を取得する (ADR 0057/0058)。
    legacy な ``--format json`` (pretty 配列) は非推奨 (ADR 0058)。
    """
    with command_boundary():
        projects = api_list_projects()

        if is_json_mode():
            for proj in projects:
                emit_item(
                    {
                        "name": proj.name,
                        "created": proj.created.strftime("%Y%m%d_%H%M%S") if proj.created else "",
                        "path": str(proj.path),
                    }
                )
            emit_result(f"{len(projects)} project(s) found", count=len(projects))
            return

        if format == "json":
            # ADR 0058: legacy `--format json` (pretty 配列) は非推奨。機械可読出力の
            # SSoT はグローバル `--json` (JSONL) に一本化済みのため、案内して table を出す。
            console.print(
                "[yellow]--format json は非推奨です。機械可読出力はグローバル --json を使ってください。[/yellow]"
            )

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


@app.command("delete")
def delete(
    name: str = typer.Argument(..., help="Project name to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Force delete without confirmation"),
) -> None:
    """Delete a project."""
    with command_boundary():
        if not force:
            # JSON mode は対話 confirm のプロンプトを stdout に書けない (JSONL 純度を
            # 破る、ADR 0057 §1)。stdin で応答できない agent driving 前提なので、JSON mode
            # では --force を契約上必須とし、未指定は INVALID_INPUT で弾く (Issue #659)。
            if is_json_mode():
                raise click.UsageError("project delete requires --force in JSON mode")
            confirm = typer.confirm(f"Delete project '{name}'? This cannot be undone.")
            if not confirm:
                console.print("[yellow]Cancelled[/yellow]")
                return

        api_delete_project(name)
        if is_json_mode():
            emit_result(f"Project deleted: {name}", name=name)
        else:
            console.print(f"[green]{OK}[/green] Project deleted: [bold]{name}[/bold]")
