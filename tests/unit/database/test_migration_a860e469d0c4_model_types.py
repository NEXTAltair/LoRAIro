"""Alembic migration `a860e469d0c4` の upgrade() 検証。

このマイグレーションは:
- model_types テーブルを作成し初期データ(tagger/score/captioner/upscaler/llm)を投入する
- model_function_associations テーブルを作成する
- models テーブルに discontinued_at カラムを追加する
- models.type カラムを削除して model_function_associations に移行する
- 新規モデルを登録する
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


def _create_schema_at_879(db_path: Path) -> None:
    """879cc87e4125 適用後のスキーマを作成する。

    a860e469d0c4 の down_revision は 879cc87e4125 なので、
    そのスキーマ状態を再現する。
    """
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE images (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    uuid VARCHAR NOT NULL,
                    phash VARCHAR NOT NULL,
                    original_image_path VARCHAR NOT NULL,
                    stored_image_path VARCHAR NOT NULL,
                    format VARCHAR NOT NULL,
                    mode VARCHAR,
                    width INTEGER,
                    height INTEGER,
                    filename VARCHAR,
                    extension VARCHAR NOT NULL,
                    file_size INTEGER,
                    color_space VARCHAR,
                    icc_profile VARCHAR,
                    has_transparency BOOLEAN,
                    manual_rating VARCHAR,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                )
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE TABLE models (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR NOT NULL,
                    type VARCHAR NOT NULL,
                    provider VARCHAR,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE TABLE ratings (
                    id INTEGER NOT NULL PRIMARY KEY,
                    image_id INTEGER NOT NULL,
                    model_id INTEGER NOT NULL,
                    raw_rating_value VARCHAR NOT NULL,
                    normalized_rating VARCHAR NOT NULL,
                    confidence_score FLOAT,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    FOREIGN KEY(image_id) REFERENCES images (id) ON DELETE CASCADE,
                    FOREIGN KEY(model_id) REFERENCES models (id) ON DELETE SET NULL
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX ix_ratings_image_id ON ratings (image_id)"))

        conn.execute(
            text(
                """
                CREATE TABLE captions (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    image_id INTEGER NOT NULL,
                    model_id INTEGER NOT NULL,
                    caption VARCHAR NOT NULL,
                    is_edited_manually BOOLEAN,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    FOREIGN KEY(image_id) REFERENCES images (id),
                    FOREIGN KEY(model_id) REFERENCES models (id)
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX ix_captions_image_id ON captions (image_id)"))

        conn.execute(
            text(
                """
                CREATE TABLE scores (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    image_id INTEGER NOT NULL,
                    model_id INTEGER NOT NULL,
                    score FLOAT,
                    is_edited_manually BOOLEAN,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    FOREIGN KEY(image_id) REFERENCES images (id),
                    FOREIGN KEY(model_id) REFERENCES models (id)
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX ix_scores_image_id ON scores (image_id)"))

        conn.execute(
            text(
                """
                CREATE TABLE tags (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    image_id INTEGER NOT NULL,
                    model_id INTEGER NOT NULL,
                    tag VARCHAR NOT NULL,
                    is_edited_manually BOOLEAN,
                    confidence_score FLOAT,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    FOREIGN KEY(image_id) REFERENCES images (id),
                    FOREIGN KEY(model_id) REFERENCES models (id)
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX ix_tags_image_id ON tags (image_id)"))

        conn.execute(
            text(
                """
                CREATE TABLE processed_images (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    image_id INTEGER NOT NULL,
                    stored_image_path VARCHAR NOT NULL,
                    width INTEGER,
                    height INTEGER,
                    mode VARCHAR,
                    filename VARCHAR,
                    color_space VARCHAR,
                    icc_profile VARCHAR,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    FOREIGN KEY(image_id) REFERENCES images (id)
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX ix_processed_images_image_id ON processed_images (image_id)"))

        # Alembic version table に 879cc87e4125 を設定
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('879cc87e4125')"))
    engine.dispose()


@pytest.mark.unit
def test_a860e469d0c4_creates_model_types_table(tmp_path: Path) -> None:
    """upgrade() 後に model_types テーブルが作成される。"""
    db_path = tmp_path / "model-types.db"
    _create_schema_at_879(db_path)

    command.upgrade(_make_alembic_config(db_path), "a860e469d0c4")

    engine = create_engine(f"sqlite:///{db_path}")
    insp = inspect(engine)
    assert "model_types" in insp.get_table_names()
    engine.dispose()


@pytest.mark.unit
def test_a860e469d0c4_inserts_initial_model_types(tmp_path: Path) -> None:
    """upgrade() 後に model_types に初期レコード(tagger/score/captioner/upscaler/llm)が存在する。"""
    db_path = tmp_path / "model-types.db"
    _create_schema_at_879(db_path)

    command.upgrade(_make_alembic_config(db_path), "a860e469d0c4")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT name FROM model_types ORDER BY name")).fetchall()
    engine.dispose()

    type_names = {row[0] for row in rows}
    assert "tagger" in type_names
    assert "score" in type_names
    assert "captioner" in type_names
    assert "upscaler" in type_names
    assert "llm" in type_names


@pytest.mark.unit
def test_a860e469d0c4_creates_model_function_associations_table(tmp_path: Path) -> None:
    """upgrade() 後に model_function_associations テーブルが作成される。"""
    db_path = tmp_path / "model-types.db"
    _create_schema_at_879(db_path)

    command.upgrade(_make_alembic_config(db_path), "a860e469d0c4")

    engine = create_engine(f"sqlite:///{db_path}")
    insp = inspect(engine)
    assert "model_function_associations" in insp.get_table_names()
    engine.dispose()


@pytest.mark.unit
def test_a860e469d0c4_existing_model_gets_association(tmp_path: Path) -> None:
    """upgrade() 前に既存モデル(type='score')が存在する場合、アソシエーションが作成される。"""
    db_path = tmp_path / "model-types.db"
    _create_schema_at_879(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO models (id, name, type, created_at, updated_at) "
                "VALUES (1, 'cafe_aesthetic', 'score', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
    engine.dispose()

    command.upgrade(_make_alembic_config(db_path), "a860e469d0c4")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        count = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM model_function_associations mfa
                JOIN model_types mt ON mfa.type_id = mt.id
                JOIN models m ON mfa.model_id = m.id
                WHERE m.name = 'cafe_aesthetic' AND mt.name = 'score'
                """
            )
        ).scalar_one()
    engine.dispose()

    assert count == 1


@pytest.mark.unit
def test_a860e469d0c4_version_is_set(tmp_path: Path) -> None:
    """upgrade() 後に alembic_version が a860e469d0c4 になる。"""
    db_path = tmp_path / "model-types.db"
    _create_schema_at_879(db_path)

    command.upgrade(_make_alembic_config(db_path), "a860e469d0c4")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()

    assert version == "a860e469d0c4"
