"""Shared image_id CSV parsing/validation for agent-facing CLI commands.

``tags add/remove/replace`` (write) and ``images show`` (read) all accept the
same ``--image-ids`` comma-separated form with the same 500-id cap and the
same "does this image exist" check. Centralized here so both call sites stay
in sync.
"""

from __future__ import annotations

import click

from lorairo.database.filter_criteria import ImageFilterCriteria
from lorairo.public_api.exceptions import ImageNotFoundError
from lorairo.services.service_container import ServiceContainer

MAX_IMAGE_IDS = 500


def parse_image_ids(image_ids_csv: str) -> list[int]:
    """カンマ区切り文字列を int リストに変換する。

    Args:
        image_ids_csv: カンマ区切りの画像 ID 文字列。

    Returns:
        画像 ID の整数リスト。

    Raises:
        click.UsageError: 整数に変換できない値が含まれていた場合。
    """
    try:
        return [int(x.strip()) for x in image_ids_csv.split(",") if x.strip()]
    except ValueError as e:
        raise click.UsageError(f"--image-ids には整数のみ指定可: {e}") from e


def validate_image_ids_exist(container: ServiceContainer, image_ids: list[int]) -> None:
    """全 image_id が DB に存在するか確認する。

    Args:
        container: サービスコンテナ。
        image_ids: 存在確認する画像 ID のリスト。

    Raises:
        ImageNotFoundError: リスト内に存在しない画像 ID があった場合。
    """
    criteria = ImageFilterCriteria(image_ids=image_ids, include_nsfw=True)
    records, _ = container.db_manager.image_repo.get_images_by_filter(criteria)
    found_ids = {int(r["id"]) for r in records}
    missing = [i for i in image_ids if i not in found_ids]
    if missing:
        raise ImageNotFoundError(missing[0])
