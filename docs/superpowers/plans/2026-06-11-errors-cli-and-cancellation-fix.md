# errors CLI コマンドグループ & キャンセル修正 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `lorairo-cli errors list / errors resolve` コマンドを追加し、DB に蓄積したエラーレコードを CLI で閲覧・解決マークできるようにする。また登録 Worker の stale docstring を修正する。

**Architecture:** `ErrorRecordRepository` に `error_type`/`message_contains` フィルターを追加、`cli/commands/errors.py` を新規作成して `main.py` と `introspection.py` に登録する。Issue #715 は SearchWorker キャンセルが現在すでに DB 記録されないことを検証するテストと stale docstring 修正で対応する。

**Tech Stack:** Python 3.13, Typer, SQLAlchemy, Rich, pytest, typer.testing.CliRunner

---

## ファイルマップ

| 操作 | ファイル |
|---|---|
| Modify | `src/lorairo/database/repository/error_record.py` |
| Create | `src/lorairo/cli/commands/errors.py` |
| Modify | `src/lorairo/cli/main.py` |
| Modify | `src/lorairo/cli/introspection.py` |
| Modify | `src/lorairo/gui/workers/registration_worker.py` |
| Modify | `tests/unit/database/test_db_repository_error_records.py` |
| Create | `tests/unit/cli/test_commands_errors.py` |
| Modify | `tests/unit/gui/workers/test_base_worker.py` |

---

## Task 1: ErrorRecordRepository にフィルター拡張メソッドを追加

**Files:**
- Modify: `src/lorairo/database/repository/error_record.py`
- Modify: `tests/unit/database/test_db_repository_error_records.py`

- [ ] **Step 1: 失敗テストを書く**

`tests/unit/database/test_db_repository_error_records.py` の末尾に追記:

```python
class TestGetErrorRecordsFilters:
    """get_error_records の error_type / message_contains フィルターのテスト"""

    @pytest.fixture
    def repo(self):
        return ErrorRecordRepository(session_factory=MagicMock())

    def _make_records(self, specs: list[dict]) -> list[Mock]:
        records = []
        for s in specs:
            r = Mock(spec=ErrorRecord)
            r.operation_type = s.get("op", "search")
            r.error_type = s.get("et", "RuntimeError")
            r.error_message = s.get("msg", "")
            r.resolved_at = s.get("resolved_at", None)
            records.append(r)
        return records

    def test_filter_by_error_type(self, repo):
        mock_session = Mock()
        repo.session_factory.return_value.__enter__.return_value = mock_session
        mock_session.execute.return_value.scalars.return_value.all.return_value = []
        repo.get_error_records(error_type="RuntimeError")
        call_args = mock_session.execute.call_args
        assert call_args is not None

    def test_filter_by_message_contains(self, repo):
        mock_session = Mock()
        repo.session_factory.return_value.__enter__.return_value = mock_session
        mock_session.execute.return_value.scalars.return_value.all.return_value = []
        repo.get_error_records(message_contains="キャンセル")
        call_args = mock_session.execute.call_args
        assert call_args is not None


class TestCountErrorRecords:
    """count_error_records のテスト"""

    @pytest.fixture
    def repo(self):
        return ErrorRecordRepository(session_factory=MagicMock())

    def test_count_unresolved(self, repo):
        mock_session = Mock()
        repo.session_factory.return_value.__enter__.return_value = mock_session
        mock_session.execute.return_value.scalar.return_value = 42
        result = repo.count_error_records(resolved=False)
        assert result == 42

    def test_count_with_filters(self, repo):
        mock_session = Mock()
        repo.session_factory.return_value.__enter__.return_value = mock_session
        mock_session.execute.return_value.scalar.return_value = 10
        result = repo.count_error_records(
            operation_type="search",
            error_type="RuntimeError",
            message_contains="キャンセル",
        )
        assert result == 10


class TestGetErrorIdsByFilter:
    """get_error_ids_by_filter のテスト"""

    @pytest.fixture
    def repo(self):
        return ErrorRecordRepository(session_factory=MagicMock())

    def test_returns_id_list(self, repo):
        mock_session = Mock()
        repo.session_factory.return_value.__enter__.return_value = mock_session
        mock_session.execute.return_value.scalars.return_value.all.return_value = [1, 2, 3]
        result = repo.get_error_ids_by_filter(operation_type="search", error_type="RuntimeError")
        assert result == [1, 2, 3]

    def test_returns_empty_list_when_no_match(self, repo):
        mock_session = Mock()
        repo.session_factory.return_value.__enter__.return_value = mock_session
        mock_session.execute.return_value.scalars.return_value.all.return_value = []
        result = repo.get_error_ids_by_filter()
        assert result == []
```

- [ ] **Step 2: テスト失敗確認**

```bash
cd /workspaces/LoRAIro
uv run pytest tests/unit/database/test_db_repository_error_records.py::TestGetErrorRecordsFilters tests/unit/database/test_db_repository_error_records.py::TestCountErrorRecords tests/unit/database/test_db_repository_error_records.py::TestGetErrorIdsByFilter -v 2>&1 | tail -20
```

Expected: `TypeError` or `AttributeError` (メソッドが存在しない)

- [ ] **Step 3: `error_record.py` に新メソッドを実装**

`src/lorairo/database/repository/error_record.py` の `get_error_records` 定義を置き換えて引数を拡張し、`count_error_records` と `get_error_ids_by_filter` を追加する。

`get_error_records` を以下に差し替える:

```python
def get_error_records(
    self,
    operation_type: str | None = None,
    error_type: str | None = None,
    message_contains: str | None = None,
    resolved: bool | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[ErrorRecord]:
    """エラーレコードを取得する (ページネーション対応)。

    Args:
        operation_type: 操作種別フィルタ (None = 全操作)。
        error_type: エラー種別フィルタ (None = 全種別)。
        message_contains: error_message 部分一致フィルタ (None = 全メッセージ)。
        resolved: None = 全て、True = 解決済み、False = 未解決。
        limit: 取得件数上限。
        offset: オフセット。

    Returns:
        list[ErrorRecord]: エラーレコードリスト。

    Raises:
        SQLAlchemyError: データベース操作でエラーが発生した場合。
    """
    with self.session_factory() as session:
        try:
            query = select(ErrorRecord).order_by(ErrorRecord.created_at.desc())
            if operation_type:
                query = query.where(ErrorRecord.operation_type == operation_type)
            if error_type:
                query = query.where(ErrorRecord.error_type == error_type)
            if message_contains:
                query = query.where(ErrorRecord.error_message.contains(message_contains))
            if resolved is not None:
                if resolved:
                    query = query.where(ErrorRecord.resolved_at.is_not(None))
                else:
                    query = query.where(ErrorRecord.resolved_at.is_(None))
            query = query.limit(limit).offset(offset)
            records = list(session.execute(query).scalars().all())
            logger.debug(
                f"エラーレコードを取得: {len(records)}件 "
                f"(operation_type={operation_type or 'all'}, "
                f"error_type={error_type or 'all'}, "
                f"message_contains={message_contains!r}, "
                f"resolved={resolved}, limit={limit}, offset={offset})",
            )
            return records
        except SQLAlchemyError as e:
            logger.error(f"エラーレコードの取得中にエラーが発生しました: {e}", exc_info=True)
            raise
```

`mark_errors_resolved_batch` の直後に以下 2 メソッドを追加:

```python
def count_error_records(
    self,
    operation_type: str | None = None,
    error_type: str | None = None,
    message_contains: str | None = None,
    resolved: bool | None = None,
) -> int:
    """条件に一致するエラーレコード件数を返す (dry-run 用)。

    Args:
        operation_type: 操作種別フィルタ。
        error_type: エラー種別フィルタ。
        message_contains: error_message 部分一致フィルタ。
        resolved: None = 全て、True = 解決済み、False = 未解決。

    Returns:
        int: 一致件数。

    Raises:
        SQLAlchemyError: データベース操作でエラーが発生した場合。
    """
    with self.session_factory() as session:
        try:
            query = select(func.count(ErrorRecord.id))
            if operation_type:
                query = query.where(ErrorRecord.operation_type == operation_type)
            if error_type:
                query = query.where(ErrorRecord.error_type == error_type)
            if message_contains:
                query = query.where(ErrorRecord.error_message.contains(message_contains))
            if resolved is not None:
                if resolved:
                    query = query.where(ErrorRecord.resolved_at.is_not(None))
                else:
                    query = query.where(ErrorRecord.resolved_at.is_(None))
            count = session.execute(query).scalar() or 0
            logger.debug(f"エラーレコード件数を集計: {count}件")
            return count
        except SQLAlchemyError as e:
            logger.error(f"エラーレコード件数集計中にエラーが発生しました: {e}", exc_info=True)
            raise

def get_error_ids_by_filter(
    self,
    operation_type: str | None = None,
    error_type: str | None = None,
    message_contains: str | None = None,
) -> list[int]:
    """未解決エラーレコードの ID リストをフィルター条件で取得する (一括 resolve 用)。

    Args:
        operation_type: 操作種別フィルタ。
        error_type: エラー種別フィルタ。
        message_contains: error_message 部分一致フィルタ。

    Returns:
        list[int]: 未解決エラーレコード ID リスト。

    Raises:
        SQLAlchemyError: データベース操作でエラーが発生した場合。
    """
    with self.session_factory() as session:
        try:
            query = (
                select(ErrorRecord.id)
                .where(ErrorRecord.resolved_at.is_(None))
                .order_by(ErrorRecord.id)
            )
            if operation_type:
                query = query.where(ErrorRecord.operation_type == operation_type)
            if error_type:
                query = query.where(ErrorRecord.error_type == error_type)
            if message_contains:
                query = query.where(ErrorRecord.error_message.contains(message_contains))
            ids = list(session.execute(query).scalars().all())
            logger.debug(f"一括 resolve 対象 ID: {len(ids)}件")
            return ids
        except SQLAlchemyError as e:
            logger.error(f"エラーレコード ID 取得中にエラーが発生しました: {e}", exc_info=True)
            raise
```

- [ ] **Step 4: テスト合格確認**

```bash
uv run pytest tests/unit/database/test_db_repository_error_records.py -v 2>&1 | tail -20
```

Expected: 全 PASS

- [ ] **Step 5: コミット**

```bash
git add src/lorairo/database/repository/error_record.py tests/unit/database/test_db_repository_error_records.py
git commit -m "feat(repository): ErrorRecordRepository に error_type/message_contains フィルターと count/get_ids メソッドを追加"
```

---

## Task 2: `errors.py` CLI コマンドを作成

**Files:**
- Create: `src/lorairo/cli/commands/errors.py`
- Create: `tests/unit/cli/test_commands_errors.py`

- [ ] **Step 1: 失敗テストを書く**

`tests/unit/cli/test_commands_errors.py` を新規作成:

```python
"""errors コマンド群のユニットテスト。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app

runner = CliRunner()

_NOW = datetime(2026, 6, 11, 0, 0, 0, tzinfo=timezone.utc)


def _make_error_record(
    id: int = 1,
    op: str = "search",
    et: str = "RuntimeError",
    msg: str = "処理がキャンセルされました",
    model_name: str | None = None,
    retry_count: int = 0,
    resolved_at: datetime | None = None,
    created_at: datetime = _NOW,
) -> MagicMock:
    r = MagicMock()
    r.id = id
    r.operation_type = op
    r.error_type = et
    r.error_message = msg
    r.model_name = model_name
    r.retry_count = retry_count
    r.resolved_at = resolved_at
    r.created_at = created_at
    return r


def _make_container(records: list, count: int = 0, resolve_result: tuple = (True, 0)) -> MagicMock:
    container = MagicMock()
    container.db_manager.error_record_repo.get_error_records.return_value = records
    container.db_manager.error_record_repo.count_error_records.return_value = count
    container.db_manager.error_record_repo.get_error_ids_by_filter.return_value = (
        [r.id for r in records]
    )
    container.db_manager.error_record_repo.mark_errors_resolved_batch.return_value = resolve_result
    return container


@pytest.fixture
def mock_project_and_container(monkeypatch):
    records = [_make_error_record(id=1), _make_error_record(id=2)]
    container = _make_container(records, count=len(records), resolve_result=(True, 2))
    monkeypatch.setattr("lorairo.cli.commands.errors.api_get_project", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(
        "lorairo.cli.commands.errors.get_service_container", MagicMock(return_value=container)
    )
    return container


@pytest.mark.unit
class TestErrorsList:
    def test_list_json_emits_items_and_result(self, mock_project_and_container):
        result = runner.invoke(
            app,
            ["--json", "errors", "list", "--project", "proj"],
        )
        assert result.exit_code == 0, result.output
        lines = [json.loads(line) for line in result.stdout.strip().splitlines() if line.strip()]
        item_rows = [r for r in lines if r.get("kind") == "item"]
        result_row = next(r for r in lines if r.get("kind") == "result")
        assert len(item_rows) == 2
        assert result_row["ok"] is True
        assert result_row["count"] == 2

    def test_list_item_fields(self, mock_project_and_container):
        result = runner.invoke(
            app,
            ["--json", "errors", "list", "--project", "proj"],
        )
        assert result.exit_code == 0
        lines = [json.loads(line) for line in result.stdout.strip().splitlines() if line.strip()]
        item = next(r for r in lines if r.get("kind") == "item")
        for field in ("id", "operation_type", "error_type", "error_message", "created_at"):
            assert field in item, f"Missing field: {field}"

    def test_list_passes_operation_filter(self, mock_project_and_container):
        runner.invoke(
            app,
            ["--json", "errors", "list", "--project", "proj", "--operation", "search"],
        )
        mock_project_and_container.db_manager.error_record_repo.get_error_records.assert_called_once()
        kwargs = mock_project_and_container.db_manager.error_record_repo.get_error_records.call_args.kwargs
        assert kwargs.get("operation_type") == "search"

    def test_list_passes_error_type_filter(self, mock_project_and_container):
        runner.invoke(
            app,
            ["--json", "errors", "list", "--project", "proj", "--error-type", "RuntimeError"],
        )
        kwargs = mock_project_and_container.db_manager.error_record_repo.get_error_records.call_args.kwargs
        assert kwargs.get("error_type") == "RuntimeError"

    def test_list_unresolved_only_by_default(self, mock_project_and_container):
        runner.invoke(app, ["--json", "errors", "list", "--project", "proj"])
        kwargs = mock_project_and_container.db_manager.error_record_repo.get_error_records.call_args.kwargs
        assert kwargs.get("resolved") is False


@pytest.mark.unit
class TestErrorsResolve:
    def test_resolve_by_ids_calls_batch_mark(self, mock_project_and_container):
        result = runner.invoke(
            app,
            ["--json", "errors", "resolve", "--project", "proj", "--ids", "1,2"],
        )
        assert result.exit_code == 0, result.output
        mock_project_and_container.db_manager.error_record_repo.mark_errors_resolved_batch.assert_called_once_with(
            [1, 2]
        )

    def test_resolve_dry_run_does_not_write(self, mock_project_and_container):
        result = runner.invoke(
            app,
            ["--json", "errors", "resolve", "--project", "proj", "--operation", "search", "--dry-run"],
        )
        assert result.exit_code == 0, result.output
        mock_project_and_container.db_manager.error_record_repo.mark_errors_resolved_batch.assert_not_called()

    def test_resolve_dry_run_result_has_dry_run_true(self, mock_project_and_container):
        result = runner.invoke(
            app,
            ["--json", "errors", "resolve", "--project", "proj", "--operation", "search", "--dry-run"],
        )
        assert result.exit_code == 0
        lines = [json.loads(line) for line in result.stdout.strip().splitlines() if line.strip()]
        result_row = next(r for r in lines if r.get("kind") == "result")
        assert result_row["dry_run"] is True

    def test_resolve_bulk_filter_uses_get_ids(self, mock_project_and_container):
        result = runner.invoke(
            app,
            [
                "--json",
                "errors",
                "resolve",
                "--project",
                "proj",
                "--operation",
                "search",
                "--error-type",
                "RuntimeError",
                "--message-contains",
                "キャンセル",
            ],
        )
        assert result.exit_code == 0
        mock_project_and_container.db_manager.error_record_repo.get_error_ids_by_filter.assert_called_once()

    def test_resolve_result_json_fields(self, mock_project_and_container):
        result = runner.invoke(
            app,
            ["--json", "errors", "resolve", "--project", "proj", "--ids", "1,2"],
        )
        assert result.exit_code == 0
        lines = [json.loads(line) for line in result.stdout.strip().splitlines() if line.strip()]
        result_row = next(r for r in lines if r.get("kind") == "result")
        assert result_row["ok"] is True
        for field in ("resolved", "dry_run"):
            assert field in result_row, f"Missing field: {field}"
```

- [ ] **Step 2: テスト失敗確認**

```bash
uv run pytest tests/unit/cli/test_commands_errors.py -v 2>&1 | tail -20
```

Expected: `ModuleNotFoundError: No module named 'lorairo.cli.commands.errors'` か ImportError

- [ ] **Step 3: `src/lorairo/cli/commands/errors.py` を実装**

```python
"""Error record management commands.

DB の error_records テーブルを閲覧・解決マークするコマンド群。

出力は ADR 0057/0058 に従う: ``--json`` 時は stdout に JSONL (item/result)、
それ以外は rich 人間向け。
"""

from __future__ import annotations

import click
import typer
from rich.table import Table

from lorairo.api.project import get_project as api_get_project
from lorairo.cli._boundary import command_boundary
from lorairo.cli._console import make_console
from lorairo.cli._emit import emit_item, emit_result
from lorairo.cli._output_mode import is_json_mode
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
    all_records: bool = typer.Option(False, "--all", help="Include resolved records (default: unresolved only)"),
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
                    id=r.id,
                    operation_type=r.operation_type,
                    error_type=r.error_type,
                    error_message=r.error_message,
                    model_name=r.model_name,
                    retry_count=r.retry_count,
                    resolved_at=r.resolved_at.isoformat() if r.resolved_at else None,
                    created_at=r.created_at.isoformat() if r.created_at else None,
                )
            emit_result(f"{len(records)} error record(s)", count=len(records))
            return

        if not records:
            console.print("[dim]No error records found.[/dim]")
            emit_result("0 error record(s)", count=0)
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
        # キャンセル RuntimeError を一括解決
        lorairo-cli errors resolve --project proj \\
          --operation search --error-type RuntimeError \\
          --message-contains "キャンセル"

        # 特定 ID を解決
        lorairo-cli errors resolve --project proj --ids 1,2,3
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
```

- [ ] **Step 4: テスト合格確認**

```bash
uv run pytest tests/unit/cli/test_commands_errors.py -v 2>&1 | tail -30
```

Expected: 全 PASS

- [ ] **Step 5: コミット**

```bash
git add src/lorairo/cli/commands/errors.py tests/unit/cli/test_commands_errors.py
git commit -m "feat(cli): errors list / errors resolve コマンドを追加 (Issue #714)"
```

---

## Task 3: CLI main.py への登録

**Files:**
- Modify: `src/lorairo/cli/main.py`

- [ ] **Step 1: import と `add_typer` を追加**

`src/lorairo/cli/main.py` の imports 行を探して `errors` を追加:

```python
# 変更前
from lorairo.cli.commands import annotate, batch, export, images, models, project, tags

# 変更後
from lorairo.cli.commands import annotate, batch, errors, export, images, models, project, tags
```

`app.add_typer(tags.app, ...)` の直後に追加:

```python
app.add_typer(errors.app, name="errors", help="Error record management commands")
```

- [ ] **Step 2: 動作確認**

```bash
uv run lorairo-cli errors --help 2>&1 | head -20
```

Expected: `errors list` と `errors resolve` が表示される

- [ ] **Step 3: コミット**

```bash
git add src/lorairo/cli/main.py
git commit -m "feat(cli): errors コマンドグループを main.py に登録"
```

---

## Task 4: introspection.py に ToolSpec を追加

**Files:**
- Modify: `src/lorairo/cli/introspection.py`

- [ ] **Step 1: 失敗テストを書く**

`tests/unit/cli/test_introspection.py` の末尾に追記:

```python
@pytest.mark.unit
def test_errors_commands_in_list_commands() -> None:
    """errors list / errors resolve が list-commands に現れる。"""
    result = runner.invoke(app, ["--json", "list-commands"])
    assert result.exit_code == 0
    lines = [json.loads(line) for line in result.stdout.strip().splitlines() if line.strip()]
    paths = {r.get("path") for r in lines if r.get("kind") == "item"}
    assert "errors list" in paths
    assert "errors resolve" in paths


@pytest.mark.unit
def test_describe_errors_list_exposes_required_fields() -> None:
    """describe errors list が project 必須フィールドを返す。"""
    result = runner.invoke(app, ["--json", "describe", "errors list"])
    assert result.exit_code == 0
    lines = [json.loads(line) for line in result.stdout.strip().splitlines() if line.strip()]
    rows = [r for r in lines if r.get("kind") == "item"]
    assert rows[0]["path"] == "errors list"


@pytest.mark.unit
def test_describe_errors_resolve_exposes_required_fields() -> None:
    """describe errors resolve が project 必須フィールドを返す。"""
    result = runner.invoke(app, ["--json", "describe", "errors resolve"])
    assert result.exit_code == 0
    lines = [json.loads(line) for line in result.stdout.strip().splitlines() if line.strip()]
    rows = [r for r in lines if r.get("kind") == "item"]
    assert rows[0]["path"] == "errors resolve"
```

- [ ] **Step 2: テスト失敗確認**

```bash
uv run pytest tests/unit/cli/test_introspection.py::test_errors_commands_in_list_commands -v 2>&1 | tail -10
```

Expected: FAIL (ToolSpec 未定義)

- [ ] **Step 3: TOOL_SPECS に entries を追加**

`src/lorairo/cli/introspection.py` の TOOL_SPECS dict の末尾 `}` の直前 ("batch cancel" や "batch fetch" の後) に追加する。

まず必要な Pydantic モデルを追加する。`BatchFetchResult` など既存モデル定義の後に:

```python
class ErrorListResult(BaseModel):
    """errors list の result 行スキーマ。"""
    count: int


class ErrorRecordItem(BaseModel):
    """errors list の item 行スキーマ。"""
    id: int
    operation_type: str
    error_type: str
    error_message: str
    model_name: str | None = None
    retry_count: int
    resolved_at: str | None = None
    created_at: str | None = None


class ErrorsResolveResult(BaseModel):
    """errors resolve の result 行スキーマ。"""
    ok: bool
    resolved: int
    dry_run: bool
```

次に TOOL_SPECS dict に追加 (最後の `}` の直前):

```python
    "errors list": ToolSpec(
        name="errors list",
        path="errors list",
        summary="List error records. Default: unresolved only.",
        read_only=True,
        side_effects=("db_read",),
        inputs=(
            _input(
                "ErrorsListInput",
                (
                    _f("project", "str", required=True),
                    _f("operation", "str?", description="Filter by operation_type (search/registration/annotation)"),
                    _f("error_type", "str?", description="Filter by error_type"),
                    _f("message_contains", "str?", description="Partial match on error_message"),
                    _f("all", "bool", default=False, description="Include resolved records"),
                    _f("limit", "int", default=50, description="Max records (max 500)"),
                    _f("offset", "int", default=0),
                ),
            ),
        ),
        outputs=(
            _output(
                "ErrorRecordItem",
                (
                    _f("id", "int"),
                    _f("operation_type", "str"),
                    _f("error_type", "str"),
                    _f("error_message", "str"),
                    _f("model_name", "str?"),
                    _f("retry_count", "int"),
                    _f("resolved_at", "str?"),
                    _f("created_at", "str?"),
                ),
                schema=ErrorRecordItem,
            ),
            _output(
                "ErrorListResult",
                (_f("count", "int"),),
                schema=ErrorListResult,
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
    "errors resolve": ToolSpec(
        name="errors resolve",
        path="errors resolve",
        summary="Mark error records as resolved. Use --dry-run to preview.",
        read_only=False,
        side_effects=("db_read", "db_write"),
        inputs=(
            _input(
                "ErrorsResolveInput",
                (
                    _f("project", "str", required=True),
                    _f("ids", "csv[int]?", description="Comma-separated error record IDs"),
                    _f("operation", "str?", description="Bulk-resolve by operation_type"),
                    _f("error_type", "str?", description="Bulk-resolve by error_type"),
                    _f("message_contains", "str?", description="Bulk-resolve by partial message match"),
                    _f("dry_run", "bool", default=False, description="Preview count without writing"),
                ),
            ),
        ),
        outputs=(
            _output(
                "ErrorsResolveResult",
                (
                    _f("ok", "bool"),
                    _f("resolved", "int"),
                    _f("dry_run", "bool"),
                ),
                schema=ErrorsResolveResult,
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
```

- [ ] **Step 4: テスト合格確認**

```bash
uv run pytest tests/unit/cli/test_introspection.py -v 2>&1 | tail -20
```

Expected: 全 PASS

- [ ] **Step 5: コミット**

```bash
git add src/lorairo/cli/introspection.py tests/unit/cli/test_introspection.py
git commit -m "feat(introspection): errors list / errors resolve ToolSpec を追加"
```

---

## Task 5: Issue #715 — stale docstring 修正と SearchWorker キャンセルテスト

**Files:**
- Modify: `src/lorairo/gui/workers/registration_worker.py`
- Modify: `tests/unit/gui/workers/test_base_worker.py`

- [ ] **Step 1: registration_worker.py の stale docstring を修正**

`src/lorairo/gui/workers/registration_worker.py` で `RuntimeError: 処理がキャンセルされた場合` となっている docstring 行を検索して `CancellationError` に修正する。

```bash
grep -n "RuntimeError: 処理がキャンセルされた場合" src/lorairo/gui/workers/registration_worker.py
```

該当行を:
```
            RuntimeError: 処理がキャンセルされた場合
```
↓
```
            CancellationError: 処理がキャンセルされた場合
```

- [ ] **Step 2: SearchWorker キャンセルが DB 非記録であることのテストを追加**

`tests/unit/gui/workers/test_base_worker.py` を読み、`TestLoRAIroWorkerBaseRun` クラスの末尾に以下を追加する:

```python
def test_search_worker_cancellation_not_recorded(self):
    """SearchWorker のキャンセルが error_records に記録されないことを検証する (Issue #715)。"""
    from lorairo.gui.workers.search_worker import SearchWorker
    from unittest.mock import MagicMock, Mock

    mock_db = Mock()
    mock_conditions = MagicMock()

    # SearchCriteriaProcessor が CancellationError を raise する経路をシミュレート
    # (実際には _check_cancellation() が raise するが、テストでは直接注入する)
    worker = SearchWorker(db_manager=mock_db, search_conditions=mock_conditions)
    # execute() の内部で CancellationError が raise されるよう cancellation フラグをセット
    worker.cancellation.cancel()

    canceled_mock = Mock()
    error_mock = Mock()
    worker.canceled.connect(canceled_mock)
    worker.error_occurred.connect(error_mock)

    worker.run()

    error_mock.assert_not_called()
    canceled_mock.assert_called_once()
    mock_db.save_error_record.assert_not_called()
```

- [ ] **Step 3: テスト実行**

```bash
uv run pytest tests/unit/gui/workers/test_base_worker.py -v -k "cancellation" 2>&1 | tail -20
```

Expected: 全 PASS (既存テストも含む)

- [ ] **Step 4: コミット**

```bash
git add src/lorairo/gui/workers/registration_worker.py tests/unit/gui/workers/test_base_worker.py
git commit -m "fix(workers): stale docstring を CancellationError に修正、SearchWorker キャンセル非記録テスト追加 (Issue #715)"
```

---

## Task 6: 全テスト確認と PR 起票

- [ ] **Step 1: CI-equivalent フィルターで全テスト実行**

```bash
uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" --timeout=60 2>&1 | tail -20
```

Expected: 全 PASS

- [ ] **Step 2: mypy & Ruff チェック**

```bash
uv run ruff check src/lorairo/cli/commands/errors.py src/lorairo/cli/introspection.py src/lorairo/database/repository/error_record.py --fix
uv run mypy -p lorairo 2>&1 | grep -E "error:|Found" | tail -20
```

Expected: エラーなし

- [ ] **Step 3: PR 起票**

```bash
git push origin <branch>
gh pr create \
  --title "feat(cli): errors list / resolve コマンド追加 & キャンセル修正 (Issue #714 #715)" \
  --body "..."
```

---

## セルフレビュー

### Spec coverage

| 要件 | 対応タスク |
|---|---|
| `errors list` JSON 出力 | Task 2 |
| `errors list` フィルター (operation/error_type/message_contains) | Task 1, 2 |
| `errors resolve --ids` | Task 2 |
| `errors resolve --dry-run` | Task 2 |
| `errors resolve` 一括フィルター | Task 1, 2 |
| introspection 登録 | Task 4 |
| main.py 登録 | Task 3 |
| キャンセル非記録テスト | Task 5 |
| stale docstring 修正 | Task 5 |

### Placeholder scan: なし

### Type consistency

- `get_error_records()` の戻り値 `list[ErrorRecord]` → `errors.py` で `r.id`, `r.error_type` 等 schema.py の `ErrorRecord` 列アクセス ✓
- `count_error_records()` 戻り値 `int` → `dry_run` 表示に使用 ✓
- `get_error_ids_by_filter()` 戻り値 `list[int]` → `mark_errors_resolved_batch(target_ids)` に渡す ✓
- `mark_errors_resolved_batch()` 戻り値 `tuple[bool, int]` → `success, updated` でアンパック ✓
