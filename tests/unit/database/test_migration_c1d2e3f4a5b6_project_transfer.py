"""Alembic migration `c1d2e3f4a5b6` プロジェクト横断コピーの記録と由来の表 (ADR 0112, Issue #1661)。

実スキーマ (`Base.metadata.create_all`) から本 migration の 3 表を外し、直前の revision に stamp した DB で
upgrade / downgrade を検証する。
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from lorairo.database.schema import Base

pytestmark = pytest.mark.unit

PREVIOUS_REVISION = "b1c2d3e4f5a6"
REVISION = "c1d2e3f4a5b6"
NEW_TABLES = {"project_transfer_runs", "image_origins", "dataset_version_origins"}


def _make_alembic_config(db_path: Path) -> Config:
    project_root = Path(__file__).resolve().parents[3]
    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "src/lorairo/database/migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _previous_revision_db(db_path: Path) -> Config:
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for name in ("dataset_version_origins", "image_origins", "project_transfer_runs"):
            conn.execute(text(f"DROP TABLE {name}"))
        conn.execute(
            text(
                "INSERT INTO images (id, uuid, phash, original_image_path, stored_image_path, "
                "width, height, format, extension) VALUES (1, 'u1', 'p1', '/o.png', '/s.png', 8, 8, 'PNG', '.png')"
            )
        )
    engine.dispose()
    cfg = _make_alembic_config(db_path)
    command.stamp(cfg, PREVIOUS_REVISION)
    return cfg


def _tables(db_path: Path) -> set[str]:
    engine = create_engine(f"sqlite:///{db_path}")
    names = set(inspect(engine).get_table_names())
    engine.dispose()
    return names


def test_upgrade_creates_tables_with_constraints(tmp_path: Path) -> None:
    db_path = tmp_path / "transfer.db"
    cfg = _previous_revision_db(db_path)

    command.upgrade(cfg, REVISION)

    assert NEW_TABLES <= _tables(db_path)
    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    origin_columns = {column["name"]: column for column in inspector.get_columns("image_origins")}
    origin_fks = {
        (fk["constrained_columns"][0], fk["referred_table"], fk.get("options", {}).get("ondelete"))
        for fk in inspector.get_foreign_keys("image_origins")
    }
    origin_uniques = inspector.get_unique_constraints("image_origins")
    version_fks = {
        (fk["constrained_columns"][0], fk["referred_table"], fk.get("options", {}).get("ondelete"))
        for fk in inspector.get_foreign_keys("dataset_version_origins")
    }
    run_columns = {column["name"] for column in inspector.get_columns("project_transfer_runs")}
    engine.dispose()

    assert set(origin_columns) == {
        "id",
        "image_id",
        "transfer_run_id",
        "source_project_name",
        "source_image_id",
        "source_image_uuid",
        "created_at",
    }
    assert origin_columns["transfer_run_id"]["nullable"] is True
    assert origin_columns["source_image_uuid"]["nullable"] is False
    assert ("image_id", "images", "CASCADE") in origin_fks
    assert ("transfer_run_id", "project_transfer_runs", "SET NULL") in origin_fks
    assert any(
        constraint["name"] == "uix_image_origins_image_source"
        and constraint["column_names"] == ["image_id", "source_project_name", "source_image_uuid"]
        for constraint in origin_uniques
    )
    assert ("version_id", "dataset_versions", "CASCADE") in version_fks
    assert run_columns == {
        "id",
        "kind",
        "source_project_name",
        "source_project_path",
        "copied_images",
        "linked_images",
        "created_at",
    }


def test_upgrade_enforces_kind_and_unique_origin(tmp_path: Path) -> None:
    db_path = tmp_path / "transfer_constraints.db"
    cfg = _previous_revision_db(db_path)
    command.upgrade(cfg, REVISION)

    with closing(sqlite3.connect(db_path)) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO project_transfer_runs (kind, source_project_name, source_project_path) "
                "VALUES ('unknown', 'a', '/a')"
            )
        conn.execute(
            "INSERT INTO project_transfer_runs (id, kind, source_project_name, source_project_path) "
            "VALUES (1, 'copy_images', 'a', '/a')"
        )
        counts = conn.execute("SELECT copied_images, linked_images FROM project_transfer_runs").fetchone()
        conn.execute(
            "INSERT INTO image_origins (image_id, transfer_run_id, source_project_name, source_image_id, "
            "source_image_uuid) VALUES (1, 1, 'a', 10, 'src-uuid')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO image_origins (image_id, transfer_run_id, source_project_name, source_image_id, "
                "source_image_uuid) VALUES (1, 1, 'a', 10, 'src-uuid')"
            )
    assert counts == (0, 0)


def test_downgrade_drops_only_new_tables_and_upgrade_again(tmp_path: Path) -> None:
    db_path = tmp_path / "transfer_downgrade.db"
    cfg = _previous_revision_db(db_path)
    command.upgrade(cfg, REVISION)

    command.downgrade(cfg, PREVIOUS_REVISION)

    tables = _tables(db_path)
    assert not (NEW_TABLES & tables)
    assert {"images", "dataset_versions", "tags"} <= tables
    with closing(sqlite3.connect(db_path)) as conn:
        assert conn.execute("SELECT count(*) FROM images").fetchone()[0] == 1
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == PREVIOUS_REVISION

    command.upgrade(cfg, REVISION)
    assert NEW_TABLES <= _tables(db_path)
