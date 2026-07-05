"""Tag editing commands.

カンマ区切り image_ids に対してタグを追加・削除・置換するコマンド群。
エージェントが判断した操作を安全に実行するための CLI インターフェース。

デフォルトは dry-run (DB 非更新)。--apply を付けた場合のみ書き込む。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import click
import typer

if TYPE_CHECKING:
    from lorairo.database.repository.annotation_record import (
        AnnotationRepository,
        ManualTagClassification,
    )

from lorairo.cli._boundary import command_boundary
from lorairo.cli._console import make_console
from lorairo.cli._emit import emit_item, emit_result
from lorairo.cli._glyphs import OK
from lorairo.cli._image_ids import MAX_IMAGE_IDS, parse_image_ids, validate_image_ids_exist
from lorairo.cli._output_mode import is_json_mode
from lorairo.public_api.project import get_project as api_get_project
from lorairo.services.service_container import get_service_container

app = typer.Typer(help="Tag editing commands (agent-friendly)")
console = make_console()


def _apply_classified_tags(
    annotation_repo: AnnotationRepository,
    addable: list[ManualTagClassification],
    image_ids: list[int],
    dry_run: bool,
) -> tuple[list[dict[str, object]], int]:
    """分類済みタグを画像へ適用し、(per-tag 解決結果, 追加件数) を返す。

    dry-run では書き込みも user DB 登録も行わず分類結果のみを返す。
    apply では未登録の新タグのみ user DB へ登録し、typo/曖昧候補は自動 alias 化せず
    verbatim + tag_id=null で追加する (Issue #1174)。
    """
    resolutions: list[dict[str, object]] = []
    total_added = 0
    for c in addable:
        tag_id = c.tag_id
        if not dry_run:
            if c.classification == "unregistered":
                tag_id = annotation_repo.register_user_tag(c.input_tag)
            # exact/alias は tag DB の canonical を保存し、それ以外 (新規登録・未解決) は
            # 旧経路と同じ strip().lower() 正規化で保存する (Codex P2: 大文字混じり入力が
            # verbatim 保存されると tags remove の小文字照合で削除できなくなる)
            if c.classification in ("exact", "alias_resolved") and tag_id is not None:
                store_tag = c.canonical_tag
            else:
                store_tag = c.input_tag.strip().lower()
            _, added = annotation_repo.add_tag_to_images_batch(
                image_ids, c.input_tag, None, resolved=(store_tag, tag_id)
            )
            total_added += added
        resolutions.append(
            {
                "tag": c.input_tag,
                "classification": c.classification,
                "canonical_tag": c.canonical_tag,
                "tag_id": tag_id,
                "candidates": c.candidates,
            }
        )
    return resolutions, total_added


def _print_add_summary(
    applied_tags: list[str],
    resolutions: list[dict[str, object]],
    invalid_tags: list[str],
    unresolved: list[dict[str, object]],
    image_ids: list[int],
    dry_run: bool,
) -> None:
    """rich モードの tags add サマリー出力 (分類・候補・未解決の surface)。"""
    prefix = "[dry-run] " if dry_run else ""
    console.print(
        f"{prefix}{OK} {len(image_ids)} 件の画像に {applied_tags} を追加{'予定' if dry_run else '完了'}"
    )
    for r in resolutions:
        if r["classification"] in ("typo_candidate", "ambiguous"):
            console.print(
                f"[yellow]候補あり:[/yellow] '{r['tag']}' は未登録です。"
                f" 候補: {r['candidates']} (自動適用しません)"
            )
        elif r["classification"] == "alias_resolved":
            console.print(f"alias 解決: '{r['tag']}' → '{r['canonical_tag']}'")
    if invalid_tags:
        console.print(f"[yellow]スキップ (空正規化):[/yellow] {invalid_tags}")
    if not dry_run and unresolved:
        console.print(f"[yellow]警告:[/yellow] {len(unresolved)} 件がタグ DB 未解決 (tag_id=null) です")


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

    各タグはタグ DB の refinement 検索で分類されます (Issue #1174):
    完全一致/既知 alias は tag_id へ自動解決、typo/曖昧候補は候補を提示
    (自動適用しない)、未登録の新タグは --apply 時に user DB へ登録します。
    解決できなかったタグは tag_id=null として明示されます。

    Example:
        lorairo-cli tags add --project proj --image-ids 1,2,3 --tags "cat,dog" --apply
    """
    with command_boundary():
        api_get_project(project)
        image_ids = parse_image_ids(image_ids_csv)
        if not image_ids:
            raise click.UsageError("--image-ids に有効な値がありません。")
        if len(image_ids) > MAX_IMAGE_IDS:
            raise click.UsageError(f"--image-ids は最大 {MAX_IMAGE_IDS} 件まで。")

        tag_list = [t.strip() for t in tags_csv.split(",") if t.strip()]
        if not tag_list:
            raise click.UsageError("--tags に有効な値がありません。")

        container = get_service_container()
        container.set_active_project(project)
        validate_image_ids_exist(container, image_ids)

        annotation_repo = container.db_manager.annotation_repo
        dry_run = not apply

        # 分類 (読み取り専用、dry-run/apply 共通)。invalid は追加対象から除外する
        classifications = [annotation_repo.classify_manual_tag(tag) for tag in tag_list]
        addable = [c for c in classifications if c.classification != "invalid"]
        if not addable:
            raise click.UsageError("--tags の全タグが正規化後に空になりました (追加対象なし)。")

        resolutions, total_added = _apply_classified_tags(annotation_repo, addable, image_ids, dry_run)
        applied_tags = [c.input_tag for c in addable]
        invalid_tags = [c.input_tag for c in classifications if c.classification == "invalid"]
        unresolved = [r for r in resolutions if r["tag_id"] is None]

        if is_json_mode():
            for image_id in image_ids:
                emit_item(
                    {
                        "image_id": image_id,
                        "action": "add",
                        "tags": applied_tags,
                        "status": "dry_run" if dry_run else "changed",
                    }
                )
            emit_result(
                f"{'[dry-run] ' if dry_run else ''}Added tags to {len(image_ids)} image(s)",
                target_images=len(image_ids),
                tags=applied_tags,
                added=total_added,
                dry_run=dry_run,
                tag_resolutions=resolutions,
                skipped_invalid_tags=invalid_tags,
                unresolved_tag_count=len(unresolved) if not dry_run else None,
            )
        else:
            _print_add_summary(applied_tags, resolutions, invalid_tags, unresolved, image_ids, dry_run)


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
        image_ids = parse_image_ids(image_ids_csv)
        if not image_ids:
            raise click.UsageError("--image-ids に有効な値がありません。")
        if len(image_ids) > MAX_IMAGE_IDS:
            raise click.UsageError(f"--image-ids は最大 {MAX_IMAGE_IDS} 件まで。")

        tag_list = [t.strip() for t in tags_csv.split(",") if t.strip()]
        if not tag_list:
            raise click.UsageError("--tags に有効な値がありません。")

        container = get_service_container()
        container.set_active_project(project)
        validate_image_ids_exist(container, image_ids)

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
        image_ids = parse_image_ids(image_ids_csv)
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
        validate_image_ids_exist(container, image_ids)

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
