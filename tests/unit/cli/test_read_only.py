"""Strict CLI reads use synthetic DBs only; do not silently prepare user data."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from typer.testing import CliRunner

from lorairo.cli.introspection import TOOL_SPECS
from lorairo.cli.main import app
from lorairo.database import db_core
from lorairo.public_api.exceptions import ReadOnlyPreconditionError

runner = CliRunner()
READ_COMMANDS = [
    ["images", "list"],
    ["images", "search", "--query", "{}"],
    ["images", "show", "1"],
    ["batch", "list"],
    ["errors", "list"],
    ["errors", "get", "1"],
]


@pytest.fixture
def project(tmp_path, monkeypatch):
    workspace = tmp_path / "作業 workspace"
    monkeypatch.setenv("LORAIRO_CLI_LOG_PATH", str(tmp_path / "cli.log"))
    result = runner.invoke(app, ["--json", "--workspace", str(workspace), "project", "create", "synthetic"])
    assert result.exit_code == 0, result.output
    path = Path(json.loads(result.stdout.splitlines()[-1])["path"])
    return workspace, path


def invoke(workspace, command):
    return runner.invoke(
        app, ["--json", "--workspace", str(workspace), "--read-only", *command, "--project", "synthetic"]
    )


def snapshot(path):
    return {
        str(p.relative_to(path)): p.read_bytes()
        for p in path.rglob("*")
        if p.is_file() and not p.name.endswith(("-wal", "-shm"))
    }


@pytest.mark.parametrize("state", ["missing", "empty", "old", "current"])
@pytest.mark.parametrize("command", READ_COMMANDS)
def test_read_commands_never_prepare_database(project, state, command, monkeypatch):
    workspace, path = project
    db = path / "image_database.db"
    if state == "missing":
        db.unlink()
    elif state in {"old", "current"}:
        engine = db_core._prepare_project_database(db)
        if state == "old":
            with engine.begin() as connection:
                connection.execute(text("UPDATE alembic_version SET version_num='synthetic_old_revision'"))
        engine.dispose()
    before = snapshot(path)
    directories = {str(p.relative_to(path)) for p in path.rglob("*") if p.is_dir()}
    monkeypatch.setattr(
        db_core, "_prepare_project_database", Mock(side_effect=AssertionError("preparation forbidden"))
    )
    monkeypatch.setattr(
        "lorairo.filesystem.FileSystemManager.initialize",
        Mock(side_effect=AssertionError("directory initialization forbidden")),
    )
    monkeypatch.setattr("socket.socket.connect", Mock(side_effect=AssertionError("network forbidden")))
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(Engine, "before_cursor_execute", capture)
    try:
        result = invoke(workspace, command)
    finally:
        event.remove(Engine, "before_cursor_execute", capture)
    payload = json.loads(result.stdout.splitlines()[-1])
    if state == "current":
        assert result.exit_code in (0, 1), result.output
        assert payload.get("code") not in {"INTERNAL_ERROR", "DB_ERROR", "PRECONDITION_FAILED"}, (
            result.output
        )
    else:
        assert result.exit_code == 1, result.output
        assert payload["code"] == "PRECONDITION_FAILED", result.output
        assert "project prepare" in payload["hint"]
    assert not [
        sql
        for sql in statements
        if sql.split()[0].upper() in {"CREATE", "INSERT", "UPDATE", "DELETE", "ALTER"}
    ]
    assert snapshot(path) == before
    assert {str(p.relative_to(path)) for p in path.rglob("*") if p.is_dir()} == directories


def test_explicit_prepare_then_strict_read_and_engine_write_rejection(project):
    workspace, path = project
    result = runner.invoke(
        app, ["--json", "--workspace", str(workspace), "project", "prepare", "--project", "synthetic"]
    )
    assert result.exit_code == 0, result.output
    assert invoke(workspace, ["images", "list"]).exit_code == 0
    factory = db_core.create_project_session_factory(path / "image_database.db", read_only=True)
    with factory() as session, pytest.raises(OperationalError, match="readonly"):
        session.execute(text("DELETE FROM model_types"))


def test_strict_mode_rejects_write_commands_before_work(project):
    workspace, path = project
    before = snapshot(path)
    for command in [
        ["project", "prepare", "--project", "synthetic"],
        ["project", "delete", "synthetic", "--force"],
        ["models", "refresh"],
    ]:
        result = runner.invoke(app, ["--json", "--workspace", str(workspace), "--read-only", *command])
        assert result.exit_code == 1, result.output
        assert json.loads(result.stdout.splitlines()[-1])["details"]["reason"] == "write_command"
    assert snapshot(path) == before


def test_strict_metadata_inventory_and_config_read_preservation(tmp_path, monkeypatch):
    expected = {
        "version",
        "status",
        "project list",
        "images list",
        "images search",
        "images show",
        "tags translations show",
        "models list",
        "batch list",
        "errors list",
        "errors get",
    }
    assert {name for name, spec in TOOL_SPECS.items() if spec.read_only} == expected
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LORAIRO_CLI_LOG_PATH", str(tmp_path / "cli.log"))
    for command in [
        ["version"],
        ["status"],
        ["project", "list"],
        ["models", "list"],
        ["describe", "images list"],
        ["list-commands"],
    ]:
        result = runner.invoke(app, ["--json", "--read-only", *command])
        assert result.exit_code == 0, result.output
    assert not (tmp_path / "lorairo_data").exists()
    assert not (tmp_path / "config").exists()
    tool = TOOL_SPECS["images list"].tool_payload()
    assert tool["strict_read_only_supported"] is True
    assert "schema_migration" in tool["conditional_side_effects"]


def test_missing_model_seed_is_a_precondition(project):
    _, path = project
    db = path / "image_database.db"
    engine = db_core._prepare_project_database(db)
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM model_types"))
    engine.dispose()
    with pytest.raises(ReadOnlyPreconditionError) as error:
        db_core.create_project_session_factory(db, read_only=True)
    assert error.value.details["reason"] == "model_seed_required"


@pytest.fixture
def offline_tag_databases(project, tmp_path, monkeypatch):
    import genai_tag_db_tools
    from genai_tag_db_tools import core_api, database_runtime_scope
    from genai_tag_db_tools.db import runtime
    from genai_tag_db_tools.db.schema import Base
    from sqlalchemy import create_engine

    workspace, path = project
    db_core._prepare_project_database(path / "image_database.db").dispose()
    base = tmp_path / "base.sqlite"
    engine = create_engine(f"sqlite:///{base}")
    Base.metadata.create_all(engine)
    engine.dispose()
    with database_runtime_scope():
        runtime.init_user_db(workspace / "lorairo_data", format_name="Lorairo")
    monkeypatch.setattr(genai_tag_db_tools, "initialize_databases", core_api.initialize_databases)
    monkeypatch.setattr(runtime, "get_user_session_factory", runtime.get_user_session_factory_optional)
    monkeypatch.setattr("huggingface_hub.try_to_load_from_cache", Mock(return_value=str(base)))
    monkeypatch.setattr("socket.socket.connect", Mock(side_effect=AssertionError("network forbidden")))
    monkeypatch.setattr(
        core_api, "ensure_databases", Mock(side_effect=AssertionError("download forbidden"))
    )
    monkeypatch.setattr(runtime, "_BUSY_TIMEOUT_MS", 30)
    monkeypatch.setattr(
        "lorairo.filesystem.FileSystemManager.initialize",
        Mock(side_effect=AssertionError("directory preparation forbidden")),
    )
    directories = {item.relative_to(workspace) for item in workspace.rglob("*") if item.is_dir()}
    yield workspace, path, base, workspace / "lorairo_data" / "user_tags.sqlite"
    assert {item.relative_to(workspace) for item in workspace.rglob("*") if item.is_dir()} == directories


@pytest.mark.parametrize("cache_available", [True, False])
def test_translation_reads_use_offline_protected_tag_runtime(
    offline_tag_databases, monkeypatch, cache_available
):
    workspace, _path, _base, _user = offline_tag_databases
    if not cache_available:
        monkeypatch.setattr("huggingface_hub.try_to_load_from_cache", Mock(return_value=None))
    before = snapshot(workspace)
    result = invoke(workspace, ["tags", "translations", "show", "--tags", "cat"])
    payload = json.loads(result.stdout.splitlines()[-1])
    if cache_available:
        assert result.exit_code == 0, result.output
    else:
        assert result.exit_code == 1, result.output
        assert payload["code"] == "PRECONDITION_FAILED"
        assert "--tags" in payload["hint"]
    assert snapshot(workspace) == before


def test_explicit_prepare_upgrades_real_old_revision(project):
    from alembic import command

    workspace, path = project
    db = path / "image_database.db"
    db_core._prepare_project_database(db).dispose()
    command.downgrade(db_core._make_alembic_config(db), "-1")
    before = snapshot(path)
    result = invoke(workspace, ["images", "list"])
    assert result.exit_code == 1
    assert json.loads(result.stdout.splitlines()[-1])["details"]["reason"] == "schema_upgrade_required"
    assert snapshot(path) == before
    prepared = runner.invoke(
        app, ["--json", "--workspace", str(workspace), "project", "prepare", "--project", "synthetic"]
    )
    assert prepared.exit_code == 0, prepared.output
    assert invoke(workspace, ["images", "list"]).exit_code == 0


def test_strict_fetch_and_manual_rating_filter_without_model_seed(project):
    from sqlalchemy import select

    from lorairo.database.schema import Image, Model

    workspace, path = project
    db = path / "image_database.db"
    factory = db_core.create_project_session_factory(db)
    image_path = path / "synthetic.png"
    image_path.write_bytes(b"synthetic metadata fixture; not decoded")
    with factory() as session:
        session.add(
            Image(
                id=1,
                uuid="synthetic",
                phash="0",
                original_image_path=str(image_path),
                stored_image_path="synthetic.png",
                width=1,
                height=1,
                format="PNG",
                extension=".png",
            )
        )
        session.commit()
    before = snapshot(path)
    for command in [
        ["images", "list", "--fetch"],
        ["images", "show", "1"],
        ["images", "search", "--query", '{"manual_rating":"UNRATED"}'],
    ]:
        result = invoke(workspace, command)
        assert result.exit_code == 0, result.output
        rows = [json.loads(line) for line in result.stdout.splitlines()]
        assert any(row.get("kind") == "item" for row in rows), result.output
    rated = invoke(workspace, ["images", "search", "--query", '{"manual_rating":"RATED"}'])
    assert rated.exit_code == 0, rated.output
    assert not any(json.loads(line).get("kind") == "item" for line in rated.stdout.splitlines())
    with factory() as session:
        assert list(session.execute(select(Model.id)).scalars()) == []
    assert snapshot(path) == before


def test_selected_default_repository_respects_strict_mode(tmp_path):
    from lorairo.database.access_policy import read_only_scope
    from lorairo.services.service_container import service_container_scope
    from lorairo.utils.config import resolve_runtime_configuration, runtime_configuration_scope

    selected = resolve_runtime_configuration(tmp_path / "workspace", None)
    old_default_factory = db_core._default_session_factory
    with runtime_configuration_scope(selected), read_only_scope(), service_container_scope() as container:
        with pytest.raises(ReadOnlyPreconditionError) as error:
            _ = container.image_repository
        assert error.value.details["database_path"] == str(
            selected.workspace / "lorairo_data/image_database.db"
        )
    assert db_core._default_session_factory is old_default_factory
    assert not selected.workspace.exists()


def test_readonly_alone_isolates_existing_writable_factories(project, tmp_path, monkeypatch):
    import importlib

    from lorairo.database.access_policy import is_read_only
    from lorairo.services.service_container import ServiceContainer

    workspace, _ = project
    config = tmp_path / "legacy.toml"
    config.write_text(
        "[directories]\ndatabase_base_dir = " + json.dumps(str(workspace / "lorairo_data")) + "\n"
    )
    monkeypatch.setattr(importlib.import_module("lorairo.cli.main"), "DEFAULT_CONFIG_PATH", config)
    legacy = ServiceContainer()
    previous_repository = legacy._image_repository
    cached_repository = Mock()
    legacy._image_repository = cached_repository
    cached_factory = Mock(side_effect=AssertionError("legacy writable factory reused"))
    monkeypatch.setattr(db_core, "_default_session_factory", cached_factory)
    before = snapshot(workspace)
    try:
        for _ in range(2):
            result = runner.invoke(
                app, ["--json", "--read-only", "images", "list", "--project", "synthetic"]
            )
            assert result.exit_code == 1, result.output
            assert json.loads(result.stdout.splitlines()[-1])["code"] == "PRECONDITION_FAILED"
            assert not is_read_only()
            assert legacy._image_repository is cached_repository
        cached_factory.assert_not_called()
        assert not cached_repository.mock_calls
        assert snapshot(workspace) == before
        assert config.read_text().startswith("[directories]")
    finally:
        legacy._image_repository = previous_repository


@pytest.mark.parametrize("state", ["untracked", "incompatible", "unreadable"])
def test_legacy_or_damaged_database_guidance_does_not_promise_prepare_repair(project, state):
    from sqlalchemy import create_engine

    from lorairo.database.schema import Base

    workspace, path = project
    db = path / "image_database.db"
    if state == "unreadable":
        db.write_bytes(b"synthetic invalid SQLite data")
    elif state == "untracked":
        engine = create_engine(f"sqlite:///{db}")
        Base.metadata.create_all(engine)
        engine.dispose()
    else:
        engine = db_core._prepare_project_database(db)
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE score_labels"))
        engine.dispose()
    before = snapshot(path)
    result = invoke(workspace, ["images", "list"])
    assert result.exit_code == 1, result.output
    payload = json.loads(result.stdout.splitlines()[-1])
    assert payload["code"] == "PRECONDITION_FAILED"
    assert (
        payload["details"]["reason"]
        == {
            "untracked": "untracked_schema",
            "incompatible": "incompatible_schema",
            "unreadable": "unreadable_or_incompatible_database",
        }[state]
    )
    assert "Preserve a backup" in payload["hint"]
    assert "project prepare may not repair" in payload["hint"]
    assert payload["details"]["documentation"] == "docs/cli-read-only.md"
    assert payload["details"]["recovery_action"] == "supported_migration_or_recovery"
    assert snapshot(path) == before


def test_strict_exclusive_lock_is_retryable_and_uses_configured_timeout(project):
    import sqlite3
    import time

    workspace, path = project
    db = path / "image_database.db"
    db_core._prepare_project_database(db).dispose()
    config = workspace / "lock-config.toml"
    config.write_text("[directories]\n[database]\nbusy_timeout_ms = 30\n")
    with sqlite3.connect(db) as writer:
        assert writer.execute("PRAGMA journal_mode=DELETE").fetchone()[0] == "delete"
        before = db.read_bytes()
        writer.execute("BEGIN EXCLUSIVE")
        started = time.monotonic()
        result = runner.invoke(
            app,
            [
                "--json",
                "--workspace",
                str(workspace),
                "--config",
                str(config),
                "--read-only",
                "images",
                "list",
                "--project",
                "synthetic",
            ],
        )
        elapsed = time.monotonic() - started
        writer.rollback()
    payload = json.loads(result.stdout.splitlines()[-1])
    assert result.exit_code == 1, result.output
    assert payload["code"] == "CONFLICT"
    assert payload["retryable"] is True
    assert payload["user_action_required"] is False
    assert elapsed < 3, "configured 30ms timeout must not fall back to sqlite's 5-second default"
    assert db.read_bytes() == before
    retry = invoke(workspace, ["images", "list"])
    assert retry.exit_code == 0, retry.output


def test_strict_connection_preserves_configured_busy_timeout(project):
    from lorairo.utils.config import RuntimeConfiguration, runtime_configuration_scope

    workspace, path = project
    db = path / "image_database.db"
    db_core._prepare_project_database(db).dispose()
    runtime = RuntimeConfiguration(
        workspace, workspace / "synthetic.toml", {"database": {"busy_timeout_ms": 47}}
    )
    with runtime_configuration_scope(runtime):
        engine = db_core._open_read_only_project_database(db)
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar() == 47
            assert connection.exec_driver_sql("PRAGMA query_only").scalar() == 1
    finally:
        engine.dispose()


@pytest.mark.parametrize("database", ["base", "user"])
def test_strict_tag_lock_preserves_conflict_and_same_process_retry(offline_tag_databases, database):
    import sqlite3

    workspace, _path, base, user = offline_tag_databases
    target = base if database == "base" else user
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    with sqlite3.connect(target) as writer:
        assert writer.execute("PRAGMA journal_mode=DELETE").fetchone()[0] == "delete"
        before = snapshot(workspace)
        base_before = base.read_bytes()
        writer.execute("BEGIN EXCLUSIVE")
        event.listen(Engine, "before_cursor_execute", capture)
        try:
            result = invoke(workspace, ["tags", "translations", "show", "--tags", "cat"])
        finally:
            event.remove(Engine, "before_cursor_execute", capture)
            writer.rollback()
    payload = json.loads(result.stdout.splitlines()[-1])
    assert result.exit_code == 1, result.output
    assert payload["code"] == "CONFLICT"
    assert payload["retryable"] is True
    assert payload["user_action_required"] is False
    assert "prepare" not in payload.get("hint", "")
    assert snapshot(workspace) == before
    assert base.read_bytes() == base_before
    assert not any(
        sql.lstrip().upper().startswith(("CREATE", "INSERT", "UPDATE", "DELETE", "ALTER"))
        for sql in statements
    )
    retry = invoke(workspace, ["tags", "translations", "show", "--tags", "cat"])
    assert retry.exit_code == 0, retry.output
    assert snapshot(workspace) == before
    assert base.read_bytes() == base_before


@pytest.mark.parametrize("database", ["project", "base", "user"])
def test_strict_database_disk_io_preserves_environment_hint(offline_tag_databases, database):
    import sqlite3

    workspace, path, base, user = offline_tag_databases
    target = {"project": path / "image_database.db", "base": base, "user": user}[database]
    command = (
        ["images", "list"] if database == "project" else ["tags", "translations", "show", "--tags", "cat"]
    )
    before = snapshot(workspace)
    base_before = base.read_bytes()

    def fail_read(conn, cursor, statement, parameters, context, executemany):
        if conn.engine.url.query.get("mode") == "ro" and str(conn.engine.url.database).endswith(
            target.name
        ):
            raise OperationalError(statement, parameters, sqlite3.OperationalError("disk I/O error"))

    event.listen(Engine, "before_cursor_execute", fail_read)
    try:
        result = invoke(workspace, command)
    finally:
        event.remove(Engine, "before_cursor_execute", fail_read)
    payload = json.loads(result.stdout.splitlines()[-1])
    assert result.exit_code == 1, result.output
    assert payload["code"] == "IO_ERROR"
    assert payload["retryable"] is False
    assert payload["user_action_required"] is True
    assert "同一 OS" in payload["hint"]
    assert "prepare" not in payload["hint"]
    assert snapshot(workspace) == before
    assert base.read_bytes() == base_before
    assert invoke(workspace, command).exit_code == 0


@pytest.mark.parametrize("state", ["missing", "incompatible"])
def test_strict_tag_preparation_conditions_remain_preconditions(offline_tag_databases, state):
    import sqlite3

    workspace, _path, base, user = offline_tag_databases
    if state == "missing":
        user.unlink()
    else:
        with sqlite3.connect(user) as connection:
            connection.execute("DROP TABLE TAG_TRANSLATIONS")
    before = snapshot(workspace)
    base_before = base.read_bytes()
    result = invoke(workspace, ["tags", "translations", "show", "--tags", "cat"])
    payload = json.loads(result.stdout.splitlines()[-1])
    assert result.exit_code == 1, result.output
    assert payload["code"] == "PRECONDITION_FAILED"
    assert payload["retryable"] is False
    assert "project prepare" in payload["hint"]
    assert snapshot(workspace) == before
    assert base.read_bytes() == base_before


def test_strict_tag_untyped_initialization_failure_is_not_preparation(offline_tag_databases, monkeypatch):
    workspace, _path, base, _user = offline_tag_databases
    monkeypatch.setattr(
        "genai_tag_db_tools.initialize_databases",
        Mock(side_effect=OSError("synthetic initialization I/O failure")),
    )
    before = snapshot(workspace)
    base_before = base.read_bytes()
    result = invoke(workspace, ["tags", "translations", "show", "--tags", "cat"])
    payload = json.loads(result.stdout.splitlines()[-1])
    assert result.exit_code == 1, result.output
    assert payload["code"] == "IO_ERROR"
    assert "prepare" not in payload.get("hint", "")
    assert snapshot(workspace) == before
    assert base.read_bytes() == base_before
