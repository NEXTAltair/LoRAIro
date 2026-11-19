"""Alembic migration `b1c2d3e4f5a6` model_id NULL のタグ行を擬似モデルへ移す (ADR 0111)。

縮約スキーマではなく、実スキーマ (`Base.metadata.create_all`。本 migration はスキーマを変えない
ため直前 revision と同じ) を作って直前 revision に stamp した DB で検証する。新規プロジェクト DB を
create_all + stamp で作るアプリの手順 (`_prepare_project_database`) と同じ形。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from lorairo.database.schema import Base

pytestmark = pytest.mark.unit

PREVIOUS_REVISION = "f8a9b0c1d2e3"
REVISION = "b1c2d3e4f5a6"

MANUAL_EDIT = "__manual_edit__"
SIDECAR_IMPORT = "__sidecar_import__"
IMAGE_PROCESSING = "__image_processing__"


def _make_alembic_config(db_path: Path) -> Config:
    project_root = Path(__file__).resolve().parents[3]
    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "src/lorairo/database/migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


# (id, image_id, model_litellm_id, tag, existing, is_edited_manually)
_SEED_TAGS: list[tuple[int, int, str | None, str, int, int | None]] = [
    (1, 1, None, "upscaled", 0, 0),  # → IMAGE_PROCESSING
    (2, 1, None, "cat", 1, 0),  # → SIDECAR_IMPORT
    (3, 1, None, "dog", 1, None),  # existing=True & NULL → SIDECAR_IMPORT
    (4, 1, None, "blue_sky", 0, 1),  # → MANUAL_EDIT
    (5, 1, None, "red_eyes", 1, 1),  # 手動フラグ優先 → MANUAL_EDIT
    (6, 1, None, "mystery", 0, 0),  # どれにも当たらない → NULL のまま
    (7, 1, None, "upscaled_extra", 0, None),  # どれにも当たらない → NULL のまま
    (8, 1, "wd-tagger", "cat", 0, 0),  # AI の行は触らない
    (9, 2, MANUAL_EDIT, "smile", 0, 1),  # 移行前からの MANUAL_EDIT 行
    (10, 2, None, "smile", 0, 1),  # 移行先に同じ行がある → NULL のまま (UNIQUE を守る)
    (11, 2, None, "upscaled", 1, 0),  # existing=True の upscaled は取り込み由来 → SIDECAR_IMPORT
    (12, 2, MANUAL_EDIT, "bow", 0, 1),  # 移行前からの MANUAL_EDIT 行
    (13, 2, None, "bow", 1, 1),  # 手動の行が衝突で移れなくても取り込みへ流さず NULL のまま
    (14, 2, None, "hat", 0, 1),  # 手動の NULL 重複の先頭 → MANUAL_EDIT
    (15, 2, None, "hat", 1, 1),  # 手動の NULL 重複の 2 行目 → 取り込みへ流さず NULL のまま
]


def _seed(db_path: Path) -> None:
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        for image_id in (1, 2):
            conn.execute(
                text(
                    "INSERT INTO images (id, uuid, phash, original_image_path, stored_image_path, "
                    "width, height, format, extension) VALUES "
                    "(:id, :uuid, :phash, '/o.png', '/s.png', 8, 8, 'PNG', '.png')"
                ),
                {"id": image_id, "uuid": f"u{image_id}", "phash": f"p{image_id}"},
            )
        for litellm_id, name in (("wd-tagger", "wd"), (MANUAL_EDIT, "MANUAL_EDIT")):
            conn.execute(
                text(
                    "INSERT INTO models (name, provider, litellm_model_id, requires_api_key) "
                    "VALUES (:name, 'user', :litellm_id, 0)"
                ),
                {"name": name, "litellm_id": litellm_id},
            )
        for tag_id, image_id, litellm_id, tag, existing, manual in _SEED_TAGS:
            conn.execute(
                text(
                    "INSERT INTO tags (id, image_id, model_id, tag, existing, is_edited_manually, "
                    "updated_at) VALUES (:id, :image_id, "
                    "(SELECT id FROM models WHERE litellm_model_id = :litellm_id), "
                    ":tag, :existing, :manual, '2024-01-01 00:00:00')"
                ),
                {
                    "id": tag_id,
                    "image_id": image_id,
                    "litellm_id": litellm_id,
                    "tag": tag,
                    "existing": existing,
                    "manual": manual,
                },
            )
    engine.dispose()


def _tag_models(db_path: Path) -> dict[int, str | None]:
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT tags.id, models.litellm_model_id FROM tags "
                "LEFT JOIN models ON models.id = tags.model_id ORDER BY tags.id"
            )
        ).all()
    engine.dispose()
    return {row[0]: row[1] for row in rows}


@pytest.fixture
def migrated_db(tmp_path: Path) -> tuple[Path, Config]:
    db_path = tmp_path / "provenance.db"
    cfg = _make_alembic_config(db_path)
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    engine.dispose()
    command.stamp(cfg, PREVIOUS_REVISION)
    _seed(db_path)
    command.upgrade(cfg, REVISION)
    return db_path, cfg


def test_upgrade_assigns_null_rows_by_origin(migrated_db: tuple[Path, Config]) -> None:
    db_path, _cfg = migrated_db

    assert _tag_models(db_path) == {
        1: IMAGE_PROCESSING,
        2: SIDECAR_IMPORT,
        3: SIDECAR_IMPORT,
        4: MANUAL_EDIT,
        5: MANUAL_EDIT,
        6: None,
        7: None,
        8: "wd-tagger",
        9: MANUAL_EDIT,
        10: None,
        11: SIDECAR_IMPORT,
        12: MANUAL_EDIT,
        13: None,
        14: MANUAL_EDIT,
        15: None,
    }


def test_upgrade_creates_pseudo_models_once_and_keeps_updated_at(migrated_db: tuple[Path, Config]) -> None:
    db_path, _cfg = migrated_db
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        models = conn.execute(
            text(
                "SELECT litellm_model_id, name, provider, requires_api_key FROM models "
                "WHERE litellm_model_id LIKE '\\_\\_%' ESCAPE '\\' ORDER BY litellm_model_id"
            )
        ).all()
        type_links = conn.execute(text("SELECT COUNT(*) FROM model_function_associations")).scalar_one()
        updated_at = set(conn.execute(text("SELECT DISTINCT updated_at FROM tags")).scalars())
    engine.dispose()

    assert [tuple(m) for m in models] == [
        (IMAGE_PROCESSING, "IMAGE_PROCESSING", "user", 0),
        (MANUAL_EDIT, "MANUAL_EDIT", "user", 0),
        (SIDECAR_IMPORT, "SIDECAR_IMPORT", "user", 0),
    ]
    assert type_links == 0
    # 移行は利用者の変更ではないので updated_at を動かさない (changed-since に出さない)
    assert updated_at == {"2024-01-01 00:00:00"}


def test_downgrade_reverts_sidecar_and_processing_rows(migrated_db: tuple[Path, Config]) -> None:
    db_path, cfg = migrated_db

    command.downgrade(cfg, PREVIOUS_REVISION)

    models = _tag_models(db_path)
    assert [models[i] for i in (1, 2, 3, 11)] == [None, None, None, None]
    # MANUAL_EDIT は移行前からの行と区別できないため戻さない (旧版も MANUAL_EDIT 行を扱える)
    assert [models[i] for i in (4, 5, 9)] == [MANUAL_EDIT, MANUAL_EDIT, MANUAL_EDIT]
    assert [models[i] for i in (6, 7, 8, 10)] == [None, None, "wd-tagger", None]


def test_upgrade_is_idempotent_after_downgrade(migrated_db: tuple[Path, Config]) -> None:
    db_path, cfg = migrated_db
    command.downgrade(cfg, PREVIOUS_REVISION)

    command.upgrade(cfg, REVISION)

    assert _tag_models(db_path)[2] == SIDECAR_IMPORT
    assert _tag_models(db_path)[1] == IMAGE_PROCESSING
