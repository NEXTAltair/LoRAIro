"""Kohya-ss 形式の学習データセットの取り込み・書き出し・版の比較コマンド (Issue #1420 / #1455)。

設計書: ``docs/superpowers/specs/2026-11-05-kohya-dataset-roundtrip-design.md``。
サービスの組み立てだけを行い、処理本体は ``DatasetImportService`` /
``KohyaDatasetExportService`` / ``DatasetVersionDiffService`` に委譲する。
"""

from dataclasses import replace
from fnmatch import fnmatch
from pathlib import Path

import typer

from lorairo.cli._boundary import command_boundary
from lorairo.cli._console import make_console
from lorairo.cli._emit import emit_item, emit_result
from lorairo.cli._output_mode import is_json_mode
from lorairo.database.repository.dataset import DatasetRepository
from lorairo.public_api.project import get_project as api_get_project
from lorairo.services.dataset_import_service import (
    DatasetImportPlan,
    DatasetImportService,
    FolderImportPlan,
)
from lorairo.services.dataset_version_diff import (
    DatasetVersionDiffService,
    FolderChange,
    ImageChange,
    TextChange,
    VersionDiff,
)
from lorairo.services.kohya_dataset_export_service import KohyaDatasetExportService
from lorairo.services.service_container import get_service_container

app = typer.Typer(help="Kohya-ss training dataset import/export commands")

console = make_console()


def _build_repository(project: str) -> DatasetRepository:
    """アクティブプロジェクトを切り替え、DatasetRepository を作る。"""
    api_get_project(project)
    container = get_service_container()
    container.set_active_project(project)
    repository = DatasetRepository(session_factory=container.image_repository.session_factory)
    return repository


def _parse_triggers(values: list[str]) -> dict[str, str]:
    """`<dir_name>=<word>` の指定を dict にする。

    Raises:
        typer.BadParameter: `=` が無い、フォルダ名かトリガーワードが空、同じフォルダを 2 回指定した場合。
    """
    triggers: dict[str, str] = {}
    for value in values:
        dir_name, sep, word = value.partition("=")
        dir_name = dir_name.strip()
        word = word.strip()
        if not sep or not dir_name or not word:
            raise typer.BadParameter(f"--trigger must be <dir_name>=<word>: '{value}'")
        if dir_name in triggers:
            raise typer.BadParameter(f"--trigger given twice for folder: '{dir_name}'")
        triggers[dir_name] = word
    return triggers


def _apply_folder_options(
    folders: list[FolderImportPlan], exclude_patterns: list[str], triggers: dict[str, str]
) -> list[FolderImportPlan]:
    """`--exclude-dir` と `--trigger` を計画のフォルダに反映する。

    Raises:
        typer.BadParameter: `--trigger` のフォルダが計画に無い場合。
    """
    known = {folder.dir_name for folder in folders}
    unknown = sorted(set(triggers) - known)
    if unknown:
        raise typer.BadParameter(f"--trigger folder not found in scan result: {', '.join(unknown)}")
    applied: list[FolderImportPlan] = []
    for folder in folders:
        if any(fnmatch(folder.dir_name, pattern) for pattern in exclude_patterns):
            folder = replace(folder, include=False)
        if folder.dir_name in triggers:
            folder = replace(folder, trigger_word=triggers[folder.dir_name])
        applied.append(folder)
    return applied


def _print_plan(plan: DatasetImportPlan) -> None:
    """取り込み計画 (スキャン情報とトリガーワード候補を含む) を表示する。"""
    included = plan.included_folders
    if is_json_mode():
        for folder in plan.folders:
            scan = folder.scan
            emit_item(
                {
                    "dir_name": folder.dir_name,
                    "name": folder.name,
                    "num_repeats": folder.num_repeats,
                    "include": folder.include,
                    "trigger_word": folder.trigger_word,
                    "images": scan.image_count if scan else None,
                    "images_without_text": scan.images_without_text if scan else None,
                    "trigger_candidate": scan.trigger_candidate if scan else None,
                    "trigger_match_rate": scan.trigger_match_rate if scan else None,
                }
            )
        emit_result(
            f"Dry run: {len(included)} of {len(plan.folders)} folder(s) would be imported",
            dry_run=True,
            dataset=plan.dataset_name,
            version=plan.version_name,
            parent_version_id=plan.parent_version_id,
            folders=len(included),
            images=sum(folder.scan.image_count for folder in included if folder.scan),
            images_without_text=sum(folder.scan.images_without_text for folder in included if folder.scan),
            config_files=[str(path) for path in plan.config_files],
            train_data_dir_hints=plan.train_data_dir_hints,
        )
        return

    console.print(
        f"dry run: dataset '{plan.dataset_name}' version '{plan.version_name}' (nothing imported)"
    )
    if plan.parent_version_id is not None:
        console.print(f"parent_version_id: {plan.parent_version_id}")
    for folder in plan.folders:
        mark = "+" if folder.include else "-"
        trigger = folder.trigger_word if folder.trigger_word else "-"
        line = f"{mark} {folder.dir_name}  repeats={folder.num_repeats}  trigger={trigger}"
        scan = folder.scan
        if scan is not None:
            line += f"  images={scan.image_count}  without_text={scan.images_without_text}"
            if scan.trigger_candidate:
                line += f"  candidate={scan.trigger_candidate} ({scan.trigger_match_rate:.0%})"
        console.print(line)
    for path in plan.config_files:
        console.print(f"config: {path}")
    console.print(f"total: {len(included)} of {len(plan.folders)} folder(s) would be imported")
    if not included:
        console.print("[yellow]No folder to import; the import would fail.[/yellow]")
        for hint in plan.train_data_dir_hints:
            console.print(f"[yellow]Hint: train_data_dir in config json: {hint}[/yellow]")


@app.command("import")
def import_dataset(
    directory: Path = typer.Argument(..., help="Kohya-ss dataset root (contains <repeats>_<name> folders)"),
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    dataset: str = typer.Option(..., "--dataset", help="Dataset name"),
    version: str = typer.Option(..., "--version", help="Version name"),
    parent_version: int | None = typer.Option(None, "--parent-version", help="Parent version ID"),
    exclude_dir: list[str] | None = typer.Option(
        None,
        "--exclude-dir",
        help=(
            "Folder name (fnmatch pattern) to skip, in addition to the default exclusions "
            "(sample*, reg, log, logs, wandb, ...). Repeatable."
        ),
    ),
    config: list[Path] | None = typer.Option(
        None, "--config", help="Kohya GUI config json to store with the version. Repeatable."
    ),
    trigger: list[str] | None = typer.Option(
        None,
        "--trigger",
        help=(
            "Trigger word of a folder as <dir_name>=<word>. Repeatable. "
            "Scan candidates are shown by --dry-run but never applied automatically."
        ),
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show the import plan (scan info and trigger candidates) without importing.",
    ),
) -> None:
    """Import a Kohya-ss dataset directory as a new dataset version.

    The import plan is proposed from the scan result. Use --dry-run to review folders, image counts,
    images without learning text and trigger word candidates first; trigger words are stored only
    when given with --trigger. Images are registered without writing image tags; learning texts are
    stored per folder. Fails without creating a version when no folder is imported.
    """
    with command_boundary():
        root = directory.resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"Directory not found: {directory}")
        for config_path in config or []:
            if not config_path.is_file():
                raise FileNotFoundError(f"Config file not found: {config_path}")

        triggers = _parse_triggers(trigger or [])

        repository = _build_repository(project)
        container = get_service_container()
        service = DatasetImportService(container.db_manager, repository, container.file_system_manager)

        explicit_configs = [path.resolve() for path in config] if config else None
        plan = service.propose_plan(root, dataset, version, explicit_configs)
        plan = replace(
            plan,
            parent_version_id=parent_version,
            folders=_apply_folder_options(plan.folders, exclude_dir or [], triggers),
        )
        if dry_run:
            _print_plan(plan)
            return
        # 取り込むフォルダが 0 個なら service が版を作らずに EmptyDatasetImportError を送出する
        result = service.import_directory(root, plan)

        if is_json_mode():
            emit_result(
                f"Imported version {result.version_id} of dataset '{dataset}'",
                dataset_id=result.dataset_id,
                version_id=result.version_id,
                folders=result.folder_count,
                images=result.image_count,
                skipped_images=result.skipped_images,
                images_without_text=result.images_without_text,
                training_config_ids=result.training_config_ids,
            )
        else:
            console.print(f"Imported dataset '{dataset}' version '{plan.version_name}'")
            console.print(f"version_id: {result.version_id}")
            console.print(f"folders: {result.folder_count}")
            console.print(f"images: {result.image_count}")
            console.print(f"skipped_images: {result.skipped_images}")
            console.print(f"images_without_text: {result.images_without_text}")
            if result.training_config_ids:
                ids = ", ".join(str(i) for i in result.training_config_ids)
                console.print(f"training_config_ids: {ids}")


@app.command("export")
def export_dataset(
    version_id: int = typer.Argument(..., help="Dataset version ID"),
    out_dir: Path = typer.Argument(..., help="Output directory (must not exist or be empty)"),
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    config_id: int | None = typer.Option(None, "--config-id", help="Training config ID to write"),
) -> None:
    """Export a dataset version in Kohya-ss layout with its original learning texts."""
    with command_boundary():
        repository = _build_repository(project)
        try:
            result = KohyaDatasetExportService(repository).export_version(
                version_id, out_dir.resolve(), training_config_id=config_id
            )
        except LookupError as e:
            raise typer.BadParameter(f"Version or config not found: {e}") from e

        if is_json_mode():
            emit_result(
                f"Exported version {version_id}",
                version_id=version_id,
                output_dir=str(result.output_dir),
                folders=result.folder_count,
                images=result.image_count,
                texts=result.text_count,
                dataset_config_path=str(result.dataset_config_path),
                training_config_path=str(result.training_config_path)
                if result.training_config_path
                else None,
            )
        else:
            console.print(f"Exported version {version_id} to {result.output_dir}")
            console.print(f"folders: {result.folder_count}")
            console.print(f"images: {result.image_count}")
            console.print(f"texts: {result.text_count}")
            console.print(f"dataset_config: {result.dataset_config_path}")
            if result.training_config_path:
                console.print(f"training_config: {result.training_config_path}")


@app.command("show")
def show_dataset(
    version_id: int = typer.Argument(..., help="Dataset version ID"),
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
) -> None:
    """Show folders, repeat counts, image counts and trigger words of a version."""
    with command_boundary():
        repository = _build_repository(project)
        try:
            snapshot = repository.get_version_snapshot(version_id)
        except LookupError as e:
            raise typer.BadParameter(f"Version not found: {e}") from e

        total_images = sum(len(folder.images) for folder in snapshot.folders)
        if is_json_mode():
            for folder in snapshot.folders:
                emit_item(
                    {
                        "dir_name": folder.dir_name,
                        "name": folder.name,
                        "num_repeats": folder.num_repeats,
                        "images": len(folder.images),
                        "trigger_word": folder.trigger_word,
                    }
                )
            emit_result(
                f"Version {version_id}: {len(snapshot.folders)} folder(s), {total_images} image(s)",
                version_id=version_id,
                dataset=snapshot.dataset_name,
                version=snapshot.version_name,
                parent_version_id=snapshot.parent_version_id,
                folders=len(snapshot.folders),
                images=total_images,
            )
            return

        console.print(f"dataset: {snapshot.dataset_name}")
        console.print(f"version: {snapshot.version_name} (id={version_id})")
        if snapshot.parent_version_id is not None:
            console.print(f"parent_version_id: {snapshot.parent_version_id}")
        for folder in snapshot.folders:
            trigger = folder.trigger_word if folder.trigger_word else "-"
            console.print(
                f"{folder.dir_name}  repeats={folder.num_repeats}  "
                f"images={len(folder.images)}  trigger={trigger}"
            )
        console.print(f"total: {len(snapshot.folders)} folder(s), {total_images} image(s)")


def _image_change_item(dir_name: str, change: ImageChange) -> dict[str, object]:
    return {
        "scope": "image",
        "dir_name": dir_name,
        "file_stem": change.file_stem,
        "status": change.status,
        "base_image_id": change.base_image_id,
        "target_image_id": change.target_image_id,
        "texts": [
            {
                "extension": text.extension,
                "status": text.status,
                "added_elements": text.added_elements,
                "removed_elements": text.removed_elements,
                "reordered": text.reordered,
            }
            for text in change.texts
        ],
    }


def _folder_change_item(change: FolderChange) -> dict[str, object]:
    return {
        "scope": "folder",
        "dir_name": change.dir_name,
        "status": change.status,
        "base_image_count": change.base_image_count,
        "target_image_count": change.target_image_count,
        "num_repeats": list(change.num_repeats) if change.num_repeats else None,
        "trigger_word": list(change.trigger_word) if change.trigger_word else None,
    }


_DIFF_MARKS = {"added": "+", "removed": "-", "changed": "~", "replaced": "!"}


def _folder_diff_line(folder: FolderChange) -> str:
    line = (
        f"{_DIFF_MARKS[folder.status]} {folder.dir_name}/  "
        f"images={folder.base_image_count}->{folder.target_image_count}"
    )
    if folder.num_repeats:
        line += f"  repeats={folder.num_repeats[0]}->{folder.num_repeats[1]}"
    if folder.trigger_word:
        before, after = (word if word else "-" for word in folder.trigger_word)
        line += f"  trigger={before}->{after}"
    return line


def _text_diff_line(text: TextChange) -> str:
    parts = [f"    {_DIFF_MARKS[text.status]} {text.extension}"]
    if text.added_elements:
        parts.append("+[" + ", ".join(text.added_elements) + "]")
    if text.removed_elements:
        parts.append("-[" + ", ".join(text.removed_elements) + "]")
    if text.reordered:
        parts.append("(reordered)")
    if len(parts) == 1 and text.status == "changed":
        parts.append("(whitespace only)")
    return "  ".join(parts)


def _print_diff(diff: VersionDiff) -> None:
    """版の差分を人間向けに表示する。"""
    # データセット名・要素に [] が入りうるため Rich の markup は解釈させない
    console.print(
        f"base: {diff.base_dataset_name} / {diff.base_version_name} (id={diff.base_version_id})",
        markup=False,
    )
    console.print(
        f"target: {diff.target_dataset_name} / {diff.target_version_name} (id={diff.target_version_id})",
        markup=False,
    )
    for folder in diff.folders:
        console.print(_folder_diff_line(folder), markup=False)
        for image in folder.images:
            console.print(
                f"  {_DIFF_MARKS[image.status]} {image.file_stem}  ({image.status})", markup=False
            )
            for text in image.texts:
                console.print(_text_diff_line(text), markup=False)
    summary = diff.summary
    console.print(
        f"folders: +{summary.folders_added} -{summary.folders_removed} ~{summary.folders_changed}  "
        f"images: +{summary.images_added} -{summary.images_removed} "
        f"!{summary.images_replaced} ~{summary.images_changed}  "
        f"texts: +{summary.texts_added} -{summary.texts_removed} ~{summary.texts_changed}"
    )
    if not diff.has_changes:
        console.print("no changes")


@app.command("diff")
def diff_dataset(
    base_version_id: int = typer.Argument(..., help="Base (older) dataset version ID"),
    target_version_id: int = typer.Argument(..., help="Target (newer) dataset version ID"),
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
) -> None:
    """Show added / removed / changed folders, images and learning texts between two versions.

    Folders are matched by folder name, images by file name (without extension) and learning
    texts by extension. An image whose file name stays but whose image differs is "replaced".
    Learning texts are compared by the exported content; element additions / removals are
    counted per element, and an order-only change is marked as reordered. Nothing is written.
    """
    with command_boundary():
        repository = _build_repository(project)
        try:
            diff = DatasetVersionDiffService(repository).diff_versions(base_version_id, target_version_id)
        except LookupError as e:
            raise typer.BadParameter(f"Version not found: {e}") from e

        if not is_json_mode():
            _print_diff(diff)
            return
        for folder in diff.folders:
            emit_item(_folder_change_item(folder))
            for image in folder.images:
                emit_item(_image_change_item(folder.dir_name, image))
        summary = diff.summary
        emit_result(
            f"Diff {base_version_id} -> {target_version_id}: {len(diff.folders)} folder change(s)",
            base_version_id=base_version_id,
            target_version_id=target_version_id,
            base_version=diff.base_version_name,
            target_version=diff.target_version_name,
            has_changes=diff.has_changes,
            folders_added=summary.folders_added,
            folders_removed=summary.folders_removed,
            folders_changed=summary.folders_changed,
            images_added=summary.images_added,
            images_removed=summary.images_removed,
            images_replaced=summary.images_replaced,
            images_changed=summary.images_changed,
            texts_added=summary.texts_added,
            texts_removed=summary.texts_removed,
            texts_changed=summary.texts_changed,
        )


@app.command("copy-tags")
def copy_tags(
    version_id: int = typer.Argument(..., help="Dataset version ID"),
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    folder: list[str] | None = typer.Option(
        None, "--folder", help="Folder name (e.g. 10_name) to copy. Repeatable. Default: all folders."
    ),
    extension: str = typer.Option(".txt", "--extension", help="Learning text extension to copy"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Count tags without writing."),
) -> None:
    """Copy learning text elements of a version to the library image tags (ADR 0104).

    Elements are copied as written (no tag normalization) as rows of the pseudo model
    KOHYA_DATASET, so they stay separate from manual and AI tags. When an image is in several
    selected folders, the union of their elements is copied. Copying again only adds missing
    tags; existing KOHYA_DATASET rows (including rejected ones) and other models' tags are not
    changed. Later edits of learning texts are not followed.
    """
    with command_boundary():
        normalized_extension = extension if extension.startswith(".") else f".{extension}"
        repository = _build_repository(project)
        try:
            result = repository.copy_learning_texts_to_tags(
                version_id, dir_names=folder or None, extension=normalized_extension, dry_run=dry_run
            )
        except LookupError as e:
            raise typer.BadParameter(f"Version or folder not found: {e}") from e

        verb = "Would copy" if dry_run else "Copied"
        if is_json_mode():
            emit_result(
                f"{verb} {result.tags_added} tag(s) to {result.images} image(s)",
                version_id=version_id,
                dry_run=dry_run,
                folders=result.folders,
                images=result.images,
                tags_added=result.tags_added,
                tags_skipped=result.tags_skipped,
            )
            return
        console.print(f"{verb} learning texts of version {version_id} to image tags (KOHYA_DATASET)")
        console.print(f"folders: {result.folders}")
        console.print(f"images: {result.images}")
        console.print(f"tags_added: {result.tags_added}")
        console.print(f"tags_skipped: {result.tags_skipped}")
