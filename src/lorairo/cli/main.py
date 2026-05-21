"""CLIアプリケーションエントリポイント。

Typer ベースの CLI フレームワークで LoRAIro コマンドを実装。
"""

from __future__ import annotations

# Issue #254: 他モジュール (typer / rich / loguru / commands → image-annotator-lib /
# LiteLLM) の import より前に stdio reconfigure / Windows console code page 切替 /
# LiteLLM 抑制 / loguru default sink 削除を行う。順序を変えると import 時 mojibake が
# 再発するため、本 import + early_init() 呼び出しは module 先頭から動かさない。
from lorairo.cli._early_init import early_init

early_init()

from typing import TYPE_CHECKING, Any

import typer
from rich.table import Table

from lorairo.cli._console import make_console
from lorairo.cli._glyphs import FAIL, OK
from lorairo.cli.commands import annotate, export, images, models, project
from lorairo.services.service_container import get_service_container
from lorairo.utils.config import DEFAULT_CLI_LOG_PATH, DEFAULT_CONFIG_PATH
from lorairo.utils.log import initialize_logging

if TYPE_CHECKING:
    from lorairo.services.service_container import ServiceContainer

# Typer app 定義
app = typer.Typer(
    name="lorairo",
    help=(
        "LoRAIro - AI-powered image annotation and dataset management\n\n"
        "Typical workflow:\n\n"
        "  1. lorairo-cli project create <name>\n\n"
        "  2. lorairo-cli images register <dir> --project <name>\n\n"
        "  3. lorairo-cli models list  (confirm model names)\n\n"
        "  4. lorairo-cli annotate run --project <name> --model <model>\n\n"
        "  5. lorairo-cli export create --project <name> --tags <tag> --output <dir>"
    ),
    add_completion=True,
    no_args_is_help=True,
)

# Rich console (Issue #254: Windows では safe_box=True で ASCII 罫線)
console = make_console()

# ===== サブコマンドグループ登録 =====
app.add_typer(project.app, name="project", help="Project management commands")
app.add_typer(images.app, name="images", help="Image management commands")
app.add_typer(annotate.app, name="annotate", help="Annotation commands")
app.add_typer(export.app, name="export", help="Dataset export commands")
app.add_typer(models.app, name="models", help="Model registry commands")


# ===== トップレベルコマンド =====
@app.command()
def version() -> None:
    """Show version information."""
    console.print("[bold cyan]LoRAIro CLI[/bold cyan] v0.0.8")
    console.print("[dim]AI-powered image annotation and dataset management[/dim]")


def _show_cli_status(container: ServiceContainer) -> None:
    """CLIモードのステータス表示。設定ファイルとAPIキー状況を表示する。"""
    table = Table(title="LoRAIro CLI Status")
    table.add_column("Item", style="cyan")
    table.add_column("Status", style="green")

    config_file_found = DEFAULT_CONFIG_PATH.exists()
    table.add_row("Config File", f"{OK} Found" if config_file_found else f"{FAIL} Not Found")

    if config_file_found:
        config = container.config_service
        api_providers = {
            "OpenAI": config.get_setting("api", "openai_key", ""),
            "Anthropic": config.get_setting("api", "claude_key", ""),
            "Google": config.get_setting("api", "google_key", ""),
        }
        for provider, key in api_providers.items():
            configured = bool(key and key.strip())
            table.add_row(f"API Key ({provider})", f"{OK} Configured" if configured else f"{FAIL} Not set")

    console.print(table)
    console.print("\n[dim]Services initialize on demand when commands are executed.[/dim]")
    console.print("[dim]Use 'lorairo-cli --help' to see available commands.[/dim]")


def _show_gui_status(summary: dict[str, Any]) -> None:
    """GUIモードのステータス表示。サービス初期化状況テーブルを表示する。"""
    table = Table(title="Service Status")
    table.add_column("Service", style="cyan")
    table.add_column("Status", style="green")

    if "initialized_services" in summary:
        for service, is_initialized in summary["initialized_services"].items():
            status_str = f"{OK} Ready" if is_initialized else f"{FAIL} Not Ready"
            table.add_row(service, status_str)

    console.print(table)


@app.command()
def status() -> None:
    """Show system status."""
    try:
        container = get_service_container()
        summary = container.get_service_summary()
        environment = summary.get("environment", "Unknown")

        console.print(f"[dim]Environment:[/dim] {environment}")
        console.print(f"[dim]Phase:[/dim] {summary.get('phase', 'Unknown')}\n")

        if environment == "CLI":
            _show_cli_status(container)
        else:
            _show_gui_status(summary)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e


def main() -> None:
    """CLIメインエントリポイント。

    ServiceContainer が NoOpSignalManager を自動選択するよう
    LORAIRO_CLI_MODE を設定してから app を起動する。
    stdio 初期化は module top-level の ``early_init()`` で完了済。
    """
    import os

    os.environ.setdefault("LORAIRO_CLI_MODE", "true")
    initialize_logging(
        {
            "level": "WARNING",  # CLI モード: DEBUG/INFO を抑制
            "file_path": str(DEFAULT_CLI_LOG_PATH),
            "rotation": "25 MB",
            "levels": {},
        }
    )
    app()


if __name__ == "__main__":
    main()
