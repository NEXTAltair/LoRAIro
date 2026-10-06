"""Latest per-image annotation review result persistence."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from json import dumps
from pathlib import Path

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from lorairo.database.db_core import create_db_engine
from lorairo.database.repository.annotation_review import AnnotationReviewRepository
from lorairo.database.schema import AnnotationReviewRecord, Base, Caption, Image, Tag

pytestmark = pytest.mark.unit


def _image(image_id: int) -> Image:
    return Image(
        id=image_id,
        uuid=f"image-{image_id}",
        phash=f"hash-{image_id}",
        original_image_path=f"original-{image_id}.png",
        stored_image_path=f"stored-{image_id}.png",
        width=32,
        height=32,
        format="PNG",
        extension=".png",
    )


@pytest.fixture
def review_sessions(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_db_engine(f"sqlite:///{tmp_path / 'review.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        session.add_all([_image(1), _image(2), _image(3)])
        session.commit()
    yield factory
    engine.dispose()


def _save(repository: AnnotationReviewRepository, image_id: int, label: str = "first") -> None:
    repository.save_result(
        image_id=image_id,
        fingerprint=f"fingerprint-{label}",
        model_name="clef-flash",
        warning_threshold=0.2,
        status="complete",
        items_json=dumps(
            [{"candidate_id": "tag_1", "text": label, "probability": 0.1}],
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        error=None,
    )


def test_results_survive_repository_and_connection_reload(review_sessions: sessionmaker[Session]) -> None:
    repository = AnnotationReviewRepository(review_sessions)
    before = datetime.now(UTC)
    _save(repository, 1, "猫")

    # End pooled connections to simulate opening the same project again.
    assert review_sessions.kw["bind"] is not None
    review_sessions.kw["bind"].dispose()
    stored = AnnotationReviewRepository(review_sessions).get_results()[1]

    assert stored.image_id == 1
    assert stored.fingerprint == "fingerprint-猫"
    assert stored.model_name == "clef-flash"
    assert stored.warning_threshold == 0.2
    assert stored.status == "complete"
    assert '"text":"猫"' in stored.items_json
    assert stored.error is None
    assert before <= stored.checked_at <= datetime.now(UTC)
    assert stored.checked_at.tzinfo is UTC
    with pytest.raises(FrozenInstanceError):
        stored.status = "changed"  # type: ignore[misc]


def test_upsert_replaces_all_fields_without_duplicating_image(
    review_sessions: sessionmaker[Session],
) -> None:
    repository = AnnotationReviewRepository(review_sessions)
    repository.save_result(
        image_id=1,
        fingerprint="old",
        model_name="clef",
        warning_threshold=0.1,
        status="failed",
        items_json="[]",
        error="provider_error",
    )
    before = repository.get_results()[1]
    _save(repository, 1, "new")
    stored = repository.get_results()[1]

    assert stored.fingerprint == "fingerprint-new"
    assert stored.model_name == "clef-flash"
    assert stored.warning_threshold == 0.2
    assert stored.status == "complete"
    assert '"text":"new"' in stored.items_json
    assert stored.error is None
    assert stored.checked_at >= before.checked_at
    with review_sessions() as session:
        assert len(session.scalars(select(AnnotationReviewRecord)).all()) == 1


def test_save_preserves_source_annotations_and_manual_review_state(
    review_sessions: sessionmaker[Session],
) -> None:
    with review_sessions() as session:
        session.add(Tag(image_id=1, tag="cat", existing=True, confidence_score=0.8))
        session.add(Caption(image_id=1, caption="A cat.", existing=True))
        session.commit()
        original_image = session.get(Image, 1)
        assert original_image is not None
        original_updated_at = original_image.updated_at
        original_tag = session.scalars(select(Tag)).one()
        original_caption = session.scalars(select(Caption)).one()
        tag_updated_at = original_tag.updated_at
        caption_updated_at = original_caption.updated_at

    repository = AnnotationReviewRepository(review_sessions)
    _save(repository, 1)
    _save(repository, 1, "second")

    with review_sessions() as session:
        image = session.get(Image, 1)
        assert image is not None
        assert image.updated_at == original_updated_at
        assert image.reviewed_at is None
        tag = session.scalars(select(Tag)).one()
        caption = session.scalars(select(Caption)).one()
        assert (tag.tag, tag.confidence_score, tag.updated_at) == ("cat", 0.8, tag_updated_at)
        assert (tag.rejected_at, tag.reject_reason) == (None, None)
        assert (caption.caption, caption.updated_at) == ("A cat.", caption_updated_at)
        assert (caption.rejected_at, caption.reject_reason) == (None, None)


def test_filter_only_returns_requested_images_in_multiple_chunks(
    review_sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = AnnotationReviewRepository(review_sessions)
    for image_id in (1, 2, 3):
        _save(repository, image_id)
    monkeypatch.setattr(AnnotationReviewRepository, "BATCH_CHUNK_SIZE", 2)

    assert set(repository.get_results((3, 1, 3, 99))) == {1, 3}
    assert repository.get_results([99]) == {}
    assert set(repository.get_results()) == {1, 2, 3}


def test_empty_selection_does_not_open_session() -> None:
    def unexpected_session() -> Session:
        pytest.fail("An empty selection must not query all results")

    assert AnnotationReviewRepository(unexpected_session).get_results([]) == {}


def test_history_limit_returns_newest_results_with_deterministic_ties(
    review_sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = AnnotationReviewRepository(review_sessions)
    for image_id in (1, 2, 3):
        _save(repository, image_id)
    with review_sessions() as session:
        session.execute(update(AnnotationReviewRecord).values(checked_at=datetime(2026, 10, 6, tzinfo=UTC)))
        session.execute(
            update(AnnotationReviewRecord)
            .where(AnnotationReviewRecord.image_id == 1)
            .values(checked_at=datetime(2026, 10, 5, tzinfo=UTC))
        )
        session.commit()

    assert list(repository.get_results(limit=2)) == [3, 2]
    assert list(repository.get_results()) == [3, 2, 1]
    # Filtering across chunks applies one global limit, rather than one per chunk.
    monkeypatch.setattr(AnnotationReviewRepository, "BATCH_CHUNK_SIZE", 1)
    assert list(repository.get_results([1, 2, 3], limit=2)) == [3, 2]
    assert list(repository.get_results([1, 3], limit=1)) == [3]


@pytest.mark.parametrize("limit", [0, -1])
def test_history_limit_must_be_positive(review_sessions: sessionmaker[Session], limit: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        AnnotationReviewRepository(review_sessions).get_results(limit=limit)


def test_missing_image_is_rejected_and_existing_result_is_preserved(
    review_sessions: sessionmaker[Session],
) -> None:
    repository = AnnotationReviewRepository(review_sessions)
    _save(repository, 1)

    with pytest.raises(IntegrityError):
        _save(repository, 99)

    assert set(repository.get_results()) == {1}
    _save(repository, 2)
    assert set(repository.get_results()) == {1, 2}


@pytest.mark.parametrize("use_orm", [True, False])
def test_deleting_image_cascades_only_its_result(
    review_sessions: sessionmaker[Session], use_orm: bool
) -> None:
    repository = AnnotationReviewRepository(review_sessions)
    _save(repository, 1)
    _save(repository, 2)

    with review_sessions() as session:
        if use_orm:
            image = session.get(Image, 1)
            assert image is not None
            session.delete(image)
        else:
            session.execute(delete(Image).where(Image.id == 1))
        session.commit()

    assert set(repository.get_results()) == {2}


def test_parallel_saves_keep_one_complete_latest_record(review_sessions: sessionmaker[Session]) -> None:
    repository = AnnotationReviewRepository(review_sessions)
    labels = [f"run-{index}" for index in range(8)]
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(_save, repository, 1, label) for label in labels]
        for future in futures:
            future.result(timeout=30)

    results = repository.get_results()
    assert set(results) == {1}
    stored = results[1]
    label = stored.fingerprint.removeprefix("fingerprint-")
    assert label in labels
    assert f'"text":"{label}"' in stored.items_json


def test_results_are_isolated_between_project_databases(
    review_sessions: sessionmaker[Session], tmp_path: Path
) -> None:
    other_engine = create_db_engine(f"sqlite:///{tmp_path / 'other-project.db'}")
    try:
        Base.metadata.create_all(other_engine)
        other_factory = sessionmaker(bind=other_engine)
        with other_factory() as session:
            session.add(_image(1))
            session.commit()
        original = AnnotationReviewRepository(review_sessions)
        other = AnnotationReviewRepository(other_factory)
        _save(original, 1, "original-project")
        assert other.get_results() == {}
        _save(other, 1, "other-project")

        assert original.get_results()[1].fingerprint == "fingerprint-original-project"
        assert other.get_results()[1].fingerprint == "fingerprint-other-project"
    finally:
        other_engine.dispose()
