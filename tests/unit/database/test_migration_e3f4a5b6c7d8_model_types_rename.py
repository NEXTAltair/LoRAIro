"""Alembic migration `e3f4a5b6c7d8` (Issue #243) の data backfill 検証。

`model_types` テーブルの旧名 (`tagger` / `score` / `captioner`) を本番 SSoT
(`tags` / `scores` / `caption`) に rename する migration の動作を確認する。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


def _make_alembic_config(db_path: Path) -> Config:
    """テスト用 Alembic Config を組み立てる (sqlalchemy.url を上書き)。"""
    project_root = Path(__file__).resolve().parents[3]
    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "src/lorairo/database/migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _create_schema_at_d8e9f0a1b2c3(db_path: Path) -> None:
    """`d8e9f0a1b2c3` 完了後の最小スキーマを CREATE する (本 migration の直前 head)。"""
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        # `models` と `model_types` の最小定義 (テスト目的なので関連テーブルは省略)
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
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('d8e9f0a1b2c3')"))
    engine.dispose()


def _upgrade_to_head(db_path: Path) -> None:
    cfg = _make_alembic_config(db_path)
    command.upgrade(cfg, "head")


@pytest.mark.unit
class TestModelTypesRenameMigration:
    """`e3f4a5b6c7d8` migration の data rename 検証 (Issue #243)。"""

    def test_renames_legacy_names_to_db_ssot(self, tmp_path: Path) -> None:
        """旧名 (`tagger` / `score` / `captioner`) が新 SSoT 値に rename される。"""
        db = tmp_path / "test.db"
        _create_schema_at_d8e9f0a1b2c3(db)
        engine = create_engine(f"sqlite:///{db}")
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO model_types (id, name) VALUES "
                    "(1, 'tagger'), (2, 'score'), (3, 'captioner'), "
                    "(4, 'upscaler'), (5, 'multimodal')"
                )
            )
        engine.dispose()

        _upgrade_to_head(db)

        engine = create_engine(f"sqlite:///{db}")
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT name FROM model_types ORDER BY id")).fetchall()
            names = [row.name for row in rows]
            assert names == ["tags", "scores", "caption", "upscaler", "multimodal"]
        engine.dispose()

    def test_already_normalized_db_is_noop(self, tmp_path: Path) -> None:
        """既に新 SSoT 値で登録済みの DB に対しては no-op (本番 DB シナリオ)。"""
        db = tmp_path / "test.db"
        _create_schema_at_d8e9f0a1b2c3(db)
        engine = create_engine(f"sqlite:///{db}")
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO model_types (id, name) VALUES "
                    "(1, 'tags'), (2, 'scores'), (3, 'caption'), "
                    "(4, 'upscaler'), (5, 'multimodal')"
                )
            )
        engine.dispose()

        _upgrade_to_head(db)

        engine = create_engine(f"sqlite:///{db}")
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT name FROM model_types ORDER BY id")).fetchall()
            names = [row.name for row in rows]
            assert names == ["tags", "scores", "caption", "upscaler", "multimodal"]
        engine.dispose()

    def test_collision_with_existing_new_name_drops_legacy(self, tmp_path: Path) -> None:
        """旧名と新名が両方存在する場合、旧名行が削除され新名行が保持される。"""
        db = tmp_path / "test.db"
        _create_schema_at_d8e9f0a1b2c3(db)
        engine = create_engine(f"sqlite:///{db}")
        with engine.begin() as conn:
            # 同じ意味の旧名 `tagger` と新名 `tags` が共存しているシナリオ
            conn.execute(
                text(
                    "INSERT INTO model_types (id, name) VALUES (1, 'tagger'), (2, 'tags'), (3, 'upscaler')"
                )
            )
        engine.dispose()

        _upgrade_to_head(db)

        engine = create_engine(f"sqlite:///{db}")
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT id, name FROM model_types ORDER BY id")).fetchall()
            # id=1 (tagger) は削除され、id=2 (tags) が残る
            names = [row.name for row in rows]
            assert "tags" in names
            assert "tagger" not in names
            assert len(rows) == 2  # tagger 行が削除されたため 3 → 2
        engine.dispose()

    def test_downgrade_restores_legacy_names(self, tmp_path: Path) -> None:
        """downgrade で `tags` / `scores` / `caption` が旧名に戻る。"""
        db = tmp_path / "test.db"
        _create_schema_at_d8e9f0a1b2c3(db)
        engine = create_engine(f"sqlite:///{db}")
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO model_types (id, name) VALUES "
                    "(1, 'tagger'), (2, 'score'), (3, 'captioner')"
                )
            )
        engine.dispose()

        _upgrade_to_head(db)

        cfg = _make_alembic_config(db)
        command.downgrade(cfg, "d8e9f0a1b2c3")

        engine = create_engine(f"sqlite:///{db}")
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT name FROM model_types ORDER BY id")).fetchall()
            names = [row.name for row in rows]
            assert names == ["tagger", "score", "captioner"]
        engine.dispose()
