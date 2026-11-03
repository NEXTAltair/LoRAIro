"""Bounded, read-only duplicate candidates from already stored 64-bit pHashes."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lorairo.database.schema import Image
from lorairo.public_api.exceptions import InvalidInputError, ResultSetTooLargeError

HASH_BITS = 64
DEFAULT_MAX_DISTANCE = 4
MAX_PROJECT_IMAGES = 10_000
MAX_REPORT_LIMIT = 500
MAX_PAIR_COMPARISONS = MAX_PROJECT_IMAGES * (MAX_PROJECT_IMAGES - 1) // 2
_HASH_PATTERN = re.compile(r"[0-9a-fA-F]{16}\Z")


def validate_duplicate_options(max_distance: int, limit: int) -> None:
    """Reject invalid options before DB access or any comparisons."""
    if type(max_distance) is not int or not 0 <= max_distance <= HASH_BITS:
        raise InvalidInputError("max_distance", f"Specify an integer from 0 to {HASH_BITS}.")
    if type(limit) is not int or not 1 <= limit <= MAX_REPORT_LIMIT:
        raise InvalidInputError("limit", f"Specify an integer from 1 to {MAX_REPORT_LIMIT}.")


def _check_project_size(count: int) -> None:
    if count > MAX_PROJECT_IMAGES:
        error = ResultSetTooLargeError(count, MAX_PROJECT_IMAGES)
        error.args = (
            f"Duplicate detection requires at most {MAX_PROJECT_IMAGES:,} project images; "
            f"this project has {count:,}. No comparisons were run. --limit controls output only.",
        )
        raise error


@dataclass(frozen=True)
class SavedImageHash:
    """DB-only input; paths are reported as stored and never opened or resolved."""

    image_id: int
    phash: str | None
    stored_image_path: str
    original_image_path: str


@dataclass(frozen=True)
class DuplicateMember:
    image_id: int
    stored_image_path: str
    original_image_path: str
    phash: str


@dataclass(frozen=True)
class DuplicateCluster:
    cluster_id: int
    member_count: int
    members: list[DuplicateMember]
    members_truncated: bool


@dataclass(frozen=True)
class DuplicateReport:
    total_images: int
    valid_phash_images: int
    missing_phash_images: int
    invalid_phash_images: int
    unique_phashes: int
    cluster_count: int
    clustered_images: int
    unclustered_images: int
    returned_clusters: int
    clusters_truncated: bool
    max_distance: int
    compared_hash_pairs: int
    limit: int
    clusters: list[DuplicateCluster]
    hash_bits: int = HASH_BITS
    distance_metric: str = "hamming"
    clustering: str = "connected_components"
    candidate_only: bool = True
    max_images: int = MAX_PROJECT_IMAGES
    max_pair_comparisons: int = MAX_PAIR_COMPARISONS

    def summary(self) -> dict[str, object]:
        """Keep bounded cluster records in their own JSONL items."""
        return {key: value for key, value in asdict(self).items() if key != "clusters"}


def _group_saved_hashes(
    images: Sequence[SavedImageHash],
) -> tuple[dict[int, list[DuplicateMember]], int, int]:
    groups: dict[int, list[DuplicateMember]] = {}
    missing = invalid = 0
    for image in sorted(images, key=lambda item: item.image_id):
        raw = image.phash
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            missing += 1
            continue
        if not isinstance(raw, str) or not _HASH_PATTERN.fullmatch(raw.strip()):
            invalid += 1
            continue
        value = int(raw.strip(), 16)
        groups.setdefault(value, []).append(
            DuplicateMember(
                image.image_id, image.stored_image_path, image.original_image_path, f"{value:016x}"
            )
        )
    return groups, missing, invalid


def _connected_components(
    groups: dict[int, list[DuplicateMember]], max_distance: int
) -> tuple[list[list[DuplicateMember]], int]:
    """Union exact hash groups without storing a potentially quadratic edge list."""
    hashes = list(groups)
    if max_distance == HASH_BITS:
        members = [member for group in groups.values() for member in group]
        return ([sorted(members, key=lambda item: item.image_id)] if members else []), 0
    parents = list(range(len(hashes)))

    def root(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    compared = 0
    if max_distance > 0:
        for right, value in enumerate(hashes):
            for left in range(right):
                # ImageHash subtraction counts differing bits; XOR/popcount uses
                # the same metric on the existing 16-hex representation directly.
                compared += 1
                if (value ^ hashes[left]).bit_count() <= max_distance:
                    left_root, right_root = root(left), root(right)
                    parents[max(left_root, right_root)] = min(left_root, right_root)
    components: dict[int, list[DuplicateMember]] = {}
    for index, value in enumerate(hashes):
        components.setdefault(root(index), []).extend(groups[value])
    return [sorted(members, key=lambda item: item.image_id) for members in components.values()], compared


def analyze_saved_hashes(
    images: Sequence[SavedImageHash], *, max_distance: int = DEFAULT_MAX_DISTANCE, limit: int = 100
) -> DuplicateReport:
    """Analyze a complete bounded project snapshot without reading image contents.

    Groups are connected components, so a chain can join endpoints whose distance
    exceeds ``max_distance``. Output limits never restrict detection or counts.
    """
    validate_duplicate_options(max_distance, limit)
    _check_project_size(len(images))
    groups, missing, invalid = _group_saved_hashes(images)
    components, compared = _connected_components(groups, max_distance)
    candidates = sorted(
        (members for members in components if len(members) > 1), key=lambda members: members[0].image_id
    )
    clusters = [
        DuplicateCluster(members[0].image_id, len(members), members[:limit], len(members) > limit)
        for members in candidates[:limit]
    ]
    valid = len(images) - missing - invalid
    clustered = sum(map(len, candidates))
    return DuplicateReport(
        total_images=len(images),
        valid_phash_images=valid,
        missing_phash_images=missing,
        invalid_phash_images=invalid,
        unique_phashes=len(groups),
        cluster_count=len(candidates),
        clustered_images=clustered,
        unclustered_images=valid - clustered,
        returned_clusters=len(clusters),
        clusters_truncated=len(candidates) > limit,
        max_distance=max_distance,
        compared_hash_pairs=compared,
        limit=limit,
        clusters=clusters,
    )


class DuplicateReportService:
    """Select saved hashes and paths only, with an explicit project-size preflight."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def report(self, *, max_distance: int = DEFAULT_MAX_DISTANCE, limit: int = 100) -> DuplicateReport:
        validate_duplicate_options(max_distance, limit)
        with self._session_factory() as session:
            count = session.execute(select(func.count()).select_from(Image)).scalar_one()
            _check_project_size(count)
            rows = session.execute(
                select(Image.id, Image.phash, Image.stored_image_path, Image.original_image_path)
                .order_by(Image.id)
                .limit(MAX_PROJECT_IMAGES + 1)
            ).all()
            # Re-check before comparison if the project grew after COUNT. Never
            # return a silent partial scan when concurrent inserts cross the cap.
            _check_project_size(len(rows))
        images = [SavedImageHash(*row) for row in rows]
        return analyze_saved_hashes(images, max_distance=max_distance, limit=limit)
