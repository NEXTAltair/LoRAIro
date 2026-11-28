"""プロジェクト横断の検索・画像コピー・由来の確認・版の作成コマンド (Issue #1661, ADR 0112)。

`images` / `dataset` グループに登録する (`images.py` / `dataset.py` の末尾)。サービスの組み立てだけを
行い、処理本体は `CrossProjectSearchService` / `ProjectTransferService` / `DatasetVersionBuildService`
に委譲する。別プロジェクトの DB は読み取り専用で開き、コピー元を変更しない。
"""

from __future__ import annotations

import typer

from lorairo.cli._boundary import command_boundary
from lorairo.cli._console import make_console
from lorairo.cli._emit import emit_item, emit_result
from lorairo.cli._help import PROJECT_OPTION_HELP
from lorairo.cli._image_ids import MAX_IMAGE_IDS, parse_image_ids, validate_image_ids_exist
from lorairo.cli._output_mode import is_json_mode
from lorairo.database.repository.dataset import DatasetRepository
from lorairo.database.repository.image_origin import ImageOriginRepository, ImageOriginSnapshot
from lorairo.public_api.project import get_project as api_get_project
from lorairo.public_api.project import list_projects as api_list_projects
from lorairo.services.dataset_version_build_service import (
    BuildVersionPlan,
    BuildVersionRequest,
    DatasetVersionBuildService,
)
from lorairo.services.project_transfer_service import (
    CrossProjectSearchService,
    ImageTransferResult,
    ProjectTransferService,
    SourceProject,
)
from lorairo.services.service_container import ServiceContainer, get_service_container

console = make_console()

# 1 プロジェクトから取得する検索結果の上限 (`images search` と同じ)
_MAX_RESULTS_PER_PROJECT = 500


def _source_project(name: str) -> SourceProject:
    info = api_get_project(name)
    return SourceProject(name=info.name, root=info.path)


def _parse_ids(positional: list[str] | None, csv: str | None) -> list[int]:
    sources = list(positional or [])
    if csv:
        sources.append(csv)
    if not sources:
        raise typer.BadParameter("画像 ID を指定してください: `42 57` または `--image-ids 42,57`。")
    image_ids = list(dict.fromkeys(parse_image_ids(",".join(sources))))
    if not image_ids:
        raise typer.BadParameter("画像 ID に有効な値がありません。")
    if len(image_ids) > MAX_IMAGE_IDS:
        raise typer.BadParameter(f"画像 ID は最大 {MAX_IMAGE_IDS} 件まで。")
    return image_ids


def _origin_item(origin: ImageOriginSnapshot) -> dict[str, object]:
    return {
        "source_project": origin.source_project_name,
        "source_image_id": origin.source_image_id,
        "source_image_uuid": origin.source_image_uuid,
        "transfer_run_id": origin.transfer_run_id,
    }


def _origins_text(origins: list[ImageOriginSnapshot]) -> str:
    if not origins:
        return "-"
    return ", ".join(f"{o.source_project_name}#{o.source_image_id}" for o in origins)


def _activate_target(project: str) -> tuple[ServiceContainer, SourceProject]:
    """取り込み先のプロジェクトを有効にし、コンテナとプロジェクトを返す。"""
    target = _source_project(project)
    container = get_service_container()
    container.set_active_project(project)
    return container, target


# --- images search-projects ---


def search_projects(
    projects: list[str] | None = typer.Option(
        None,
        "--projects",
        help=f"Projects to search (comma separated or repeated). {PROJECT_OPTION_HELP}",
    ),
    all_projects: bool = typer.Option(False, "--all-projects", help="Search every project."),
    query_file: str | None = typer.Option(None, "--query-file", help="Path to JSON search schema file"),
    query: str | None = typer.Option(None, "--query", help="JSON search schema string or '-' for stdin"),
) -> None:
    """Search images across several projects (read-only) and show where each image came from.

    Uses the same JSON search schema as `images search`. Each project is opened read-only; a
    project whose schema is not up to date is not opened (run `project prepare` for it first).
    Each hit shows the project, its image ID there and the origins already recorded for it.

    Example:
        lorairo-cli images search-projects --projects a,b --query '{"tags":["cat"]}' --json
    """
    from lorairo.cli.commands.images import _load_search_query, _search_query_to_criteria

    with command_boundary():
        names = [name.strip() for value in projects or [] for name in value.split(",") if name.strip()]
        if all_projects and names:
            raise typer.BadParameter("--projects and --all-projects are mutually exclusive.")
        if all_projects:
            names = [info.name for info in api_list_projects()]
        if not names:
            raise typer.BadParameter("Specify --projects or --all-projects.")
        sources = [_source_project(name) for name in dict.fromkeys(names)]
        criteria = _search_query_to_criteria(_load_search_query(query_file, query))

        # --all-projects では開けない (schema が古い等) プロジェクトを飛ばし、理由を結果に出す
        results = CrossProjectSearchService().search(
            sources,
            criteria,
            max_results_per_project=_MAX_RESULTS_PER_PROJECT,
            skip_unavailable=all_projects,
        )
        skipped = {
            r.project_name: r.unavailable_reason for r in results if r.unavailable_reason is not None
        }

        hit_count = sum(len(result.hits) for result in results)
        if is_json_mode():
            for result in results:
                for hit in result.hits:
                    emit_item(
                        {
                            "project": hit.project_name,
                            "image_id": hit.image_id,
                            "uuid": hit.uuid,
                            "filename": hit.filename,
                            "width": hit.width,
                            "height": hit.height,
                            "phash": hit.phash,
                            "file_path": hit.file_path.as_posix(),
                            "origins": [_origin_item(origin) for origin in hit.origins],
                        }
                    )
            emit_result(
                f"{hit_count} image(s) in {len(results)} project(s)",
                count=hit_count,
                projects={result.project_name: result.total for result in results},
                skipped_projects=skipped,
            )
            return
        for result in results:
            for hit in result.hits:
                console.print(
                    f"{hit.project_name}\t{hit.image_id}\t{hit.filename or '-'}\t"
                    f"origins={_origins_text(hit.origins)}"
                )
        console.print(f"total: {hit_count} image(s) in {len(results)} project(s)")
        for name, reason in skipped.items():
            console.print(
                f"skipped: {name} ({reason}). Run `project prepare --project {name}` to update it, then retry."
            )


# --- images copy ---


def _print_transfer(result: ImageTransferResult, target: str) -> None:
    if is_json_mode():
        for item in result.items:
            emit_item(
                {
                    "source_image_id": item.source_image_id,
                    "source_uuid": item.source_uuid,
                    "action": item.action,
                    "target_image_id": item.target_image_id,
                    "annotations_added": item.annotations_added,
                }
            )
        emit_result(
            (
                f"Plan: {len(result.items)} image(s) from '{result.source_project_name}' (nothing written)"
                if result.dry_run
                else f"Copied {len(result.items)} image(s) from '{result.source_project_name}' into '{target}'"
            ),
            dry_run=result.dry_run,
            transfer_run_id=result.transfer_run_id,
            copied=result.count("copy"),
            linked=result.count("link"),
            already_linked=result.count("already_linked"),
        )
        return
    for item in result.items:
        target_id = item.target_image_id if item.target_image_id is not None else "(new)"
        console.print(
            f"{item.action}\t{result.source_project_name}#{item.source_image_id} -> {target}#{target_id}\t"
            f"annotations+{item.annotations_added}"
        )
    console.print(
        f"copy: {result.count('copy')}  link: {result.count('link')}  "
        f"already_linked: {result.count('already_linked')}"
    )
    if result.dry_run:
        console.print("Nothing was written. Re-run with --confirm to copy.")
    else:
        console.print(f"transfer_run_id: {result.transfer_run_id}")


def copy_images(
    image_ids_positional: list[str] | None = typer.Argument(
        None, metavar="[IMAGE_IDS]...", help="Image IDs in the source project (space or comma separated)."
    ),
    project: str = typer.Option(..., "--project", "-p", help=PROJECT_OPTION_HELP),
    from_project: str = typer.Option(
        ..., "--from-project", help=f"Project to copy the images from. {PROJECT_OPTION_HELP}"
    ),
    image_ids_csv: str | None = typer.Option(None, "--image-ids", help="Comma-separated source image IDs"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show the plan without copying."),
    confirm: bool = typer.Option(
        False, "--confirm", help="Copy the images. Without it, the plan is shown and nothing is written."
    ),
) -> None:
    """Copy images of another project into this project, with their annotations and origin.

    The image files, processed images, tags, captions, scores, score labels, ratings and generation
    metadata are copied; the source project and image ID are recorded as the origin. When the same
    image already exists here, it is not copied again: the origin is added to the existing image and
    the annotations are merged. The source project is opened read-only and is never changed.
    """
    with command_boundary():
        if dry_run and confirm:
            raise typer.BadParameter("--dry-run and --confirm are mutually exclusive.")
        image_ids = _parse_ids(image_ids_positional, image_ids_csv)
        source = _source_project(from_project)
        container, target = _activate_target(project)
        service = ProjectTransferService(
            container.image_repository.session_factory, target.root, target.name
        )
        result = service.copy_images(source, image_ids, dry_run=not confirm)
        _print_transfer(result, target.name)


# --- images origins ---


def show_image_origins(
    image_ids_positional: list[str] | None = typer.Argument(
        None, metavar="[IMAGE_IDS]...", help="Image IDs (space or comma separated)."
    ),
    project: str = typer.Option(..., "--project", "-p", help=PROJECT_OPTION_HELP),
    image_ids_csv: str | None = typer.Option(None, "--image-ids", help="Comma-separated image IDs"),
) -> None:
    """Show where images were copied from (source project and image ID). Read-only."""
    with command_boundary():
        image_ids = _parse_ids(image_ids_positional, image_ids_csv)
        container, _ = _activate_target(project)
        validate_image_ids_exist(container, image_ids)
        origins = ImageOriginRepository(
            session_factory=container.image_repository.session_factory
        ).list_origins(image_ids)
        if is_json_mode():
            for image_id in image_ids:
                emit_item({"image_id": image_id, "origins": [_origin_item(o) for o in origins[image_id]]})
            emit_result(f"{len(image_ids)} image(s)", count=len(image_ids))
            return
        for image_id in image_ids:
            console.print(f"{image_id}\torigins={_origins_text(origins[image_id])}")


# --- dataset build-version / dataset origins ---


def _print_build_plan(plan: BuildVersionPlan) -> None:
    request = plan.request
    if is_json_mode():
        for image in plan.images:
            emit_item(
                {
                    "image_id": image.image_id,
                    "file_stem": image.file_stem,
                    "text": image.text,
                    "origins": [_origin_item(o) for o in image.origins],
                }
            )
        emit_result(
            f"Plan: version '{request.version_name}' with {len(plan.images)} image(s) (nothing written)",
            dry_run=True,
            dataset=request.dataset_name,
            version=request.version_name,
            dir_name=request.dir_name,
            images=len(plan.images),
        )
        return
    console.print(
        f"dataset: {request.dataset_name}  version: {request.version_name}  folder: {request.dir_name}"
    )
    for image in plan.images:
        console.print(
            f"{image.image_id}\t{image.file_stem}\t{image.text}\torigins={_origins_text(image.origins)}"
        )
    console.print(f"images: {len(plan.images)}")
    console.print("Nothing was written. Re-run with --confirm to create the version.")


def build_version(
    project: str = typer.Option(..., "--project", "-p", help=PROJECT_OPTION_HELP),
    dataset: str = typer.Option(..., "--dataset", help="Dataset name (created when missing)"),
    version: str = typer.Option(..., "--version", help="Version name"),
    folder: str = typer.Option(..., "--folder", help="Folder name as <repeats>_<name> (e.g. 10_mychar)"),
    image_ids_csv: str = typer.Option(..., "--image-ids", help="Comma-separated image IDs of this project"),
    trigger: str | None = typer.Option(
        None, "--trigger", help="Trigger word of the folder; placed first in each learning text."
    ),
    parent_version: int | None = typer.Option(None, "--parent-version", help="Parent version ID"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show the plan without creating the version."),
    confirm: bool = typer.Option(
        False, "--confirm", help="Create the version. Without it, the plan is shown and nothing is written."
    ),
) -> None:
    """Create a dataset version from images of this project (including images copied from others).

    Each image gets a .txt learning text made from its adopted tags, joined with ", " in the same
    format as export. Use `dataset origins` to see the images, texts and source projects afterwards.
    """
    with command_boundary():
        if dry_run and confirm:
            raise typer.BadParameter("--dry-run and --confirm are mutually exclusive.")
        image_ids = _parse_ids(None, image_ids_csv)
        container, _ = _activate_target(project)
        session_factory = container.image_repository.session_factory
        service = DatasetVersionBuildService(
            session_factory, DatasetRepository(session_factory=session_factory)
        )
        request = BuildVersionRequest(
            dataset_name=dataset,
            version_name=version,
            dir_name=folder,
            image_ids=image_ids,
            trigger_word=trigger,
            parent_version_id=parent_version,
        )
        if not confirm:
            _print_build_plan(service.propose(request))
            return
        result = service.build(request)
        if is_json_mode():
            emit_result(
                f"Created version {result.version_id} of dataset '{dataset}'",
                dataset_id=result.dataset_id,
                version_id=result.version_id,
                images=len(result.plan.images),
                tags_added=result.tags_added,
                tags_removed=result.tags_removed,
            )
            return
        console.print(f"Created dataset '{dataset}' version '{version}'")
        console.print(f"version_id: {result.version_id}")
        console.print(f"images: {len(result.plan.images)}")


def show_version_origins(
    version_id: int = typer.Argument(..., help="Dataset version ID"),
    project: str = typer.Option(..., "--project", "-p", help=PROJECT_OPTION_HELP),
) -> None:
    """Show the images of a version with their learning text and source projects. Read-only."""
    with command_boundary():
        container, _ = _activate_target(project)
        session_factory = container.image_repository.session_factory
        service = DatasetVersionBuildService(
            session_factory, DatasetRepository(session_factory=session_factory)
        )
        try:
            dataset_name, version_name, rows = service.describe_version(version_id)
        except LookupError as e:
            raise typer.BadParameter(f"Version not found: {e}") from e
        source_projects = sorted({o.source_project_name for row in rows for o in row.origins})
        if is_json_mode():
            for row in rows:
                emit_item(
                    {
                        "dir_name": row.dir_name,
                        "file_stem": row.file_stem,
                        "image_id": row.image_id,
                        "text": row.text,
                        "origins": [_origin_item(o) for o in row.origins],
                    }
                )
            emit_result(
                f"Version {version_id}: {len(rows)} image(s)",
                version_id=version_id,
                dataset=dataset_name,
                version=version_name,
                images=len(rows),
                source_projects=source_projects,
            )
            return
        console.print(f"dataset: {dataset_name}  version: {version_name} (id={version_id})")
        for row in rows:
            console.print(
                f"{row.dir_name}/{row.file_stem}\t{row.image_id}\t{row.text or '-'}\t"
                f"origins={_origins_text(row.origins)}"
            )
        console.print(f"source_projects: {', '.join(source_projects) if source_projects else '-'}")
