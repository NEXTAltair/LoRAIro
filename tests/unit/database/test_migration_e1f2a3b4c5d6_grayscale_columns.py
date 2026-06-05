"""Alembic migration `e1f2a3b4c5d6` グレースケール相当カラム追加 (Issue #631 / ADR 0061)."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


def _make_alembic_config(db_path: Path) -> Config:
    project_root = Path(__file__).resolve().parents[3]
    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "src/lorairo/database/migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _create_prior_images_table(db_path: Path) -> None:
    """新カラム追加前 (revision c8d9e0f1a2b3 相当) の images テーブルを作成する。"""
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
                    mode VARCHAR,
                    has_alpha BOOLEAN,
                    filename VARCHAR,
                    extension VARCHAR NOT NULL,
                    color_space VARCHAR,
                    icc_profile VARCHAR
                )
                """
            )
        )
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('c8d9e0f1a2b3')"))
    engine.dispose()


def _column_names(db_path: Path) -> set[str]:
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        rows = conn.execute(text("PRAGMA table_info(images)")).all()
    engine.dispose()
    return {row[1] for row in rows}


@pytest.mark.unit
def test_upgrade_adds_grayscale_columns(tmp_path: Path) -> None:
    db = tmp_path / "grayscale_upgrade.db"
    _create_prior_images_table(db)

    command.upgrade(_make_alembic_config(db), "e1f2a3b4c5d6")

    cols = _column_names(db)
    assert "is_grayscale_like" in cols
    assert "colorfulness_score" in cols


@pytest.mark.unit
def test_upgrade_leaves_existing_rows_null(tmp_path: Path) -> None:
    """遅延 backfill 方針: 既存行は両カラムとも NULL のまま (全件再計算しない)。"""
    db = tmp_path / "grayscale_backfill.db"
    _create_prior_images_table(db)
    engine = create_engine(f"sqlite:///{db}")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO images
                    (uuid, phash, original_image_path, stored_image_path,
                     width, height, format, extension)
                VALUES
                    ('u1', 'p1', '/a.png', '/s/a.png', 10, 10, 'png', '.png')
                """
            )
        )
    engine.dispose()

    command.upgrade(_make_alembic_config(db), "e1f2a3b4c5d6")

    engine = create_engine(f"sqlite:///{db}")
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT is_grayscale_like, colorfulness_score FROM images WHERE uuid = 'u1'")
        ).one()
    engine.dispose()

    assert row[0] is None
    assert row[1] is None


@pytest.mark.unit
def test_downgrade_removes_grayscale_columns(tmp_path: Path) -> None:
    db = tmp_path / "grayscale_downgrade.db"
    _create_prior_images_table(db)

    command.upgrade(_make_alembic_config(db), "e1f2a3b4c5d6")
    command.downgrade(_make_alembic_config(db), "c8d9e0f1a2b3")

    cols = _column_names(db)
    assert "is_grayscale_like" not in cols
    assert "colorfulness_score" not in cols
