"""Alembic migration `879cc87e4125` の upgrade() 検証。

このマイグレーションは:
- ratings テーブルを新規作成する
- captions/images/models/processed_images/scores/tags テーブルを改修する
- images に manual_rating カラムを追加する
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def _make_alembic_config(db_path: Path) -> Config:
    """Build an Alembic Config that targets the temporary DB."""
    project_root = Path(__file__).resolve().parents[3]
    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "src/lorairo/database/migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _create_pre_879_schema(db_path: Path) -> None:
    """879cc87e4125 適用前のレガシースキーマを作成する。

    旧スキーマ(20241023バックアップ相当)を再現する。
    """
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE images (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    uuid TEXT NOT NULL,
                    phash TEXT,
                    original_image_path TEXT NOT NULL,
                    stored_image_path TEXT NOT NULL,
                    format TEXT NOT NULL,
                    mode TEXT,
                    width INTEGER,
                    height INTEGER,
                    filename TEXT,
                    extension TEXT NOT NULL,
                    file_size INTEGER,
                    color_space TEXT,
                    icc_profile TEXT,
                    has_transparency BOOLEAN,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX idx_images_uuid ON images (uuid)"))
        conn.execute(text("CREATE INDEX idx_images_phash ON images (phash)"))

        conn.execute(
            text(
                """
                CREATE TABLE models (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    provider TEXT,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP
                )
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE TABLE captions (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    image_id INTEGER NOT NULL,
                    model_id INTEGER NOT NULL,
                    caption TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    FOREIGN KEY(image_id) REFERENCES images (id),
                    FOREIGN KEY(model_id) REFERENCES models (id)
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX idx_captions_image_id ON captions (image_id)"))

        conn.execute(
            text(
                """
                CREATE TABLE scores (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    image_id INTEGER NOT NULL,
                    model_id INTEGER NOT NULL,
                    score FLOAT,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    FOREIGN KEY(image_id) REFERENCES images (id),
                    FOREIGN KEY(model_id) REFERENCES models (id)
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX idx_scores_image_id ON scores (image_id)"))

        conn.execute(
            text(
                """
                CREATE TABLE tags (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    image_id INTEGER NOT NULL,
                    model_id INTEGER NOT NULL,
                    tag TEXT NOT NULL,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    FOREIGN KEY(image_id) REFERENCES images (id),
                    FOREIGN KEY(model_id) REFERENCES models (id)
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX idx_tags_image_id ON tags (image_id)"))

        conn.execute(
            text(
                """
                CREATE TABLE processed_images (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    image_id INTEGER NOT NULL,
                    stored_image_path TEXT NOT NULL,
                    width INTEGER,
                    height INTEGER,
                    mode TEXT,
                    filename TEXT,
                    color_space TEXT,
                    icc_profile TEXT,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    FOREIGN KEY(image_id) REFERENCES images (id)
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX idx_processed_images_image_id ON processed_images (image_id)"))

        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        # このマイグレーションは down_revision=None なので、空の alembic_version から始まる
        # (alembic_version に行がない = 未適用状態)

    engine.dispose()


@pytest.mark.unit
def test_879cc87e4125_creates_ratings_table(tmp_path: Path) -> None:
    """upgrade() 後に ratings テーブルが作成される。"""
    db_path = tmp_path / "initial-schema.db"
    _create_pre_879_schema(db_path)

    command.upgrade(_make_alembic_config(db_path), "879cc87e4125")

    engine = create_engine(f"sqlite:///{db_path}")
    insp = inspect(engine)
    assert "ratings" in insp.get_table_names()
    engine.dispose()


@pytest.mark.unit
def test_879cc87e4125_ratings_table_has_expected_columns(tmp_path: Path) -> None:
    """ratings テーブルの必須カラムが存在する。"""
    db_path = tmp_path / "initial-schema.db"
    _create_pre_879_schema(db_path)

    command.upgrade(_make_alembic_config(db_path), "879cc87e4125")

    engine = create_engine(f"sqlite:///{db_path}")
    insp = inspect(engine)
    cols = {col["name"] for col in insp.get_columns("ratings")}
    engine.dispose()

    assert "id" in cols
    assert "image_id" in cols
    assert "model_id" in cols
    assert "raw_rating_value" in cols
    assert "normalized_rating" in cols
    assert "created_at" in cols
    assert "updated_at" in cols


@pytest.mark.unit
def test_879cc87e4125_images_gets_manual_rating_column(tmp_path: Path) -> None:
    """upgrade() 後に images テーブルに manual_rating カラムが追加される。"""
    db_path = tmp_path / "initial-schema.db"
    _create_pre_879_schema(db_path)

    command.upgrade(_make_alembic_config(db_path), "879cc87e4125")

    engine = create_engine(f"sqlite:///{db_path}")
    insp = inspect(engine)
    cols = {col["name"] for col in insp.get_columns("images")}
    engine.dispose()

    assert "manual_rating" in cols


@pytest.mark.unit
def test_879cc87e4125_version_is_set(tmp_path: Path) -> None:
    """upgrade() 後に alembic_version が 879cc87e4125 になる。"""
    db_path = tmp_path / "initial-schema.db"
    _create_pre_879_schema(db_path)

    command.upgrade(_make_alembic_config(db_path), "879cc87e4125")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()

    assert version == "879cc87e4125"
