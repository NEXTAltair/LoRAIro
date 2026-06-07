"""CLI guards for image selection safety."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

import click

_ORIGINAL_IMAGE_PREFIX = PurePosixPath("image_dataset/original_images")


@dataclass(frozen=True)
class OriginalImageSelection:
    image_id: int | None
    stored_image_path: str


def is_original_image_stored_path(stored_image_path: str | None) -> bool:
    """Return whether a DB stored path points at the original image storage."""
    if not stored_image_path:
        return False

    normalized = PurePosixPath(str(stored_image_path).replace("\\", "/"))
    parts = normalized.parts
    prefix_parts = _ORIGINAL_IMAGE_PREFIX.parts
    for idx in range(0, len(parts) - len(prefix_parts) + 1):
        if parts[idx : idx + len(prefix_parts)] == prefix_parts:
            return True
    return False


def find_original_image_records(
    image_records: Iterable[Mapping[str, Any]],
) -> list[OriginalImageSelection]:
    """Extract image records that still point to original image storage."""
    original_records: list[OriginalImageSelection] = []
    for record in image_records:
        stored_path = record.get("stored_image_path")
        if not is_original_image_stored_path(str(stored_path) if stored_path is not None else None):
            continue

        raw_image_id = record.get("id")
        image_id = (
            int(raw_image_id)
            if isinstance(raw_image_id, int | str) and str(raw_image_id).isdigit()
            else None
        )
        original_records.append(
            OriginalImageSelection(
                image_id=image_id,
                stored_image_path=str(stored_path),
            )
        )
    return original_records


def reject_original_image_records(
    image_records: Iterable[Mapping[str, Any]],
    *,
    command_name: str,
) -> None:
    """Reject CLI annotation routes that would operate on original images."""
    original_records = find_original_image_records(image_records)
    if not original_records:
        return

    samples = ", ".join(
        f"{record.image_id}:{record.stored_image_path}"
        if record.image_id is not None
        else record.stored_image_path
        for record in original_records[:5]
    )
    extra = "" if len(original_records) <= 5 else f", ... (+{len(original_records) - 5} more)"
    raise click.UsageError(
        f"{command_name} cannot operate directly on original images. "
        "Select processed/resized image records instead. "
        f"Rejected {len(original_records)} original image(s): {samples}{extra}"
    )
