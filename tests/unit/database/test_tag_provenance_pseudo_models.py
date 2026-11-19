"""タグの出所を擬似モデルで持つ (ADR 0111) 書き込み経路・読み取り経路のテスト。

model_id NULL の行を作らず、手入力は MANUAL_EDIT、関連ファイル (.txt) 取り込みは
SIDECAR_IMPORT、画像処理の自動タグは IMAGE_PROCESSING の model_id で保存することと、
AI 判定 (changed-since・最近使ったモデル・出所表示) が擬似モデルを AI と扱わないことを確認する。
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from lorairo.database.repository.annotation_record import AnnotationRepository
from lorairo.database.repository.image import ImageRepository
from lorairo.database.repository.model import ModelRepository
from lorairo.database.schema import (
    GENERATION_METADATA_LITELLM_ID,
    IMAGE_PROCESSING_LITELLM_ID,
    KOHYA_DATASET_LITELLM_ID,
    MANUAL_EDIT_LITELLM_ID,
    PSEUDO_MODEL_LITELLM_IDS,
    REJECT_REASON_INCORRECT,
    SIDECAR_IMPORT_LITELLM_ID,
    Image,
    Model,
    Tag,
)

pytestmark = pytest.mark.unit


def _insert_image(session_factory: Any, name: str) -> int:
    with session_factory() as session:
        image = Image(
            uuid=name,
            phash=f"p-{name}",
            original_image_path=f"/tmp/{name}.png",
            stored_image_path=f"/tmp/{name}.png",
            width=8,
            height=8,
            format="PNG",
            extension=".png",
            filename=f"{name}.png",
        )
        session.add(image)
        session.commit()
        image_id: int = image.id
    return image_id


def _tag_rows(session_factory: Any, image_id: int) -> list[tuple[str, str | None, bool]]:
    """(tag, litellm_model_id, 採用中か) の一覧を id 順で返す。"""
    with session_factory() as session:
        rows = session.execute(
            select(Tag.tag, Model.litellm_model_id, Tag.rejected_at)
            .outerjoin(Model, Model.id == Tag.model_id)
            .where(Tag.image_id == image_id)
            .order_by(Tag.id)
        ).all()
    return [(row[0], row[1], row[2] is None) for row in rows]


def _pseudo_model_id(session_factory: Any, litellm_id: str) -> int | None:
    with session_factory() as session:
        return session.execute(
            select(Model.id).where(Model.litellm_model_id == litellm_id)
        ).scalar_one_or_none()


def test_pseudo_model_set_covers_all_sentinels() -> None:
    assert {
        MANUAL_EDIT_LITELLM_ID,
        KOHYA_DATASET_LITELLM_ID,
        GENERATION_METADATA_LITELLM_ID,
        SIDECAR_IMPORT_LITELLM_ID,
        IMAGE_PROCESSING_LITELLM_ID,
    } == PSEUDO_MODEL_LITELLM_IDS


@pytest.mark.parametrize(
    ("factory", "litellm_id", "name"),
    [
        (ModelRepository.get_or_create_sidecar_import_model, SIDECAR_IMPORT_LITELLM_ID, "SIDECAR_IMPORT"),
        (
            ModelRepository.get_or_create_image_processing_model,
            IMAGE_PROCESSING_LITELLM_ID,
            "IMAGE_PROCESSING",
        ),
    ],
)
def test_new_pseudo_models_are_created_once_without_model_types(
    db_session_factory: Any, factory: Any, litellm_id: str, name: str
) -> None:
    with db_session_factory() as session:
        first = factory(session)
        second = factory(session)
        session.commit()
    assert first == second
    with db_session_factory() as session:
        model = session.scalars(select(Model).where(Model.litellm_model_id == litellm_id)).one()
        assert model.name == name
        assert model.provider == "user"
        assert model.requires_api_key is False
        assert model.model_types == []


# --- 書き込み経路: 手入力 (CLI images / tags add・preview、置換) は MANUAL_EDIT ---


class TestManualTagWrites:
    @pytest.fixture
    def repo(self, db_session_factory: Any, monkeypatch: pytest.MonkeyPatch) -> AnnotationRepository:
        repository = AnnotationRepository(db_session_factory)
        # 外部タグ DB には触れない (tag_id は空で保存)
        monkeypatch.setattr(repository, "_get_or_create_tag_id_external", lambda _session, _tag: None)
        return repository

    def test_add_without_model_id_writes_manual_edit(self, repo, db_session_factory) -> None:
        image_id = _insert_image(db_session_factory, "add")

        ok, added = repo.add_tag_to_images_batch([image_id], "cat", None, resolved=("cat", None))

        assert (ok, added) == (True, 1)
        assert _tag_rows(db_session_factory, image_id) == [("cat", MANUAL_EDIT_LITELLM_ID, True)]

    def test_add_revives_soft_rejected_manual_edit_row(self, repo, db_session_factory) -> None:
        image_id = _insert_image(db_session_factory, "revive")
        repo.add_tag_to_images_batch([image_id], "cat", None, resolved=("cat", None))
        repo.remove_tag_from_images_batch([image_id], "cat", reason=REJECT_REASON_INCORRECT)
        assert _tag_rows(db_session_factory, image_id) == [("cat", MANUAL_EDIT_LITELLM_ID, False)]

        assert repo.preview_add_tag_to_images_batch([image_id], "cat") == 1
        ok, added = repo.add_tag_to_images_batch([image_id], "cat", None, resolved=("cat", None))

        assert (ok, added) == (True, 1)
        # 新しい行を作らず (UNIQUE 違反にもならず) 同じ MANUAL_EDIT 行を復活させる
        assert _tag_rows(db_session_factory, image_id) == [("cat", MANUAL_EDIT_LITELLM_ID, True)]

    def test_preview_does_not_create_manual_edit_model(self, repo, db_session_factory) -> None:
        image_id = _insert_image(db_session_factory, "preview")

        assert repo.preview_add_tag_to_images_batch([image_id], "cat") == 1

        assert _pseudo_model_id(db_session_factory, MANUAL_EDIT_LITELLM_ID) is None

    def test_replace_writes_target_as_manual_edit(self, repo, db_session_factory) -> None:
        image_id = _insert_image(db_session_factory, "replace")
        repo.add_tag_to_images_batch([image_id], "dog", None, resolved=("dog", None))

        ok, per_item = repo.replace_tag_for_images_batch([image_id], "dog", "cat")

        assert ok is True
        assert per_item == [(image_id, "changed")]
        assert _tag_rows(db_session_factory, image_id) == [
            ("dog", MANUAL_EDIT_LITELLM_ID, False),
            ("cat", MANUAL_EDIT_LITELLM_ID, True),
        ]

    def test_replace_revives_soft_rejected_manual_target(self, repo, db_session_factory) -> None:
        image_id = _insert_image(db_session_factory, "replace-revive")
        repo.add_tag_to_images_batch([image_id], "cat", None, resolved=("cat", None))
        repo.remove_tag_from_images_batch([image_id], "cat")
        repo.add_tag_to_images_batch([image_id], "dog", None, resolved=("dog", None))

        ok, _ = repo.replace_tag_for_images_batch([image_id], "dog", "cat")

        assert ok is True
        assert _tag_rows(db_session_factory, image_id) == [
            ("cat", MANUAL_EDIT_LITELLM_ID, True),
            ("dog", MANUAL_EDIT_LITELLM_ID, False),
        ]


# --- 書き込み経路: 関連ファイル (.txt) 取り込みは SIDECAR_IMPORT ---


def test_sidecar_import_writes_sidecar_import_model(test_db_manager: Any, monkeypatch) -> None:
    annotation_repo = test_db_manager.annotation_repo
    monkeypatch.setattr(annotation_repo, "_resolve_danbooru_canonical", lambda _tags: {})
    monkeypatch.setattr(annotation_repo, "_get_or_create_tag_id_external", lambda _session, _tag: None)
    session_factory = annotation_repo.session_factory
    image_id = _insert_image(session_factory, "sidecar")

    test_db_manager._import_associated_files(
        Path("/tmp/sidecar.png"), image_id, annotations={"tags": ["cat", "dog"], "captions": []}
    )
    # 再取り込みは同じ行を更新し、重複行を作らない
    test_db_manager._import_associated_files(
        Path("/tmp/sidecar.png"), image_id, annotations={"tags": ["cat"], "captions": []}
    )

    assert _tag_rows(session_factory, image_id) == [
        ("cat", SIDECAR_IMPORT_LITELLM_ID, True),
        ("dog", SIDECAR_IMPORT_LITELLM_ID, True),
    ]


# --- 読み取り: 擬似モデルを AI と扱わない ---


def _add_tag(
    session_factory: Any,
    image_id: int,
    tag: str,
    litellm_id: str,
    *,
    existing: bool,
    is_edited_manually: bool,
) -> None:
    with session_factory() as session:
        model_id = session.execute(
            select(Model.id).where(Model.litellm_model_id == litellm_id)
        ).scalar_one_or_none()
        if model_id is None:
            model = Model(name=litellm_id, provider="user", litellm_model_id=litellm_id)
            session.add(model)
            session.flush()
            model_id = model.id
        session.add(
            Tag(
                image_id=image_id,
                model_id=model_id,
                tag=tag,
                existing=existing,
                is_edited_manually=is_edited_manually,
            )
        )
        session.commit()


def test_changed_since_ignores_pseudo_model_rows(db_session_factory: Any) -> None:
    repo = ImageRepository(session_factory=db_session_factory)
    since = datetime.datetime(2000, 1, 1, tzinfo=datetime.UTC)
    ai_image = _insert_image(db_session_factory, "ai")
    sidecar_image = _insert_image(db_session_factory, "sc")
    processing_image = _insert_image(db_session_factory, "up")
    generation_image = _insert_image(db_session_factory, "gm")
    manual_image = _insert_image(db_session_factory, "man")
    _add_tag(db_session_factory, ai_image, "cat", "openai/gpt-4o", existing=False, is_edited_manually=False)
    _add_tag(
        db_session_factory,
        sidecar_image,
        "cat",
        SIDECAR_IMPORT_LITELLM_ID,
        existing=True,
        is_edited_manually=False,
    )
    _add_tag(
        db_session_factory,
        processing_image,
        "upscaled",
        IMAGE_PROCESSING_LITELLM_ID,
        existing=False,
        is_edited_manually=False,
    )
    _add_tag(
        db_session_factory,
        generation_image,
        "ai generated",
        GENERATION_METADATA_LITELLM_ID,
        existing=False,
        is_edited_manually=False,
    )
    _add_tag(
        db_session_factory,
        manual_image,
        "cat",
        MANUAL_EDIT_LITELLM_ID,
        existing=False,
        is_edited_manually=True,
    )

    changed = repo.filter_image_ids_with_tag_changes_since(
        [ai_image, sidecar_image, processing_image, generation_image, manual_image], since
    )

    # AI 実行と手動編集だけが「変更」。擬似モデルの自動付与・取り込みは AI 扱いしない
    assert sorted(changed) == sorted([ai_image, manual_image])


def test_recently_used_models_exclude_pseudo_models(db_session_factory: Any) -> None:
    repo = ImageRepository(session_factory=db_session_factory)
    image_id = _insert_image(db_session_factory, "recent")
    _add_tag(db_session_factory, image_id, "cat", "openai/gpt-4o", existing=False, is_edited_manually=False)
    for litellm_id in sorted(PSEUDO_MODEL_LITELLM_IDS):
        _add_tag(
            db_session_factory,
            image_id,
            f"t-{litellm_id}",
            litellm_id,
            existing=True,
            is_edited_manually=True,
        )

    result = repo.get_recently_used_model_ids()

    assert "openai/gpt-4o" in result
    assert not set(result) & PSEUDO_MODEL_LITELLM_IDS


def test_tag_source_label_distinguishes_pseudo_models(db_session_factory: Any) -> None:
    repo = ImageRepository(session_factory=db_session_factory)
    image_id = _insert_image(db_session_factory, "source")
    _add_tag(db_session_factory, image_id, "a", "openai/gpt-4o", existing=False, is_edited_manually=False)
    _add_tag(
        db_session_factory,
        image_id,
        "b",
        SIDECAR_IMPORT_LITELLM_ID,
        existing=True,
        is_edited_manually=False,
    )
    _add_tag(
        db_session_factory,
        image_id,
        "upscaled",
        IMAGE_PROCESSING_LITELLM_ID,
        existing=False,
        is_edited_manually=False,
    )
    _add_tag(
        db_session_factory, image_id, "c", MANUAL_EDIT_LITELLM_ID, existing=False, is_edited_manually=True
    )

    with db_session_factory() as session:
        image = session.get(Image, image_id)
        annotations: dict[str, Any] = {}
        repo._format_tags(image, annotations)

    sources = {row["tag"]: row["source"] for row in annotations["tags"]}
    assert sources == {"a": "AI", "b": "Import", "upscaled": "Processing", "c": "Manual"}
