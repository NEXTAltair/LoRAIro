"""Duplicate reporting never prepares databases or reads image contents."""

from unittest.mock import Mock

import pytest
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from lorairo.database import db_core
from lorairo.database.access_policy import is_read_only
from lorairo.database.schema import Image
from lorairo.public_api.duplicate_report import report_duplicates
from lorairo.public_api.exceptions import ReadOnlyPreconditionError
from lorairo.services.project_management_service import ProjectManagementService
from lorairo.utils.config import resolve_runtime_configuration, runtime_configuration_scope

pytestmark = pytest.mark.unit


def snapshot(workspace):
    return {
        str(path.relative_to(workspace)): path.read_bytes() if path.is_file() else None
        for path in workspace.rglob("*")
        if not path.name.endswith(("-wal", "-shm"))
    }


@pytest.mark.parametrize("state", ["current", "missing", "empty", "old", "incompatible"])
def test_duplicate_report_is_strictly_read_only_for_real_project(tmp_path, monkeypatch, state):
    workspace = tmp_path / "duplicate-workspace"
    configuration = resolve_runtime_configuration(workspace, None)
    with runtime_configuration_scope(configuration):
        project = ProjectManagementService().create_project("synthetic")
    database = project.path / "image_database.db"
    if state != "empty":
        engine = db_core._prepare_project_database(database)
        with Session(engine) as session:
            session.add_all(
                Image(
                    id=index,
                    uuid=f"synthetic-{index}",
                    phash=value,
                    original_image_path=f"unread/{index}.png",
                    stored_image_path=f"missing/{index}.png",
                    width=32,
                    height=32,
                    format="PNG",
                    extension=".png",
                )
                for index, value in enumerate(["0" * 16, "0000000000000001", "f" * 16, "bad", ""], 1)
            )
            session.commit()
        if state == "old":
            with engine.begin() as connection:
                connection.execute(text("UPDATE alembic_version SET version_num='synthetic_old_revision'"))
        elif state == "incompatible":
            with engine.begin() as connection:
                connection.execute(text("DROP TABLE images"))
        engine.dispose()
    if state == "missing":
        database.unlink()
    before = snapshot(workspace)
    for target in (
        "lorairo.database.db_core._prepare_project_database",
        "lorairo.database.db_core.ensure_tag_db_initialized",
        "lorairo.filesystem.FileSystemManager.initialize",
        "lorairo.services.configuration_service.ensure_config_file",
        "lorairo.utils.tools.calculate_phash",
        "PIL.Image.open",
        "socket.socket.connect",
    ):
        monkeypatch.setattr(target, Mock(side_effect=AssertionError(f"Forbidden: {target}")))
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    previous_db = db_core.IMG_DB_PATH
    event.listen(Engine, "before_cursor_execute", capture)
    try:
        with runtime_configuration_scope(configuration):
            if state == "current":
                report = report_duplicates("synthetic", max_distance=1, limit=1)
                assert report.total_images == 5
                assert report.cluster_count == 1 and report.clustered_images == 2
                assert report.missing_phash_images == report.invalid_phash_images == 1
                assert report.clusters[0].members[0].stored_image_path == "missing/1.png"
                assert report.clusters[0].members_truncated
            else:
                with pytest.raises(ReadOnlyPreconditionError):
                    report_duplicates("synthetic")
        if state == "current":
            monkeypatch.chdir(workspace)
            monkeypatch.setattr(
                "lorairo.utils.config.DEFAULT_CONFIG_PATH", workspace / "config" / "lorairo.toml"
            )
            assert report_duplicates("synthetic", max_distance=64).clustered_images == 3
    finally:
        event.remove(Engine, "before_cursor_execute", capture)
    assert db_core.IMG_DB_PATH == previous_db and not is_read_only()
    assert snapshot(workspace) == before
    assert not any(
        statement.lstrip().upper().startswith(("CREATE", "INSERT", "UPDATE", "DELETE", "ALTER", "DROP"))
        for statement in statements
    )
