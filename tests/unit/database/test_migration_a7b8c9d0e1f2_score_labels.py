"""Alembic migration `a7b8c9d0e1f2` convergence checks."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def _make_alembic_config(db_path: Path) -> Config:
    """Build an Alembic Config that targets the temporary DB."""
    project_root = Path(__file__).resolve().parents[3]
    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "src/lorairo/database/migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _create_d8_schema_with_precreated_score_labels(db_path: Path) -> None:
    """Create the stale state caused by metadata create_all before migration."""
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE images (
                    id INTEGER NOT NULL PRIMARY KEY,
                    uuid VARCHAR NOT NULL,
                    phash VARCHAR NOT NULL,
                    original_image_path VARCHAR NOT NULL,
                    stored_image_path VARCHAR NOT NULL,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    format VARCHAR NOT NULL,
                    mode VARCHAR NOT NULL,
                    has_alpha BOOLEAN NOT NULL,
                    filename VARCHAR NOT NULL,
                    extension VARCHAR NOT NULL,
                    color_space VARCHAR,
                    icc_profile BLOB,
                    manual_rating VARCHAR,
                    project_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE models (
                    id INTEGER NOT NULL PRIMARY KEY,
                    name VARCHAR NOT NULL,
                    provider VARCHAR,
                    discontinued_at TIMESTAMP,
                    litellm_model_id VARCHAR NOT NULL,
                    estimated_size_gb FLOAT,
                    requires_api_key BOOLEAN DEFAULT '0' NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    UNIQUE (litellm_model_id)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE model_types (
                    id INTEGER NOT NULL PRIMARY KEY,
                    name VARCHAR NOT NULL UNIQUE
                )
                """
            )
        )
        conn.execute(
            text(
                "INSERT INTO model_types (id, name) VALUES "
                "(1, 'tags'), (2, 'scores'), (3, 'caption'), "
                "(4, 'upscaler'), (5, 'multimodal')"
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE score_labels (
                    id INTEGER NOT NULL PRIMARY KEY,
                    image_id INTEGER NOT NULL,
                    model_id INTEGER NOT NULL,
                    label VARCHAR NOT NULL,
                    is_edited_manually BOOLEAN,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    FOREIGN KEY(image_id) REFERENCES images (id) ON DELETE CASCADE,
                    FOREIGN KEY(model_id) REFERENCES models (id) ON DELETE CASCADE
                )
                """
            )
        )
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('d8e9f0a1b2c3')"))
    engine.dispose()


@pytest.mark.unit
def test_score_labels_migration_converges_when_table_was_precreated(tmp_path: Path) -> None:
    """Upgrade succeeds even if create_all already added score_labels."""
    db_path = tmp_path / "stale.db"
    _create_d8_schema_with_precreated_score_labels(db_path)

    command.upgrade(_make_alembic_config(db_path), "head")

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    indexes = {index["name"] for index in inspector.get_indexes("score_labels")}
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()

    assert version == "f0a1b2c3d4e5"
    assert "ix_score_labels_image_id" in indexes


@pytest.mark.unit
def test_project_database_prepare_upgrades_alembic_managed_db(tmp_path: Path) -> None:
    """Project DB preparation applies pending migrations before repository use."""
    from lorairo.database.db_core import _prepare_project_database

    db_path = tmp_path / "project.db"
    _create_d8_schema_with_precreated_score_labels(db_path)

    engine = _prepare_project_database(db_path)
    engine.dispose()

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        score_label_count = conn.execute(text("SELECT count(*) FROM score_labels")).scalar_one()
    engine.dispose()

    assert version == "f0a1b2c3d4e5"
    assert score_label_count == 0


@pytest.mark.unit
def test_alembic_config_uses_package_relative_migrations(tmp_path: Path) -> None:
    """Runtime Alembic config does not depend on a source checkout alembic.ini."""
    from lorairo.database import db_core

    cfg = db_core._make_alembic_config(tmp_path / "project.db")

    assert cfg.config_file_name is None
    assert Path(cfg.get_main_option("script_location")) == Path(db_core.__file__).parent / "migrations"


@pytest.mark.unit
def test_default_session_local_prepares_database_lazily(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Importing db_core should not run migrations; first session creation should."""
    from lorairo.database import db_core

    calls: list[Path] = []
    session = object()

    def fake_prepare_project_database(db_path: Path) -> object:
        calls.append(db_path)
        return object()

    def fake_create_session_factory(_engine: object) -> object:
        return lambda: session

    db_path = tmp_path / "image_database.db"
    monkeypatch.setattr(db_core, "IMG_DB_PATH", db_path)
    monkeypatch.setattr(db_core, "_default_session_factory", None)
    monkeypatch.setattr(db_core, "_prepare_project_database", fake_prepare_project_database)
    monkeypatch.setattr(db_core, "create_session_factory", fake_create_session_factory)

    assert calls == []
    assert db_core.DefaultSessionLocal() is session
    assert calls == [db_path]
    assert db_core.DefaultSessionLocal() is session
    assert calls == [db_path]
