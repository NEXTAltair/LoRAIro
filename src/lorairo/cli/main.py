"""CLIアプリケーションエントリポイント。

Typer ベースの CLI フレームワークで LoRAIro コマンドを実装。
"""

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from lorairo.cli.commands import project, images

# Typer app 定義
app = typer.Typer(
    name="lorairo",
    help="LoRAIro - AI-powered image annotation and dataset management",
    add_completion=True,
    no_args_is_help=True,
)

# Rich console（カラー出力・テーブル表示用）
console = Console()

# ===== サブコマンドグループ登録 =====
app.add_typer(project.app, name="project", help="Project management commands")
app.add_typer(images.app, name="images", help="Image management commands")


# ===== トップレベルコマンド =====
@app.command()
def version() -> None:
    """Show version information."""
    console.print("[bold cyan]LoRAIro CLI[/bold cyan] v0.0.8")
    console.print("[dim]AI-powered image annotation and dataset management[/dim]")


@app.command()
def status() -> None:
    """Show system status."""
    try:
        from lorairo.services.service_container import get_service_container

        container = get_service_container()

        # サービス情報テーブル
        table = Table(title="Service Status")
        table.add_column("Service", style="cyan")
        table.add_column("Status", style="green")

        summary = container.get_service_summary()

        # initialized_services セクションを表示
        if "initialized_services" in summary:
            for service, is_initialized in summary["initialized_services"].items():
                status_str = "✓ Ready" if is_initialized else "✗ Not Ready"
                table.add_row(service, status_str)

        console.print(table)

        # その他の情報も表示
        console.print(f"\n[dim]Environment:[/dim] {summary.get('environment', 'Unknown')}")
        console.print(f"[dim]Phase:[/dim] {summary.get('phase', 'Unknown')}")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


def main() -> None:
    """CLIメインエントリポイント。"""
    app()


if __name__ == "__main__":
    main()
