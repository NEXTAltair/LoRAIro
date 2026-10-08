"""Manual correction replaces the reviewed row and rejects outdated editors."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from lorairo.database.repository.annotation_record import AnnotationRepository
from lorairo.database.schema import Caption, Image

pytestmark = pytest.mark.unit


@pytest.fixture
def caption_row(db_session_factory):
    with db_session_factory() as session:
        image = Image(
            uuid="caption-edit",
            phash="caption-edit",
            original_image_path="/tmp/c.png",
            stored_image_path="/tmp/c.png",
            width=32,
            height=32,
            format="PNG",
            extension=".png",
        )
        session.add(image)
        session.flush()
        caption = Caption(image_id=image.id, caption="A dog.", existing=True, is_edited_manually=False)
        session.add(caption)
        session.commit()
        return image.id, caption.id


def test_correction_updates_exact_row_and_manual_flag(db_session_factory, caption_row):
    image_id, caption_id = caption_row
    repository = AnnotationRepository(db_session_factory)
    assert repository.edit_caption(image_id, caption_id, "A cat.", expected_text="A dog.")
    with db_session_factory() as session:
        rows = session.scalars(select(Caption).where(Caption.image_id == image_id)).all()
        assert len(rows) == 1
        assert rows[0].id == caption_id
        assert rows[0].caption == "A cat."
        assert rows[0].is_edited_manually is True
        assert rows[0].existing is True


def test_outdated_editor_or_wrong_image_cannot_overwrite(db_session_factory, caption_row):
    image_id, caption_id = caption_row
    repository = AnnotationRepository(db_session_factory)
    assert repository.edit_caption(image_id, caption_id, "A cat.", expected_text="A dog.")
    assert not repository.edit_caption(image_id, caption_id, "A bird.", expected_text="A dog.")
    assert not repository.edit_caption(image_id + 1, caption_id, "A bird.", expected_text="A cat.")
    with db_session_factory() as session:
        row = session.get(Caption, caption_id)
        assert row.caption == "A cat."
        row.rejected_at = datetime.now(UTC)
        session.commit()
    assert not repository.edit_caption(image_id, caption_id, "A bird.", expected_text="A cat.")
    with pytest.raises(ValueError):
        repository.edit_caption(image_id, caption_id, " ", expected_text="A cat.")
