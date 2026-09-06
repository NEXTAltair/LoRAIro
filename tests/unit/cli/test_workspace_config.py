"""Explicit CLI workspace/config selection uses temporary projects only (#1311)."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app
from lorairo.services.service_container import ServiceContainer, service_container_scope
from lorairo.utils.config import (
    get_config,
    get_runtime_configuration,
    resolve_runtime_configuration,
    runtime_configuration_scope,
)

runner = CliRunner()


def invoke(workspace: Path, *arguments: str):
    result = runner.invoke(app, ["--json", "--workspace", str(workspace), *arguments])
    assert result.exit_code == 0, result.output
    return [json.loads(line) for line in result.stdout.splitlines()]


@pytest.mark.unit
def test_same_explicit_workspace_from_two_cwds(tmp_path, monkeypatch):
    workspace = tmp_path / "作業 領域"
    created = invoke(workspace, "project", "create", "common-project")[-1]
    outputs = []
    for cwd in (tmp_path / "cwd a", tmp_path / "cwd 日本語"):
        cwd.mkdir()
        monkeypatch.chdir(cwd)
        outputs.append(invoke(workspace, "project", "list"))
        status = invoke(workspace, "status")[-1]
        assert status["workspace"] == str(workspace)
        assert status["config_path"] == str(workspace / "config" / "lorairo.toml")
        assert status["projects_base_dir"] == str(workspace / "lorairo_data")
        assert status["config_found"] is False
    assert outputs[0] == outputs[1]
    assert outputs[0][0]["path"] == created["path"]
    assert not (workspace / "config").exists()


@pytest.mark.unit
def test_same_name_workspaces_do_not_cross_write_or_cache(tmp_path):
    left, right = tmp_path / "left", tmp_path / "right"
    left_project = Path(invoke(left, "project", "create", "same")[-1]["path"])
    right_project = Path(invoke(right, "project", "create", "same")[-1]["path"])
    marker = right_project / "preserve.txt"
    marker.write_text("right data")
    invoke(left, "project", "delete", "same", "--force")
    assert not left_project.exists()
    assert marker.read_text() == "right data"
    assert invoke(right, "project", "list")[-1]["count"] == 1
    assert invoke(left, "project", "list")[-1]["count"] == 0
    assert get_runtime_configuration() is None


@pytest.mark.unit
def test_config_only_relative_and_absolute_paths_have_stable_anchor(tmp_path, monkeypatch):
    config = tmp_path / "設定 フォルダ" / "custom.toml"
    config.parent.mkdir()
    config.write_text('[directories]\ndatabase_base_dir = "画像 データ"\n', encoding="utf-8")
    before = config.read_bytes()
    for cwd, option in ((tmp_path, config.relative_to(tmp_path)), (config.parent, config)):
        monkeypatch.chdir(cwd)
        result = runner.invoke(app, ["--json", "--config", str(option), "status"])
        assert result.exit_code == 0, result.output
        row = json.loads(result.stdout)
        assert row["workspace"] == str(config.parent)
        assert row["config_path"] == str(config)
        assert row["projects_base_dir"] == str(config.parent / "画像 データ")
    assert config.read_bytes() == before
    assert not (config.parent / "画像 データ").exists()


@pytest.mark.unit
def test_workspace_precedence_and_absolute_configured_base(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    workspace = tmp_path / "workspace"
    config = tmp_path / "outside.toml"
    config.write_text('[directories]\ndatabase_base_dir = "custom-data"\n')
    for value, expected in (
        ("custom-data", workspace / "custom-data"),
        (str(tmp_path / "absolute"), tmp_path / "absolute"),
    ):
        config.write_text(f'[directories]\ndatabase_base_dir = "{value}"\n')
        result = runner.invoke(
            app, ["--json", "--workspace", "workspace", "--config", "outside.toml", "status"]
        )
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["projects_base_dir"] == str(expected)


@pytest.mark.unit
@pytest.mark.parametrize("bad_config", ["missing.toml", "bad.toml"])
def test_explicit_config_errors_are_structured_and_scope_is_restored(tmp_path, bad_config):
    (tmp_path / "bad.toml").write_text("invalid [ toml")
    result = runner.invoke(app, ["--json", "--config", str(tmp_path / bad_config), "project", "list"])
    assert result.exit_code == 2
    row = json.loads(result.stdout)
    assert row["code"] == "INVALID_INPUT"
    assert get_runtime_configuration() is None
    assert not (tmp_path / "missing.toml").exists()


@pytest.mark.unit
def test_command_error_restores_scoped_container_and_config(tmp_path):
    original = ServiceContainer()
    result = runner.invoke(
        app, ["--json", "--workspace", str(tmp_path), "project", "delete", "missing", "--force"]
    )
    assert result.exit_code == 1
    assert get_runtime_configuration() is None
    assert ServiceContainer() is original


@pytest.mark.unit
def test_nested_scopes_restore_config_container_and_active_db_path(tmp_path, monkeypatch):
    from lorairo.database import db_core

    outer = resolve_runtime_configuration(tmp_path / "outer", None)
    inner = resolve_runtime_configuration(tmp_path / "inner", None)
    previous = db_core.IMG_DB_PATH
    with runtime_configuration_scope(outer), service_container_scope() as outer_container:
        outer_db = tmp_path / "outer.db"
        monkeypatch.setattr(db_core, "IMG_DB_PATH", outer_db)
        with runtime_configuration_scope(inner), service_container_scope() as inner_container:
            assert inner_container is ServiceContainer()
            assert inner_container is not outer_container
            assert (
                inner_container.project_management_service.projects_base_dir
                == inner.workspace / "lorairo_data"
            )
            db_core.IMG_DB_PATH = tmp_path / "inner.db"
        assert db_core.IMG_DB_PATH == outer_db
        assert ServiceContainer() is outer_container
        assert get_config()["directories"]["database_base_dir"] == str(outer.workspace / "lorairo_data")
    assert db_core.IMG_DB_PATH == previous
    assert get_runtime_configuration() is None


@pytest.mark.unit
def test_explicit_scope_active_project_uses_selected_database(tmp_path, monkeypatch):
    from sqlalchemy import Column, MetaData, String, Table, create_engine, select
    from sqlalchemy.orm import sessionmaker

    from lorairo.database import db_core

    metadata = MetaData()
    probe = Table("workspace_probe", metadata, Column("value", String, primary_key=True))
    engines = []
    selected_paths = []

    def session_factory(path):
        selected_paths.append(path)
        engine = create_engine(f"sqlite:///{path}")
        metadata.create_all(engine)
        engines.append(engine)
        return sessionmaker(bind=engine)

    monkeypatch.setattr(db_core, "create_project_session_factory", session_factory)
    try:
        for name in ("left", "right"):
            selection = resolve_runtime_configuration(tmp_path / name, None)
            with runtime_configuration_scope(selection), service_container_scope() as container:
                project = container.project_management_service.create_project("same")
                container.set_active_project("same")
                assert selected_paths[-1] == project.path / "image_database.db"
                assert db_core.IMG_DB_PATH == selected_paths[-1]
                with container.image_repository.session_factory() as session:
                    session.execute(probe.insert().values(value=name))
                    session.commit()
        assert selected_paths[0] != selected_paths[1]
        for engine, expected in zip(engines, ("left", "right"), strict=True):
            with engine.connect() as connection:
                assert connection.execute(select(probe.c.value)).scalars().all() == [expected]
    finally:
        for engine in engines:
            engine.dispose()


@pytest.mark.unit
def test_nonexplicit_project_resolution_preserves_cwd_semantics(tmp_path, monkeypatch):
    from lorairo.services.project_management_service import ProjectManagementService

    monkeypatch.setattr(
        "lorairo.services.project_management_service.get_config",
        lambda: {"directories": {"database_base_dir": "legacy-data"}},
    )
    for directory in (tmp_path / "a", tmp_path / "b"):
        directory.mkdir()
        monkeypatch.chdir(directory)
        assert ProjectManagementService().projects_base_dir == directory / "legacy-data"


@pytest.mark.unit
def test_help_and_describe_expose_root_path_contract():
    help_result = runner.invoke(app, ["--help"], color=False)
    assert help_result.exit_code == 0
    assert "--workspace" in help_result.stdout and "--config" in help_result.stdout
    for schema in ("compact", "json_schema"):
        result = runner.invoke(app, ["--json", "describe", "project list", "--schema", schema])
        assert result.exit_code == 0
        rows = [json.loads(line) for line in result.stdout.splitlines()]
        assert {option["name"] for option in rows[0]["global_options"]} == {
            "workspace",
            "config",
            "read_only",
        }
        assert any(row.get("name") == "GlobalOptions" for row in rows)


@pytest.mark.unit
def test_nested_cli_invocation_restores_outer_workspace(tmp_path, monkeypatch):
    outer = tmp_path / "outer"
    inner = tmp_path / "inner"

    def list_with_nested_status():
        container = ServiceContainer()
        nested = invoke(inner, "status")[-1]
        assert nested["workspace"] == str(inner)
        assert ServiceContainer() is container
        assert get_runtime_configuration().workspace == outer
        return []

    monkeypatch.setattr("lorairo.cli.commands.project.api_list_projects", list_with_nested_status)
    assert invoke(outer, "project", "list")[-1]["count"] == 0
    assert get_runtime_configuration() is None


@pytest.mark.unit
def test_workspace_default_config_is_loaded_without_modification(tmp_path):
    config = tmp_path / "config" / "lorairo.toml"
    config.parent.mkdir()
    config.write_text(
        '[directories]\ndatabase_base_dir = "selected-data"\n[api]\nopenai_key = "synthetic-test-key"\n'
    )
    before = config.read_bytes()
    status = invoke(tmp_path, "status")[-1]
    assert status["projects_base_dir"] == str(tmp_path / "selected-data")
    assert status["api_keys"]["openai"] is True
    assert config.read_bytes() == before


@pytest.mark.unit
def test_explicit_config_disappearing_does_not_fall_back_to_defaults(tmp_path, monkeypatch):
    config = tmp_path / "config.toml"
    config.write_text("[directories]\n")
    monkeypatch.setattr(
        "lorairo.utils.config.load_config", Mock(side_effect=FileNotFoundError("config disappeared"))
    )
    result = runner.invoke(app, ["--json", "--config", str(config), "project", "list"])
    assert result.exit_code == 2
    assert json.loads(result.stdout)["code"] == "INVALID_INPUT"
    assert get_runtime_configuration() is None


@pytest.mark.unit
def test_explicit_config_database_timeout_is_snapshotted_per_engine(tmp_path):
    from sqlalchemy import text

    from lorairo.database.db_core import create_db_engine

    config = tmp_path / "database.toml"
    config.write_text("[directories]\n[database]\nbusy_timeout_ms = 1234\n")
    selection = resolve_runtime_configuration(None, config)
    with runtime_configuration_scope(selection):
        engine = create_db_engine("sqlite:///:memory:")
    try:
        # First connection happens after scope exit: it must retain the selected setting.
        with engine.connect() as connection:
            assert connection.execute(text("PRAGMA busy_timeout")).scalar_one() == 1234
    finally:
        engine.dispose()


@pytest.mark.unit
def test_selected_tag_runtime_nested_and_sequential_writes_are_isolated(tmp_path, monkeypatch):
    import genai_tag_db_tools
    from genai_tag_db_tools.db import runtime
    from sqlalchemy import text

    from lorairo.database import db_core

    initialized = []

    def initialize(*, user_db_dir, **kwargs):
        initialized.append(user_db_dir)
        runtime.init_user_db(user_db_dir)
        return []

    monkeypatch.setattr(genai_tag_db_tools, "initialize_databases", initialize)
    legacy_directory = db_core.DB_DIR
    legacy_user_path = db_core.USER_TAG_DB_PATH
    legacy_initialized = db_core._tag_db_initialized
    outer = resolve_runtime_configuration(tmp_path / "外側 workspace", None)
    config_path = tmp_path / "selected.toml"
    config_path.write_text('[directories]\ndatabase_dir = "指定 tag DB"\n', encoding="utf-8")
    inner = resolve_runtime_configuration(tmp_path / "内側 workspace", config_path)

    def write_marker(value):
        db_core.ensure_tag_db_initialized()
        db_core.ensure_tag_db_initialized()
        factory = runtime.get_user_session_factory_optional()
        with factory() as session:
            session.execute(text("CREATE TABLE IF NOT EXISTS workspace_marker (value TEXT)"))
            session.execute(text("INSERT INTO workspace_marker VALUES (:value)"), {"value": value})
            session.commit()
        return factory

    with genai_tag_db_tools.database_runtime_scope():
        old_path = runtime.init_user_db(tmp_path / "existing legacy")
        old_factory = runtime.get_user_session_factory_optional()
        old_bytes = old_path.read_bytes()
        with runtime_configuration_scope(outer), service_container_scope():
            outer_factory = write_marker("outer")
            assert db_core.get_user_tag_db_path() == outer.workspace / "lorairo_data/user_tags.sqlite"
            with (
                pytest.raises(ValueError, match="synthetic"),
                runtime_configuration_scope(inner),
                service_container_scope(),
            ):
                write_marker("inner")
                assert db_core.get_user_tag_db_path() == inner.workspace / "指定 tag DB/user_tags.sqlite"
                raise ValueError("synthetic")
            assert runtime.get_user_session_factory_optional() is outer_factory
            with outer_factory() as session:
                assert session.execute(text("SELECT value FROM workspace_marker")).scalars().all() == [
                    "outer"
                ]
        assert runtime.get_user_session_factory_optional() is old_factory
        assert old_path.read_bytes() == old_bytes
        with runtime_configuration_scope(inner), service_container_scope():
            db_core.ensure_tag_db_initialized()
            with runtime.get_user_session_factory_optional()() as session:
                assert session.execute(text("SELECT value FROM workspace_marker")).scalars().all() == [
                    "inner"
                ]
        assert runtime.get_user_session_factory_optional() is old_factory
    assert initialized == [
        outer.workspace / "lorairo_data",
        inner.workspace / "指定 tag DB",
        inner.workspace / "指定 tag DB",
    ]
    assert db_core.DB_DIR == legacy_directory
    assert db_core.USER_TAG_DB_PATH == legacy_user_path
    assert db_core._tag_db_initialized == legacy_initialized


@pytest.mark.unit
def test_tag_initialization_failure_can_retry_in_selected_scope(tmp_path, monkeypatch):
    import genai_tag_db_tools

    from lorairo.database import db_core

    initialize = Mock(side_effect=[OSError("synthetic initialization failure"), []])
    monkeypatch.setattr(genai_tag_db_tools, "initialize_databases", initialize)
    selected = resolve_runtime_configuration(tmp_path / "workspace", None)
    with runtime_configuration_scope(selected), service_container_scope():
        with pytest.raises(RuntimeError, match="Tag database initialization failed"):
            db_core.ensure_tag_db_initialized()
        assert db_core.get_user_tag_db_path() is None
        db_core.ensure_tag_db_initialized()
        assert db_core.get_user_tag_db_path() == selected.workspace / "lorairo_data/user_tags.sqlite"
    assert initialize.call_count == 2
