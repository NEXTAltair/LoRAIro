"""Alembic migration `c9b242b21b87` の upgrade() 検証。

このマイグレーションは:
- 定義済みモデルと model_types の対応関係（アソシエーション）のうち、
  a860e469d0c4 で未作成だったものを補完して挿入する
- 既存アソシエーションとの重複は排除される
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


def _make_alembic_config(db_path: Path) -> Config:
    """Build an Alembic Config that targets the temporary DB."""
    project_root = Path(__file__).resolve().parents[3]
    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "src/lorairo/database/migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _create_schema_at_a860(db_path: Path) -> None:
    """a860e469d0c4 適用後のスキーマを作成する。

    c9b242b21b87 の down_revision は a860e469d0c4 なので、
    そのスキーマ状態（model_types + model_function_associations あり、
    models.type カラムなし）を再現する。
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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
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
                    provider VARCHAR,
                    discontinued_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
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
        conn.execute(
            text(
                "INSERT INTO model_types (id, name) VALUES "
                "(1, 'tagger'), (2, 'score'), (3, 'captioner'), (4, 'upscaler'), (5, 'llm')"
            )
        )

        conn.execute(
            text(
                """
                CREATE TABLE model_function_associations (
                    model_id INTEGER NOT NULL,
                    type_id INTEGER NOT NULL,
                    PRIMARY KEY (model_id, type_id),
                    FOREIGN KEY(model_id) REFERENCES models (id),
                    FOREIGN KEY(type_id) REFERENCES model_types (id)
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
                    FOREIGN KEY(model_id) REFERENCES models (id) ON DELETE CASCADE
                )
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE TABLE scores (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    image_id INTEGER NOT NULL,
                    model_id INTEGER NOT NULL,
                    score FLOAT,
                    is_edited_manually BOOLEAN,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    FOREIGN KEY(image_id) REFERENCES images (id),
                    FOREIGN KEY(model_id) REFERENCES models (id)
                )
                """
            )
        )

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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    FOREIGN KEY(image_id) REFERENCES images (id),
                    FOREIGN KEY(model_id) REFERENCES models (id)
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
                    caption VARCHAR NOT NULL,
                    is_edited_manually BOOLEAN,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    FOREIGN KEY(image_id) REFERENCES images (id),
                    FOREIGN KEY(model_id) REFERENCES models (id)
                )
                """
            )
        )

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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    FOREIGN KEY(image_id) REFERENCES images (id)
                )
                """
            )
        )

        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('a860e469d0c4')"))
    engine.dispose()


@pytest.mark.unit
def test_c9b242b21b87_inserts_missing_tagger_association(tmp_path: Path) -> None:
    """upgrade() 後に tagger モデルのアソシエーションが補完される。"""
    db_path = tmp_path / "model-associations.db"
    _create_schema_at_a860(db_path)

    # wd-vit-tagger-v3 を登録するがアソシエーションは未作成にしておく
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO models (id, name) VALUES (1, 'wd-vit-tagger-v3')"))
    engine.dispose()

    command.upgrade(_make_alembic_config(db_path), "c9b242b21b87")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        count = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM model_function_associations mfa
                JOIN model_types mt ON mfa.type_id = mt.id
                JOIN models m ON mfa.model_id = m.id
                WHERE m.name = 'wd-vit-tagger-v3' AND mt.name = 'tagger'
                """
            )
        ).scalar_one()
    engine.dispose()

    assert count == 1


@pytest.mark.unit
def test_c9b242b21b87_does_not_duplicate_existing_associations(tmp_path: Path) -> None:
    """upgrade() 時にアソシエーションが既存の場合は重複挿入されない。"""
    db_path = tmp_path / "model-associations.db"
    _create_schema_at_a860(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO models (id, name) VALUES (1, 'wd-vit-tagger-v3')"))
        # 事前にアソシエーションを作成
        conn.execute(text("INSERT INTO model_function_associations (model_id, type_id) VALUES (1, 1)"))
    engine.dispose()

    command.upgrade(_make_alembic_config(db_path), "c9b242b21b87")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        count = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM model_function_associations mfa
                JOIN model_types mt ON mfa.type_id = mt.id
                JOIN models m ON mfa.model_id = m.id
                WHERE m.name = 'wd-vit-tagger-v3' AND mt.name = 'tagger'
                """
            )
        ).scalar_one()
    engine.dispose()

    # 重複せず1件のみ
    assert count == 1


@pytest.mark.unit
def test_c9b242b21b87_version_is_set(tmp_path: Path) -> None:
    """upgrade() 後に alembic_version が c9b242b21b87 になる。"""
    db_path = tmp_path / "model-associations.db"
    _create_schema_at_a860(db_path)

    command.upgrade(_make_alembic_config(db_path), "c9b242b21b87")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()

    assert version == "c9b242b21b87"
