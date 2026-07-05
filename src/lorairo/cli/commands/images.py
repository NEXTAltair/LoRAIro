"""Image management commands.

画像の登録、メタデータ更新などの画像管理コマンド。
API層（lorairo.public_api）を経由してService層を利用する。

出力は ADR 0057/0058 に従う: ``--json`` 時は stdout に JSONL (item/result)、
それ以外は rich 人間向け。エラー整形は :func:`lorairo.cli._boundary.command_boundary`
に集約する。
"""

import json
import sys
from pathlib import Path
from typing import Literal

import click
import typer
from pydantic import BaseModel, Field, ValidationError
from rich.table import Table

from lorairo.cli._boundary import command_boundary
from lorairo.cli._console import make_console
from lorairo.cli._emit import emit_item, emit_result
from lorairo.cli._glyphs import OK
from lorairo.cli._image_ids import MAX_IMAGE_IDS, parse_image_ids, validate_image_ids_exist
from lorairo.cli._output_mode import is_json_mode
from lorairo.database.filter_criteria import ImageFilterCriteria
from lorairo.database.repository.annotation_record import AnnotationRepository
from lorairo.public_api.exceptions import ImageNotFoundError, ResultSetTooLargeError
from lorairo.public_api.images import register_images as api_register_images
from lorairo.public_api.project import get_project as api_get_project
from lorairo.public_api.types import RegistrationResult
from lorairo.services.service_container import get_service_container

# サブコマンドアプリ定義
app = typer.Typer(help="Image management commands")

# Rich console (Issue #254: Windows では safe_box=True で ASCII 罫線)
console = make_console()

MAX_IMAGE_LIST_FETCH = 500


class _SortSpec(BaseModel):
    """images search JSON スキーマのソート指定。"""

    field: Literal["image_id", "file_path"] = "image_id"
    direction: Literal["asc", "desc"] = "asc"


class ImageSearchQuery(BaseModel):
    """images search コマンドが受け付ける JSON 検索スキーマ。"""

    image_ids: list[int] | None = None
    tags: list[str] | None = None
    excluded_tags: list[str] | None = None
    caption: str | None = None
    manual_rating: str | None = None
    ai_rating: str | None = None
    score_min: float | None = None
    score_max: float | None = None
    only_unrated: bool = False
    missing_model: str | None = None
    include_nsfw: bool = False
    limit: int = Field(default=500, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    sort: list[_SortSpec] = Field(default_factory=lambda: [_SortSpec()])


def _print_registration_summary(result: RegistrationResult, project: str) -> None:
    """画像登録結果のサマリーを表示する。

    Args:
        result: 登録結果
        project: プロジェクト名
    """
    console.print("\n[bold]Registration Summary[/bold]")
    table = Table(show_header=False)
    table.add_row("Total", f"{result.total}")
    table.add_row("Registered", f"[green]{result.successful}[/green]")
    table.add_row("Skipped (duplicates)", f"[yellow]{result.skipped}[/yellow]")
    table.add_row("Errors", f"[red]{result.failed}[/red]")
    console.print(table)

    if result.error_details:
        console.print("\n[yellow]Error details:[/yellow]")
        for err in result.error_details:
            console.print(f"  - {err}")

    if result.successful > 0:
        console.print(f"\n[green]{OK}[/green] Images registered to project: {project}")


def _apply_tags_to_images(
    repository: AnnotationRepository,
    image_ids: list[int],
    tag_list: list[str],
) -> tuple[int, list[str]]:
    """画像リストにタグを追加し、(追加数, 失敗タグリスト)を返す。

    Args:
        repository: 画像リポジトリ
        image_ids: 対象画像IDのリスト
        tag_list: 追加するタグのリスト

    Returns:
        (追加されたタグ件数, 失敗したタグのリスト)
    """
    total_added = 0
    failed_tags: list[str] = []
    for tag in tag_list:
        success, added = repository.add_tag_to_images_batch(image_ids, tag, None)
        if success:
            total_added += added
        else:
            failed_tags.append(tag)
    return total_added, failed_tags


def _print_update_summary(
    project: str,
    target_count: int,
    tag_list: list[str],
    total_added: int,
    failed_tags: list[str],
) -> None:
    """画像更新結果のサマリーを表示する。

    Args:
        project: プロジェクト名
        target_count: 対象画像数
        tag_list: 追加リクエストしたタグのリスト
        total_added: 実際に追加されたタグ件数
        failed_tags: 追加に失敗したタグのリスト
    """
    console.print("\n[bold]Update Summary[/bold]")
    table = Table(show_header=False)
    table.add_row("Project", project)
    table.add_row("Target images", str(target_count))
    table.add_row("Tags requested", ", ".join(tag_list))
    table.add_row("Tag assignments added", f"[green]{total_added}[/green]")
    if failed_tags:
        table.add_row("Failed tags", f"[red]{', '.join(failed_tags)}[/red]")
    console.print(table)

    if not failed_tags:
        console.print(f"\n[green]{OK}[/green] Updated {target_count} image(s) in project: {project}")


@app.command("register")
def register(
    path: str = typer.Argument(
        ...,
        help="Image file or directory path",
    ),
    project: str = typer.Option(
        ...,
        "--project",
        "-p",
        help="Project name",
    ),
    skip_duplicates: bool = typer.Option(
        True,
        "--skip-duplicates/--include-duplicates",
        help="Skip duplicate images (detected by pHash)",
    ),
) -> None:
    """Register images from file or directory to project.

    画像ファイルまたはディレクトリからプロジェクトへ画像を登録します。
    pHashを計算して重複検出を行います。
    """
    with command_boundary():
        input_path = Path(path).resolve()

        # パス存在確認 (FileNotFoundError → IO_ERROR exit 1)
        if not input_path.exists():
            raise FileNotFoundError(f"Path not found: {path}")
        if not input_path.is_file() and not input_path.is_dir():
            raise FileNotFoundError(f"Not a file or directory: {path}")

        # プロジェクト存在確認 (未存在は ProjectNotFoundError → NOT_FOUND で伝播)
        api_get_project(project)
        get_service_container().set_active_project(project)

        # API層経由で画像登録（プロジェクトコンテキスト付き）
        result = api_register_images(input_path, skip_duplicates, project_name=project)

        if result.total == 0:
            if is_json_mode():
                emit_result(
                    f"No image files found in {path}",
                    total=0,
                    registered=0,
                    skipped=0,
                    errors=0,
                )
            else:
                console.print(f"[yellow]Warning:[/yellow] No image files found in {path}")
            return

        if is_json_mode():
            emit_result(
                f"Registered {result.successful} image(s) to project: {project}",
                total=result.total,
                registered=result.successful,
                skipped=result.skipped,
                errors=result.failed,
                error_details=list(result.error_details) if result.error_details else [],
            )
        else:
            _print_registration_summary(result, project)


@app.command("list")
def list_images(
    project: str = typer.Option(
        ...,
        "--project",
        "-p",
        help="Project name",
    ),
    fetch: bool = typer.Option(
        False,
        "--fetch",
        help="Fetch image_id and file_path rows. Without this flag only the matching count is shown.",
    ),
    limit: int = typer.Option(
        MAX_IMAGE_LIST_FETCH,
        "--limit",
        "-l",
        max=MAX_IMAGE_LIST_FETCH,
        min=1,
        help=f"Maximum number of image rows to fetch (1-{MAX_IMAGE_LIST_FETCH})",
    ),
    offset: int = typer.Option(
        0,
        "--offset",
        min=0,
        help="Number of matching images to skip before fetching rows.",
    ),
    unrated: bool = typer.Option(
        False,
        "--unrated",
        help="Show only images without any saved rating rows.",
    ),
) -> None:
    """List images in a project.

    プロジェクトに登録されている画像の一覧を表示します (``--json`` で JSONL)。
    """
    with command_boundary():
        api_get_project(project)

        container = get_service_container()
        container.set_active_project(project)

        repository = container.db_manager.image_repo
        count_criteria = ImageFilterCriteria(include_nsfw=True, only_unrated=unrated)
        total_count = repository.get_images_count_only(count_criteria)

        if not fetch:
            suffix = " without ratings" if unrated else ""
            message = f"{total_count} image(s){suffix} found in project: {project}"
            if is_json_mode():
                # count = この応答の item 行数、total = 総ヒット数 に語義を統一する (#664)。
                # count-first は item を出さないため count=0、件数は total に載せる。
                emit_result(message, count=0, total=total_count)
            else:
                console.print(message)
            return

        if total_count > MAX_IMAGE_LIST_FETCH:
            raise ResultSetTooLargeError(matched=total_count, limit=MAX_IMAGE_LIST_FETCH)

        fetch_criteria = ImageFilterCriteria(
            include_nsfw=True,
            only_unrated=unrated,
            limit=limit,
            offset=offset,
        )
        image_records, total_count = repository.get_image_list_page(fetch_criteria)
        count = len(image_records)
        has_more = offset + count < total_count

        if is_json_mode():
            for record in image_records:
                emit_item(
                    {
                        "image_id": record.get("image_id"),
                        "file_path": record.get("file_path"),
                    }
                )
            emit_result(
                f"{count} image(s)",
                count=count,
                total=total_count,
                limit=limit,
                offset=offset,
                has_more=has_more,
            )
            return

        for record in image_records:
            print(f"{record.get('image_id')}\t{record.get('file_path')}")


@app.command("update")
def update(
    project: str = typer.Option(
        ...,
        "--project",
        "-p",
        help="Project name",
    ),
    tags: str | None = typer.Option(
        None,
        "--tags",
        help="Tags to add (comma-separated)",
    ),
    image_id: int | None = typer.Option(
        None,
        "--image-id",
        help="Target specific image by ID",
    ),
) -> None:
    """Add tags to images in a project.

    プロジェクト内の画像にタグを追加します。
    --image-id を指定すると特定の1枚のみ更新します。
    指定しない場合はプロジェクト全画像が対象です。

    Example:
        lorairo-cli images update --project myproject --tags "cat,dog"
    """
    with command_boundary():
        if not tags:
            raise click.UsageError('At least one update operation is required. Example: --tags "tag1,tag2"')

        api_get_project(project)

        container = get_service_container()
        container.set_active_project(project)
        image_repo = container.db_manager.image_repo
        annotation_repo = container.db_manager.annotation_repo

        if image_id is not None:
            metadata = image_repo.get_image_metadata(image_id)
            if metadata is None:
                raise ImageNotFoundError(image_id)
            image_ids: list[int] = [image_id]
        else:
            criteria = ImageFilterCriteria(include_nsfw=True)
            image_records, _total = image_repo.get_images_by_filter(criteria)
            if not image_records:
                if is_json_mode():
                    emit_result(f"No images found in project: {project}", count=0)
                else:
                    console.print(f"[yellow]Warning:[/yellow] No images found in project: {project}")
                return
            image_ids = [int(r["id"]) for r in image_records]

        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        if not tag_list:
            raise click.UsageError("No valid tags specified.")

        total_added, failed_tags = _apply_tags_to_images(annotation_repo, image_ids, tag_list)

        if is_json_mode():
            emit_result(
                f"Updated {len(image_ids)} image(s) in project: {project}",
                project=project,
                target_images=len(image_ids),
                tags=tag_list,
                added=total_added,
                failed_tags=failed_tags,
            )
        else:
            _print_update_summary(
                project=project,
                target_count=len(image_ids),
                tag_list=tag_list,
                total_added=total_added,
                failed_tags=failed_tags,
            )

        # 一部タグが失敗した場合は exit 1 (部分失敗を exit code で示す)。
        if failed_tags:
            raise typer.Exit(code=1)


@app.command("search")
def search_images(
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    query_file: str | None = typer.Option(None, "--query-file", help="Path to JSON search schema file"),
    query: str | None = typer.Option(None, "--query", help="JSON search schema string or '-' for stdin"),
) -> None:
    """Search images using a JSON search schema (read-only).

    JSON 検索スキーマを受け取り、条件に合う画像を返します（副作用なし）。

    Examples:

        lorairo-cli images search --project proj --query-file search.json --json

        echo '{"tags":["cat"]}' | lorairo-cli images search --project proj --query - --json
    """
    with command_boundary():
        if query_file is None and query is None:
            raise click.UsageError("--query-file または --query - のいずれかを指定してください。")
        if query_file is not None and query is not None:
            raise click.UsageError("--query-file と --query は同時に指定できません。")

        try:
            if query_file is not None:
                raw = Path(query_file).read_text(encoding="utf-8")
            else:
                raw = sys.stdin.read() if query == "-" else (query or "")
            parsed = json.loads(raw)
        except (OSError, json.JSONDecodeError) as e:
            raise click.UsageError(f"JSON 読み込みエラー: {e}") from e

        try:
            q = ImageSearchQuery.model_validate(parsed)
        except ValidationError as e:
            raise click.UsageError(f"検索スキーマが無効です: {e}") from e

        api_get_project(project)
        container = get_service_container()
        container.set_active_project(project)

        sort_spec = q.sort[0] if q.sort else _SortSpec()
        criteria = ImageFilterCriteria(
            image_ids=q.image_ids,
            tags=q.tags,
            excluded_tags=q.excluded_tags,
            # ImageFilterCriteria.caption はキーワードリスト (#1093)。単一キャプション文字列を包む
            caption=[q.caption] if q.caption else None,
            manual_rating_filter=q.manual_rating,
            ai_rating_filter=q.ai_rating,
            score_min=q.score_min,
            score_max=q.score_max,
            only_unrated=q.only_unrated,
            missing_model_litellm_id=q.missing_model,
            include_nsfw=q.include_nsfw,
            limit=q.limit,
            offset=q.offset,
            sort_field=sort_spec.field,
            sort_direction=sort_spec.direction,
        )

        total_count = container.db_manager.image_repo.get_images_count_only(criteria)
        if total_count > MAX_IMAGE_LIST_FETCH and criteria.image_ids is None:
            raise ResultSetTooLargeError(matched=total_count, limit=MAX_IMAGE_LIST_FETCH)

        records, total = container.db_manager.image_repo.get_images_by_filter(criteria)
        count = len(records)
        has_more = q.offset + count < total

        if is_json_mode():
            for record in records:
                emit_item(
                    {
                        "image_id": record.get("id") or record.get("image_id"),
                        "file_path": record.get("file_path"),
                    }
                )
            emit_result(
                f"{count} image(s)",
                count=count,
                total=total,
                limit=q.limit,
                offset=q.offset,
                has_more=has_more,
            )
        else:
            for record in records:
                print(f"{record.get('id') or record.get('image_id')}\t{record.get('file_path')}")


@app.command("show")
def show(
    image_ids_positional: list[str] | None = typer.Argument(
        None,
        metavar="[IMAGE_IDS]...",
        help="Image IDs (space or comma separated). Alternative to --image-ids.",
    ),
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    image_ids_csv: str | None = typer.Option(None, "--image-ids", help="Comma-separated image IDs"),
    include_rejected: bool = typer.Option(
        False,
        "--include-rejected",
        help="Include soft-rejected tags/captions in the output.",
    ),
) -> None:
    """Show current tags, captions, scores, and ratings for images (read-only).

    指定した image_ids の現行アノテーション（タグ/キャプション/スコア/レーティング）を
    表示します。タグ修正の判断材料として使うためのコマンドで、書き込みは行いません。
    画像 ID は位置引数 (`images show 42 57`) と `--image-ids 42,57` のどちらでも指定できます。

    Example:
        lorairo-cli images show --project proj --image-ids 42,57 --json
        lorairo-cli images show 42 57 --project proj --json
    """
    with command_boundary():
        api_get_project(project)
        id_sources = list(image_ids_positional or [])
        if image_ids_csv:
            id_sources.append(image_ids_csv)
        if not id_sources:
            raise click.UsageError(
                "画像 ID を指定してください: `images show 42 57` または `--image-ids 42,57`。"
            )
        image_ids = parse_image_ids(",".join(id_sources))
        if not image_ids:
            raise click.UsageError("画像 ID に有効な値がありません。")
        if len(image_ids) > MAX_IMAGE_IDS:
            raise click.UsageError(f"--image-ids は最大 {MAX_IMAGE_IDS} 件まで。")

        container = get_service_container()
        container.set_active_project(project)
        validate_image_ids_exist(container, image_ids)

        image_repo = container.db_manager.image_repo
        annotations_by_id = image_repo.get_image_annotations_batch(
            image_ids, include_rejected=include_rejected
        )

        if is_json_mode():
            for image_id in image_ids:
                annotations = annotations_by_id[image_id]
                emit_item(
                    {
                        "image_id": image_id,
                        "tags": annotations["tags"],
                        "captions": annotations["captions"],
                        "scores": annotations["scores"],
                        "score_labels": annotations["score_labels"],
                        "ratings": annotations["ratings"],
                        "quality_summary": annotations["quality_summary"],
                    }
                )
            emit_result(f"{len(image_ids)} image(s)", target_images=len(image_ids))
        else:
            for image_id in image_ids:
                annotations = annotations_by_id[image_id]
                tag_names = [t["tag"] for t in annotations["tags"]]
                caption_texts = [c["caption"] for c in annotations["captions"]]
                console.print(f"\n[bold]Image {image_id}[/bold]")
                console.print(f"  tags: {', '.join(tag_names) if tag_names else '(none)'}")
                console.print(f"  captions: {' | '.join(caption_texts) if caption_texts else '(none)'}")
