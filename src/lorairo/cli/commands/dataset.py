"""Kohya-ss 形式の学習データセットの取り込み・書き出しコマンド (Issue #1420)。

設計書: ``docs/superpowers/specs/2026-11-05-kohya-dataset-roundtrip-design.md``。
サービスの組み立てだけを行い、処理本体は ``DatasetImportService`` /
``KohyaDatasetExportService`` に委譲する。
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
