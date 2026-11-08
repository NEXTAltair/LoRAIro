"""`GenerationMetadataRepository.add_ai_generated_tag` の単体テスト (ADR 0107, Issue #1396)。"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import select

from lorairo.database.repository.generation_metadata import GenerationMetadataRepository
from lorairo.database.schema import GENERATION_METADATA_LITELLM_ID, Image, Model, Tag

pytestmark = pytest.mark.unit


@pytest.fixture
def repo(db_session_factory) -> GenerationMetadataRepository:
    return GenerationMetadataRepository(session_factory=db_session_factory)


def _insert_image(db_session_factory) -> int:
    with db_session_factory() as session:
        image = Image(
            uuid="u",
            phash="p",
            original_image_path="/tmp/u.png",
            stored_image_path="/tmp/u.png",
            width=8,
            height=8,
            format="PNG",
            extension=".png",
            filename="u.png",
        )
        session.add(image)
        session.commit()
        image_id: int = image.id
    return image_id


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
