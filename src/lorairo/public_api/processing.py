"""Offline processed-image generation for exact registered image IDs."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ProcessingOutcome:
    """One original ID's processed-image generation outcome."""

    image_id: int
    status: Literal["success", "skipped", "failed"]
    resolution: int
    output_path: str | None = None
    processed_image_id: int | None = None
    reason: str | None = None


def process_images(
    project_name: str, image_ids: list[int], resolution: int, *, rebuild: bool = False
) -> list[ProcessingOutcome]:
    """Generate processed images offline, without re-registering originals.

    Args:
        project_name: Target project name.
        image_ids: Exact original image IDs, in requested order.
        resolution: Long-side resolution, a multiple of 32 from 32 to 8192.
        rebuild: Regenerate valid existing exact-resolution outputs as well.

    Returns:
        Per-ID success, validated skip, or failure outcomes.
    """
    from lorairo.services.service_container import get_service_container

    container = get_service_container()
    container.set_active_project(project_name)
    return container.image_processing_service.process_image_ids_offline(
        image_ids, resolution, rebuild=rebuild
    )
