"""Error record management commands.

DB の error_records テーブルを閲覧・解決マークするコマンド群。

出力は ADR 0057/0058 に従う: ``--json`` 時は stdout に JSONL (item/result)、
それ以外は rich 人間向け。
"""

from __future__ import annotations

import click
import typer
from rich.table import Table

from lorairo.cli._boundary import command_boundary
from lorairo.cli._console import make_console
from lorairo.cli._emit import emit_item, emit_result
from lorairo.cli._output_mode import is_json_mode
from lorairo.public_api.exceptions import ErrorRecordNotFoundError
from lorairo.public_api.project import get_project as api_get_project
from lorairo.services.service_container import get_service_container

app = typer.Typer(help="Error record management commands")
console = make_console()

MAX_LIST_LIMIT = 500


def _parse_ids(ids_csv: str) -> list[int]:
    """カンマ区切り文字列を int リストに変換する。

    Args:
        ids_csv: カンマ区切りの ID 文字列。

    Returns:
        ID の整数リスト。

    Raises:
        click.UsageError: 整数に変換できない値が含まれていた場合。
    """
    try:
        return [int(x.strip()) for x in ids_csv.split(",") if x.strip()]
    except ValueError as e:
        raise click.UsageError(f"--ids には整数のみ指定可: {e}") from e


@app.command("list")
def list_errors(
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    operation: str | None = typer.Option(
        None, "--operation", help="Filter by operation_type (search/registration/annotation)"
    ),
    error_type: str | None = typer.Option(None, "--error-type", help="Filter by error_type"),
    message_contains: str | None = typer.Option(
        None, "--message-contains", help="Filter by partial error_message match"
    ),
    all_records: bool = typer.Option(
        False, "--all", help="Include resolved records (default: unresolved only)"
    ),
    limit: int = typer.Option(50, "--limit", help="Max records to return (max 500)"),
    offset: int = typer.Option(0, "--offset", help="Offset for pagination"),
) -> None:
    """List error records.

    デフォルトは未解決のみ。--all で解決済みを含む全レコードを返す。

    Example:
        lorairo-cli errors list --project proj --operation search --error-type RuntimeError
    """
    with command_boundary():
        api_get_project(project)
        if limit > MAX_LIST_LIMIT:
            raise click.UsageError(f"--limit は最大 {MAX_LIST_LIMIT}。")

        container = get_service_container()
        container.set_active_project(project)
        repo = container.db_manager.error_record_repo

        resolved_filter: bool | None = None if all_records else False

        records = repo.get_error_records(
            operation_type=operation,
            error_type=error_type,
            message_contains=message_contains,
            resolved=resolved_filter,
            limit=limit,
            offset=offset,
        )

        if is_json_mode():
            for r in records:
                emit_item(
                    {
                        "id": r.id,
                        "operation_type": r.operation_type,
                        "error_type": r.error_type,
                        "error_message": r.error_message,
                        "model_name": r.model_name,
                        "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
                        "created_at": r.created_at.isoformat() if r.created_at else None,
                    }
                )
            emit_result(f"{len(records)} error record(s)", count=len(records))
            return

        if not records:
            console.print("[dim]No error records found.[/dim]")
            return

        table = Table(title=f"Error Records ({project})")
        table.add_column("ID", style="cyan", width=6)
        table.add_column("Op", style="blue", width=12)
        table.add_column("Type", style="red", width=18)
        table.add_column("Message", style="white")
        table.add_column("Created", style="dim", width=20)

        for r in records:
            table.add_row(
                str(r.id),
                r.operation_type,
                r.error_type,
                (r.error_message or "")[:80],
                r.created_at.isoformat()[:19] if r.created_at else "",
            )
        console.print(table)
        console.print(f"[dim]{len(records)} record(s) shown[/dim]")


@app.command("get")
def get_error(
    error_id: int = typer.Argument(..., help="Error record ID to retrieve"),
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
) -> None:
    """Get a single error record by ID (full detail).

    `list` は error_message を切り詰め stack_trace / file_path / image_id を省くため、
    1 件の全容を確認するには本コマンドを使う。

    Example:
        lorairo-cli errors get 42 --project proj
    """
    with command_boundary():
        api_get_project(project)

        container = get_service_container()
        container.set_active_project(project)
        repo = container.db_manager.error_record_repo

        record = repo.get_error_record(error_id)
        if record is None:
            raise ErrorRecordNotFoundError(error_id)

        fields = {
            "id": record.id,
            "image_id": record.image_id,
            "operation_type": record.operation_type,
            "error_type": record.error_type,
            "error_message": record.error_message,
            "stack_trace": record.stack_trace,
            "file_path": record.file_path,
            "model_name": record.model_name,
            "resolved_at": record.resolved_at.isoformat() if record.resolved_at else None,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }

        if is_json_mode():
            emit_item(fields)
            emit_result("1 error record", count=1)
            return

        table = Table(title=f"Error Record #{record.id} ({project})", show_header=False)
        table.add_column("Field", style="cyan", no_wrap=True)
        table.add_column("Value", style="white")
        for key, value in fields.items():
            table.add_row(key, "" if value is None else str(value))
        console.print(table)


@app.command("resolve")
def resolve_errors(
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    ids: str | None = typer.Option(None, "--ids", help="Comma-separated error record IDs"),
    operation: str | None = typer.Option(None, "--operation", help="Bulk-resolve by operation_type"),
    error_type: str | None = typer.Option(None, "--error-type", help="Bulk-resolve by error_type"),
    message_contains: str | None = typer.Option(
        None, "--message-contains", help="Bulk-resolve by partial error_message match"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show target count without writing"),
) -> None:
    """Mark error records as resolved.

    --ids でレコード ID を指定するか、--operation / --error-type / --message-contains
    でフィルターして一括解決する。

    Example:
        lorairo-cli errors resolve --project proj \\
          --operation search --error-type RuntimeError \\
          --message-contains "キャンセル"
    """
    with command_boundary():
        if ids is None and operation is None and error_type is None and message_contains is None:
            raise click.UsageError(
                "--ids / --operation / --error-type / --message-contains のいずれかを指定してください。"
            )

        api_get_project(project)
        container = get_service_container()
        container.set_active_project(project)
        repo = container.db_manager.error_record_repo

        if ids is not None:
            target_ids = _parse_ids(ids)
            if not target_ids:
                raise click.UsageError("--ids に有効な値がありません。")
        else:
            target_ids = repo.get_error_ids_by_filter(
                operation_type=operation,
                error_type=error_type,
                message_contains=message_contains,
            )

        target_count = len(target_ids)

        if dry_run:
            if is_json_mode():
                emit_result(
                    f"Dry-run: {target_count} record(s) would be resolved",
                    resolved=target_count,
                    dry_run=True,
                )
            else:
                console.print(f"[dim]Dry-run: {target_count} record(s) would be resolved[/dim]")
            return

        if not target_ids:
            if is_json_mode():
                emit_result("No matching error records found", resolved=0, dry_run=False)
            else:
                console.print("[dim]No matching error records found.[/dim]")
            return

        success, updated = repo.mark_errors_resolved_batch(target_ids)

        if is_json_mode():
            emit_result(
                f"Resolved {updated} error record(s)",
                ok=success,
                resolved=updated,
                dry_run=False,
            )
        else:
            if success:
                console.print(f"[green]Resolved {updated} error record(s)[/green]")
            else:
                console.print(f"[yellow]Partial resolve: {updated}/{target_count}[/yellow]")
