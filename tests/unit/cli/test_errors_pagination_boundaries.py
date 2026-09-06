"""Real SQLite pagination boundary checks for errors list (#1318)."""

import json
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from typer.testing import CliRunner

from lorairo.cli.introspection import ErrorsListInput
from lorairo.cli.main import app
from lorairo.database.repository.error_record import ErrorRecordRepository
from lorairo.database.schema import Base, ErrorRecord


@pytest.mark.parametrize("limit", [-1, 0, 1, 500, 501])
@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_error_list_real_repository_bounds(monkeypatch, limit: int, offset: int) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    with factory() as session:
        session.add_all(
            ErrorRecord(operation_type="synthetic", error_type="TestError", error_message=str(number))
            for number in range(501)
        )
        session.commit()
    statements: list[str] = []
    event.listen(
        engine, "before_cursor_execute", lambda conn, cursor, sql, params, ctx, many: statements.append(sql)
    )
    container = MagicMock()
    container.db_manager.error_record_repo = ErrorRecordRepository(session_factory=factory)
    get_project = MagicMock()
    monkeypatch.setattr("lorairo.cli.commands.errors.api_get_project", get_project)
    monkeypatch.setattr("lorairo.cli.commands.errors.get_service_container", lambda: container)
    try:
        result = CliRunner().invoke(
            app,
            [
                "--json",
                "errors",
                "list",
                "--project",
                "synthetic",
                "--limit",
                str(limit),
                "--offset",
                str(offset),
            ],
        )
        rows = [json.loads(line) for line in result.stdout.splitlines() if line]
        invalid = limit < 0 or limit > 500 or offset < 0
        if invalid:
            assert result.exit_code == 2
            assert rows[-1]["code"] == "INVALID_INPUT"
            assert rows[-1]["ok"] is False
            assert statements == []
            get_project.assert_not_called()
            container.set_active_project.assert_not_called()
        else:
            assert result.exit_code == 0, result.output
            assert rows[-1]["count"] == limit
            assert sum(row["kind"] == "item" for row in rows) == limit
            assert len(statements) == 1
            ErrorsListInput(project="synthetic", limit=limit, offset=offset)
    finally:
        engine.dispose()


def test_describe_and_help_explain_zero_and_bounds() -> None:
    result = CliRunner().invoke(app, ["--json", "describe", "errors list", "--schema", "json_schema"])
    assert result.exit_code == 0, result.output
    schema = ErrorsListInput.model_json_schema()["properties"]
    assert (schema["limit"]["minimum"], schema["limit"]["maximum"]) == (0, 500)
    assert schema["offset"]["minimum"] == 0
    assert '"minimum": 0' in result.stdout
    help_result = CliRunner().invoke(app, ["errors", "list", "--help"], terminal_width=160)
    assert help_result.exit_code == 0
    assert "0..500; 0" in help_result.stdout
    assert "returns no records" in help_result.stdout
