"""Read-only statistics and conservative suggestions for saved project tags."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from itertools import groupby
from typing import Literal

from genai_tag_db_tools.utils.cleanup_str import TagCleaner
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from lorairo.database.schema import Image, Tag
from lorairo.public_api.exceptions import InvalidInputError

MAX_REPORT_LIMIT = 500
MAX_EXPECTED_TAGS = 500
SPELLING_VOCABULARY_LIMIT = 500
SPELLING_MAX_TAG_LENGTH = 128
SPELLING_SIMILARITY_THRESHOLD = 0.85


def comparison_key(tag: str) -> str:
    """Reuse format cleanup for comparisons only, without consulting a tag database."""
    cleaned: str = TagCleaner.clean_format(tag)
    return cleaned.strip().casefold()


def validate_health_options(expected_tags: Sequence[str], limit: int) -> dict[str, str]:
    """Validate before opening a DB; preserve the first explicit label per comparison key."""
    if type(limit) is not int or not 1 <= limit <= MAX_REPORT_LIMIT:
        raise InvalidInputError("limit", f"Specify an integer from 1 to {MAX_REPORT_LIMIT}.")
    if isinstance(expected_tags, str):
        raise InvalidInputError("expected_tag", "Supply a sequence of tags, not a single string.")
    expected: dict[str, str] = {}
    for tag in expected_tags:
        if not isinstance(tag, str) or not tag.strip() or not (key := comparison_key(tag)):
            raise InvalidInputError("expected_tag", "Expected tags must be nonempty strings.")
        expected.setdefault(key, tag)
        if len(expected) > MAX_EXPECTED_TAGS:
            raise InvalidInputError("expected_tag", f"Specify at most {MAX_EXPECTED_TAGS} expected tags.")
    return expected


@dataclass(frozen=True)
class TagFrequency:
    tag: str
    image_count: int


@dataclass(frozen=True)
class TagVariant:
    tag: str
    candidate: str
    reason: Literal["normalization", "spelling"]
    similarity: float | None = None


@dataclass(frozen=True)
class MissingExpectedTag:
    expected_tag: str
    normalized_tag: str
    missing_count: int
    image_ids: list[int]
    image_ids_truncated: bool


@dataclass(frozen=True)
class TagHealthReport:
    total_images: int
    tagged_images: int
    untagged_images: int
    unique_tags: int
    expected_tag_count: int
    frequencies: list[TagFrequency]
    variants: list[TagVariant]
    missing_expected: list[MissingExpectedTag]
    frequency_count: int
    variant_count: int
    missing_expected_count: int
    frequencies_truncated: bool
    variants_truncated: bool
    missing_expected_truncated: bool
    spelling_candidates_truncated: bool
    limit: int
    spelling_vocabulary_limit: int = SPELLING_VOCABULARY_LIMIT
    spelling_max_tag_length: int = SPELLING_MAX_TAG_LENGTH
    spelling_similarity_threshold: float = SPELLING_SIMILARITY_THRESHOLD

    def summary(self) -> dict[str, object]:
        """Metadata for the final CLI row, keeping records in their own JSONL rows."""
        return {
            key: value
            for key, value in asdict(self).items()
            if key not in {"frequencies", "variants", "missing_expected"}
        }


def _spelling_variants(vocabulary: list[str], representatives: dict[str, str]) -> Iterator[TagVariant]:
    # Vocabulary is ordered by descending image frequency, then text. A candidate
    # is always another saved tag, never an invented correction or a dictionary lookup.
    for index, candidate in enumerate(vocabulary):
        for tag in vocabulary[index + 1 :]:
            matcher = SequenceMatcher(None, tag, candidate, autojunk=False)
            if matcher.real_quick_ratio() < SPELLING_SIMILARITY_THRESHOLD:
                continue
            if matcher.quick_ratio() < SPELLING_SIMILARITY_THRESHOLD:
                continue
            similarity = matcher.ratio()
            if similarity >= SPELLING_SIMILARITY_THRESHOLD:
                yield TagVariant(
                    representatives[tag], representatives[candidate], "spelling", round(similarity, 4)
                )


def _suggest_variants(
    sorted_tags: list[str],
    normalized: dict[str, str],
    normalized_frequencies: Counter[str],
    limit: int,
) -> tuple[list[TagVariant], int, bool]:
    representatives: dict[str, str] = {}
    for tag in sorted_tags:
        representatives.setdefault(normalized[tag], tag)
    all_vocabulary = sorted(normalized_frequencies, key=lambda key: (-normalized_frequencies[key], key))
    eligible = [key for key in all_vocabulary if 4 <= len(key) <= SPELLING_MAX_TAG_LENGTH]
    vocabulary = eligible[:SPELLING_VOCABULARY_LIMIT]
    spelling_truncated = len(eligible) > len(vocabulary) or any(
        len(key) > SPELLING_MAX_TAG_LENGTH for key in all_vocabulary
    )
    variants: list[TagVariant] = []
    variant_count = 0
    for tag in sorted_tags:
        if normalized[tag] and normalized[tag] != tag:
            variant_count += 1
            if len(variants) < limit:
                variants.append(TagVariant(tag, normalized[tag], "normalization"))
    for variant in _spelling_variants(vocabulary, representatives):
        variant_count += 1
        if len(variants) < limit:
            variants.append(variant)
    return variants, variant_count, spelling_truncated


class TagHealthService:
    """Count each exact saved tag once per image, across all accepted model outputs."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def report(self, expected_tags: Sequence[str] = (), *, limit: int = 100) -> TagHealthReport:
        expected = validate_health_options(expected_tags, limit)
        frequencies: Counter[str] = Counter()
        normalized_frequencies: Counter[str] = Counter()
        normalized: dict[str, str] = {}
        missing_ids: dict[str, list[int]] = {key: [] for key in expected}
        total_images = tagged_images = 0
        statement = (
            select(Image.id, Tag.tag)
            .outerjoin(Tag, and_(Tag.image_id == Image.id, Tag.rejected_at.is_(None)))
            .order_by(Image.id, Tag.tag)
            .execution_options(yield_per=1000)
        )
        with self._session_factory() as session:
            rows = session.execute(statement)
            for image_id, image_rows in groupby(rows, key=lambda row: row[0]):
                total_images += 1
                tags = {tag for _image_id, tag in image_rows if tag is not None and tag.strip()}
                tagged_images += bool(tags)
                frequencies.update(tags)
                for tag in tags:
                    if tag not in normalized:
                        normalized[tag] = comparison_key(tag)
                keys = {normalized[tag] for tag in tags}
                normalized_frequencies.update(keys)
                for key, sample in missing_ids.items():
                    if key not in keys and len(sample) < limit:
                        sample.append(image_id)

        sorted_tags = sorted(frequencies, key=lambda tag: (-frequencies[tag], tag))
        variants, variant_count, spelling_truncated = _suggest_variants(
            sorted_tags, normalized, normalized_frequencies, limit
        )
        missing = [
            MissingExpectedTag(
                label,
                key,
                total_images - normalized_frequencies[key],
                missing_ids[key],
                total_images - normalized_frequencies[key] > len(missing_ids[key]),
            )
            for key, label in expected.items()
            if total_images > normalized_frequencies[key]
        ]
        return TagHealthReport(
            total_images=total_images,
            tagged_images=tagged_images,
            untagged_images=total_images - tagged_images,
            unique_tags=len(frequencies),
            expected_tag_count=len(expected),
            frequencies=[TagFrequency(tag, frequencies[tag]) for tag in sorted_tags[:limit]],
            variants=variants,
            missing_expected=missing[:limit],
            frequency_count=len(frequencies),
            variant_count=variant_count,
            missing_expected_count=len(missing),
            frequencies_truncated=len(frequencies) > limit,
            variants_truncated=variant_count > limit,
            missing_expected_truncated=len(missing) > limit,
            spelling_candidates_truncated=spelling_truncated,
            limit=limit,
        )
