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

import sys
import traceback
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import click
import typer
from rich.table import Table

from lorairo.cli._console import make_console
from lorairo.cli._emit import emit_error
from lorairo.cli._errors import ErrorCode, ErrorInfo, classify_exception, hint_for
from lorairo.cli._glyphs import FAIL, OK
from lorairo.cli._output_mode import resolve_output_mode, set_json_mode
from lorairo.cli.commands import annotate, batch, export, images, models, project
from lorairo.services.service_container import get_service_container
from lorairo.utils.config import DEFAULT_CLI_LOG_PATH, DEFAULT_CONFIG_PATH
from lorairo.utils.log import initialize_logging

if TYPE_CHECKING:
    from lorairo.services.service_container import ServiceContainer


class LogLevel(StrEnum):
    """`--log-level` で指定可能なログレベル。"""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


# Typer app 定義
app = typer.Typer(
    name="lorairo",
    help=(
        "LoRAIro - AI-powered image annotation and dataset management\n\n"
        "Typical workflow:\n\n"
        "  1. lorairo-cli project create <name>\n\n"
        "  2. lorairo-cli images register <dir> --project <name>\n\n"
        "  3. lorairo-cli models refresh --project <name>\n\n"
        "  4. lorairo-cli models list  (confirm model names)\n\n"
        "  5. lorairo-cli annotate run --project <name> --model <model>\n\n"
        "  6. lorairo-cli export create --project <name> --tags <tag> --output <dir>\n\n"
        "Rating workflow with OpenAI moderation:\n\n"
        "  Small sets: lorairo-cli annotate run --project <name> "
        "--model openai/omni-moderation-latest\n\n"
        "  Large sets: lorairo-cli images list --project <name> --unrated\n"
        "              lorairo-cli batch submit --project <name> --task-type rating_preflight "
        "--model openai/omni-moderation-latest --image-id <id>"
    ),
    add_completion=True,
    no_args_is_help=True,
)

# Rich console (Issue #254: Windows では safe_box=True で ASCII 罫線)
console = make_console()
# エラー/人間向け装飾は stderr へ (stdout は機械可読 JSONL 専用、ADR 0057 §1)
console_err = make_console(stderr=True)

# ===== サブコマンドグループ登録 =====
app.add_typer(project.app, name="project", help="Project management commands")
app.add_typer(images.app, name="images", help="Image management commands")
app.add_typer(annotate.app, name="annotate", help="Annotation commands")
app.add_typer(export.app, name="export", help="Dataset export commands")
app.add_typer(models.app, name="models", help="Model registry commands")
app.add_typer(batch.app, name="batch", help="Provider Batch API job commands")


@app.callback()
def _configure(
    log_level: LogLevel = typer.Option(
        LogLevel.INFO,
        "--log-level",
        help="Logging verbosity (DEBUG/INFO/WARNING/ERROR/CRITICAL).",
        case_sensitive=False,
    ),
) -> None:
    """全サブコマンド共通の初期化フック。

    Issue #539: ログレベルを ``--log-level`` で設定可能にする (既定 INFO)。
    Issue #540: ``@app.callback()`` は ``--help`` 時には実行されないため、ここで
    ログ初期化を行うことで help 表示時の不要な副作用を避ける。callback は各
    サブコマンド実行時に必ず一度走る。
    """
    import os

    os.environ.setdefault("LORAIRO_CLI_MODE", "true")
    initialize_logging(
        {
            "level": log_level.value,
            "file_path": str(DEFAULT_CLI_LOG_PATH),
            "rotation": "25 MB",
            "levels": {},
        }
    )


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


def _report_error(message: str, info: ErrorInfo, *, json_mode: bool) -> None:
    """エラーを出力モードに応じて出す (JSONL or rich)。

    Args:
        message: 人間可読のエラー文。
        info: 分類済みの :class:`ErrorInfo`。
        json_mode: JSONL モードなら ``True``。
    """
    if json_mode:
        emit_error(
            info.code,
            message,
            retryable=info.retryable,
            user_action_required=info.user_action_required,
            hint=hint_for(info.code),
        )
    else:
        console_err.print(f"[red]Error:[/red] {message}")


def _handle_click_exception(exc: click.ClickException, *, json_mode: bool) -> int:
    """Click の usage / parse error を ``INVALID_INPUT`` で処理する (ADR 0057 §7)。

    Args:
        exc: ``UsageError`` / ``BadParameter`` / ``NoSuchOption`` 等。
        json_mode: JSONL モードなら ``True``。

    Returns:
        process exit code (2)。
    """
    message = exc.format_message() if hasattr(exc, "format_message") else str(exc)
    info = ErrorInfo(ErrorCode.INVALID_INPUT, retryable=False, user_action_required=True)
    _report_error(message, info, json_mode=json_mode)
    return info.exit_code


def _handle_cli_exception(exc: Exception, *, json_mode: bool) -> int:
    """コマンドが伝播した例外を分類して構造化エラーに写す (ADR 0057 §5/§6/§7)。

    Args:
        exc: コマンド本体から伝播した例外。
        json_mode: JSONL モードなら ``True``。

    Returns:
        分類コードから導出した process exit code。
    """
    info = classify_exception(exc)
    message = str(exc) or type(exc).__name__
    _report_error(message, info, json_mode=json_mode)
    # stdout の JSONL 純度を保つため、traceback は INTERNAL_ERROR のときだけ stderr へ
    if info.code == ErrorCode.INTERNAL_ERROR:
        traceback.print_exc(file=sys.stderr)
    return info.exit_code


def main(argv: list[str] | None = None) -> None:
    """CLIメインエントリポイント兼中央エラー境界 (ADR 0057 §7 / ADR 0058 §1)。

    出力モード (``--json`` / ``--no-json`` / env) を Click のパース前に解決し、
    ``standalone_mode=False`` で Typer/Click の自動 exit をバイパスして、
    usage error も含む全失敗を 1 箇所で構造化エラー + exit code に写す。

    ``LORAIRO_CLI_MODE`` 設定とログ初期化は ``@app.callback()`` (``_configure``)
    でサブコマンド実行時に行う (Issue #539 / #540)。stdio 初期化は module top-level の
    ``early_init()`` で完了済。

    Args:
        argv: 引数列 (省略時は ``sys.argv[1:]`` を Click が解決)。テスト用に注入可能。
    """
    json_mode = resolve_output_mode(argv)
    set_json_mode(json_mode)
    try:
        # standalone_mode=False: ctx.exit() / --help は exit code を返し、
        # ClickException / Abort / 一般例外は伝播する。
        result = app(args=argv, standalone_mode=False)
    except click.exceptions.Abort:
        raise SystemExit(130) from None
    except click.ClickException as exc:
        raise SystemExit(_handle_click_exception(exc, json_mode=json_mode)) from exc
    except SystemExit:
        raise
    except Exception as exc:  # CLI 最上位エラー境界 (ADR 0057 §7)
        raise SystemExit(_handle_cli_exception(exc, json_mode=json_mode)) from exc
    # ctx.exit(code) / --help は標準終了の exit code を int で返す。
    if isinstance(result, int) and result != 0:
        raise SystemExit(result)


if __name__ == "__main__":
    main()
