"""errors コマンド群のユニットテスト。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app

runner = CliRunner()

_NOW = datetime(2026, 6, 11, 0, 0, 0, tzinfo=UTC)


def _make_error_record(
    id: int = 1,
    op: str = "search",
    et: str = "RuntimeError",
    msg: str = "処理がキャンセルされました",
    model_name: str | None = None,
    resolved_at: datetime | None = None,
    created_at: datetime = _NOW,
    image_id: int | None = None,
    stack_trace: str | None = None,
    file_path: str | None = None,
) -> MagicMock:
    r = MagicMock()
    r.id = id
    r.operation_type = op
    r.error_type = et
    r.error_message = msg
    r.model_name = model_name
    r.resolved_at = resolved_at
    r.created_at = created_at
    r.image_id = image_id
    r.stack_trace = stack_trace
    r.file_path = file_path
    return r


def _make_container(
    records: list,
    count: int = 0,
    resolve_result: tuple = (True, 0),
    ids: list[int] | None = None,
) -> MagicMock:
    container = MagicMock()
    container.db_manager.error_record_repo.get_error_records.return_value = records
    container.db_manager.error_record_repo.count_error_records.return_value = count
    container.db_manager.error_record_repo.get_error_ids_by_filter.return_value = (
        ids if ids is not None else [r.id for r in records]
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

    def test_list_all_flag_includes_resolved(self, mock_project_and_container):
        runner.invoke(app, ["--json", "errors", "list", "--project", "proj", "--all"])
        kwargs = mock_project_and_container.db_manager.error_record_repo.get_error_records.call_args.kwargs
        assert kwargs.get("resolved") is None


@pytest.mark.unit
class TestErrorsGet:
    @pytest.fixture
    def mock_get(self, monkeypatch):
        record = _make_error_record(
            id=7,
            op="annotation",
            et="APIError",
            msg="long error message " * 20,
            model_name="gpt-4",
            image_id=42,
            stack_trace="Traceback (most recent call last):\n  ...",
            file_path="/path/to/file.jpg",
        )
        container = MagicMock()
        container.db_manager.error_record_repo.get_error_record.return_value = record
        monkeypatch.setattr(
            "lorairo.cli.commands.errors.api_get_project", MagicMock(return_value=MagicMock())
        )
        monkeypatch.setattr(
            "lorairo.cli.commands.errors.get_service_container", MagicMock(return_value=container)
        )
        return container, record

    def test_get_calls_repo_with_id(self, mock_get):
        container, _ = mock_get
        result = runner.invoke(app, ["--json", "errors", "get", "7", "--project", "proj"])
        assert result.exit_code == 0, result.output
        container.db_manager.error_record_repo.get_error_record.assert_called_once_with(7)

    def test_get_json_emits_full_fields(self, mock_get):
        _, record = mock_get
        result = runner.invoke(app, ["--json", "errors", "get", "7", "--project", "proj"])
        assert result.exit_code == 0, result.output
        lines = [json.loads(line) for line in result.stdout.strip().splitlines() if line.strip()]
        item = next(r for r in lines if r.get("kind") == "item")
        for field in (
            "id",
            "image_id",
            "operation_type",
            "error_type",
            "error_message",
            "stack_trace",
            "file_path",
            "model_name",
            "resolved_at",
            "created_at",
        ):
            assert field in item, f"Missing field: {field}"
        # error_message は truncate されず全文が出る
        assert item["error_message"] == record.error_message
        assert item["stack_trace"] == record.stack_trace

    def test_get_not_found_returns_error_exit(self, monkeypatch):
        container = MagicMock()
        container.db_manager.error_record_repo.get_error_record.return_value = None
        monkeypatch.setattr(
            "lorairo.cli.commands.errors.api_get_project", MagicMock(return_value=MagicMock())
        )
        monkeypatch.setattr(
            "lorairo.cli.commands.errors.get_service_container", MagicMock(return_value=container)
        )
        result = runner.invoke(app, ["--json", "errors", "get", "999", "--project", "proj"])
        assert result.exit_code != 0
        lines = [json.loads(line) for line in result.stdout.strip().splitlines() if line.strip()]
        error_row = next(r for r in lines if r.get("kind") == "error")
        assert error_row["code"] == "NOT_FOUND"

    def test_get_rich_output(self, mock_get):
        result = runner.invoke(app, ["errors", "get", "7", "--project", "proj"])
        assert result.exit_code == 0, result.output
        assert "7" in result.stdout


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
        assert result.exit_code == 0, result.output
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

    def test_resolve_no_filter_raises_usage_error(self, mock_project_and_container):
        result = runner.invoke(
            app,
            ["--json", "errors", "resolve", "--project", "proj"],
        )
        assert result.exit_code != 0

    def test_resolve_empty_ids_raises_usage_error(self, mock_project_and_container):
        result = runner.invoke(
            app,
            ["--json", "errors", "resolve", "--project", "proj", "--ids", ""],
        )
        assert result.exit_code != 0
