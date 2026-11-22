"""Complete, deterministic clusters over synthetic saved hashes only."""

from unittest.mock import Mock

import imagehash
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from lorairo.database.schema import Base, Image
from lorairo.public_api.exceptions import InvalidInputError, ResultSetTooLargeError
from lorairo.services.duplicate_report_service import (
    DuplicateReportService,
    SavedImageHash,
    analyze_saved_hashes,
)

pytestmark = pytest.mark.unit


def saved(image_id, phash):
    return SavedImageHash(image_id, phash, f"stored/{image_id}.png", f"original/{image_id}.png")


def test_connected_chain_can_exceed_threshold_at_endpoints():
    images = [saved(3, "0000000000000003"), saved(1, "0000000000000000"), saved(2, "0000000000000001")]
    report = analyze_saved_hashes(images, max_distance=1)
    assert report.cluster_count == 1
    cluster = report.clusters[0]
    assert cluster.cluster_id == 1
    assert cluster.member_count == 3
    assert [member.image_id for member in cluster.members] == [1, 2, 3]
    assert report.compared_hash_pairs == 3
    assert imagehash.hex_to_hash(images[0].phash) - imagehash.hex_to_hash(images[1].phash) == 2
    assert analyze_saved_hashes(list(reversed(images)), max_distance=1) == report


@pytest.mark.parametrize("distance", [0, 1, 4, 32, 63, 64])
@pytest.mark.parametrize(
    "left,right", [("0000000000000000", "ffffffffffffffff"), ("0123456789abcdef", "0123456789abcdea")]
)
def test_threshold_agrees_with_existing_imagehash_distance(distance, left, right):
    report = analyze_saved_hashes([saved(1, left), saved(2, right)], max_distance=distance)
    expected = imagehash.hex_to_hash(left) - imagehash.hex_to_hash(right) <= distance
    assert report.cluster_count == int(expected)
    assert report.clustered_images == (2 if expected else 0)
    assert report.unclustered_images == (0 if expected else 2)


def test_exact_groups_use_normalized_saved_hex_and_no_pair_scan():
    report = analyze_saved_hashes(
        [saved(7, "FFFFFFFFFFFFFFFF"), saved(2, " ffffffffffffffff "), saved(3, "0000000000000000")],
        max_distance=0,
    )
    assert report.cluster_count == 1
    assert report.clusters[0].cluster_id == 2
    assert [member.image_id for member in report.clusters[0].members] == [2, 7]
    assert all(member.phash == "ffffffffffffffff" for member in report.clusters[0].members)
    assert report.unique_phashes == 2
    assert report.compared_hash_pairs == 0


def test_missing_invalid_and_all_valid_at_distance_64_are_explicit():
    hashes = [None, "", " \t", "short", "z" * 16, "+000000000000000", "0" * 17, "0" * 16, "f" * 16]
    report = analyze_saved_hashes(
        [saved(index, value) for index, value in enumerate(hashes, 1)], max_distance=64
    )
    assert report.total_images == 9
    assert report.missing_phash_images == 3
    assert report.invalid_phash_images == 4
    assert report.valid_phash_images == 2
    assert report.clustered_images == 2 and report.unclustered_images == 0
    assert [member.image_id for member in report.clusters[0].members] == [8, 9]
    assert report.compared_hash_pairs == 0
    assert report.summary()["candidate_only"] is True


@pytest.mark.parametrize("images", [[], [saved(1, "bad")], [saved(1, "0000000000000001")]])
def test_empty_unusable_or_single_image_has_no_cluster(images):
    report = analyze_saved_hashes(images)
    assert report.total_images == len(images)
    assert report.clusters == []
    assert report.cluster_count == report.clustered_images == 0


def test_limit_caps_cluster_and_member_output_but_not_detection():
    images = [saved(index, value) for index, value in enumerate(["0" * 16] * 3 + ["f" * 16] * 2, 1)]
    report = analyze_saved_hashes(images, max_distance=0, limit=1)
    assert report.cluster_count == 2 and report.clustered_images == 5
    assert report.returned_clusters == 1 and report.clusters_truncated
    assert report.clusters[0].member_count == 3 and report.clusters[0].members_truncated
    assert [member.image_id for member in report.clusters[0].members] == [1]
    assert report.total_images == report.valid_phash_images == 5


@pytest.mark.parametrize(
    "distance,limit", [(-1, 1), (65, 1), (True, 1), (1.0, 1), (4, 0), (4, 501), (4, True)]
)
def test_invalid_options_fail_before_opening_database(distance, limit):
    factory = Mock(side_effect=AssertionError("must not open DB"))
    with pytest.raises(InvalidInputError):
        DuplicateReportService(factory).report(max_distance=distance, limit=limit)
    factory.assert_not_called()


def test_project_cap_rejects_before_loading_hashes_or_comparing(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    with factory() as session:
        session.add_all(
            Image(
                id=index,
                uuid=f"synthetic-{index}",
                phash=f"{index:016x}",
                original_image_path="never-open.png",
                stored_image_path="never-open.png",
                width=1,
                height=1,
                format="PNG",
                extension=".png",
            )
            for index in range(1, 4)
        )
        session.commit()
    monkeypatch.setattr("lorairo.services.duplicate_report_service.MAX_PROJECT_IMAGES", 2)
    compare = Mock(side_effect=AssertionError("comparisons forbidden"))
    monkeypatch.setattr("lorairo.services.duplicate_report_service._connected_components", compare)
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        with pytest.raises(ResultSetTooLargeError) as caught:
            DuplicateReportService(factory).report(limit=1)
        assert caught.value.details == {"limit": 2, "matched": 3}
        assert "--limit controls output only" in str(caught.value)
        assert len(statements) == 1 and "count(" in statements[0].lower()
        compare.assert_not_called()
    finally:
        engine.dispose()


def test_project_growth_after_count_is_rejected_before_comparing(monkeypatch):
    monkeypatch.setattr("lorairo.services.duplicate_report_service.MAX_PROJECT_IMAGES", 2)
    session = Mock()
    session.execute.side_effect = [
        Mock(scalar_one=Mock(return_value=2)),
        Mock(all=Mock(return_value=[(), (), ()])),
    ]
    factory = Mock()
    factory.return_value.__enter__ = Mock(return_value=session)
    factory.return_value.__exit__ = Mock(return_value=False)
    with pytest.raises(ResultSetTooLargeError) as caught:
        DuplicateReportService(factory).report()
    assert caught.value.matched == 3


# ---- 代表画像の決定 (#1604) ----


def sized(image_id, phash, width, height):
    return SavedImageHash(
        image_id, phash, f"stored/{image_id}.png", f"original/{image_id}.png", width=width, height=height
    )


def test_representative_is_largest_pixel_count_with_smallest_id_on_tie():
    images = [
        sized(1, "0000000000000000", 100, 100),  # 10,000 px
        sized(2, "0000000000000000", 200, 100),  # 20,000 px (最大, 同点)
        sized(3, "0000000000000000", 100, 200),  # 20,000 px (同点, id が大きい)
        sized(4, "0000000000000000", 50, 50),
    ]
    report = analyze_saved_hashes(images, max_distance=0)
    assert [(r.image_id, r.cluster_id, r.member_count) for r in report.representatives] == [(2, 1, 4)]
    assert (report.representatives[0].width, report.representatives[0].height) == (200, 100)
    assert report.representatives[0].pixel_count == 20_000


def test_representatives_cover_every_cluster_and_exclude_singletons():
    images = [
        sized(1, "0000000000000000", 10, 10),
        sized(2, "0000000000000000", 20, 20),
        sized(3, "ffffffffffffffff", 30, 30),  # 単独画像
        sized(4, "00000000000000ff", 40, 40),
        sized(5, "00000000000000ff", 40, 40),
        sized(6, "0f0f0f0f0f0f0f0f", 99, 99),  # 単独画像 (面積最大でも含めない)
    ]
    report = analyze_saved_hashes(images, max_distance=0)
    assert report.cluster_count == 2
    assert [(r.cluster_id, r.image_id) for r in report.representatives] == [(1, 2), (4, 4)]
    assert report.unclustered_images == 2
    assert {3, 6}.isdisjoint(r.image_id for r in report.representatives)


def test_representatives_do_not_depend_on_input_order_or_output_limit():
    images = [
        sized(1, "0000000000000000", 10, 10),
        sized(2, "0000000000000000", 20, 20),
        sized(3, "00000000000000ff", 5, 5),
        sized(4, "00000000000000ff", 6, 6),
        sized(5, "ff00000000000000", 1, 1),
        sized(6, "ff00000000000000", 1, 1),
    ]
    expected = [(1, 2), (3, 4), (5, 5)]
    for ordering in (images, list(reversed(images)), images[2:] + images[:2]):
        report = analyze_saved_hashes(ordering, max_distance=0, limit=1)
        assert [(r.cluster_id, r.image_id) for r in report.representatives] == expected
    # limit は cluster 行の出力上限であり、代表の決定には影響しない
    assert analyze_saved_hashes(images, max_distance=0, limit=1).returned_clusters == 1


def test_unknown_pixel_count_loses_to_known_and_falls_back_to_smallest_id():
    known = analyze_saved_hashes(
        [sized(1, "0" * 16, None, None), sized(2, "0" * 16, 0, 500), sized(3, "0" * 16, 2, 2)],
        max_distance=0,
    )
    assert known.representatives[0].image_id == 3
    assert known.representatives[0].pixel_count == 4
    unknown = analyze_saved_hashes(
        [sized(9, "0" * 16, None, 10), sized(4, "0" * 16, -1, 10), sized(7, "0" * 16, 0, 0)],
        max_distance=0,
    )
    assert unknown.representatives[0].image_id == 4
    assert unknown.representatives[0].pixel_count is None
    assert unknown.representatives[0].width is None and unknown.representatives[0].height is None


def test_images_without_usable_hash_are_never_representatives():
    report = analyze_saved_hashes(
        [sized(1, None, 99, 99), sized(2, "not-a-hash", 99, 99), sized(3, "0" * 16, 1, 1)],
        max_distance=0,
    )
    assert report.representatives == []


def test_summary_excludes_representatives_like_clusters():
    report = analyze_saved_hashes([sized(1, "0" * 16, 1, 1), sized(2, "0" * 16, 1, 1)], max_distance=0)
    assert "representatives" not in report.summary() and "clusters" not in report.summary()


def test_service_selects_dimensions_from_database_for_representatives():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        for image_id, width, height in ((1, 10, 10), (2, 30, 20), (3, 20, 30)):
            session.add(
                Image(
                    id=image_id,
                    uuid=f"u{image_id}",
                    phash="0" * 16,
                    original_image_path=f"o{image_id}.png",
                    stored_image_path=f"s{image_id}.png",
                    width=width,
                    height=height,
                    format="PNG",
                    extension=".png",
                )
            )
        session.commit()
    report = DuplicateReportService(factory).report(max_distance=0)
    assert [(r.image_id, r.pixel_count) for r in report.representatives] == [(2, 600)]
