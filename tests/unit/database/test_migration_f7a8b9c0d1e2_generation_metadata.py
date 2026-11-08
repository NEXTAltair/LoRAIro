"""Alembic migration `f7a8b9c0d1e2` 生成メタデータのテーブル追加 (ADR 0105, Issue #1481)。"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.unit

PREVIOUS_REVISION = "e5f6a7b8c9d0"
REVISION = "f7a8b9c0d1e2"


def _make_alembic_config(db_path: Path) -> Config:
    project_root = Path(__file__).resolve().parents[3]
    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "src/lorairo/database/migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _seed_previous_db(db_path: Path) -> None:
    """生成メタデータ追加前 (revision e5f6a7b8c9d0) の最小 DB を用意する。"""
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE images (id INTEGER NOT NULL PRIMARY KEY)"))
        conn.execute(text("INSERT INTO images (id) VALUES (1), (2)"))
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        conn.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": PREVIOUS_REVISION},
        )
    engine.dispose()


def test_upgrade_creates_tables_with_constraints(tmp_path: Path) -> None:
    db_path = tmp_path / "gen.db"
    cfg = _make_alembic_config(db_path)
    _seed_previous_db(db_path)

    command.upgrade(cfg, REVISION)

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {"generation_metadata", "generation_metadata_sources"} <= tables

    meta_cols = {c["name"]: c for c in inspector.get_columns("generation_metadata")}
    for name in ("image_id", "status", "parser_name", "parser_version", "analyzed_at"):
        assert meta_cols[name]["nullable"] is False
    for name in ("tool", "input_sha256", "positive_prompt", "seed", "steps", "cfg_scale", "error_message"):
        assert meta_cols[name]["nullable"] is True

    source_cols = {c["name"]: c for c in inspector.get_columns("generation_metadata_sources")}
    assert source_cols["raw_text"]["nullable"] is True
    assert source_cols["raw_bytes"]["nullable"] is True
    assert source_cols["sha256"]["nullable"] is False

    for table in ("generation_metadata", "generation_metadata_sources"):
        fks = inspector.get_foreign_keys(table)
        assert [(fk["referred_table"], fk["options"].get("ondelete")) for fk in fks] == [
            ("images", "CASCADE")
        ]
    assert {u["name"] for u in inspector.get_unique_constraints("generation_metadata")} == {
        "uix_generation_metadata_image"
    }
    assert {u["name"] for u in inspector.get_unique_constraints("generation_metadata_sources")} == {
        "uix_generation_metadata_sources_image_kind_key"
    }
    assert "ix_generation_metadata_tool" in {
        i["name"] for i in inspector.get_indexes("generation_metadata")
    }

    # 既存の画像は変更されず、未解析 (行なし) のまま
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM images")).scalar() == 2
        assert conn.execute(text("SELECT COUNT(*) FROM generation_metadata")).scalar() == 0
    engine.dispose()


def test_status_check_constraint_after_upgrade(tmp_path: Path) -> None:
    db_path = tmp_path / "gen_check.db"
    cfg = _make_alembic_config(db_path)
    _seed_previous_db(db_path)
    command.upgrade(cfg, REVISION)

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO generation_metadata (image_id, status, parser_name, parser_version) "
                "VALUES (1, 'no_metadata', 'none', '1')"
            )
        )
        with pytest.raises(IntegrityError, match="CHECK constraint failed"):
            conn.execute(
                text(
                    "INSERT INTO generation_metadata (image_id, status, parser_name, parser_version) "
                    "VALUES (2, 'bogus', 'none', '1')"
                )
            )
    engine.dispose()


def test_downgrade_drops_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "gen_down.db"
    cfg = _make_alembic_config(db_path)
    _seed_previous_db(db_path)
    command.upgrade(cfg, REVISION)

    command.downgrade(cfg, PREVIOUS_REVISION)

    engine = create_engine(f"sqlite:///{db_path}")
    tables = set(inspect(engine).get_table_names())
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    engine.dispose()
    assert "generation_metadata" not in tables
    assert "generation_metadata_sources" not in tables
    assert "images" in tables
    assert version == PREVIOUS_REVISION
