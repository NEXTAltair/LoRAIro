"""`GenerationMetadataRepository.add_ai_generated_tag` の単体テスト (ADR 0107, Issue #1396)。"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import select

from lorairo.database.repository.generation_metadata import GenerationMetadataRepository
from lorairo.database.schema import (
    GENERATION_METADATA_LITELLM_ID,
    GenerationMetadata,
    Image,
    Model,
    Tag,
)
from lorairo.domain.generation_metadata import AiGeneratedTagBatchResult

pytestmark = pytest.mark.unit


@pytest.fixture
def repo(db_session_factory) -> GenerationMetadataRepository:
    return GenerationMetadataRepository(session_factory=db_session_factory)


def _insert_image(db_session_factory, name: str = "u") -> int:
    with db_session_factory() as session:
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


def _insert_metadata(db_session_factory, image_id: int, *, status: str, tool: str | None = None) -> None:
    with db_session_factory() as session:
        session.add(
            GenerationMetadata(
                image_id=image_id,
                status=status,
                tool=tool,
                parser_name="test",
                parser_version="1",
            )
        )
        session.commit()


def _tags(db_session_factory, image_id: int) -> list[tuple[str, str | None]]:
    with db_session_factory() as session:
        rows = session.execute(
            select(Tag.tag, Model.litellm_model_id)
            .outerjoin(Model, Model.id == Tag.model_id)
            .where(Tag.image_id == image_id)
            .order_by(Tag.id)
        ).all()
        return [(row[0], row[1]) for row in rows]


def test_adds_tag_under_pseudo_model_once(repo, db_session_factory) -> None:
    image_id = _insert_image(db_session_factory)

    assert repo.add_ai_generated_tag(image_id) is True
    assert repo.add_ai_generated_tag(image_id) is False

    assert _tags(db_session_factory, image_id) == [("ai generated", GENERATION_METADATA_LITELLM_ID)]
    with db_session_factory() as session:
        model = session.scalars(
            select(Model).where(Model.litellm_model_id == GENERATION_METADATA_LITELLM_ID)
        ).one()
        assert model.name == "GENERATION_METADATA"
        assert model.requires_api_key is False
        assert model.model_types == []
        tag = session.scalars(select(Tag)).one()
        assert (tag.existing, tag.is_edited_manually, tag.tag_id) == (False, False, None)


@pytest.mark.parametrize(
    "existing_tag", ["ai generated", "ai_generated", "AI Generated", " ai  generated "]
)
def test_existing_same_tag_from_other_source_is_kept(repo, db_session_factory, existing_tag: str) -> None:
    image_id = _insert_image(db_session_factory)
    with db_session_factory() as session:
        session.add(Tag(image_id=image_id, model_id=None, tag=existing_tag, existing=True))
        session.commit()

    assert repo.add_ai_generated_tag(image_id) is False
    assert _tags(db_session_factory, image_id) == [(existing_tag, None)]


def test_soft_rejected_tag_blocks_readding(repo, db_session_factory) -> None:
    image_id = _insert_image(db_session_factory)
    repo.add_ai_generated_tag(image_id)
    with db_session_factory() as session:
        tag = session.scalars(select(Tag)).one()
        tag.rejected_at = datetime.datetime(2026, 1, 1)
        session.commit()

    assert repo.add_ai_generated_tag(image_id) is False
    assert len(_tags(db_session_factory, image_id)) == 1


def test_similar_but_different_tag_does_not_block(repo, db_session_factory) -> None:
    image_id = _insert_image(db_session_factory)
    with db_session_factory() as session:
        session.add(Tag(image_id=image_id, model_id=None, tag="ai-generated art", existing=True))
        session.commit()

    assert repo.add_ai_generated_tag(image_id) is True


def test_batch_apply_follows_evidence_and_dedup_rules(repo, db_session_factory) -> None:
    webui_parsed = _insert_image(db_session_factory, "webui_parsed")
    comfy_unsupported = _insert_image(db_session_factory, "comfy_unsupported")
    already_tagged = _insert_image(db_session_factory, "already_tagged")
    soft_rejected = _insert_image(db_session_factory, "soft_rejected")
    no_metadata = _insert_image(db_session_factory, "no_metadata")
    unsupported_no_tool = _insert_image(db_session_factory, "unsupported_no_tool")
    failed = _insert_image(db_session_factory, "failed")
    unanalyzed = _insert_image(db_session_factory, "unanalyzed")

    _insert_metadata(db_session_factory, webui_parsed, status="parsed", tool="sd_webui")
    _insert_metadata(db_session_factory, comfy_unsupported, status="unsupported", tool="comfyui")
    _insert_metadata(db_session_factory, already_tagged, status="partial", tool="sd_webui")
    _insert_metadata(db_session_factory, soft_rejected, status="parsed", tool="comfyui")
    _insert_metadata(db_session_factory, no_metadata, status="no_metadata", tool=None)
    _insert_metadata(db_session_factory, unsupported_no_tool, status="unsupported", tool=None)
    _insert_metadata(db_session_factory, failed, status="failed", tool=None)

    with db_session_factory() as session:
        session.add(Tag(image_id=already_tagged, model_id=None, tag="AI_Generated", existing=True))
        session.add(
            Tag(
                image_id=soft_rejected,
                model_id=None,
                tag="ai generated",
                existing=False,
                rejected_at=datetime.datetime(2026, 1, 1),
            )
        )
        session.commit()

    dry = repo.apply_ai_generated_tags_batch(dry_run=True)
    assert dry == AiGeneratedTagBatchResult(
        target_images=8,
        evidence_images=4,
        tags_added=2,
        tags_skipped=2,
        tags_revoked=0,
        dry_run=True,
        revoked=False,
    )
    with db_session_factory() as session:
        assert (
            session.scalars(
                select(Model).where(Model.litellm_model_id == GENERATION_METADATA_LITELLM_ID)
            ).one_or_none()
            is None
        )
    assert _tags(db_session_factory, webui_parsed) == []

    applied = repo.apply_ai_generated_tags_batch()
    assert applied == AiGeneratedTagBatchResult(
        target_images=8,
        evidence_images=4,
        tags_added=2,
        tags_skipped=2,
        tags_revoked=0,
        dry_run=False,
        revoked=False,
    )
    assert _tags(db_session_factory, webui_parsed) == [("ai generated", GENERATION_METADATA_LITELLM_ID)]
    assert _tags(db_session_factory, comfy_unsupported) == [
        ("ai generated", GENERATION_METADATA_LITELLM_ID)
    ]
    assert _tags(db_session_factory, already_tagged) == [("AI_Generated", None)]
    assert _tags(db_session_factory, no_metadata) == []
    assert _tags(db_session_factory, unsupported_no_tool) == []
    assert _tags(db_session_factory, failed) == []
    assert _tags(db_session_factory, unanalyzed) == []

    # 2 回目は全件 skip で冪等
    second = repo.apply_ai_generated_tags_batch()
    assert second.tags_added == 0
    assert second.tags_skipped == 4


def test_batch_apply_and_revoke_respect_image_ids_and_keep_other_sources(repo, db_session_factory) -> None:
    first = _insert_image(db_session_factory, "first")
    second = _insert_image(db_session_factory, "second")
    _insert_metadata(db_session_factory, first, status="parsed", tool="sd_webui")
    _insert_metadata(db_session_factory, second, status="parsed", tool="sd_webui")
    with db_session_factory() as session:
        session.add(Tag(image_id=first, model_id=None, tag="1girl", existing=True))
        session.commit()

    # モデル行が無い状態で revoke してもモデル行を作らず 0 件で終わる
    assert repo.revoke_ai_generated_tags_batch() == AiGeneratedTagBatchResult(
        target_images=2,
        evidence_images=0,
        tags_added=0,
        tags_skipped=0,
        tags_revoked=0,
        dry_run=False,
        revoked=True,
    )

    # image_ids で対象を絞って付与
    scoped = repo.apply_ai_generated_tags_batch([first])
    assert scoped.target_images == 1
    assert scoped.tags_added == 1
    assert _tags(db_session_factory, first) == [
        ("1girl", None),
        ("ai generated", GENERATION_METADATA_LITELLM_ID),
    ]
    assert _tags(db_session_factory, second) == []

    repo.apply_ai_generated_tags_batch([second])
    # dry-run revoke は消さない
    dry_revoke = repo.revoke_ai_generated_tags_batch([first], dry_run=True)
    assert dry_revoke == AiGeneratedTagBatchResult(
        target_images=1,
        evidence_images=0,
        tags_added=0,
        tags_skipped=0,
        tags_revoked=1,
        dry_run=True,
        revoked=True,
    )
    assert len(_tags(db_session_factory, first)) == 2

    # first だけ revoke すると GENERATION_METADATA の行だけ消え、既存の 1girl と second は残る
    revoked = repo.revoke_ai_generated_tags_batch([first])
    assert revoked.tags_revoked == 1
    assert _tags(db_session_factory, first) == [("1girl", None)]
    assert _tags(db_session_factory, second) == [("ai generated", GENERATION_METADATA_LITELLM_ID)]
