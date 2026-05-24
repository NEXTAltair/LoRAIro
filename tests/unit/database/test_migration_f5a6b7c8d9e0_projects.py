"""Alembic migration `f5a6b7c8d9e0` の upgrade() 検証。

このマイグレーションは:
- projects テーブルを新規作成する
- images テーブルに project_id カラム(FK)を追加する
- DB ファイルパスからプロジェクト情報をバックフィルする（テスト用DBはスキップ）

Issue #175 (ADR 0017): プロジェクトを第一級エンティティとして DB 正規化する。
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


def _create_schema_at_e4a8(db_path: Path) -> None:
    """e4a8f1b2c3d5 適用後のスキーマを作成する。

    f5a6b7c8d9e0 の down_revision は e4a8f1b2c3d5 なので、
    images.manual_rating カラムがなく、projects テーブルもない状態を再現する。
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
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('e4a8f1b2c3d5')"))
    engine.dispose()


@pytest.mark.unit
def test_f5a6b7c8d9e0_creates_projects_table(tmp_path: Path) -> None:
    """upgrade() 後に projects テーブルが作成される。"""
    db_path = tmp_path / "projects.db"
    _create_schema_at_e4a8(db_path)

    command.upgrade(_make_alembic_config(db_path), "f5a6b7c8d9e0")

    engine = create_engine(f"sqlite:///{db_path}")
    insp = inspect(engine)
    assert "projects" in insp.get_table_names()
    engine.dispose()


@pytest.mark.unit
def test_f5a6b7c8d9e0_projects_table_has_expected_columns(tmp_path: Path) -> None:
    """projects テーブルの必須カラムが存在する。"""
    db_path = tmp_path / "projects.db"
    _create_schema_at_e4a8(db_path)

    command.upgrade(_make_alembic_config(db_path), "f5a6b7c8d9e0")

    engine = create_engine(f"sqlite:///{db_path}")
    insp = inspect(engine)
    cols = {col["name"] for col in insp.get_columns("projects")}
    engine.dispose()

    assert "id" in cols
    assert "name" in cols
    assert "path" in cols
    assert "created_at" in cols


@pytest.mark.unit
def test_f5a6b7c8d9e0_images_gets_project_id_column(tmp_path: Path) -> None:
    """upgrade() 後に images テーブルに project_id カラムが追加される。"""
    db_path = tmp_path / "projects.db"
    _create_schema_at_e4a8(db_path)

    command.upgrade(_make_alembic_config(db_path), "f5a6b7c8d9e0")

    engine = create_engine(f"sqlite:///{db_path}")
    insp = inspect(engine)
    cols = {col["name"] for col in insp.get_columns("images")}
    engine.dispose()

    assert "project_id" in cols


@pytest.mark.unit
def test_f5a6b7c8d9e0_project_id_is_nullable(tmp_path: Path) -> None:
    """images.project_id カラムは nullable=True である。"""
    db_path = tmp_path / "projects.db"
    _create_schema_at_e4a8(db_path)

    command.upgrade(_make_alembic_config(db_path), "f5a6b7c8d9e0")

    engine = create_engine(f"sqlite:///{db_path}")
    insp = inspect(engine)
    cols = {col["name"]: col for col in insp.get_columns("images")}
    engine.dispose()

    assert cols["project_id"]["nullable"] is True


@pytest.mark.unit
def test_f5a6b7c8d9e0_version_is_set(tmp_path: Path) -> None:
    """upgrade() 後に alembic_version が f5a6b7c8d9e0 になる。"""
    db_path = tmp_path / "projects.db"
    _create_schema_at_e4a8(db_path)

    command.upgrade(_make_alembic_config(db_path), "f5a6b7c8d9e0")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()

    assert version == "f5a6b7c8d9e0"
