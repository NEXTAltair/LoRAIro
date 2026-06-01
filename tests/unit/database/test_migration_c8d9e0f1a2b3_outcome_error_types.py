"""Alembic migration `c8d9e0f1a2b3` annotation outcome error_type normalization."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


def _make_alembic_config(db_path: Path) -> Config:
    project_root = Path(__file__).resolve().parents[3]
    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "src/lorairo/database/migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _create_parent_schema(db_path: Path) -> None:
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE error_records (
                    id INTEGER NOT NULL PRIMARY KEY,
                    image_id INTEGER,
                    operation_type VARCHAR NOT NULL,
                    error_type VARCHAR NOT NULL,
                    error_message TEXT NOT NULL,
                    stack_trace TEXT,
                    file_path VARCHAR,
                    model_name VARCHAR,
                    resolved_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
        )
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('b7c8d9e0f1a2')"))
    engine.dispose()


@pytest.mark.unit
def test_upgrade_noops_when_error_records_table_is_absent(tmp_path: Path) -> None:
    db = tmp_path / "outcome_error_types_no_table.db"
    engine = create_engine(f"sqlite:///{db}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('b7c8d9e0f1a2')"))
    engine.dispose()

    command.upgrade(_make_alembic_config(db), "c8d9e0f1a2b3")

    engine = create_engine(f"sqlite:///{db}")
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()

    assert version == "c8d9e0f1a2b3"


@pytest.mark.unit
def test_upgrade_normalizes_legacy_refusal_error_types(tmp_path: Path) -> None:
    db = tmp_path / "outcome_error_types.db"
    _create_parent_schema(db)
    engine = create_engine(f"sqlite:///{db}")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO error_records
                    (operation_type, error_type, error_message, model_name)
                VALUES
                    ('annotation', 'SafetyRefusalError', 'blocked', 'openai/gpt-4o'),
                    ('annotation', 'ContentPolicyRefusalError', 'blocked', 'openai/gpt-4o'),
                    ('annotation', 'ApiTimeoutError', 'timeout', 'openai/gpt-4o'),
                    ('registration', 'SafetyRefusalError', 'not annotation', NULL)
                """
            )
        )
    engine.dispose()

    command.upgrade(_make_alembic_config(db), "c8d9e0f1a2b3")

    engine = create_engine(f"sqlite:///{db}")
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT operation_type, error_type FROM error_records ORDER BY id")).all()
    engine.dispose()

    assert rows == [
        ("annotation", "SAFETY_REFUSAL"),
        ("annotation", "CONTENT_POLICY_REFUSAL"),
        ("annotation", "ApiTimeoutError"),
        ("registration", "SafetyRefusalError"),
    ]


@pytest.mark.unit
def test_downgrade_restores_legacy_refusal_error_types(tmp_path: Path) -> None:
    db = tmp_path / "outcome_error_types.db"
    _create_parent_schema(db)
    engine = create_engine(f"sqlite:///{db}")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO error_records
                    (operation_type, error_type, error_message, model_name)
                VALUES
                    ('annotation', 'SAFETY_REFUSAL', 'blocked', 'openai/gpt-4o'),
                    ('annotation', 'CONTENT_POLICY_REFUSAL', 'blocked', 'openai/gpt-4o'),
                    ('annotation', 'EMPTY_ANNOTATION', 'empty', 'openai/o1')
                """
            )
        )
    engine.dispose()

    command.upgrade(_make_alembic_config(db), "c8d9e0f1a2b3")
    command.downgrade(_make_alembic_config(db), "b7c8d9e0f1a2")

    engine = create_engine(f"sqlite:///{db}")
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT error_type FROM error_records ORDER BY id")).scalars().all()
    engine.dispose()

    assert rows == ["SafetyRefusalError", "ContentPolicyRefusalError", "EMPTY_ANNOTATION"]
