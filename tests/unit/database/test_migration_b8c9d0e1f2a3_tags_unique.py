"""Alembic migration `b8c9d0e1f2a3` tags 重複畳み + UNIQUE インデックス (Issue #1065)。"""

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


def _seed_pre_unique_db(db_path: Path) -> None:
    """UNIQUE 追加前 (revision f6a7b8c9d0e1) の tags を重複入りで用意する。"""
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE tags (
                    id INTEGER NOT NULL PRIMARY KEY,
                    tag_id INTEGER,
                    image_id INTEGER,
                    model_id INTEGER,
                    tag VARCHAR NOT NULL,
                    existing BOOLEAN NOT NULL DEFAULT 0,
                    is_edited_manually BOOLEAN,
                    confidence_score FLOAT,
                    rejected_at TIMESTAMP,
                    reject_reason VARCHAR,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        rows = [
            # グループA: (1, 170, 'heart') x3 — id=1 (最古) を残す。
            # id=2 は soft-reject 済み (reject 維持で残る行へ集約)、id=3 が最新付与。
            "(1, 30, 1, 170, 'heart', 0, NULL, 0.9, NULL, NULL, '2026-06-01', '2026-06-01')",
            "(2, 30, 1, 170, 'heart', 0, NULL, 0.8, '2026-06-10', 'not_needed', '2026-06-05', '2026-06-10')",
            "(3, 30, 1, 170, 'heart', 0, 1, 0.7, NULL, NULL, '2026-06-17', '2026-06-17')",
            # グループB: 別モデル (171) の 'heart' — provenance として別行のまま残る
            "(4, 30, 1, 171, 'heart', 0, NULL, 0.6, NULL, NULL, '2026-06-17', '2026-06-17')",
            # グループC: 重複なしの通常行
            "(5, 40, 1, 170, 'solo', 0, NULL, 0.5, NULL, NULL, '2026-06-01', '2026-06-01')",
        ]
        for row in rows:
            conn.execute(
                text(
                    "INSERT INTO tags (id, tag_id, image_id, model_id, tag, existing,"
                    " is_edited_manually, confidence_score, rejected_at, reject_reason,"
                    f" created_at, updated_at) VALUES {row}"
                )
            )
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('f6a7b8c9d0e1')"))
    engine.dispose()


@pytest.mark.unit
def test_tags_unique_migration_collapses_duplicates(tmp_path: Path) -> None:
    db_path = tmp_path / "tags_unique.db"
    cfg = _make_alembic_config(db_path)
    _seed_pre_unique_db(db_path)

    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, model_id, tag, updated_at, rejected_at, reject_reason,"
                " is_edited_manually, confidence_score FROM tags ORDER BY id"
            )
        ).fetchall()
    engine.dispose()

    ids = [row.id for row in rows]
    # グループAは最古 id=1 のみ残り、別モデル行 (id=4) と非重複行 (id=5) は不変
    assert ids == [1, 4, 5]

    kept = rows[0]
    # updated_at はグループ内の最新付与日時
    assert str(kept.updated_at).startswith("2026-06-17")
    # soft-reject はユーザー判断を優先して維持 (グループ内最新の reject を集約)
    assert str(kept.rejected_at).startswith("2026-06-10")
    assert kept.reject_reason == "not_needed"
    # is_edited_manually はグループ内に True があれば True
    assert kept.is_edited_manually == 1
    # confidence はグループ内の最新行 (MAX(id)=3) の値
    assert kept.confidence_score == 0.7


@pytest.mark.unit
def test_tags_unique_migration_adds_unique_index(tmp_path: Path) -> None:
    db_path = tmp_path / "tags_unique_idx.db"
    cfg = _make_alembic_config(db_path)
    _seed_pre_unique_db(db_path)

    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    unique_indexes = {
        index["name"]: index for index in inspector.get_indexes("tags") if index.get("unique")
    }
    engine.dispose()

    assert "uq_tags_image_model_tag" in unique_indexes
    assert unique_indexes["uq_tags_image_model_tag"]["column_names"] == ["image_id", "model_id", "tag"]

    # 制約が実際に効く: 同一 (image_id, model_id, tag) の INSERT は拒否される
    with sqlite3.connect(db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO tags (tag_id, image_id, model_id, tag, existing)"
                " VALUES (30, 1, 170, 'heart', 0)"
            )


@pytest.mark.unit
def test_tags_unique_migration_downgrade_drops_index(tmp_path: Path) -> None:
    db_path = tmp_path / "tags_unique_down.db"
    cfg = _make_alembic_config(db_path)
    _seed_pre_unique_db(db_path)

    command.upgrade(cfg, "b8c9d0e1f2a3")
    command.downgrade(cfg, "f6a7b8c9d0e1")

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    index_names = {index["name"] for index in inspector.get_indexes("tags")}
    engine.dispose()

    assert "uq_tags_image_model_tag" not in index_names
