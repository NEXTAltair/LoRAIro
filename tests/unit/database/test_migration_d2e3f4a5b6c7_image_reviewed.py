"""Alembic migration `d2e3f4a5b6c7` image reviewed_at column checks."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def _make_alembic_config(db_path: Path) -> Config:
    project_root = Path(__file__).resolve().parents[3]
    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "src/lorairo/database/migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


@pytest.mark.unit
def test_image_reviewed_migration_adds_reviewed_at(tmp_path: Path) -> None:
    db_path = tmp_path / "image_reviewed.db"
    cfg = _make_alembic_config(db_path)
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE images (
                    id INTEGER NOT NULL PRIMARY KEY,
                    uuid VARCHAR NOT NULL
                )
                """
            )
        )
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('e2f3a4b5c6d7')"))
    engine.dispose()

    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    image_columns = {column["name"] for column in inspector.get_columns("images")}
    image_indexes = {index["name"] for index in inspector.get_indexes("images")}
    engine.dispose()

    assert "reviewed_at" in image_columns
    assert "ix_images_reviewed_at" in image_indexes


@pytest.mark.unit
def test_image_reviewed_migration_downgrade_removes_column(tmp_path: Path) -> None:
    db_path = tmp_path / "image_reviewed_down.db"
    cfg = _make_alembic_config(db_path)
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE images (
                    id INTEGER NOT NULL PRIMARY KEY,
                    uuid VARCHAR NOT NULL
                )
                """
            )
        )
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('e2f3a4b5c6d7')"))
    engine.dispose()

    command.upgrade(cfg, "d2e3f4a5b6c7")
    command.downgrade(cfg, "e2f3a4b5c6d7")

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    image_columns = {column["name"] for column in inspector.get_columns("images")}
    engine.dispose()

    assert "reviewed_at" not in image_columns
