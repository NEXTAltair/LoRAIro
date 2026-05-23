"""Alembic migration `f1b2c3d4e5f6` ratings association backfill checks."""

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


def _create_schema_at_f0(db_path: Path) -> None:
    """Create the minimal schema after f0 ratings model_type migration."""
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
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
                "INSERT INTO model_types (id, name) VALUES "
                "(1, 'tags'), (2, 'scores'), (3, 'caption'), "
                "(4, 'upscaler'), (5, 'multimodal'), (6, 'ratings')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO models (id, name, provider, litellm_model_id) VALUES "
                "(1, 'wd-vit-tagger-v3', 'local', 'wd-vit-tagger-v3'), "
                "(2, 'Z3D-E621-Convnext', 'local', 'Z3D-E621-Convnext'), "
                "(3, 'clip-aesthetic', 'local', 'clip-aesthetic')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO model_function_associations (model_id, type_id) VALUES (1, 1), (2, 1), (3, 2)"
            )
        )
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('f0a1b2c3d4e5')"))
    engine.dispose()


@pytest.mark.unit
def test_ratings_backfill_adds_associations_for_known_rating_models(tmp_path: Path) -> None:
    db_path = tmp_path / "ratings-backfill.db"
    _create_schema_at_f0(db_path)

    command.upgrade(_make_alembic_config(db_path), "head")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT m.name, group_concat(mt.name)
                FROM models AS m
                JOIN model_function_associations AS mfa ON m.id = mfa.model_id
                JOIN model_types AS mt ON mt.id = mfa.type_id
                GROUP BY m.id
                ORDER BY m.id
                """
            )
        ).fetchall()
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()

    assert version == "b4c5d6e7f8a9"
    assert rows == [
        ("wd-vit-tagger-v3", "tags,ratings"),
        ("Z3D-E621-Convnext", "tags,ratings"),
        ("clip-aesthetic", "scores"),
    ]


@pytest.mark.unit
def test_ratings_backfill_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "ratings-backfill.db"
    _create_schema_at_f0(db_path)

    cfg = _make_alembic_config(db_path)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "f0a1b2c3d4e5")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        count_after_downgrade = conn.execute(
            text(
                """
                SELECT count(*)
                FROM model_function_associations AS mfa
                JOIN model_types AS mt ON mt.id = mfa.type_id
                WHERE mt.name = 'ratings'
                """
            )
        ).scalar_one()
    engine.dispose()

    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        count = conn.execute(
            text(
                """
                SELECT count(*)
                FROM model_function_associations AS mfa
                JOIN model_types AS mt ON mt.id = mfa.type_id
                WHERE mt.name = 'ratings'
                """
            )
        ).scalar_one()
    engine.dispose()

    assert count_after_downgrade == 2
    assert count == 2


@pytest.mark.unit
def test_downgrade_preserves_preexisting_ratings_associations(tmp_path: Path) -> None:
    db_path = tmp_path / "ratings-backfill.db"
    _create_schema_at_f0(db_path)
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO model_function_associations (model_id, type_id) VALUES (3, 6)"))
    engine.dispose()

    cfg = _make_alembic_config(db_path)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "f0a1b2c3d4e5")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT m.name
                FROM models AS m
                JOIN model_function_associations AS mfa ON m.id = mfa.model_id
                JOIN model_types AS mt ON mt.id = mfa.type_id
                WHERE mt.name = 'ratings'
                ORDER BY m.id
                """
            )
        ).fetchall()
    engine.dispose()

    assert [row.name for row in rows] == [
        "wd-vit-tagger-v3",
        "Z3D-E621-Convnext",
        "clip-aesthetic",
    ]
