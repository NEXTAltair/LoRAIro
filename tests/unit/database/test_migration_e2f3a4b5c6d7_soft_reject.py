"""Alembic migration `e2f3a4b5c6d7` soft-reject column checks."""

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
def test_soft_reject_migration_adds_tag_and_caption_rejected_at(tmp_path: Path) -> None:
    db_path = tmp_path / "soft_reject.db"
    cfg = _make_alembic_config(db_path)
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE tags (
                    id INTEGER NOT NULL PRIMARY KEY,
                    tag VARCHAR NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE captions (
                    id INTEGER NOT NULL PRIMARY KEY,
                    caption VARCHAR NOT NULL
                )
                """
            )
        )
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('d1e2f3a4b5c6')"))
    engine.dispose()

    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    tag_columns = {column["name"] for column in inspector.get_columns("tags")}
    caption_columns = {column["name"] for column in inspector.get_columns("captions")}
    tag_indexes = {index["name"] for index in inspector.get_indexes("tags")}
    caption_indexes = {index["name"] for index in inspector.get_indexes("captions")}
    engine.dispose()

    assert "rejected_at" in tag_columns
    assert "rejected_at" in caption_columns
    assert "ix_tags_rejected_at" in tag_indexes
    assert "ix_captions_rejected_at" in caption_indexes
