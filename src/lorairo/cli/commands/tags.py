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
) -> None:
    """Show ja/en translation status for tags (read-only).

    画像のタグ (--image-ids) または指定タグ (--tags) の翻訳状況 (候補・主訳・missing) を
    表示します。読みは ja/japanese・en/english の表記ゆれを集約します。

    Example:
        lorairo-cli --json tags translations show -p proj --image-ids 1052,1082
        lorairo-cli --json tags translations show -p proj --tags "cat,dog"
    """
    with command_boundary():
        if bool(image_ids_csv) == bool(tags_csv):
            raise click.UsageError("--image-ids か --tags のどちらか一方を指定してください。")
        api_get_project(project)
        container = get_service_container()
        container.set_active_project(project)
        service = container.tag_management_service

        if tags_csv:
            _show_translations_for_tags(service, tags_csv)
        else:
            _show_translations_for_images(container, service, image_ids_csv or "")


def _show_translations_for_tags(service: TagManagementService, tags_csv: str) -> None:
    """--tags 指定の翻訳状況表示 (translations show の下請け)。"""
    tag_names = [t.strip() for t in tags_csv.split(",") if t.strip()]
    if not tag_names:
        raise click.UsageError("--tags に有効な値がありません。")
    if len(tag_names) > MAX_TRANSLATION_TAGS:
        raise click.UsageError(f"--tags は最大 {MAX_TRANSLATION_TAGS} 件まで。")
    entries = _translation_status_entries(service, tag_names)
    if is_json_mode():
        for entry in entries:
            emit_item(entry)
        emit_result(f"{len(entries)} tag(s)", target_tags=len(entries))
    else:
        for entry in entries:
            console.print(f"{entry['tag']} (tag_id={entry['tag_id']}) missing={entry['missing']}")


def _show_translations_for_images(
    container: ServiceContainer, service: TagManagementService, image_ids_csv: str
) -> None:
    """--image-ids 指定の翻訳状況表示 (translations show の下請け)。"""
    image_ids = parse_image_ids(image_ids_csv)
    if not image_ids:
        raise click.UsageError("--image-ids に有効な値がありません。")
    if len(image_ids) > MAX_IMAGE_IDS:
        raise click.UsageError(f"--image-ids は最大 {MAX_IMAGE_IDS} 件まで。")
    validate_image_ids_exist(container, image_ids)

    annotations_by_id = container.db_manager.image_repo.get_image_annotations_batch(image_ids)
    total_tags = 0
    for image_id in image_ids:
        tag_rows = annotations_by_id.get(image_id, {}).get("tags", [])
        # 同一画像内の重複タグ文字列は初出優先で畳む
        seen: set[str] = set()
        tag_names = []
        for row in tag_rows:
            name = row.get("tag")
            if name and name not in seen:
                seen.add(name)
                tag_names.append(name)
        entries = _translation_status_entries(service, tag_names)
        total_tags += len(entries)
        if is_json_mode():
            emit_item({"image_id": image_id, "tags": entries})
        else:
            console.print(f"[bold]Image {image_id}[/bold]")
            for entry in entries:
                console.print(f"  {entry['tag']} (tag_id={entry['tag_id']}) missing={entry['missing']}")
    if is_json_mode():
        emit_result(
            f"{len(image_ids)} image(s), {total_tags} tag(s)",
            target_images=len(image_ids),
            target_tags=total_tags,
        )


@trans_app.command("add")
def translations_add(
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    tag: str = typer.Option(..., "--tag", help="Target tag (canonical or new)"),
    lang: str = typer.Option(..., "--lang", help="Language key: ja | en"),
    text: str = typer.Option(..., "--text", help="Translation text"),
    preferred: bool = typer.Option(
        False, "--preferred", help="Set this translation as the preferred one for the language"
    ),
    apply: bool = typer.Option(False, "--apply", help="Write to user DB (default: dry-run)"),
) -> None:
    """Add a translation to a tag (user DB overlay, dry-run by default).

    tag_id の解決は `tags add` (Issue #1174) と同じ経路: 完全一致/既知 alias は解決、
    真の新タグは --apply 時に user DB へ登録します。typo/曖昧候補があるタグは登録せず
    候補を提示します (`tags alias` で確定してから再実行)。

    Example:
        lorairo-cli tags translations add -p proj --tag "european architecture" \\
            --lang ja --text "ヨーロッパ建築" --preferred --apply
    """
    with command_boundary():
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

        dry_run = not apply
        tag_id = classification.tag_id
        registered = False
        if not dry_run:
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
