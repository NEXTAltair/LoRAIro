"""Bounded ID intersection and processed-selection equivalence (#1307)."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from lorairo.database.filter_criteria import ImageFilterCriteria
from lorairo.database.repository.image import ImageRepository
from lorairo.database.schema import Base, Image, ProcessedImage, Rating


@pytest.fixture
def candidate_repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    with factory() as session:
        session.add_all(
            Image(
                id=i,
                uuid=str(i),
                phash=str(i),
                original_image_path=f"input/{i}.png",
                stored_image_path=f"stored/{i}.png",
                width=512,
                height=512,
                format="PNG",
                extension="png",
                filename=f"{i}.png",
            )
            for i in range(1, 1002)
        )
        session.add(Rating(image_id=2, model_id=1, raw_rating_value="PG", normalized_rating="PG"))
        session.add_all(
            ProcessedImage(
                image_id=1,
                stored_image_path=f"processed/{size}.png",
                width=size,
                height=size,
                has_alpha=False,
                filename=f"{size}.png",
            )
            for size in [128, 496, 512]
        )
        session.commit()
    yield ImageRepository(session_factory=factory)
    engine.dispose()


@pytest.mark.parametrize("count", [0, 1, 500, 501])
def test_candidate_selection_cap_and_no_metadata(candidate_repo, monkeypatch, count):
    def forbidden(*args, **kwargs):
        raise AssertionError("ID-only selection must not load metadata")

    monkeypatch.setattr(candidate_repo, "_fetch_filtered_metadata", forbidden)
    monkeypatch.setattr(candidate_repo, "get_images_by_ids", forbidden)
    ids = list(range(1, count + 1))
    if count > 500:
        with pytest.raises(ValueError, match="500"):
            candidate_repo.get_candidate_image_ids(ids)
    else:
        assert sorted(candidate_repo.get_candidate_image_ids(ids)) == ids


def test_unrated_intersection_never_expands_to_other_project_images(candidate_repo):
    criteria = ImageFilterCriteria(only_unrated=True, include_nsfw=True)
    assert candidate_repo.get_candidate_image_ids([1, 2], criteria) == [1]
    assert candidate_repo.get_candidate_image_ids([9999], criteria) == []
    assert candidate_repo.get_candidate_image_ids([], criteria) == []


@pytest.mark.parametrize("resolution", [0, 128, 496, 500, 512, 2000])
def test_bulk_processed_selection_matches_existing_individual_contract(candidate_repo, resolution):
    old = candidate_repo.get_processed_image(1, resolution=resolution)
    bulk = candidate_repo.get_processed_image_paths_by_resolution([1, 2], resolution)
    assert bulk == ({1: old["stored_image_path"]} if old else {})
