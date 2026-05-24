"""Alembic migration `e4a8f1b2c3d5` の upgrade() 検証。

このマイグレーションは:
- images.manual_rating の値を ratings テーブル(MANUAL_EDIT モデル)へ移行する
- images.manual_rating カラムを削除する
- manual_rating=NULL の行は ratings に行を作成しない

Issue #119 の修正: manual_rating の書き込み先と読み込み先が異なるテーブルを使う
バグを修正し、Rating(MANUAL_EDIT) テーブルに一元化する。
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


def _create_schema_at_b2f3(db_path: Path) -> None:
    """b2f3a4c5d6e7 適用後のスキーマを作成する。

    e4a8f1b2c3d5 の down_revision は b2f3a4c5d6e7 なので、
    images.manual_rating カラムが存在する状態を再現する。
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
        conn.execute(text("CREATE UNIQUE INDEX ix_images_uuid ON images (uuid)"))

        conn.execute(
            text(
                """
                CREATE TABLE models (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR NOT NULL,
                    provider VARCHAR,
                    discontinued_at TIMESTAMP,
                    api_model_id VARCHAR,
                    estimated_size_gb FLOAT,
                    requires_api_key BOOLEAN DEFAULT '0' NOT NULL,
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
                "(1, 'tagger'), (2, 'score'), (3, 'captioner'), "
                "(4, 'upscaler'), (5, 'multimodal'), (6, 'ratings')"
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
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    image_id INTEGER NOT NULL,
                    model_id INTEGER NOT NULL,
                    raw_rating_value VARCHAR NOT NULL,
                    normalized_rating VARCHAR NOT NULL,
                    confidence_score FLOAT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
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
                    upscaler_used VARCHAR,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    FOREIGN KEY(image_id) REFERENCES images (id)
                )
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE TABLE error_records (
                    id INTEGER NOT NULL PRIMARY KEY,
                    image_id INTEGER,
                    operation_type VARCHAR NOT NULL,
                    error_type VARCHAR NOT NULL,
                    error_message VARCHAR NOT NULL,
                    stack_trace VARCHAR,
                    file_path VARCHAR,
                    model_name VARCHAR,
                    retry_count INTEGER NOT NULL,
                    resolved_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    FOREIGN KEY(image_id) REFERENCES images (id) ON DELETE CASCADE
                )
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE TABLE image_filename_aliases (
                    id INTEGER NOT NULL PRIMARY KEY,
                    image_id INTEGER NOT NULL,
                    stem VARCHAR NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (stem),
                    FOREIGN KEY(image_id) REFERENCES images (id) ON DELETE CASCADE
                )
                """
            )
        )

        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('b2f3a4c5d6e7')"))
    engine.dispose()


@pytest.mark.unit
def test_e4a8f1b2c3d5_manual_rating_safe_migrated_to_ratings(tmp_path: Path) -> None:
    """images.manual_rating='safe' の行がある → upgrade() → ratings テーブルに MANUAL_EDIT 行が作成される。"""
    db_path = tmp_path / "manual-rating.db"
    _create_schema_at_b2f3(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO images (id, uuid, phash, original_image_path, stored_image_path, "
                "format, extension, manual_rating, created_at, updated_at) "
                "VALUES (1, 'test-uuid-1', 'aabbcc', '/orig/a.png', '/stored/a.png', "
                "'PNG', 'png', 'safe', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
    engine.dispose()

    command.upgrade(_make_alembic_config(db_path), "e4a8f1b2c3d5")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        rating_rows = conn.execute(
            text(
                """
                SELECT r.image_id, r.normalized_rating, m.name
                FROM ratings r
                JOIN models m ON r.model_id = m.id
                WHERE m.name = 'MANUAL_EDIT'
                """
            )
        ).fetchall()
    engine.dispose()

    assert len(rating_rows) == 1
    assert rating_rows[0].image_id == 1
    assert rating_rows[0].normalized_rating == "safe"
    assert rating_rows[0].name == "MANUAL_EDIT"


@pytest.mark.unit
def test_e4a8f1b2c3d5_null_manual_rating_not_migrated(tmp_path: Path) -> None:
    """images.manual_rating=NULL の行がある → upgrade() → ratings に行が作成されない。"""
    db_path = tmp_path / "manual-rating-null.db"
    _create_schema_at_b2f3(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO images (id, uuid, phash, original_image_path, stored_image_path, "
                "format, extension, manual_rating, created_at, updated_at) "
                "VALUES (1, 'test-uuid-2', 'aabbcc', '/orig/b.png', '/stored/b.png', "
                "'PNG', 'png', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
    engine.dispose()

    command.upgrade(_make_alembic_config(db_path), "e4a8f1b2c3d5")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        count = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM ratings r
                JOIN models m ON r.model_id = m.id
                WHERE m.name = 'MANUAL_EDIT'
                """
            )
        ).scalar_one()
    engine.dispose()

    assert count == 0


@pytest.mark.unit
def test_e4a8f1b2c3d5_manual_rating_column_removed(tmp_path: Path) -> None:
    """upgrade() 後に images.manual_rating カラムが存在しない。"""
    db_path = tmp_path / "manual-rating-col.db"
    _create_schema_at_b2f3(db_path)

    command.upgrade(_make_alembic_config(db_path), "e4a8f1b2c3d5")

    engine = create_engine(f"sqlite:///{db_path}")
    insp = inspect(engine)
    cols = {col["name"] for col in insp.get_columns("images")}
    engine.dispose()

    assert "manual_rating" not in cols


@pytest.mark.unit
def test_e4a8f1b2c3d5_existing_manual_edit_rating_is_skipped(tmp_path: Path) -> None:
    """upgrade() 時に images.manual_rating があっても、既にRatingがある画像はスキップされる。"""
    db_path = tmp_path / "manual-rating-skip.db"
    _create_schema_at_b2f3(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO images (id, uuid, phash, original_image_path, stored_image_path, "
                "format, extension, manual_rating, created_at, updated_at) "
                "VALUES (1, 'test-uuid-3', 'aabbcc', '/orig/c.png', '/stored/c.png', "
                "'PNG', 'png', 'questionable', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        # MANUAL_EDIT モデルを事前に作成し、既存 rating 行を挿入
        conn.execute(text("INSERT INTO models (id, name, provider) VALUES (99, 'MANUAL_EDIT', 'user')"))
        conn.execute(
            text(
                "INSERT INTO ratings (image_id, model_id, raw_rating_value, normalized_rating) "
                "VALUES (1, 99, 'safe', 'safe')"
            )
        )
    engine.dispose()

    command.upgrade(_make_alembic_config(db_path), "e4a8f1b2c3d5")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        # 既存の safe rating はそのまま保持され、questionable は追加されない
        rows = conn.execute(
            text(
                """
                SELECT r.normalized_rating FROM ratings r
                JOIN models m ON r.model_id = m.id
                WHERE m.name = 'MANUAL_EDIT'
                """
            )
        ).fetchall()
    engine.dispose()

    # 1件のみ（事前挿入の safe、manual_rating の questionable はスキップ）
    assert len(rows) == 1
    assert rows[0][0] == "safe"
