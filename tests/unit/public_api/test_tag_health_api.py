"""The actual tag health facade never prepares or changes its project database."""

import json
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from lorairo.cli.main import app
from lorairo.database import db_core
from lorairo.database.access_policy import is_read_only
from lorairo.database.schema import Image, Tag
from lorairo.public_api.exceptions import ReadOnlyPreconditionError
from lorairo.public_api.tag_health import report_tag_health
from lorairo.services.project_management_service import ProjectManagementService
from lorairo.utils.config import resolve_runtime_configuration, runtime_configuration_scope

pytestmark = pytest.mark.unit


def _snapshot(workspace):
    return {
        str(path.relative_to(workspace)): path.read_bytes()
        for path in workspace.rglob("*")
        if path.is_file() and not path.name.endswith(("-wal", "-shm"))
    }


@pytest.mark.parametrize("database_state", ["current", "missing", "old", "incompatible"])
def test_report_uses_real_read_only_database_without_side_effects(tmp_path, monkeypatch, database_state):
    workspace = tmp_path / "tag-health-workspace"
    monkeypatch.setenv("LORAIRO_CLI_LOG_PATH", str(tmp_path / "cli.log"))
    configuration = resolve_runtime_configuration(workspace, None)
    with runtime_configuration_scope(configuration):
        info = ProjectManagementService().create_project("project")
    db = info.path / "image_database.db"
    engine = db_core._prepare_project_database(db)
    with Session(engine) as session:
        for image_id in (1, 2, 3):
            session.add(
                Image(
                    id=image_id,
                    uuid=f"synthetic-{image_id}",
                    phash=f"synthetic-{image_id}",
                    original_image_path=f"{image_id}.png",
                    stored_image_path=f"{image_id}.png",
                    width=32,
                    height=32,
                    format="PNG",
                    extension=".png",
                )
            )
        session.add_all(
            [Tag(image_id=1, tag="Cat"), Tag(image_id=2, tag="cat", rejected_at=datetime.now(UTC))]
        )
        session.commit()
    if database_state == "old":
        with engine.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num='synthetic_old_revision'"))
    elif database_state == "incompatible":
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE tags"))
    engine.dispose()
    if database_state == "missing":
        db.unlink()

    before = _snapshot(workspace)
    directories = {str(path.relative_to(workspace)) for path in workspace.rglob("*") if path.is_dir()}
    for target in (
        "lorairo.database.db_core._prepare_project_database",
        "lorairo.database.db_core.ensure_tag_db_initialized",
        "lorairo.filesystem.FileSystemManager.initialize",
        "lorairo.services.configuration_service.ensure_config_file",
        "socket.socket.connect",
    ):
        monkeypatch.setattr(target, Mock(side_effect=AssertionError(f"Forbidden side effect: {target}")))
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    previous_db = db_core.IMG_DB_PATH
    event.listen(Engine, "before_cursor_execute", capture)
    try:
        with runtime_configuration_scope(configuration):
            if database_state == "current":
                report = report_tag_health("project", ["cat"], limit=1)
                assert report.total_images == 3 and report.untagged_images == 2
                assert report.frequencies[0].tag == "Cat" and report.frequencies[0].image_count == 1
                assert report.missing_expected[0].missing_count == 2
                assert report.missing_expected[0].image_ids == [2]
            else:
                with pytest.raises(ReadOnlyPreconditionError):
                    report_tag_health("project", ["cat"])
        # The command must enforce read-only behavior even without the global flag.
        result = CliRunner().invoke(
            app,
            [
                "--json",
                "--log-level",
                "ERROR",
                "--workspace",
                str(workspace),
                "tags",
                "health",
                "-p",
                "project",
                "--expected-tag",
                "cat",
            ],
        )
        payload = json.loads(result.stdout.splitlines()[-1])
        if database_state == "current":
            assert result.exit_code == 0, result.output
            assert payload["read_only"] is True and payload["total_images"] == 3
        else:
            assert result.exit_code == 1, result.output
            assert payload["code"] == "PRECONDITION_FAILED"
        if database_state == "current":
            monkeypatch.chdir(workspace)
            monkeypatch.setattr(
                "lorairo.utils.config.DEFAULT_CONFIG_PATH", workspace / "config" / "lorairo.toml"
            )
            assert report_tag_health("project").total_images == 3
            assert not (workspace / "config" / "lorairo.toml").exists()
    finally:
        event.remove(Engine, "before_cursor_execute", capture)
    assert db_core.IMG_DB_PATH == previous_db and not is_read_only()
    assert _snapshot(workspace) == before
    assert {
        str(path.relative_to(workspace)) for path in workspace.rglob("*") if path.is_dir()
    } == directories
    assert not any(
        sql.lstrip().upper().startswith(("CREATE", "INSERT", "UPDATE", "DELETE", "ALTER", "DROP"))
        for sql in statements
    )
