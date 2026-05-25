"""Alembic migration `c6d7e8f9a0b1` provider batch schema checks."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


def _make_alembic_config(db_path: Path) -> Config:
    project_root = Path(__file__).resolve().parents[3]
    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "src/lorairo/database/migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _create_minimal_parent_schema(db_path: Path) -> None:
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
                CREATE TABLE images (
                    id INTEGER NOT NULL PRIMARY KEY,
                    uuid VARCHAR NOT NULL,
                    phash VARCHAR NOT NULL,
                    original_image_path VARCHAR NOT NULL,
                    stored_image_path VARCHAR NOT NULL,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    format VARCHAR NOT NULL,
                    extension VARCHAR NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    UNIQUE (uuid, phash)
                )
                """
            )
        )
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('b4c5d6e7f8a9')"))
    engine.dispose()


@pytest.mark.unit
def test_provider_batch_tables_upgrade_and_downgrade(tmp_path: Path) -> None:
    db = tmp_path / "provider_batch.db"
    _create_minimal_parent_schema(db)
    cfg = _make_alembic_config(db)

    command.upgrade(cfg, "c6d7e8f9a0b1")

    engine = create_engine(f"sqlite:///{db}")
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    assert "provider_batch_jobs" in table_names
    assert "provider_batch_items" in table_names
    assert "provider_batch_artifacts" in table_names

    job_columns = {col["name"] for col in inspector.get_columns("provider_batch_jobs")}
    assert {
        "provider",
        "provider_job_id",
        "status",
        "request_count",
        "raw_provider_payload",
        "created_at",
        "updated_at",
    }.issubset(job_columns)
    assert "uq_provider_batch_jobs_provider_job" in {
        index["name"] for index in inspector.get_indexes("provider_batch_jobs")
    }

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO provider_batch_jobs
                    (provider, provider_job_id, status)
                VALUES
                    ('openai', 'batch_1', 'submitted')
                """
            )
        )
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    """
                    INSERT INTO provider_batch_jobs
                        (provider, provider_job_id, status)
                    VALUES
                        ('openai', 'batch_1', 'submitted')
                    """
                )
            )
        conn.execute(
            text(
                """
                INSERT INTO provider_batch_jobs
                    (provider, provider_job_id, status)
                VALUES
                    ('anthropic', 'batch_1', 'submitted')
                """
            )
        )
    engine.dispose()

    command.downgrade(cfg, "b4c5d6e7f8a9")

    engine = create_engine(f"sqlite:///{db}")
    table_names = set(inspect(engine).get_table_names())
    assert "provider_batch_jobs" not in table_names
    assert "provider_batch_items" not in table_names
    assert "provider_batch_artifacts" not in table_names
    engine.dispose()
