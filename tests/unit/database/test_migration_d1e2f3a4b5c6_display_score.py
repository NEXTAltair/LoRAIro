"""Alembic migration `d1e2f3a4b5c6` display_score backfill checks."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text


def _make_alembic_config(db_path: Path) -> Config:
    project_root = Path(__file__).resolve().parents[3]
    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "src/lorairo/database/migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _get_current_head(cfg: Config) -> str:
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert len(heads) == 1
    return heads[0]


def _create_schema_at_e1(db_path: Path) -> None:
    """e1f2a3b4c5d6 (grayscale) 直後の最小スキーマを作る (display_score カラムはまだない)。"""
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE models (
                    id INTEGER NOT NULL PRIMARY KEY,
                    name VARCHAR NOT NULL,
                    provider VARCHAR,
                    litellm_model_id VARCHAR NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
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
                    mode VARCHAR NOT NULL,
                    has_alpha BOOLEAN NOT NULL,
                    filename VARCHAR NOT NULL,
                    extension VARCHAR NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE scores (
                    id INTEGER NOT NULL PRIMARY KEY,
                    image_id INTEGER,
                    model_id INTEGER,
                    score FLOAT NOT NULL,
                    is_edited_manually BOOLEAN,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    FOREIGN KEY(image_id) REFERENCES images (id) ON DELETE CASCADE,
                    FOREIGN KEY(model_id) REFERENCES models (id) ON DELETE SET NULL
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX ix_scores_image_id ON scores (image_id)"))
        # モデル行を登録
        conn.execute(
            text(
                "INSERT INTO models (id, name, litellm_model_id) VALUES "
                "(1, 'aesthetic_shadow_v2', 'aesthetic_shadow_v2'), "
                "(2, 'openai/gpt-4o-mini', 'openai/gpt-4o-mini'), "
                "(3, 'MANUAL_EDIT', 'MANUAL_EDIT'), "
                "(4, 'unknown_legacy_model', 'unknown_legacy_model')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO images (id, uuid, phash, original_image_path, stored_image_path,"
                " width, height, format, mode, has_alpha, filename, extension) VALUES"
                " (1, 'u1', 'p1', 'orig1', 'stored1', 512, 512, 'PNG', 'RGB', 0, 'img1', 'png')"
            )
        )
        # aesthetic_shadow_v2: hq=0.45 → 区分線形補間 → 8.0
        conn.execute(
            text(
                "INSERT INTO scores (id, image_id, model_id, score, is_edited_manually) VALUES (1, 1, 1, 0.45, 0)"
            )
        )
        # WebAPI (openai/gpt-4o-mini): raw=7.5 → identity + clamp → 7.5
        conn.execute(
            text(
                "INSERT INTO scores (id, image_id, model_id, score, is_edited_manually) VALUES (2, 1, 2, 7.5, 0)"
            )
        )
        # MANUAL_EDIT: raw=6.5 (already 0-10) → display_score=6.5
        conn.execute(
            text(
                "INSERT INTO scores (id, image_id, model_id, score, is_edited_manually) VALUES (3, 1, 3, 6.5, 1)"
            )
        )
        # 未知モデル: raw=0.3 → 0.3 * 10 = 3.0
        conn.execute(
            text(
                "INSERT INTO scores (id, image_id, model_id, score, is_edited_manually) VALUES (4, 1, 4, 0.3, 0)"
            )
        )
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('e1f2a3b4c5d6')"))
    engine.dispose()


@pytest.mark.unit
def test_display_score_column_added(tmp_path: Path) -> None:
    """upgrade 後に display_score カラムが追加されること。"""
    db_path = tmp_path / "display-score.db"
    _create_schema_at_e1(db_path)
    cfg = _make_alembic_config(db_path)

    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        columns = {c["name"] for c in inspect(engine).get_columns("scores")}
    engine.dispose()

    assert version == _get_current_head(cfg)
    assert "display_score" in columns


@pytest.mark.unit
def test_display_score_backfill_aesthetic_shadow(tmp_path: Path) -> None:
    """aesthetic_shadow_v2 の raw=0.45 は区分線形補間で display_score=8.0 になること。"""
    db_path = tmp_path / "display-score.db"
    _create_schema_at_e1(db_path)
    cfg = _make_alembic_config(db_path)

    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        display = conn.execute(text("SELECT display_score FROM scores WHERE id = 1")).scalar_one()
    engine.dispose()

    assert display == pytest.approx(8.0, abs=1e-6)


@pytest.mark.unit
def test_display_score_backfill_webapi(tmp_path: Path) -> None:
    """WebAPI モデル (name に '/' 含む) の raw=7.5 は identity → display_score=7.5 になること。"""
    db_path = tmp_path / "display-score.db"
    _create_schema_at_e1(db_path)
    cfg = _make_alembic_config(db_path)

    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        display = conn.execute(text("SELECT display_score FROM scores WHERE id = 2")).scalar_one()
    engine.dispose()

    assert display == pytest.approx(7.5, abs=1e-6)


@pytest.mark.unit
def test_display_score_backfill_manual_edit(tmp_path: Path) -> None:
    """is_edited_manually=True の行は raw をそのまま display_score に使うこと。"""
    db_path = tmp_path / "display-score.db"
    _create_schema_at_e1(db_path)
    cfg = _make_alembic_config(db_path)

    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        display = conn.execute(text("SELECT display_score FROM scores WHERE id = 3")).scalar_one()
    engine.dispose()

    assert display == pytest.approx(6.5, abs=1e-6)


@pytest.mark.unit
def test_display_score_backfill_unknown_model(tmp_path: Path) -> None:
    """未知モデルは raw * 10 fallback で display_score が計算されること。"""
    db_path = tmp_path / "display-score.db"
    _create_schema_at_e1(db_path)
    cfg = _make_alembic_config(db_path)

    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        display = conn.execute(text("SELECT display_score FROM scores WHERE id = 4")).scalar_one()
    engine.dispose()

    assert display == pytest.approx(3.0, abs=1e-6)


@pytest.mark.unit
def test_downgrade_removes_column(tmp_path: Path) -> None:
    """downgrade 後に display_score カラムが削除されること。"""
    db_path = tmp_path / "display-score.db"
    _create_schema_at_e1(db_path)
    cfg = _make_alembic_config(db_path)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "e1f2a3b4c5d6")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        columns = {c["name"] for c in inspect(engine).get_columns("scores")}
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()

    assert "display_score" not in columns
    assert version == "e1f2a3b4c5d6"
