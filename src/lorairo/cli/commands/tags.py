"""Tag editing commands.

カンマ区切り image_ids に対してタグを追加・削除・置換するコマンド群。
エージェントが判断した操作を安全に実行するための CLI インターフェース。

デフォルトは dry-run (DB 非更新)。--apply を付けた場合のみ書き込む。
"""

from __future__ import annotations

import click
import typer

from lorairo.cli._boundary import command_boundary
from lorairo.cli._console import make_console
from lorairo.cli._emit import emit_item, emit_result
from lorairo.cli._glyphs import OK
from lorairo.cli._output_mode import is_json_mode
from lorairo.database.filter_criteria import ImageFilterCriteria
from lorairo.public_api.exceptions import ImageNotFoundError
from lorairo.public_api.project import get_project as api_get_project
from lorairo.services.service_container import ServiceContainer, get_service_container

app = typer.Typer(help="Tag editing commands (agent-friendly)")
console = make_console()

MAX_IMAGE_IDS = 500


def _parse_image_ids(image_ids_csv: str) -> list[int]:
    """カンマ区切り文字列を int リストに変換。不正値は UsageError。

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


def _validate_image_ids_exist(container: ServiceContainer, image_ids: list[int]) -> None:
    """全 image_id が DB に存在するか確認。存在しなければ ImageNotFoundError。

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


@app.command("add")
def add(
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    image_ids_csv: str = typer.Option(..., "--image-ids", help="Comma-separated image IDs"),
    tags_csv: str = typer.Option(..., "--tags", help="Comma-separated tags to add"),
    apply: bool = typer.Option(False, "--apply", help="Write to DB (default: dry-run)"),
) -> None:
    """Add tags to images.

    指定した image_ids に対してタグを追加します。
    デフォルトは dry-run です。--apply を付けると DB に書き込みます。

    Example:
        lorairo-cli tags add --project proj --image-ids 1,2,3 --tags "cat,dog" --apply
    """
    with command_boundary():
        api_get_project(project)
        image_ids = _parse_image_ids(image_ids_csv)
        if not image_ids:
            raise click.UsageError("--image-ids に有効な値がありません。")
        if len(image_ids) > MAX_IMAGE_IDS:
            raise click.UsageError(f"--image-ids は最大 {MAX_IMAGE_IDS} 件まで。")

        tag_list = [t.strip() for t in tags_csv.split(",") if t.strip()]
        if not tag_list:
            raise click.UsageError("--tags に有効な値がありません。")

        container = get_service_container()
        container.set_active_project(project)
        _validate_image_ids_exist(container, image_ids)

        dry_run = not apply
        total_added = 0

        if not dry_run:
            for tag in tag_list:
                _, added = container.db_manager.annotation_repo.add_tag_to_images_batch(
                    image_ids, tag, None
                )
                total_added += added

        if is_json_mode():
            for image_id in image_ids:
                emit_item(
                    {
                        "image_id": image_id,
                        "action": "add",
                        "tags": tag_list,
                        "status": "dry_run" if dry_run else "changed",
                    }
                )
            emit_result(
                f"{'[dry-run] ' if dry_run else ''}Added tags to {len(image_ids)} image(s)",
                target_images=len(image_ids),
                tags=tag_list,
                added=total_added,
                dry_run=dry_run,
            )
        else:
            prefix = "[dry-run] " if dry_run else ""
            console.print(
                f"{prefix}{OK} {len(image_ids)} 件の画像に {tag_list} を追加{'予定' if dry_run else '完了'}"
            )


@app.command("remove")
def remove(
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    image_ids_csv: str = typer.Option(..., "--image-ids", help="Comma-separated image IDs"),
    tags_csv: str = typer.Option(..., "--tags", help="Comma-separated tags to remove"),
    apply: bool = typer.Option(False, "--apply", help="Write to DB (default: dry-run)"),
) -> None:
    """Remove tags from images.

    指定した image_ids からタグを削除します。
    対象タグが存在しない画像はスキップします（エラーにしません）。
    デフォルトは dry-run です。--apply を付けると DB に書き込みます。

    Example:
        lorairo-cli tags remove --project proj --image-ids 1,2,3 --tags "bad_tag" --apply
    """
    with command_boundary():
        api_get_project(project)
        image_ids = _parse_image_ids(image_ids_csv)
        if not image_ids:
            raise click.UsageError("--image-ids に有効な値がありません。")
        if len(image_ids) > MAX_IMAGE_IDS:
            raise click.UsageError(f"--image-ids は最大 {MAX_IMAGE_IDS} 件まで。")

        tag_list = [t.strip() for t in tags_csv.split(",") if t.strip()]
        if not tag_list:
            raise click.UsageError("--tags に有効な値がありません。")

        container = get_service_container()
        container.set_active_project(project)
        _validate_image_ids_exist(container, image_ids)

        dry_run = not apply
        per_item_results: list[tuple[int, str]] = []
        total_removed = 0

        if not dry_run:
            for tag in tag_list:
                _, item_results = container.db_manager.annotation_repo.remove_tag_from_images_batch(
                    image_ids, tag
                )
                per_item_results = item_results
                total_removed += sum(1 for _, s in item_results if s == "changed")

        if is_json_mode():
            for image_id in image_ids:
                status = (
                    "dry_run"
                    if dry_run
                    else next((s for iid, s in per_item_results if iid == image_id), "unknown")
                )
                emit_item(
                    {
                        "image_id": image_id,
                        "action": "remove",
                        "tags": tag_list,
                        "status": status,
                    }
                )
            emit_result(
                f"{'[dry-run] ' if dry_run else ''}Removed tags from {len(image_ids)} image(s)",
                target_images=len(image_ids),
                tags=tag_list,
                removed=total_removed,
                dry_run=dry_run,
            )
        else:
            prefix = "[dry-run] " if dry_run else ""
            console.print(
                f"{prefix}{OK} {len(image_ids)} 件の画像から {tag_list} を削除"
                f"{'予定' if dry_run else '完了'}"
            )


@app.command("replace")
def replace(
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    image_ids_csv: str = typer.Option(..., "--image-ids", help="Comma-separated image IDs"),
    from_tag: str = typer.Option(..., "--from", help="Tag to replace (変換元)"),
    to_tag: str = typer.Option(..., "--to", help="Replacement tag (変換先)"),
    apply: bool = typer.Option(False, "--apply", help="Write to DB (default: dry-run)"),
) -> None:
    """Replace a tag with another tag across images.

    指定した image_ids の変換元タグを変換先タグに置換します。

    - 変換元タグが存在しない画像はスキップします。
    - 変換先タグが既に存在する場合は変換元のみ削除します（重複しません）。

    デフォルトは dry-run です。--apply を付けると DB に書き込みます。

    Example:
        lorairo-cli tags replace --project proj --image-ids 1,2,3 --from "bad tag" --to "good_tag" --apply
    """
    with command_boundary():
        api_get_project(project)
        image_ids = _parse_image_ids(image_ids_csv)
        if not image_ids:
            raise click.UsageError("--image-ids に有効な値がありません。")
        if len(image_ids) > MAX_IMAGE_IDS:
            raise click.UsageError(f"--image-ids は最大 {MAX_IMAGE_IDS} 件まで。")
        if not from_tag.strip():
            raise click.UsageError("--from に有効な値がありません。")
        if not to_tag.strip():
            raise click.UsageError("--to に有効な値がありません。")

        container = get_service_container()
        container.set_active_project(project)
        _validate_image_ids_exist(container, image_ids)

        dry_run = not apply
        per_item_results: list[tuple[int, str]] = []

        if not dry_run:
            _, per_item_results = container.db_manager.annotation_repo.replace_tag_for_images_batch(
                image_ids, from_tag, to_tag
            )

        changed = sum(1 for _, s in per_item_results if s == "changed")
        skipped = sum(1 for _, s in per_item_results if s == "skipped")

        if is_json_mode():
            for image_id in image_ids:
                status = (
                    "dry_run"
                    if dry_run
                    else next((s for iid, s in per_item_results if iid == image_id), "unknown")
                )
                item: dict[str, object] = {
                    "image_id": image_id,
                    "action": "replace",
                    "from": from_tag.strip().lower(),
                    "to": to_tag.strip().lower(),
                    "status": status,
                }
                if status == "skipped":
                    item["reason"] = "from_tag_not_found"
                emit_item(item)
            emit_result(
                f"{'[dry-run] ' if dry_run else ''}Replaced tags in {len(image_ids)} image(s)",
                target_images=len(image_ids),
                changed=changed,
                skipped=skipped,
                errors=0,
                dry_run=dry_run,
            )
        else:
            prefix = "[dry-run] " if dry_run else ""
            console.print(
                f"{prefix}{OK} {len(image_ids)} 件対象: '{from_tag}' -> '{to_tag}' "
                f"({'予定' if dry_run else f'変更={changed}, スキップ={skipped}'})"
            )
