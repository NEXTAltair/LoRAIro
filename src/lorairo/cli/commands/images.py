"""Image management commands.

画像の登録、メタデータ更新などの画像管理コマンド。
API層（lorairo.api）を経由してService層を利用する。
"""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from lorairo.api.exceptions import ImageRegistrationError, ProjectNotFoundError
from lorairo.api.images import register_images as api_register_images
from lorairo.api.project import get_project as api_get_project
from lorairo.api.types import RegistrationResult
from lorairo.database.db_repository import ImageRepository
from lorairo.database.filter_criteria import ImageFilterCriteria
from lorairo.services.service_container import get_service_container

# サブコマンドアプリ定義
app = typer.Typer(help="Image management commands")

# Rich console（出力用）
console = Console()


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
        console.print(f"\n[green]✓[/green] Images registered to project: {project}")


def _apply_tags_to_images(
    repository: ImageRepository,
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
        console.print(f"\n[green]✓[/green] Updated {target_count} image(s) in project: {project}")


@app.command("register")
def register(
    directory: str = typer.Argument(
        ...,
        help="Image directory path",
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
    """Register images from directory to project.

    画像ディレクトリからプロジェクトへ画像を登録します。
    pHashを計算して重複検出を行います。
    """
    try:
        dir_path = Path(directory).resolve()

        # ディレクトリ存在確認
        if not dir_path.exists():
            console.print(f"[red]Error:[/red] Directory not found: {directory}")
            raise typer.Exit(code=1)

        if not dir_path.is_dir():
            console.print(f"[red]Error:[/red] Not a directory: {directory}")
            raise typer.Exit(code=1)

        # プロジェクト存在確認 & DB 接続切り替え
        try:
            api_get_project(project)
        except ProjectNotFoundError as e:
            console.print(f"[red]Error:[/red] Project not found: {project}")
            raise typer.Exit(code=1) from e

        get_service_container().set_active_project(project)

        # API層経由で画像登録（プロジェクトコンテキスト付き）
        result = api_register_images(dir_path, skip_duplicates, project_name=project)

        if result.total == 0:
            console.print(f"[yellow]Warning:[/yellow] No image files found in {directory}")
            raise typer.Exit(code=0)

        _print_registration_summary(result, project)

    except ImageRegistrationError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e


@app.command("list")
def list_images(
    project: str = typer.Option(
        ...,
        "--project",
        "-p",
        help="Project name",
    ),
    limit: int | None = typer.Option(
        None,
        "--limit",
        "-l",
        min=1,
        help="Maximum number of images to display (>= 1)",
    ),
) -> None:
    """List images in a project.

    プロジェクトに登録されている画像の一覧をテーブル形式で表示します。
    """
    try:
        try:
            api_get_project(project)
        except ProjectNotFoundError as e:
            console.print(f"[red]Error:[/red] Project not found: {project}")
            raise typer.Exit(code=1) from e

        container = get_service_container()
        container.set_active_project(project)

        repository = container.image_repository
        criteria = ImageFilterCriteria(include_nsfw=True)
        image_records, total_count = repository.get_images_by_filter(criteria)

        if not image_records:
            console.print(f"No images found in project: {project}")
            return

        display_records = image_records[:limit] if limit else image_records

        console.print(f"Images in project: {project}")
        table = Table()
        table.add_column("ID", style="cyan")
        table.add_column("Filename")
        table.add_column("Tags", style="green")
        table.add_column("Annotated", style="yellow")

        for record in display_records:
            image_id = str(record.get("id", ""))
            filename = Path(record.get("stored_image_path", "")).name or str(record.get("filename", ""))
            tag_count = len(record.get("tags") or [])
            has_any_annotation = bool(
                record.get("tags")
                or record.get("captions")
                or record.get("scores")
                or record.get("ratings")
            )
            annotated = "Yes" if has_any_annotation else "No"
            table.add_row(image_id, filename, str(tag_count), annotated)

        console.print(table)

        if limit and total_count > limit:
            console.print(f"Showing {limit} of {total_count} images.")

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e


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
    if not tags:
        console.print("[red]Error:[/red] At least one update operation is required.")
        console.print('Example: --tags "tag1,tag2"')
        raise typer.Exit(code=2)

    try:
        try:
            api_get_project(project)
        except ProjectNotFoundError as e:
            console.print(f"[red]Error:[/red] Project not found: {project}")
            raise typer.Exit(code=1) from e

        container = get_service_container()
        container.set_active_project(project)
        repository = container.image_repository

        if image_id is not None:
            metadata = repository.get_image_metadata(image_id)
            if metadata is None:
                console.print(f"[red]Error:[/red] No image found with ID: {image_id}")
                raise typer.Exit(code=1)
            image_ids: list[int] = [image_id]
        else:
            criteria = ImageFilterCriteria(include_nsfw=True)
            image_records, _total = repository.get_images_by_filter(criteria)
            if not image_records:
                console.print(f"[yellow]Warning:[/yellow] No images found in project: {project}")
                return
            image_ids = [int(r["id"]) for r in image_records]

        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        if not tag_list:
            console.print("[red]Error:[/red] No valid tags specified.")
            raise typer.Exit(code=2)

        total_added, failed_tags = _apply_tags_to_images(repository, image_ids, tag_list)

        _print_update_summary(
            project=project,
            target_count=len(image_ids),
            tag_list=tag_list,
            total_added=total_added,
            failed_tags=failed_tags,
        )

        if failed_tags:
            raise typer.Exit(code=1)

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e
