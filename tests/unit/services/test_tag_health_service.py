"""Tag health counts and bounded suggestions against isolated SQLite fixtures."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from lorairo.database.schema import Base, Image, Tag
from lorairo.public_api.exceptions import InvalidInputError
from lorairo.services.tag_health_service import TagHealthService, validate_health_options

pytestmark = pytest.mark.unit


def _image(image_id):
    return Image(
        id=image_id,
        uuid=f"synthetic-{image_id}",
        phash=f"synthetic-{image_id}",
        original_image_path=f"{image_id}.png",
        stored_image_path=f"{image_id}.png",
        width=32,
        height=32,
        format="PNG",
        extension=".png",
    )


@pytest.fixture
def database():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    yield factory
    engine.dispose()


def test_frequency_deduplicates_models_excludes_rejected_and_includes_zero_tags(database):
    with database() as session:
        session.add_all([_image(i) for i in range(1, 5)])
        session.add_all(
            [
                Tag(image_id=1, tag="cat", model_id=10),
                Tag(image_id=1, tag="cat", model_id=11),
                Tag(image_id=1, tag="blue_hair"),
                Tag(image_id=1, tag="blue hair"),
                Tag(image_id=2, tag="cat"),
                Tag(image_id=2, tag="blue hair"),
                Tag(image_id=3, tag="cat", rejected_at=datetime.now(UTC)),
                Tag(image_id=3, tag="  "),
            ]
        )
        session.commit()
    report = TagHealthService(database).report(["Blue Hair", "cat", "BLUE_HAIR", "dog"])
    assert (report.total_images, report.tagged_images, report.untagged_images) == (4, 2, 2)
    assert {item.tag: item.image_count for item in report.frequencies} == {
        "cat": 2,
        "blue hair": 2,
        "blue_hair": 1,
    }
    assert report.expected_tag_count == 3
    assert [
        (item.expected_tag, item.missing_count, item.image_ids) for item in report.missing_expected
    ] == [
        ("Blue Hair", 2, [3, 4]),
        ("cat", 2, [3, 4]),
        ("dog", 4, [1, 2, 3, 4]),
    ]
    assert any(
        item.reason == "normalization" and item.tag == "blue_hair" and item.candidate == "blue hair"
        for item in report.variants
    )


def test_limits_cap_only_records_and_samples_not_counts(database):
    with database() as session:
        session.add_all([_image(i) for i in range(1, 5)])
        session.add_all([Tag(image_id=1, tag="Cat"), Tag(image_id=2, tag="Dog")])
        session.commit()
    report = TagHealthService(database).report(["cat", "dog", "bird"], limit=1)
    assert report.total_images == 4 and report.unique_tags == report.frequency_count == 2
    assert report.variant_count == 2 and report.missing_expected_count == 3
    assert report.frequencies_truncated and report.variants_truncated and report.missing_expected_truncated
    assert len(report.frequencies) == len(report.variants) == len(report.missing_expected) == 1
    assert report.missing_expected[0].missing_count == 3
    assert report.missing_expected[0].image_ids == [2]
    assert report.missing_expected[0].image_ids_truncated


def test_expected_tags_never_invented_and_empty_project_is_valid(database):
    report = TagHealthService(database).report()
    assert report.total_images == report.unique_tags == report.expected_tag_count == 0
    assert report.frequencies == report.variants == report.missing_expected == []
    report = TagHealthService(database).report(["cat"])
    assert report.expected_tag_count == 1 and report.missing_expected_count == 0
    with database() as session:
        session.add(_image(1))
        session.add(Tag(image_id=1, tag="cat"))
        session.commit()
    assert TagHealthService(database).report().missing_expected == []


def test_spelling_suggestions_reference_observed_tags_are_deterministic(database):
    with database() as session:
        session.add_all([_image(1), _image(2)])
        session.add_all(
            [
                Tag(image_id=1, tag="blue hair"),
                Tag(image_id=2, tag="blue hair"),
                Tag(image_id=2, tag="blue hait"),
                Tag(image_id=1, tag="cats"),
                Tag(image_id=2, tag="cat"),
            ]
        )
        session.commit()
    first = TagHealthService(database).report()
    second = TagHealthService(database).report()
    assert first == second
    spelling = [item for item in first.variants if item.reason == "spelling"]
    assert len(spelling) == 1
    assert (spelling[0].tag, spelling[0].candidate, spelling[0].similarity) == (
        "blue hait",
        "blue hair",
        0.8889,
    )


def test_spelling_pool_and_length_caps_are_explicit_without_losing_counts(database):
    with database() as session:
        session.add(_image(1))
        session.add_all([Tag(image_id=1, tag=f"tag {i:04}") for i in range(501)])
        session.add(Tag(image_id=1, tag="x" * 129))
        session.commit()
    report = TagHealthService(database).report(["x" * 129], limit=2)
    assert report.unique_tags == report.frequency_count == 502
    assert report.spelling_candidates_truncated and report.frequencies_truncated
    assert report.spelling_vocabulary_limit == 500 and report.spelling_max_tag_length == 128
    assert report.missing_expected_count == 0


@pytest.mark.parametrize("limit", [0, 501, True, 1.5])
def test_invalid_limits_are_rejected(limit):
    with pytest.raises(InvalidInputError):
        validate_health_options([], limit)


@pytest.mark.parametrize("expected", ["cat", [""], ["   "], [None], ["#"], [str(i) for i in range(501)]])
def test_invalid_expected_tags_are_rejected(expected):
    with pytest.raises(InvalidInputError):
        validate_health_options(expected, 100)
