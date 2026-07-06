"""Shared image_id CSV parsing/validation for agent-facing CLI commands.

``tags add/remove/replace`` (write) and ``images show`` (read) all accept the
same ``--image-ids`` comma-separated form with the same 500-id cap and the
same "does this image exist" check. Centralized here so both call sites stay
in sync.
"""

from __future__ import annotations

from pathlib import Path

import click

from lorairo.database.filter_criteria import ImageFilterCriteria
from lorairo.public_api.exceptions import ImageNotFoundError
from lorairo.services.service_container import ServiceContainer

MAX_IMAGE_IDS = 500
# --image-ids-file の 1 プロセス上限。数千規模の一括操作を 1 起動で処理する (Issue #1216)。
# チャンク分割は呼び出し側 (CLI コマンド) が BULK_CHUNK_SIZE 単位で行う。
MAX_IMAGE_IDS_FILE = 100_000
# --image-ids-file 処理の 1 トランザクション件数。巨大単一 txn を避け進捗も刻む (Issue #1216)。
BULK_CHUNK_SIZE = 500


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


def parse_image_ids_file(file_path: str) -> list[int]:
    """改行/カンマ区切りの ID リストファイルを int リストへ変換する (Issue #1216)。

    数千規模の一括タグ操作で、手動チャンク分割 + 複数プロセス起動を避けるための
    入力手段。空行・空白・重複を無視し、初出順を保って返す。

    Args:
        file_path: 改行またはカンマ区切りの画像 ID を含むファイルパス。

    Returns:
        画像 ID の整数リスト (初出順、重複排除済み)。

    Raises:
        click.UsageError: ファイル不在・整数変換失敗・有効値なし・件数超過。
    """
    path = Path(file_path)
    if not path.is_file():
        raise click.UsageError(f"--image-ids-file '{file_path}' が見つかりません。")
    tokens: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        tokens.extend(part.strip() for part in raw_line.split(",") if part.strip())
    seen: set[int] = set()
    image_ids: list[int] = []
    for token in tokens:
        try:
            value = int(token)
        except ValueError as e:
            raise click.UsageError(f"--image-ids-file に整数以外の値: '{token}' ({e})") from e
        if value not in seen:
            seen.add(value)
            image_ids.append(value)
    if not image_ids:
        raise click.UsageError("--image-ids-file に有効な画像 ID がありません。")
    if len(image_ids) > MAX_IMAGE_IDS_FILE:
        raise click.UsageError(f"--image-ids-file は最大 {MAX_IMAGE_IDS_FILE} 件まで。")
    return image_ids


def resolve_image_ids_input(
    image_ids_csv: str | None, image_ids_file: str | None, *, option_label: str = "--image-ids"
) -> tuple[list[int], bool]:
    """``--image-ids`` / ``--image-ids-file`` の排他入力を解決する (Issue #1216)。

    Args:
        image_ids_csv: カンマ区切り ID (直接指定)。
        image_ids_file: ID リストファイルパス。
        option_label: エラーメッセージに使うオプション名。

    Returns:
        (画像 ID リスト, ファイル入力だったか)。ファイル入力は上限 MAX_IMAGE_IDS_FILE、
        直接指定は上限 MAX_IMAGE_IDS を適用する。

    Raises:
        click.UsageError: 両方指定 / 未指定 / 各パースエラー / 直接指定の件数超過。
    """
    if bool(image_ids_csv) == bool(image_ids_file):
        raise click.UsageError(f"{option_label} か --image-ids-file のどちらか一方を指定してください。")
    if image_ids_file:
        return parse_image_ids_file(image_ids_file), True
    ids = parse_image_ids(image_ids_csv or "")
    if not ids:
        raise click.UsageError(f"{option_label} に有効な値がありません。")
    if len(ids) > MAX_IMAGE_IDS:
        raise click.UsageError(f"{option_label} は最大 {MAX_IMAGE_IDS} 件まで。")
    return ids, False


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
