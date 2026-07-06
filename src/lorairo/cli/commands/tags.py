"""Tag editing commands.

カンマ区切り image_ids に対してタグを追加・削除・置換するコマンド群。
エージェントが判断した操作を安全に実行するための CLI インターフェース。

デフォルトは dry-run (DB 非更新)。--apply を付けた場合のみ書き込む。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import click
import typer

if TYPE_CHECKING:
    from lorairo.database.repository.annotation_record import (
        AnnotationRepository,
        ManualTagClassification,
    )
    from lorairo.services.service_container import ServiceContainer
    from lorairo.services.tag_management_service import TagManagementService

from lorairo.cli._boundary import command_boundary
from lorairo.cli._console import make_console
from lorairo.cli._emit import emit_item, emit_result
from lorairo.cli._glyphs import OK
from lorairo.cli._image_ids import MAX_IMAGE_IDS, parse_image_ids, validate_image_ids_exist
from lorairo.cli._output_mode import is_json_mode
from lorairo.public_api.exceptions import DatabaseError
from lorairo.public_api.project import get_project as api_get_project
from lorairo.services.service_container import get_service_container

app = typer.Typer(help="Tag editing commands (agent-friendly)")
console = make_console()
# 診断/警告用 stderr console。show --missing-only の stdout (add --file 入力) を
# 機械可読に保つため、打ち切り警告等は stderr へ回す (Issue #1211 / Codex P2)。
err_console = make_console(stderr=True)


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


# ===== translations サブコマンド (Issue #1173 / ADR 0085) =====

trans_app = typer.Typer(help="Tag translation commands (read/write user DB overlay)")
app.add_typer(trans_app, name="translations")

# 言語キーは入力を ja/en に限定し、書き込みも ja/en の一貫形にする (#1050 / ADR 0085)。
# 読みはエイリアス両表記 (ja/japanese, en/english) を service 層が集約する。
_SUPPORTED_LANGS = ("ja", "en")
MAX_TRANSLATION_TAGS = 100


def _translation_status_entries(
    service: TagManagementService, tag_names: list[str]
) -> list[dict[str, object]]:
    """タグごとの翻訳状況 (ja/en の候補・主訳・missing) を組み立てる。

    読み出しは ja/japanese・en/english のエイリアス両表記を service 側で集約する。
    タグごとに search_tags を 3 回 (tag_id 解決 + 言語別候補 x2) 呼ぶ N+1 は、
    `translation_status_batch` の 2 クエリに畳む (#1203: 70 タグで約 5 分 -> 秒台)。
    """
    statuses = service.translation_status_batch(tag_names, languages=_SUPPORTED_LANGS)
    entries: list[dict[str, object]] = []
    for tag in tag_names:
        status = statuses.get(tag)
        tag_id = status.tag_id if status is not None else None
        translations: dict[str, object] = {}
        missing: list[str] = []
        if tag_id is None or status is None:
            missing = list(_SUPPORTED_LANGS)
        else:
            for lang in _SUPPORTED_LANGS:
                candidates, preferred = status.by_language.get(lang, ([], None))
                translations[lang] = {"candidates": candidates, "preferred": preferred}
                if not candidates:
                    missing.append(lang)
        entries.append({"tag": tag, "tag_id": tag_id, "translations": translations, "missing": missing})
    return entries


@trans_app.command("show")
def translations_show(
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    image_ids_csv: str | None = typer.Option(
        None, "--image-ids", help="Comma-separated image IDs (show translations of their tags)"
    ),
    tags_csv: str | None = typer.Option(None, "--tags", help="Comma-separated tags"),
    missing_only: bool = typer.Option(
        False,
        "--missing-only",
        help=(
            "Emit only untranslated (tag, lang) pairs, one JSONL row each, in the shape "
            "accepted by `translations add --file` (fill in `text` and feed back)."
        ),
    ),
) -> None:
    """Show ja/en translation status for tags (read-only).

    画像のタグ (--image-ids) または指定タグ (--tags) の翻訳状況 (候補・主訳・missing) を
    表示します。読みは ja/japanese・en/english の表記ゆれを集約します。

    --missing-only (Issue #1211) は未翻訳の (tag, lang) ペアだけを 1 行 1 件で出力します。
    出力行は `text` を埋めるだけで `translations add --file` の入力に使えます。

    Example:
        lorairo-cli --json tags translations show -p proj --image-ids 1052,1082
        lorairo-cli --json tags translations show -p proj --tags "cat,dog"
        lorairo-cli --json tags translations show -p proj --image-ids 1033 --missing-only
    """
    with command_boundary():
        if bool(image_ids_csv) == bool(tags_csv):
            raise click.UsageError("--image-ids か --tags のどちらか一方を指定してください。")
        api_get_project(project)
        container = get_service_container()
        container.set_active_project(project)
        service = container.tag_management_service

        if tags_csv:
            _show_translations_for_tags(service, tags_csv, missing_only)
        else:
            _show_translations_for_images(container, service, image_ids_csv or "", missing_only)


def _missing_pair_items(
    entries: list[dict[str, object]], image_id: int | None = None
) -> list[dict[str, object]]:
    """未翻訳 (tag, lang) ペアを add --file round-trip 形式へ展開する (Issue #1211)。"""
    items: list[dict[str, object]] = []
    for entry in entries:
        missing = entry.get("missing", [])
        if not isinstance(missing, list):
            continue
        for lang in missing:
            item: dict[str, object] = {
                "tag": entry["tag"],
                "tag_id": entry["tag_id"],
                "lang": lang,
                "text": "",
            }
            if image_id is not None:
                item["image_id"] = image_id
            items.append(item)
    return items


def _emit_capped_missing_pairs(
    items: list[dict[str, object]], target_tags: int, extra_result: dict[str, object] | None = None
) -> None:
    """未翻訳ペアを `add --file` の上限 (MAX_TRANSLATION_TAGS) で cap して出力する (Codex P2)。

    show --missing-only の出力は 1 タグ最大 2 ペア (ja/en) 出るため、タグ数が上限近くだと
    ペア数が MAX_TRANSLATION_TAGS を超え、そのまま add --file に渡すと import が拒否する。
    上限で cap し、超過時は truncated=true + stderr 警告で明示する (silent 打ち切り回避)。
    残りは絞り込んで再実行する。
    """
    truncated = len(items) > MAX_TRANSLATION_TAGS
    capped = items[:MAX_TRANSLATION_TAGS]
    result_extra = dict(extra_result or {})
    if is_json_mode():
        for item in capped:
            emit_item(item)
        emit_result(
            f"{len(capped)} missing pair(s)" + (f" (truncated from {len(items)})" if truncated else ""),
            target_tags=target_tags,
            missing_pairs=len(capped),
            truncated=truncated,
            **result_extra,
        )
    else:
        for item in capped:
            console.print(f"{item['tag']} (tag_id={item['tag_id']}) missing={item['lang']}")
    if truncated:
        # stdout (add --file 入力) を汚さないよう警告は stderr へ。
        err_console.print(
            f"[yellow]警告:[/yellow] 未翻訳ペア {len(items)} 件を "
            f"add --file 上限 {MAX_TRANSLATION_TAGS} 件で打ち切り。絞り込んで再実行してください。"
        )


def _show_translations_for_tags(
    service: TagManagementService, tags_csv: str, missing_only: bool = False
) -> None:
    """--tags 指定の翻訳状況表示 (translations show の下請け)。"""
    tag_names = [t.strip() for t in tags_csv.split(",") if t.strip()]
    if not tag_names:
        raise click.UsageError("--tags に有効な値がありません。")
    if len(tag_names) > MAX_TRANSLATION_TAGS:
        raise click.UsageError(f"--tags は最大 {MAX_TRANSLATION_TAGS} 件まで。")
    entries = _translation_status_entries(service, tag_names)
    if missing_only:
        _emit_capped_missing_pairs(_missing_pair_items(entries), target_tags=len(entries))
        return
    if is_json_mode():
        for entry in entries:
            emit_item(entry)
        emit_result(f"{len(entries)} tag(s)", target_tags=len(entries))
    else:
        for entry in entries:
            console.print(f"{entry['tag']} (tag_id={entry['tag_id']}) missing={entry['missing']}")


def _dedup_image_tag_names(tag_rows: list[dict[str, object]]) -> list[str]:
    """画像 1 件の tag 行から重複タグ文字列を初出優先で畳んだ tag 名リストを返す。"""
    seen: set[str] = set()
    tag_names: list[str] = []
    for row in tag_rows:
        name = row.get("tag")
        if isinstance(name, str) and name and name not in seen:
            seen.add(name)
            tag_names.append(name)
    return tag_names


def _emit_image_translation_entries(image_id: int, entries: list[dict[str, object]]) -> None:
    """通常表示 (画像単位ラッパー) の 1 画像分を出力する。"""
    if is_json_mode():
        emit_item({"image_id": image_id, "tags": entries})
    else:
        console.print(f"[bold]Image {image_id}[/bold]")
        for entry in entries:
            console.print(f"  {entry['tag']} (tag_id={entry['tag_id']}) missing={entry['missing']}")


def _show_missing_pairs_for_images(
    service: TagManagementService,
    image_ids: list[int],
    annotations_by_id: dict[int, dict[str, object]],
) -> None:
    """--image-ids + --missing-only の未翻訳ペア出力 (全画像横断で (tag, lang) 重複排除)。

    翻訳はタグ単位 (画像非依存) で `add --file` も image_id を無視するため、複数画像が
    同じ未翻訳タグを共有しても (tag, lang) は 1 回だけ出す (Codex P2)。

    全画像の unique tag を先に集約し、翻訳解決 (`_translation_status_entries` =
    translation_status_batch) を **1 回だけ**行う (Codex P2)。画像ごとに解決すると、
    同じタグを共有する数百画像で数百回の tag DB 検索が走り、本 workflow が回避したい
    多分単位の検索経路を再現してしまう。各タグの初出 image_id を参照として残す。
    """
    # 全画像の unique tag を集約し、初出 image_id を記録する。
    tag_first_image: dict[str, int] = {}
    for image_id in image_ids:
        tag_rows = annotations_by_id.get(image_id, {}).get("tags", [])
        for name in _dedup_image_tag_names(tag_rows if isinstance(tag_rows, list) else []):
            tag_first_image.setdefault(name, image_id)

    # 解決は 1 回だけ。entries は tag 単位で一意なので (tag, lang) の重複は構造的に無い。
    entries = _translation_status_entries(service, list(tag_first_image))
    deduped: list[dict[str, object]] = []
    for entry in entries:
        first_image = tag_first_image.get(str(entry["tag"]))
        deduped.extend(_missing_pair_items([entry], image_id=first_image))
    # add --file 上限で cap する (Codex P2)。超過時は truncated=true + stderr 警告。
    _emit_capped_missing_pairs(
        deduped, target_tags=len(entries), extra_result={"target_images": len(image_ids)}
    )


def _show_translations_for_images(
    container: ServiceContainer,
    service: TagManagementService,
    image_ids_csv: str,
    missing_only: bool = False,
) -> None:
    """--image-ids 指定の翻訳状況表示 (translations show の下請け)。"""
    image_ids = parse_image_ids(image_ids_csv)
    if not image_ids:
        raise click.UsageError("--image-ids に有効な値がありません。")
    if len(image_ids) > MAX_IMAGE_IDS:
        raise click.UsageError(f"--image-ids は最大 {MAX_IMAGE_IDS} 件まで。")
    validate_image_ids_exist(container, image_ids)

    annotations_by_id = container.db_manager.image_repo.get_image_annotations_batch(image_ids)
    if missing_only:
        _show_missing_pairs_for_images(service, image_ids, annotations_by_id)
        return

    total_tags = 0
    for image_id in image_ids:
        tag_rows = annotations_by_id.get(image_id, {}).get("tags", [])
        tag_names = _dedup_image_tag_names(tag_rows)
        entries = _translation_status_entries(service, tag_names)
        total_tags += len(entries)
        _emit_image_translation_entries(image_id, entries)
    if is_json_mode():
        emit_result(
            f"{len(image_ids)} image(s), {total_tags} tag(s)",
            target_images=len(image_ids),
            target_tags=total_tags,
        )


def _write_translation(
    container: ServiceContainer,
    tag: str,
    tag_id: int | None,
    lang: str,
    text_value: str,
    preferred: bool,
) -> tuple[int, bool]:
    """翻訳 1 件を user DB へ書き込む (apply 時の下請け、Issue #1211 でバッチと共有)。

    Returns:
        (書き込んだ tag_id, 新規 user タグを登録したか)。

    Raises:
        DatabaseError: 未登録タグの user DB 登録に失敗した場合。
    """
    annotation_repo = container.db_manager.annotation_repo
    registered = False
    if tag_id is None:
        # 真の新タグは #1174 と同経路で user DB (format 1000+) へ登録
        tag_id = annotation_repo.register_user_tag(tag)
        registered = tag_id is not None
        if tag_id is None:
            # tagdb #124 edge 等: 静かに落とさず DB_ERROR で明示する
            raise DatabaseError(
                f"タグ '{tag}' の user DB 登録に失敗したため翻訳を追加できません (tag_id=null)。"
            )
    service = container.tag_management_service
    if preferred:
        # 書き込み + 主訳化 (write_user_translation + set_preferred_translation)
        service.add_translation(tag_id, lang, text_value)
    else:
        from genai_tag_db_tools import write_user_translation

        write_user_translation(service.repository, tag_id, lang, text_value)
    return tag_id, registered


def _parse_translation_line(
    line: str, line_no: int, default_preferred: bool = False
) -> dict[str, object] | None:
    """`translations add --file` の JSONL 1 行を検証済み request へ変換する (Issue #1211)。

    `show --missing-only --json` の出力をそのまま保存すると、item 行の後に
    `kind=result` (終端サマリ) 行も含まれる。これを request と誤解しないよう、
    `kind` が item 以外 (result/error) の行はスキップする (None を返す、Codex P2)。

    `preferred` を省いた行は、コマンドの `--preferred` フラグ (default_preferred) を
    既定とする (Codex P2: --file と --preferred を併用しても行に preferred が無いと
    無視されるのは驚き)。

    Returns:
        検証済み request。スキップ対象 (kind=result/error) の行は None。

    Raises:
        click.UsageError: JSON 不正・object 以外・必須キー欠落・非対応言語・空 text。
    """
    try:
        row = json.loads(line)
    except json.JSONDecodeError as e:
        raise click.UsageError(f"--file {line_no} 行目が JSON として不正です: {e}") from e
    if not isinstance(row, dict):
        raise click.UsageError(f"--file {line_no} 行目は JSON object ではありません。")
    # show --missing-only --json の終端 result 行 (や error 行) はスキップする。
    kind = row.get("kind")
    if kind in ("result", "error"):
        return None
    tag = str(row.get("tag") or "").strip()
    lang = str(row.get("lang") or "").strip()
    text = str(row.get("text") or "").strip()
    if not tag:
        raise click.UsageError(f"--file {line_no} 行目: 'tag' がありません。")
    if lang not in _SUPPORTED_LANGS:
        raise click.UsageError(
            f"--file {line_no} 行目: 'lang' は {'/'.join(_SUPPORTED_LANGS)} のみ対応です。"
        )
    if not text:
        raise click.UsageError(f"--file {line_no} 行目: 'text' が空です (翻訳を埋めてください)。")
    # preferred は JSON boolean のみ許容する (Codex P2)。"false" 等の文字列を bool() で
    # 強制すると非空文字列が True 扱いになり、行が false でも主訳化されてしまう。
    if "preferred" in row and not isinstance(row["preferred"], bool):
        raise click.UsageError(
            f"--file {line_no} 行目: 'preferred' は true/false (JSON boolean) で指定してください。"
        )
    preferred = bool(row["preferred"]) if "preferred" in row else default_preferred
    return {"tag": tag, "lang": lang, "text": text, "preferred": preferred}


def _parse_translation_file(file_path: str, default_preferred: bool = False) -> list[dict[str, object]]:
    """`translations add --file` の JSONL 入力を読み込み検証する (Issue #1211)。

    各行は ``{"tag": str, "lang": "ja"|"en", "text": str}`` (+任意 ``"preferred": bool``)。
    `translations show --missing-only` の出力行 (余分な ``tag_id`` / ``image_id`` キー付き)
    をそのまま text だけ埋めて渡せる。``preferred`` を省いた行は default_preferred
    (コマンドの --preferred フラグ) を既定にする (Codex P2)。

    Raises:
        click.UsageError: JSON 不正・必須キー欠落・非対応言語・空 text・件数超過。
    """
    path = Path(file_path)
    if not path.is_file():
        raise click.UsageError(f"--file '{file_path}' が見つかりません。")
    requests: list[dict[str, object]] = []
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parsed = _parse_translation_line(line, line_no, default_preferred)
        if parsed is not None:  # kind=result/error 行はスキップ
            requests.append(parsed)
    if not requests:
        raise click.UsageError("--file に有効な行がありません。")
    if len(requests) > MAX_TRANSLATION_TAGS:
        raise click.UsageError(f"--file は最大 {MAX_TRANSLATION_TAGS} 行まで。")
    return requests


def _add_translations_batch(
    container: ServiceContainer, requests: list[dict[str, object]], dry_run: bool
) -> None:
    """--file バッチ入力の翻訳追加 (translations add の下請け、Issue #1211)。

    単発 (--tag) と違い typo/曖昧/登録失敗で全体を中断せず、per-item の status で
    surface して続行する。既に同一訳が存在する行はスキップする (再実行が冪等)。
    """
    annotation_repo = container.db_manager.annotation_repo
    service = container.tag_management_service

    unique_tags = list({str(r["tag"]): None for r in requests})
    classifications = {t: annotation_repo.classify_manual_tag(t) for t in unique_tags}
    # 既存訳チェックは解決後の canonical tag で行う (Codex P2)。alias 行は preferred タグへ
    # 書き込むため、raw タグの翻訳を見ると preferred 側の既存訳を取りこぼし、再実行で
    # skipped_existing にならず changed を出し続ける。canonical で status を引く。
    canonical_tags = list({c.canonical_tag for c in classifications.values()})
    statuses = service.translation_status_batch(canonical_tags, languages=_SUPPORTED_LANGS)

    counts = {"changed": 0, "dry_run": 0, "skipped_existing": 0, "skipped_candidates": 0, "error": 0}
    for req in requests:
        tag = str(req["tag"])
        lang = str(req["lang"])
        text_value = str(req["text"])
        preferred = bool(req["preferred"])
        c = classifications[tag]
        payload: dict[str, object] = {
            "tag": tag,
            "canonical_tag": c.canonical_tag,
            "classification": c.classification,
            "tag_id": c.tag_id,
            "language": lang,
            "translation": text_value,
            "preferred": preferred,
            "registered_new_tag": False,
        }
        if c.classification == "invalid":
            payload["status"] = "skipped_invalid"
            counts["error"] += 1
        elif c.tag_id is None and c.classification in ("typo_candidate", "ambiguous"):
            payload["status"] = "skipped_candidates"
            payload["candidates"] = c.candidates
            counts["skipped_candidates"] += 1
        else:
            status = statuses.get(c.canonical_tag)
            existing, current_preferred = (
                status.by_language.get(lang, ([], None)) if status is not None else ([], None)
            )
            already_exists = text_value in existing
            # preferred=true で既存訳だが未だ主訳でないなら promote する (単発 --preferred と
            # 同じ挙動、Codex P2)。skip すると主訳昇格が無言で無視される。
            needs_promotion = preferred and already_exists and text_value != current_preferred
            if already_exists and not needs_promotion:
                payload["status"] = "skipped_existing"
                counts["skipped_existing"] += 1
            elif dry_run:
                payload["status"] = "dry_run"
                counts["dry_run"] += 1
            else:
                try:
                    tag_id, registered = _write_translation(
                        container, tag, c.tag_id, lang, text_value, preferred
                    )
                    payload["tag_id"] = tag_id
                    payload["registered_new_tag"] = registered
                    payload["status"] = "changed"
                    counts["changed"] += 1
                except DatabaseError as e:
                    payload["status"] = "error"
                    payload["error"] = str(e)
                    counts["error"] += 1
        if is_json_mode():
            emit_item(payload)
        else:
            console.print(f"[{payload['status']}] {tag} ({lang}) ← '{text_value}'")

    message = (
        f"{'[dry-run] ' if dry_run else ''}Batch translations "
        f"{'planned' if dry_run else 'processed'}: {len(requests)} request(s)"
    )
    if is_json_mode():
        emit_result(
            message,
            dry_run=dry_run,
            total=len(requests),
            changed=counts["changed"],
            would_add=counts["dry_run"] if dry_run else None,
            skipped_existing=counts["skipped_existing"],
            skipped_candidates=counts["skipped_candidates"],
            errors=counts["error"],
        )
    else:
        console.print(f"{'[dry-run] ' if dry_run else ''}{OK} {len(requests)} 件処理: {counts}")


@trans_app.command("add")
def translations_add(
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    tag: str | None = typer.Option(None, "--tag", help="Target tag (canonical or new)"),
    lang: str | None = typer.Option(None, "--lang", help="Language key: ja | en"),
    text: str | None = typer.Option(None, "--text", help="Translation text"),
    file: str | None = typer.Option(
        None,
        "--file",
        help=(
            'JSONL batch input: one {"tag", "lang", "text"[, "preferred"]} per line '
            "(accepts `translations show --missing-only` rows with `text` filled in)."
        ),
    ),
    preferred: bool = typer.Option(
        False, "--preferred", help="Set this translation as the preferred one for the language"
    ),
    apply: bool = typer.Option(False, "--apply", help="Write to user DB (default: dry-run)"),
) -> None:
    """Add translations to tags (user DB overlay, dry-run by default).

    tag_id の解決は `tags add` (Issue #1174) と同じ経路: 完全一致/既知 alias は解決、
    真の新タグは --apply 時に user DB へ登録します。typo/曖昧候補があるタグは登録せず
    候補を提示します (`tags alias` で確定してから再実行)。

    --file (Issue #1211) は JSONL バッチ入力で 1 プロセス N 件を書き込みます。
    typo/曖昧・既存訳・登録失敗の行は per-item status でスキップ/報告して続行します
    (単発 --tag はこれまで通りエラーで中断)。

    Example:
        lorairo-cli tags translations add -p proj --tag "european architecture" \\
            --lang ja --text "ヨーロッパ建築" --preferred --apply
        lorairo-cli --json tags translations add -p proj --file translations.jsonl --apply
    """
    with command_boundary():
        if file is not None and (tag is not None or lang is not None or text is not None):
            raise click.UsageError("--file と --tag/--lang/--text は同時に指定できません。")
        if file is None and (tag is None or lang is None or text is None):
            raise click.UsageError("--tag/--lang/--text の3つ、または --file を指定してください。")

        dry_run = not apply

        if file is not None:
            # --preferred は preferred を省いた行の既定にする (Codex P2)。
            requests = _parse_translation_file(file, default_preferred=preferred)
            api_get_project(project)
            container = get_service_container()
            container.set_active_project(project)
            _add_translations_batch(container, requests, dry_run)
            return

        assert tag is not None and lang is not None and text is not None
        if lang not in _SUPPORTED_LANGS:
            raise click.UsageError(f"--lang は {'/'.join(_SUPPORTED_LANGS)} のみ対応です。")
        text_value = text.strip()
        if not text_value:
            raise click.UsageError("--text に有効な値がありません。")
        api_get_project(project)
        container = get_service_container()
        container.set_active_project(project)
        annotation_repo = container.db_manager.annotation_repo

        classification = annotation_repo.classify_manual_tag(tag)
        if classification.classification == "invalid":
            raise click.UsageError(f"--tag '{tag}' は正規化後に空になるため対象にできません。")
        if classification.tag_id is None and classification.classification in (
            "typo_candidate",
            "ambiguous",
        ):
            raise click.UsageError(
                f"--tag '{tag}' は未登録で類似候補があります: {classification.candidates}。"
                "正タグへ翻訳を付けるか、`tags alias` で確定してから再実行してください。"
            )

        tag_id = classification.tag_id
        registered = False
        if not dry_run:
            tag_id, registered = _write_translation(container, tag, tag_id, lang, text_value, preferred)

        payload = {
            "tag": tag,
            "canonical_tag": classification.canonical_tag,
            "classification": classification.classification,
            "tag_id": tag_id,
            "language": lang,
            "translation": text_value,
            "preferred": preferred,
            "registered_new_tag": registered,
            "status": "dry_run" if dry_run else "changed",
        }
        if is_json_mode():
            emit_item(payload)
            emit_result(
                f"{'[dry-run] ' if dry_run else ''}Translation {'planned' if dry_run else 'added'}",
                dry_run=dry_run,
                tag_id=tag_id,
                language=lang,
            )
        else:
            prefix = "[dry-run] " if dry_run else ""
            console.print(
                f"{prefix}{OK} '{classification.canonical_tag}' ({lang}) ← '{text_value}'"
                f"{' [主訳]' if preferred else ''}{'を追加予定' if dry_run else ' を追加完了'}"
            )


@app.command("alias")
def alias_tag(
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    from_tag: str = typer.Option(..., "--from", help="Alias source (e.g. typo spelling)"),
    to_tag: str = typer.Option(..., "--to", help="Preferred tag to resolve to (must exist)"),
    apply: bool = typer.Option(False, "--apply", help="Write to user DB (default: dry-run)"),
) -> None:
    """Record an alias (typo → preferred tag) in the user DB (dry-run by default).

    `tags add` の分類 (Issue #1174) で surface された typo 候補を人間/エージェントが
    確定させる導線です。typo の自動 alias 化はしません。

    Example:
        lorairo-cli tags alias -p proj --from "europian architecture" \\
            --to "european architecture" --apply
    """
    with command_boundary():
        api_get_project(project)
        container = get_service_container()
        container.set_active_project(project)
        annotation_repo = container.db_manager.annotation_repo

        to_cls = annotation_repo.classify_manual_tag(to_tag)
        if to_cls.tag_id is None:
            raise click.UsageError(
                f"--to '{to_tag}' が tag DB に見つかりません。alias 先は既存タグを指定してください。"
            )
        from_cls = annotation_repo.classify_manual_tag(from_tag)
        if from_cls.classification == "invalid":
            raise click.UsageError(f"--from '{from_tag}' は正規化後に空になるため登録できません。")
        if from_cls.tag_id is not None:
            if from_cls.canonical_tag == to_cls.canonical_tag:
                # 既に同じ preferred へ解決される → 冪等 no-op
                if is_json_mode():
                    emit_result(
                        "Alias already resolves to the preferred tag (no-op)",
                        dry_run=not apply,
                        from_tag=from_tag,
                        to_tag=to_cls.canonical_tag,
                        status="noop",
                    )
                else:
                    console.print(f"{OK} '{from_tag}' は既に '{to_cls.canonical_tag}' へ解決されます")
                return
            raise click.UsageError(
                f"--from '{from_tag}' は既存タグ (tag_id={from_cls.tag_id}, "
                f"canonical='{from_cls.canonical_tag}') です。既存タグの付け替えは CLI では行いません。"
            )

        dry_run = not apply
        alias_tag_id: int | None = None
        if not dry_run:
            alias_tag_id = annotation_repo.register_user_alias(from_tag, to_cls.canonical_tag)
            if alias_tag_id is None:
                raise DatabaseError(f"alias 登録に失敗しました: '{from_tag}' → '{to_cls.canonical_tag}'")

        if is_json_mode():
            emit_result(
                f"{'[dry-run] ' if dry_run else ''}Alias {'planned' if dry_run else 'recorded'}",
                dry_run=dry_run,
                from_tag=from_tag,
                to_tag=to_cls.canonical_tag,
                alias_tag_id=alias_tag_id,
                status="dry_run" if dry_run else "changed",
            )
        else:
            prefix = "[dry-run] " if dry_run else ""
            console.print(
                f"{prefix}{OK} alias '{from_tag}' → '{to_cls.canonical_tag}' を"
                f"{'登録予定' if dry_run else '登録完了'}"
            )
