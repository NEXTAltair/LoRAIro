"""Alembic migration `f6a7b8c9d0e1` reject_reason column + backfill checks (Issue #1003)."""

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


def _seed_pre_reject_reason_db(db_path: Path) -> None:
    """reject_reason 追加前 (revision 9c1d2e3f4a5b) の tags/captions を用意する。"""
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE tags (
                    id INTEGER NOT NULL PRIMARY KEY,
                    tag VARCHAR NOT NULL,
                    rejected_at TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE captions (
                    id INTEGER NOT NULL PRIMARY KEY,
                    caption VARCHAR NOT NULL,
                    rejected_at TIMESTAMP
                )
                """
            )
        )
        # rejected_at 非 NULL の行 (backfill 対象) と NULL の行 (採用中)。
        conn.execute(
            text("INSERT INTO tags (id, tag, rejected_at) VALUES (1, 'rejected_tag', '2026-06-01')")
        )
        conn.execute(text("INSERT INTO tags (id, tag, rejected_at) VALUES (2, 'active_tag', NULL)"))
        conn.execute(
            text("INSERT INTO captions (id, caption, rejected_at) VALUES (1, 'rejected cap', '2026-06-01')")
        )
        conn.execute(text("INSERT INTO captions (id, caption, rejected_at) VALUES (2, 'active cap', NULL)"))
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('9c1d2e3f4a5b')"))
    engine.dispose()


@pytest.mark.unit
def test_reject_reason_migration_adds_column_and_backfills(tmp_path: Path) -> None:
    db_path = tmp_path / "reject_reason.db"
    cfg = _make_alembic_config(db_path)
    _seed_pre_reject_reason_db(db_path)

    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    tag_columns = {column["name"] for column in inspector.get_columns("tags")}
    caption_columns = {column["name"] for column in inspector.get_columns("captions")}
    with engine.connect() as conn:
        tag_reasons = {
            row[0]: row[1] for row in conn.execute(text("SELECT id, reject_reason FROM tags")).fetchall()
        }
        caption_reasons = {
            row[0]: row[1]
            for row in conn.execute(text("SELECT id, reject_reason FROM captions")).fetchall()
        }
    engine.dispose()

    assert "reject_reason" in tag_columns
    assert "reject_reason" in caption_columns
    # 既存 rejected_at 非 NULL 行は not_needed に backfill (見た目不変)。
    assert tag_reasons[1] == "not_needed"
    assert caption_reasons[1] == "not_needed"
    # rejected_at IS NULL 行は reject_reason も NULL のまま。
    assert tag_reasons[2] is None
    assert caption_reasons[2] is None


@pytest.mark.unit
def test_reject_reason_migration_downgrade_removes_column(tmp_path: Path) -> None:
    db_path = tmp_path / "reject_reason_down.db"
    cfg = _make_alembic_config(db_path)
    _seed_pre_reject_reason_db(db_path)

    command.upgrade(cfg, "f6a7b8c9d0e1")
    command.downgrade(cfg, "9c1d2e3f4a5b")

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    tag_columns = {column["name"] for column in inspector.get_columns("tags")}
    caption_columns = {column["name"] for column in inspector.get_columns("captions")}
    engine.dispose()

    assert "reject_reason" not in tag_columns
    assert "reject_reason" not in caption_columns
