"""Project management commands.

プロジェクトの作成、一覧表示、削除などの管理コマンド。
API層（lorairo.public_api）を経由してService層を利用する。

出力は ADR 0057/0058 に従う: ``--json`` 時は stdout に JSONL (item/result)、
それ以外は rich 人間向け。エラー整形は :func:`lorairo.cli._boundary.command_boundary`
に集約し、本モジュールは型付き例外を伝播するだけにする。
"""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import typer
from rich.table import Table

from lorairo.cli._boundary import command_boundary
from lorairo.cli._console import make_console
from lorairo.cli._emit import emit_item, emit_result
from lorairo.cli._glyphs import OK
from lorairo.cli._help import PROJECT_OPTION_HELP, project_created_next_steps
from lorairo.cli._output_mode import is_json_mode
from lorairo.database.repository.dataset import DatasetRepository
from lorairo.public_api.exceptions import ProjectError
from lorairo.public_api.project import (
    create_project as api_create_project,
)
from lorairo.public_api.project import (
    delete_project as api_delete_project,
)
from lorairo.public_api.project import get_project as api_get_project
from lorairo.public_api.project import (
    list_projects as api_list_projects,
)
from lorairo.public_api.types import ProjectCreateRequest
from lorairo.services.project_merge_service import (
    MergeMapping,
    MergePlan,
    PlannedVersion,
    ProjectMergeService,
    SourceDatasetRef,
    SourceVersionRef,
)
from lorairo.services.project_transfer_service import SourceProject
from lorairo.utils.log import logger

# サブコマンドアプリ定義
app = typer.Typer(help="Project management commands")

# Rich console (Issue #254: Windows では safe_box=True で ASCII 罫線)
console = make_console()


@app.command("create")
def create(
    name: str = typer.Argument(..., help="Project name"),
    description: str = typer.Option("", "--description", "-d", help="Project description"),
) -> None:
    """Create a new project (an empty library). It is not how you add a dataset version.

    A project holds one library (database and images); a dataset version is a snapshot of a
    training dataset inside a project. To add a new version of an existing dataset, do not create
    one project per version: import it into the existing project.

    Add a version to an existing project: lorairo-cli dataset import ./v2 -p my-project --dataset my-dataset

    Add images only (no dataset version is created): lorairo-cli images register ./images -p my-project

    Creating a project whose name already exists fails with ALREADY_EXISTS and shows the
    dataset import command to use instead. `--project` of other commands takes the name given
    here; run `lorairo-cli project list` to see the names.
    """
    with command_boundary():
        request = ProjectCreateRequest(name=name, description=description or None)
        project = api_create_project(request)
        next_steps = project_created_next_steps(project.name)
        if is_json_mode():
            emit_result(
                f"Project created: {project.name}. {next_steps}",
                name=project.name,
                path=str(project.path),
            )
        else:
            console.print(f"[green]{OK}[/green] Project created: [bold]{project.name}[/bold]")
            console.print(f"[dim]Location: {project.path}[/dim]")
            console.print(f"[dim]{next_steps}[/dim]", soft_wrap=True)


@app.command("list")
def list_projects(
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Human-readable format (table)。機械可読出力はグローバル --json を使う (ADR 0057/0058)。",
    ),
) -> None:
    """List all projects.

    人間向けは rich テーブル (``--format table``、既定)。機械可読出力は
    グローバル ``--json`` フラグで JSONL (item/result) を取得する (ADR 0057/0058)。
    legacy な ``--format json`` (pretty 配列) は非推奨 (ADR 0058)。
    """
    with command_boundary():
        projects = api_list_projects()

        if is_json_mode():
            for proj in projects:
                emit_item(
                    {
                        "name": proj.name,
                        "created": proj.created.strftime("%Y%m%d_%H%M%S") if proj.created else "",
                        "path": str(proj.path),
                    }
                )
            emit_result(f"{len(projects)} project(s) found", count=len(projects))
            return

        if format == "json":
            # ADR 0058: legacy `--format json` (pretty 配列) は非推奨。機械可読出力の
            # SSoT はグローバル `--json` (JSONL) に一本化済みのため、案内して table を出す。
            console.print(
                "[yellow]--format json は非推奨です。機械可読出力はグローバル --json を使ってください。[/yellow]"
            )

        if not projects:
            console.print("[yellow]No projects found[/yellow]")
            return

        table = Table(title="Projects")
        table.add_column("Name", style="cyan")
        table.add_column("Created", style="magenta")
        table.add_column("Path", style="dim")

        for proj in projects:
            created_str = proj.created.strftime("%Y%m%d_%H%M%S") if proj.created else ""
            table.add_row(proj.name, created_str, str(proj.path))

        console.print(table)


@app.command("delete")
def delete(
    name: str = typer.Argument(..., help="Project name to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Force delete without confirmation"),
) -> None:
    """Delete a project."""
    with command_boundary():
        if not force:
            # JSON mode は対話 confirm のプロンプトを stdout に書けない (JSONL 純度を
            # 破る、ADR 0057 §1)。stdin で応答できない agent driving 前提なので、JSON mode
            # では --force を契約上必須とし、未指定は INVALID_INPUT で弾く (Issue #659)。
            if is_json_mode():
                raise typer.BadParameter("project delete requires --force in JSON mode")
            confirm = typer.confirm(f"Delete project '{name}'? This cannot be undone.")
            if not confirm:
                console.print("[yellow]Cancelled[/yellow]")
                return

        api_delete_project(name)
        if is_json_mode():
            emit_result(f"Project deleted: {name}", name=name)
        else:
            console.print(f"[green]{OK}[/green] Project deleted: [bold]{name}[/bold]")


@app.command("prepare")
def prepare(
    project: str = typer.Option(
        ...,
        "--project",
        "-p",
        help=f"Existing project to prepare for database access. {PROJECT_OPTION_HELP}",
    ),
    tags: bool = typer.Option(
        False, "--tags", help="Also initialize/download tag databases with write permission"
    ),
) -> None:
    """Explicitly initialize/migrate the image database and seed required model types."""
    with command_boundary():
        from lorairo.services.service_container import get_service_container

        container = get_service_container()
        container.set_active_project(project)
        if tags:
            from lorairo.database.db_core import ensure_tag_db_initialized

            ensure_tag_db_initialized()
        if is_json_mode():
            emit_result("Project database prepared", project=project, tags=tags)
        else:
            console.print(f"Project database prepared: {project}")


# --- project merge / merge-show (Issue #1660, ADR 0113) ---


def _merge_source(name: str) -> SourceProject:
    info = api_get_project(name)
    return SourceProject(name=info.name, root=info.path)


def _split_dataset_ref(text: str, option: str) -> SourceDatasetRef:
    project, sep, dataset = text.strip().partition(":")
    if not sep or not project.strip() or not dataset.strip():
        raise typer.BadParameter(f"{option}: expected PROJECT:DATASET, got '{text}'.")
    return SourceDatasetRef(project.strip(), dataset.strip())


def _split_assignment(text: str, option: str, shape: str) -> tuple[str, str]:
    key, sep, value = text.rpartition("=")
    if not sep or not key.strip() or not value.strip():
        raise typer.BadParameter(f"{option}: expected {shape}, got '{text}'.")
    return key.strip(), value.strip()


def _parse_merge_mapping(
    mapping_file: Path | None,
    map_dataset: list[str] | None,
    map_version: list[str] | None,
    join_dataset: list[str] | None,
) -> MergeMapping:
    """mapping ファイルと CLI の指定から名前の対応を作る (CLI の指定を優先する)。"""
    base = MergeMapping()
    if mapping_file is not None:
        try:
            data = json.loads(mapping_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise typer.BadParameter(f"--mapping-file is not valid JSON: {e}") from e
        base = MergeMapping.from_json_dict(data)
    dataset_names: dict[SourceDatasetRef, str] = {}
    for text in map_dataset or []:
        key, value = _split_assignment(text, "--map-dataset", "PROJECT:DATASET=NEW_NAME")
        dataset_names[_split_dataset_ref(key, "--map-dataset")] = value
    version_names: dict[SourceVersionRef, str] = {}
    for text in map_version or []:
        key, value = _split_assignment(text, "--map-version", "PROJECT:DATASET/VERSION=NEW_NAME")
        dataset_part, sep, version = key.rpartition("/")
        if not sep or not version.strip():
            raise typer.BadParameter(
                f"--map-version: expected PROJECT:DATASET/VERSION=NEW_NAME, got '{text}'."
            )
        ref = _split_dataset_ref(dataset_part, "--map-version")
        version_names[SourceVersionRef(ref.project, ref.dataset, version.strip())] = value
    joins: dict[str, list[SourceDatasetRef]] = {}
    for text in join_dataset or []:
        name, sep, sources = text.partition("=")
        if not sep or not name.strip() or not sources.strip():
            raise typer.BadParameter(
                f"--join-dataset: expected NEW_NAME=PROJECT:DATASET,PROJECT:DATASET, got '{text}'."
            )
        joins[name.strip()] = [_split_dataset_ref(part, "--join-dataset") for part in sources.split(",")]
    return base.updated(MergeMapping(dataset_names=dataset_names, version_names=version_names, joins=joins))


def _parent_text(version: PlannedVersion) -> str:
    parent = version.parent
    if parent is None:
        return "-"
    owner = parent.source_project if parent.source_project is not None else "(target)"
    return f"{owner}:{parent.dataset}/{parent.version}{' (joined)' if version.joined_parent else ''}"


def _emit_merge_plan(plan: MergePlan) -> None:
    """計画を JSONL の item で出す (画像の集計・まとめる画像・版の対応・衝突)。"""
    for summary in plan.images:
        emit_item(
            {
                "entry": "images",
                "source_project": summary.source_project,
                "images": summary.images,
                "copy": summary.copy,
                "link": summary.link,
                "already_linked": summary.already_linked,
            }
        )
    for duplicate in plan.duplicates:
        emit_item(
            {
                "entry": "duplicate",
                "source_project": duplicate.source_project,
                "source_image_id": duplicate.source_image_id,
                "source_uuid": duplicate.source_uuid,
                "merged_into_project": duplicate.merged_into_project,
                "merged_into_image_id": duplicate.merged_into_image_id,
            }
        )
    for version in plan.versions:
        emit_item(
            {
                "entry": "version",
                "source": version.source.label,
                "source_version_id": version.source_version_id,
                "target_dataset": version.target_dataset,
                "target_version": version.target_version,
                "parent": _parent_text(version) if version.parent is not None else None,
                "is_working": version.is_working,
                "images": version.image_count,
            }
        )
    for conflict in plan.conflicts:
        emit_item(
            {
                "entry": "conflict",
                # `kind` は JSONL の行の種類 (item/result/error) に使うため、衝突の種類は `conflict` に置く
                "conflict": conflict.kind,
                "target_dataset": conflict.target_dataset,
                "target_version": conflict.target_version,
                "sources": list(conflict.sources),
                "message": conflict.message,
            }
        )


def _print_merge_plan(plan: MergePlan) -> None:
    console.print(f"target: {plan.target_project}  sources: {', '.join(plan.source_projects)}")
    for summary in plan.images:
        console.print(
            f"images\t{summary.source_project}\ttotal={summary.images}\tcopy={summary.copy}\t"
            f"link={summary.link}\talready_linked={summary.already_linked}"
        )
    for duplicate in plan.duplicates:
        into = duplicate.merged_into_project or "(target)"
        console.print(
            f"same image\t{duplicate.source_project}#{duplicate.source_image_id} -> "
            f"{into}#{duplicate.merged_into_image_id}",
            soft_wrap=True,
        )
    for version in plan.versions:
        working = " (working)" if version.is_working else ""
        console.print(
            f"version\t{version.source.label} -> {version.target_dataset}/{version.target_version}{working}"
            f"\tparent={_parent_text(version)}\timages={version.image_count}",
            soft_wrap=True,
        )
    for conflict in plan.conflicts:
        console.print(f"[red]conflict[/red]\t{conflict.kind}\t{conflict.message}", soft_wrap=True)


@app.command("merge")
def merge(
    sources: list[str] = typer.Argument(
        ..., metavar="SOURCES...", help="Projects to merge (in this order)."
    ),
    project: str = typer.Option(
        ..., "--into", "--project", "-p", help=f"Target project to merge into. {PROJECT_OPTION_HELP}"
    ),
    create: bool = typer.Option(
        False, "--create", help="Create the target project. It must not exist yet."
    ),
    map_dataset: list[str] | None = typer.Option(
        None, "--map-dataset", help="Rename a source dataset: PROJECT:DATASET=NEW_NAME (repeatable)."
    ),
    map_version: list[str] | None = typer.Option(
        None,
        "--map-version",
        help="Rename a source version: PROJECT:DATASET/VERSION=NEW_NAME (repeatable).",
    ),
    join_dataset: list[str] | None = typer.Option(
        None,
        "--join-dataset",
        help=(
            "Join source datasets into one history: NEW_NAME=PROJECT:DATASET,PROJECT:DATASET (repeatable). "
            "The latest version of each becomes the parent of the first version of the next. When the "
            "target already has NEW_NAME, its history comes first."
        ),
    ),
    mapping_file: Path | None = typer.Option(
        None,
        "--mapping-file",
        exists=True,
        dir_okay=False,
        help=(
            "JSON mapping in the form of `mapping_template` from the --json plan "
            "(datasets / versions / joins). The --map-* and --join-* options override it."
        ),
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show the plan without merging."),
    confirm: bool = typer.Option(
        False,
        "--confirm",
        help="Merge. Without it, the plan is shown and nothing is written. Refused while conflicts remain.",
    ),
) -> None:
    """Merge projects into one, with their images, annotations, datasets and version history.

    The same image (by hash) in several sources becomes one image whose tags and annotations are
    merged. Each version is copied with its parent chain, and its source project, dataset, version ID
    and name are recorded (see `project merge-show`). Dataset and version names that collide are
    reported as conflicts; rename them with --map-dataset / --map-version or join histories with
    --join-dataset (or --mapping-file) until none remain, then re-run with --confirm. The sources are
    opened read-only and never changed; a failure leaves the target unchanged.
    """
    with command_boundary():
        if dry_run and confirm:
            raise typer.BadParameter("--dry-run and --confirm are mutually exclusive.")
        mapping = _parse_merge_mapping(mapping_file, map_dataset, map_version, join_dataset)
        source_projects = [_merge_source(name) for name in sources]
        if create and any(proj.name == project for proj in api_list_projects()):
            raise typer.BadParameter(f"--create: project '{project}' already exists. Omit --create.")

        if not confirm:
            if create:
                plan = ProjectMergeService.plan_into_new_project(source_projects, mapping, project)
            else:
                with _open_merge_target(project) as service:
                    plan = service.plan(source_projects, mapping)
            _report_merge_plan(plan)
            return

        if create:
            api_create_project(ProjectCreateRequest(name=project, description=None))
        merged = False
        try:
            # 統合先の engine は with を抜けた時点で破棄される (作った統合先を消す前に接続を閉じる)
            with _open_merge_target(project) as service:
                result = service.apply(source_projects, mapping)
            merged = True
        finally:
            # 作った統合先は、統合が失敗したら消す (中途半端なプロジェクトを残さない)
            if create and not merged:
                _delete_created_target(project)
        if is_json_mode():
            _emit_merge_plan(result.plan)
            emit_result(
                f"Merged {len(result.plan.source_projects)} project(s) into '{project}'",
                dry_run=False,
                target=project,
                images=result.plan.image_count,
                duplicates=len(result.plan.duplicates),
                versions=len(result.version_ids),
                transfer_run_ids=result.transfer_run_ids,
            )
            return
        _print_merge_plan(result.plan)
        console.print(
            f"[green]{OK}[/green] Merged {len(result.plan.source_projects)} project(s) into "
            f"[bold]{project}[/bold]: versions={len(result.version_ids)}"
        )
        console.print(
            f"Run `lorairo-cli project merge-show -p {project}` to see where each version came from."
        )


@contextmanager
def _open_merge_target(project: str) -> Iterator[ProjectMergeService]:
    """統合先の DB を専用の engine で開いて service を返し、抜けるときに engine を破棄する。

    service container の singleton には載せない。統合が失敗して作った統合先を消すとき、
    接続が開いたままだと Windows では削除が共有違反で失敗するため (Codex P2, PR #1671)。
    """
    from sqlalchemy import Engine

    from lorairo.database.db_core import IMG_DB_FILENAME, create_project_session_factory

    target = _merge_source(project)
    factory = create_project_session_factory(target.root / IMG_DB_FILENAME)
    try:
        yield ProjectMergeService(factory, target.root, target.name)
    finally:
        engine = factory.kw.get("bind")
        if isinstance(engine, Engine):
            engine.dispose()


def _delete_created_target(project: str) -> None:
    """統合に失敗したとき、作った統合先を消す。消せなくても元のエラーを隠さない (ログに残す)。"""
    try:
        api_delete_project(project)
    except (ProjectError, OSError):
        logger.opt(exception=True).error(
            f"統合に失敗した統合先のプロジェクトを削除できませんでした: {project}"
        )


def _report_merge_plan(plan: MergePlan) -> None:
    if is_json_mode():
        _emit_merge_plan(plan)
        emit_result(
            (
                f"Plan: merge {len(plan.source_projects)} project(s) into '{plan.target_project}' "
                f"with {len(plan.conflicts)} unresolved conflict(s) (nothing written)"
            ),
            dry_run=True,
            target=plan.target_project,
            resolved=plan.is_resolved,
            images=plan.image_count,
            duplicates=len(plan.duplicates),
            versions=len(plan.versions),
            conflicts=len(plan.conflicts),
            mapping_template=plan.mapping_template(),
        )
        return
    _print_merge_plan(plan)
    if plan.is_resolved:
        console.print("No conflicts. Nothing was written. Re-run with --confirm to merge.")
    else:
        console.print(
            f"{len(plan.conflicts)} conflict(s) remain. Nothing was written. Resolve them with "
            "--map-dataset / --map-version / --join-dataset (or --mapping-file; `--json` prints "
            "`mapping_template`), then re-run with --confirm.",
            soft_wrap=True,
        )


@app.command("merge-show")
def merge_show(
    project: str = typer.Option(..., "--project", "-p", help=PROJECT_OPTION_HELP),
) -> None:
    """Show which source project, dataset and version each merged version came from. Read-only."""
    with command_boundary():
        from lorairo.services.service_container import get_service_container

        container = get_service_container()
        container.set_active_project(project)
        origins = DatasetRepository(
            session_factory=container.image_repository.session_factory
        ).list_version_origins()
        if is_json_mode():
            for origin in origins:
                emit_item(
                    {
                        "version_id": origin.version_id,
                        "dataset": origin.dataset_name,
                        "version": origin.version_name,
                        "parent_version_id": origin.parent_version_id,
                        "is_working": origin.is_working,
                        "source_project": origin.source_project_name,
                        "source_dataset": origin.source_dataset_name,
                        "source_version_id": origin.source_version_id,
                        "source_version": origin.source_version_name,
                        "transfer_run_id": origin.transfer_run_id,
                    }
                )
            emit_result(f"{len(origins)} merged version(s)", count=len(origins))
            return
        if not origins:
            console.print("No merged versions")
            return
        table = Table(title=f"Merged versions in {project}")
        for column in ("Version ID", "Dataset", "Version", "Parent ID", "Source", "Source version ID"):
            table.add_column(column)
        for origin in origins:
            table.add_row(
                str(origin.version_id),
                origin.dataset_name,
                origin.version_name,
                str(origin.parent_version_id) if origin.parent_version_id is not None else "-",
                f"{origin.source_project_name}:{origin.source_dataset_name}/{origin.source_version_name}",
                str(origin.source_version_id),
            )
        console.print(table)
