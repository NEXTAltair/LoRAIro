"""Plain export --dry-run enforces strict access against isolated project DBs."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from typer.testing import CliRunner

from lorairo.cli.main import app
from lorairo.database import db_core

runner = CliRunner()
pytestmark = pytest.mark.unit


@pytest.mark.parametrize("state", ["missing", "empty", "old", "current", "tags_missing"])
def test_export_dry_run_never_prepares_project_database(tmp_path, monkeypatch, state):
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("LORAIRO_CLI_LOG_PATH", str(tmp_path / "cli.log"))
    created = runner.invoke(
        app, ["--json", "--workspace", str(workspace), "project", "create", "synthetic"]
    )
    assert created.exit_code == 0, created.output
    project_path = Path(json.loads(created.stdout.splitlines()[-1])["path"])
    database = project_path / "image_database.db"
    if state == "missing":
        database.unlink()
    elif state in {"old", "current", "tags_missing"}:
        engine = db_core._prepare_project_database(database)
        if state == "old":
            with engine.begin() as connection:
                connection.execute(text("UPDATE alembic_version SET version_num='synthetic_old_revision'"))
        engine.dispose()
    before = {
        str(path.relative_to(workspace)): path.read_bytes() if path.is_file() else None
        for path in workspace.rglob("*")
        if not path.name.endswith(("-wal", "-shm"))
    }
    monkeypatch.setattr(
        db_core, "_prepare_project_database", Mock(side_effect=AssertionError("migration forbidden"))
    )
    monkeypatch.setattr(
        "lorairo.filesystem.FileSystemManager.initialize",
        Mock(side_effect=AssertionError("mkdir forbidden")),
    )
    monkeypatch.setattr("socket.socket.connect", Mock(side_effect=AssertionError("network forbidden")))
    if state == "tags_missing":
        import genai_tag_db_tools
        from genai_tag_db_tools import core_api
        from genai_tag_db_tools.db import runtime

        monkeypatch.setattr(genai_tag_db_tools, "initialize_databases", core_api.initialize_databases)
        monkeypatch.setattr("huggingface_hub.try_to_load_from_cache", Mock(return_value=None))
        monkeypatch.setattr(
            core_api, "ensure_databases", Mock(side_effect=AssertionError("download forbidden"))
        )
        monkeypatch.setattr(
            runtime, "init_user_db", Mock(side_effect=AssertionError("tag DB initialization forbidden"))
        )
    else:
        # The project DB is real. Tag resolution is isolated for these cases.
        monkeypatch.setattr(
            "lorairo.services.dataset_export_service.DatasetExportService._get_export_reader",
            lambda self: None,
        )
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    output = tmp_path / "output"
    event.listen(Engine, "before_cursor_execute", capture)
    try:
        result = runner.invoke(
            app,
            [
                "--json",
                "--workspace",
                str(workspace),
                "export",
                "create",
                "--dry-run",
                "--project",
                "synthetic",
                "--image-ids",
                "1",
                "--output",
                str(output),
            ],
        )
    finally:
        event.remove(Engine, "before_cursor_execute", capture)
    row = json.loads(result.stdout.splitlines()[-1])
    assert result.exit_code == 1, result.output
    if state == "current":
        assert row["kind"] == "result", result.output
        assert row["dry_run"] is True
        assert row["would_export"] == 0
        assert row["error_details"][0]["errors"][0]["reason"] == "image_not_found"
    else:
        assert row["code"] == "PRECONDITION_FAILED", result.output
    assert not output.exists()
    assert not [
        sql
        for sql in statements
        if sql.split()[0].upper() in {"CREATE", "INSERT", "UPDATE", "DELETE", "ALTER"}
    ]
    assert {
        str(path.relative_to(workspace)): path.read_bytes() if path.is_file() else None
        for path in workspace.rglob("*")
        if not path.name.endswith(("-wal", "-shm"))
    } == before
