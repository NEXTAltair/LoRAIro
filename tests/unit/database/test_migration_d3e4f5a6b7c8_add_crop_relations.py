"""Alembic migration `d3e4f5a6b7c8` crop_relations テーブル追加 (ADR 0092, Issue #1343)。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

pytestmark = pytest.mark.unit

PREVIOUS_REVISION = "c9d0e1f2a3b4"
REVISION = "d3e4f5a6b7c8"


def _make_alembic_config(db_path: Path) -> Config:
    project_root = Path(__file__).resolve().parents[3]
    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "src/lorairo/database/migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _seed_pre_crop_db(db_path: Path) -> None:
    """crop_relations 追加前 (revision c9d0e1f2a3b4) の最小 DB を用意する。"""
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE images (id INTEGER NOT NULL PRIMARY KEY)"))
        conn.execute(text("INSERT INTO images (id) VALUES (1), (2), (3)"))
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        conn.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": PREVIOUS_REVISION},
        )
    engine.dispose()


def test_migration_creates_table_with_expected_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "crop_relations.db"
    cfg = _make_alembic_config(db_path)
    _seed_pre_crop_db(db_path)

    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    assert "crop_relations" in inspector.get_table_names()
    columns = {column["name"]: column for column in inspector.get_columns("crop_relations")}
    engine.dispose()

    assert set(columns) == {
        "id",
        "parent_image_id",
        "child_image_id",
        "x",
        "y",
        "width",
        "height",
        "origin",
        "created_at",
    }
    for name in ("parent_image_id", "child_image_id", "x", "y", "width", "height", "origin", "created_at"):
        assert columns[name]["nullable"] is False


def test_migration_creates_foreign_keys_unique_and_index(tmp_path: Path) -> None:
    db_path = tmp_path / "crop_relations_constraints.db"
    cfg = _make_alembic_config(db_path)
    _seed_pre_crop_db(db_path)

    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    foreign_keys = inspector.get_foreign_keys("crop_relations")
    unique_constraints = inspector.get_unique_constraints("crop_relations")
    indexes = inspector.get_indexes("crop_relations")
    engine.dispose()

    referenced = {
        (fk["constrained_columns"][0], fk["referred_table"], fk.get("options", {}).get("ondelete"))
        for fk in foreign_keys
    }
    assert ("parent_image_id", "images", "CASCADE") in referenced
    assert ("child_image_id", "images", "CASCADE") in referenced
    assert any(
        constraint["name"] == "uix_crop_relations_child"
        and constraint["column_names"] == ["child_image_id"]
        for constraint in unique_constraints
    )
    assert any(
        index["name"] == "ix_crop_relations_parent_image_id"
        and index["column_names"] == ["parent_image_id"]
        for index in indexes
    )


def test_migration_origin_server_default_is_manual(tmp_path: Path) -> None:
    """`origin` を省略した INSERT は server default の `manual` になる。"""
    db_path = tmp_path / "crop_relations_default.db"
    cfg = _make_alembic_config(db_path)
    _seed_pre_crop_db(db_path)

    command.upgrade(cfg, "head")

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO crop_relations (parent_image_id, child_image_id, x, y, width, height)"
            " VALUES (1, 2, 10, 20, 30, 40)"
        )
        origin = conn.execute("SELECT origin FROM crop_relations").fetchone()[0]

    assert origin == "manual"


def test_migration_child_unique_constraint_is_enforced(tmp_path: Path) -> None:
    """1 子 = 1 親。同じ子を別の親で二重登録できない。"""
    db_path = tmp_path / "crop_relations_unique.db"
    cfg = _make_alembic_config(db_path)
    _seed_pre_crop_db(db_path)

    command.upgrade(cfg, "head")

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO crop_relations (parent_image_id, child_image_id, x, y, width, height)"
            " VALUES (1, 2, 0, 0, 10, 10)"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO crop_relations (parent_image_id, child_image_id, x, y, width, height)"
                " VALUES (3, 2, 0, 0, 10, 10)"
            )
        # 同じ親から別の子は登録できる
        conn.execute(
            "INSERT INTO crop_relations (parent_image_id, child_image_id, x, y, width, height)"
            " VALUES (1, 3, 0, 0, 10, 10)"
        )


def test_migration_downgrade_drops_table(tmp_path: Path) -> None:
    db_path = tmp_path / "crop_relations_down.db"
    cfg = _make_alembic_config(db_path)
    _seed_pre_crop_db(db_path)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, PREVIOUS_REVISION)

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    engine.dispose()

    assert "crop_relations" not in table_names
