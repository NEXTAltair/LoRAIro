"""`review run` がクロップ子画像だけを Clef で確認し、指定時だけ結果を保存する (#1603)。

実プロジェクト (テスト用ワークスペース) の SQLite と、HTTP を MockTransport に差し替えた
実 Clef クライアント (fake backend) を使う。
"""

from __future__ import annotations

import json
import re
from functools import partial
from pathlib import Path

import httpx
import pytest
from PIL import Image as PILImage
from sqlalchemy import select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from lorairo.cli.main import app
from lorairo.services import annotation_review_service

pytestmark = [pytest.mark.integration, pytest.mark.cli]

PARENT, CHILD_A, CHILD_B, UNRELATED, LONELY_PARENT, OTHER_PARENT, OTHER_CHILD = 1, 2, 3, 4, 5, 6, 7


@pytest.fixture
def crop_project(tmp_path, monkeypatch, local_clef_settings):
    """親 1 枚・子 2 枚・無関係 1 枚・子の無い親・別の親子を持つプロジェクト。"""
    from lorairo.database import db_core
    from lorairo.database.schema import Caption, CropRelation, Image, Tag
    from lorairo.services.project_management_service import ProjectManagementService
    from lorairo.utils.config import resolve_runtime_configuration, runtime_configuration_scope

    workspace = tmp_path / "crop-review-workspace"
    config_path = workspace / "config" / "lorairo.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        '[directories]\ndatabase_base_dir = "lorairo_data"\n\n[annotation_review]\n'
        + "".join(f'{key} = "{value}"\n' for key, value in local_clef_settings.items()),
        encoding="utf-8",
    )
    configuration = resolve_runtime_configuration(workspace, config_path)
    with runtime_configuration_scope(configuration):
        info = ProjectManagementService().create_project("crops")
    engine = db_core._prepare_project_database(info.path / "image_database.db")
    image_path = info.path / "image_dataset" / "original_images" / "sample.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    PILImage.new("RGB", (32, 32), "red").save(image_path)
    with Session(engine) as session:
        for image_id in (PARENT, CHILD_A, CHILD_B, UNRELATED, LONELY_PARENT, OTHER_PARENT, OTHER_CHILD):
            session.add(
                Image(
                    id=image_id,
                    uuid=f"crop-review-{image_id}",
                    phash=f"crop-review-{image_id}",
                    original_image_path=str(image_path),
                    stored_image_path=str(image_path),
                    width=32,
                    height=32,
                    format="PNG",
                    extension=".png",
                )
            )
        session.flush()
        for image_id in (PARENT, CHILD_A, CHILD_B, UNRELATED, OTHER_CHILD):
            session.add_all([Tag(image_id=image_id, tag="portrait"), Tag(image_id=image_id, tag="dog")])
            session.add(Caption(image_id=image_id, caption=f"A dog {image_id}."))
        session.add_all(
            [
                CropRelation(parent_image_id=PARENT, child_image_id=CHILD_A, x=0, y=0, width=16, height=16),
                CropRelation(
                    parent_image_id=PARENT, child_image_id=CHILD_B, x=16, y=16, width=16, height=16
                ),
                CropRelation(
                    parent_image_id=OTHER_PARENT, child_image_id=OTHER_CHILD, x=0, y=0, width=8, height=8
                ),
            ]
        )
        session.commit()
    engine.dispose()

    requested_image_ids: list[int] = []

    def transport(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        # 画像ごとに固有のキャプション "A dog {id}." から評価対象の画像 ID を特定する。
        texts = [annotation["text"] for annotation in payload["state"]["annotations"].values()]
        requested_image_ids.extend(
            int(match.group(1)) for text in texts if (match := re.fullmatch(r"A dog (\d+)\.", text))
        )
        answers = {
            question_id: {"type": "noul", "noul": 0.04 if annotation["text"] == "dog" else 0.93}
            for question_id, annotation in payload["state"]["annotations"].items()
        }
        return httpx.Response(200, json={"model": "clef-flash", "answers": answers})

    from image_annotator_lib.decisions import LocalDecisionClient

    original = annotation_review_service.AnnotationReviewService
    monkeypatch.setattr(
        annotation_review_service,
        "AnnotationReviewService",
        partial(
            original, client_factory=partial(LocalDecisionClient, transport=httpx.MockTransport(transport))
        ),
    )
    monkeypatch.setattr("lorairo.utils.config.get_user_config_path", lambda: workspace / "no-user.toml")
    return workspace, config_path, info.path / "image_database.db", requested_image_ids


def _invoke(project_setup, *args: str):
    workspace, config_path, _db, _requested = project_setup
    return CliRunner().invoke(
        app,
        ["--json", "--workspace", str(workspace), "--config", str(config_path), *args],
    )


def _rows(result) -> list[dict]:
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def _annotation_state(db_path: Path) -> dict[str, list[tuple]]:
    """タグ・キャプション・画像 (reject / reviewed 状態を含む) の全列を比較用に読む。"""
    from sqlalchemy import create_engine

    from lorairo.database.schema import Caption, Image, Tag

    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with Session(engine) as session:
            state = {}
            for model in (Tag, Caption, Image):
                columns = [column.key for column in model.__table__.columns]
                rows = session.execute(select(*(getattr(model, name) for name in columns))).all()
                state[model.__tablename__] = sorted(tuple(row) for row in rows)
            return state
    finally:
        engine.dispose()


def _stored_review_ids(db_path: Path) -> list[int]:
    from sqlalchemy import create_engine, text

    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as connection:
            return sorted(
                connection.execute(text("SELECT image_id FROM annotation_review_results")).scalars()
            )
    finally:
        engine.dispose()


def test_saved_crop_child_reviews_only_children_and_appear_as_needs_review(crop_project):
    _workspace, _config, db_path, requested = crop_project
    before = _annotation_state(db_path)

    result = _invoke(
        crop_project, "review", "run", "--project", "crops", "--crop-children-of", "1", "--save-results"
    )

    assert result.exit_code == 0, result.output
    rows = _rows(result)
    outcomes = [row for row in rows if row.get("type") == "annotation_review_outcome"]
    assert [row["image_id"] for row in outcomes] == [CHILD_A, CHILD_B]
    assert all(row["status"] == "completed" and row["save_status"] == "saved" for row in outcomes)
    summary = rows[-1]
    assert summary["ok"] is True and summary["image_count"] == 2
    assert summary["save_results"] is True and summary["saved"] == 2 and summary["save_failed"] == 0
    # 子だけが評価され、親・無関係画像・別の親の子は評価されない。
    assert sorted(set(requested)) == [CHILD_A, CHILD_B]
    assert _stored_review_ids(db_path) == [CHILD_A, CHILD_B]
    # タグ・キャプション・画像 (reject 状態を含む) は変わらない。
    assert _annotation_state(db_path) == before

    # 既存の検索の「要確認」判定 (保存済み結果の鮮度確認を含む) にそのまま現れる。
    from lorairo.database import db_core
    from lorairo.database.db_manager import ImageDatabaseManager
    from lorairo.database.repository.image import ImageRepository
    from lorairo.services.annotation_review_store import AnnotationReviewStore
    from lorairo.services.configuration_service import ConfigurationService
    from lorairo.services.search_review_status import apply_review_filter

    _workspace, config_path, _db, _requested = crop_project
    from lorairo.utils.config import resolve_runtime_configuration, runtime_configuration_scope

    with runtime_configuration_scope(resolve_runtime_configuration(_workspace, config_path)):
        engine = db_core._open_read_only_project_database(db_path)
        try:
            session_factory = db_core.create_session_factory(engine)
            config = ConfigurationService()
            db_manager = ImageDatabaseManager(
                ImageRepository(session_factory=session_factory), config, session_factory=session_factory
            )
            service = annotation_review_service.AnnotationReviewService(config, db_manager)
            store = AnnotationReviewStore(db_manager)
            images = [{"id": image_id} for image_id in (PARENT, CHILD_A, CHILD_B, UNRELATED)]
            flagged = apply_review_filter(images, service, store, warnings_only=True)
        finally:
            engine.dispose()
    assert [image["id"] for image in flagged] == [CHILD_A, CHILD_B]
    assert all(image["annotation_review_warning_count"] == 1 for image in flagged)


def test_all_crop_children_without_save_leaves_database_unchanged(crop_project):
    _workspace, _config, db_path, requested = crop_project
    before = _annotation_state(db_path)

    result = _invoke(crop_project, "review", "run", "--project", "crops", "--crop-children")

    assert result.exit_code == 0, result.output
    outcomes = [row for row in _rows(result) if row.get("type") == "annotation_review_outcome"]
    assert [row["image_id"] for row in outcomes] == [CHILD_A, CHILD_B, OTHER_CHILD]
    assert all(row["save_status"] is None for row in outcomes)
    assert sorted(set(requested)) == [CHILD_A, CHILD_B, OTHER_CHILD]
    assert _stored_review_ids(db_path) == []
    assert _annotation_state(db_path) == before


def test_parent_without_children_succeeds_with_zero_targets(crop_project):
    _workspace, _config, db_path, requested = crop_project

    result = _invoke(
        crop_project,
        "review",
        "run",
        "--project",
        "crops",
        "--crop-children-of",
        str(LONELY_PARENT),
        "--save-results",
    )

    assert result.exit_code == 0, result.output
    rows = _rows(result)
    assert len(rows) == 1
    assert rows[0]["kind"] == "result" and rows[0]["ok"] is True
    assert rows[0]["message"].startswith("対象 0 件")
    assert rows[0]["image_count"] == 0 and rows[0]["saved"] == 0
    assert requested == [] and _stored_review_ids(db_path) == []


def test_unknown_parent_fails_with_not_found(crop_project):
    _workspace, _config, _db, requested = crop_project

    result = _invoke(crop_project, "review", "run", "--project", "crops", "--crop-children-of", "999")

    assert result.exit_code == 1, result.output
    assert _rows(result)[-1]["code"] == "NOT_FOUND"
    assert requested == []
