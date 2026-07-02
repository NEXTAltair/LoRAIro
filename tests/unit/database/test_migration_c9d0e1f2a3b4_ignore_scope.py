"""Alembic migration `c9d0e1f2a3b4` refinement_ignores 画像スコープ (Issue #1053)。"""

from __future__ import annotations

import sqlite3
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


def _seed_pre_scope_db(db_path: Path) -> None:
    """image_id 追加前 (revision b8c9d0e1f2a3) の refinement_ignores を用意する。"""
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE images (
                    id INTEGER NOT NULL PRIMARY KEY
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE refinement_ignores (
                    id INTEGER NOT NULL PRIMARY KEY,
                    tag VARCHAR NOT NULL,
                    reason_code VARCHAR NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uix_refinement_ignore_tag_reason UNIQUE (tag, reason_code)
                )
                """
            )
        )
        conn.execute(
            text("INSERT INTO refinement_ignores (id, tag, reason_code) VALUES (1, 'heart', 'alias_tag')")
        )
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('b8c9d0e1f2a3')"))
    engine.dispose()


@pytest.mark.unit
def test_ignore_scope_migration_adds_column_and_keeps_rows_global(tmp_path: Path) -> None:
    db_path = tmp_path / "ignore_scope.db"
    cfg = _make_alembic_config(db_path)
    _seed_pre_scope_db(db_path)

    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("refinement_ignores")}
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT tag, reason_code, image_id FROM refinement_ignores")).fetchall()
    engine.dispose()

    assert "image_id" in columns
    # 既存行は image_id NULL = 全画像スコープのまま
    assert rows == [("heart", "alias_tag", None)]


@pytest.mark.unit
def test_ignore_scope_migration_partial_unique_indexes(tmp_path: Path) -> None:
    """全画像スコープ (NULL) と画像限定スコープが部分 UNIQUE インデックスで別々に一意化される。"""
    db_path = tmp_path / "ignore_scope_uniq.db"
    cfg = _make_alembic_config(db_path)
    _seed_pre_scope_db(db_path)

    command.upgrade(cfg, "head")

    with sqlite3.connect(db_path) as conn:
        # 全画像スコープの重複は拒否 (SQLite UNIQUE の NULL 別値扱いを部分インデックスで回避)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO refinement_ignores (tag, reason_code, image_id)"
                " VALUES ('heart', 'alias_tag', NULL)"
            )
        # 画像限定スコープは別行として登録でき、同一画像の重複は拒否
        conn.execute(
            "INSERT INTO refinement_ignores (tag, reason_code, image_id) VALUES ('heart', 'alias_tag', 7)"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO refinement_ignores (tag, reason_code, image_id)"
                " VALUES ('heart', 'alias_tag', 7)"
            )
        # 別画像なら共存できる
        conn.execute(
            "INSERT INTO refinement_ignores (tag, reason_code, image_id) VALUES ('heart', 'alias_tag', 8)"
        )


@pytest.mark.unit
def test_ignore_scope_migration_downgrade(tmp_path: Path) -> None:
    """downgrade は画像限定行を落とし、旧 UNIQUE(tag, reason_code) に戻る。"""
    db_path = tmp_path / "ignore_scope_down.db"
    cfg = _make_alembic_config(db_path)
    _seed_pre_scope_db(db_path)

    command.upgrade(cfg, "c9d0e1f2a3b4")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO refinement_ignores (tag, reason_code, image_id) VALUES ('heart', 'alias_tag', 7)"
        )
    command.downgrade(cfg, "b8c9d0e1f2a3")

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("refinement_ignores")}
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT tag, reason_code FROM refinement_ignores")).fetchall()
    engine.dispose()

    assert "image_id" not in columns
    # 画像限定行は旧 schema で表現できないため削除され、全画像行のみ残る
    assert rows == [("heart", "alias_tag")]
