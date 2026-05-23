"""Alembic migration `a3b4c5d6e7f8` legacy sentinel removal checks.

ADR 0033 Decision 7 で導入された `__legacy_<id>__` sentinel 行削除 migration の
verification。Codex P1-1 指摘 (LIKE wildcard 誤マッチ) の regression 防止も含む。
"""

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


@pytest.mark.unit
def test_sentinel_rows_are_removed_and_non_sentinel_preserved(tmp_path: Path) -> None:
    """`__legacy_<id>__` sentinel のみ削除され、非 sentinel 行は残る。

    Codex P1-1 (PR #407) で指摘された LIKE wildcard 誤マッチを防ぐ。
    SQL LIKE で `_` がワイルドカード扱いされると `mylegacy-foo` 等も削除対象になる
    可能性があったため、ESCAPE 句で literal 化していることを保証する。
    """
    db = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db}")
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
        # 削除対象: legacy sentinel
        conn.execute(
            text("INSERT INTO models (id, name, litellm_model_id) VALUES (1, 'a', '__legacy_17__')")
        )
        conn.execute(
            text("INSERT INTO models (id, name, litellm_model_id) VALUES (2, 'b', '__legacy_22__')")
        )
        # 削除されてはいけない: `_` をワイルドカード扱いすると `__legacy_` プレフィックス
        # でないが `_` 含む ID が誤マッチする可能性。これらが残ることで ESCAPE が効いている
        # ことを保証する (Codex P1-1 regression test)。
        conn.execute(
            text("INSERT INTO models (id, name, litellm_model_id) VALUES (3, 'c', 'mylegacy-model')")
        )
        conn.execute(
            text("INSERT INTO models (id, name, litellm_model_id) VALUES (4, 'd', 'xxlegacyZmodel')")
        )
        conn.execute(
            text("INSERT INTO models (id, name, litellm_model_id) VALUES (5, 'e', 'openai/gpt-4o')")
        )
        # alembic_version を `f1b2c3d4e5f6` (a3b4c5d6e7f8 の down_revision) に
        # 直接スタンプして、対象 migration だけを走らせる
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('f1b2c3d4e5f6')"))
    engine.dispose()

    command.upgrade(_make_alembic_config(db), "a3b4c5d6e7f8")

    engine = create_engine(f"sqlite:///{db}")
    with engine.connect() as conn:
        remaining = {
            row.litellm_model_id for row in conn.execute(text("SELECT litellm_model_id FROM models"))
        }
    engine.dispose()

    # legacy sentinel は両方削除
    assert "__legacy_17__" not in remaining
    assert "__legacy_22__" not in remaining
    # 非 sentinel は残る (ESCAPE で wildcard 誤マッチを防ぐ)
    assert "mylegacy-model" in remaining
    assert "xxlegacyZmodel" in remaining
    assert "openai/gpt-4o" in remaining
