"""プロジェクト横断の検索・画像コピー・版作成の統合テスト (Issue #1661, ADR 0112)。

tmp_path に合成した 3 つのプロジェクト (コピー元 A / B と取り込み先 T) で、本物の migration を
通した DB と本物の画像ファイルを使う。コピー元の DB と画像のハッシュ・mtime が変わらないこと、
途中で失敗したときに取り込み先へ行もファイルも残らないことを確かめる。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path

import pytest
from project_transfer_fixtures import (
    SyntheticProject,
    add_image,
    build_migrated_template,
    file_fingerprints,
    make_project,
    table_counts,
)
from sqlalchemy import text
from sqlalchemy.orm import Session

from lorairo.database.filter_criteria import ImageFilterCriteria
from lorairo.database.repository.dataset import DatasetConflictError, DatasetRepository
from lorairo.public_api.exceptions import ReadOnlyPreconditionError
from lorairo.services import project_transfer_service
from lorairo.services.dataset_version_build_service import BuildVersionRequest, DatasetVersionBuildService
from lorairo.services.project_transfer_service import (
    CrossProjectSearchService,
    ProjectTransferService,
)

pytestmark = pytest.mark.integration

_TARGET_TABLES = (
    "images",
    "processed_images",
    "tags",
    "captions",
    "scores",
    "ratings",
    "generation_metadata",
    "image_origins",
    "project_transfer_runs",
    "models",
    "projects",
)


@pytest.fixture(scope="module")
def template_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_migrated_template(tmp_path_factory.mktemp("transfer_template") / "image_database.db")


@pytest.fixture
def projects(tmp_path: Path, template_db: Path) -> dict[str, SyntheticProject]:
    created = {name: make_project(tmp_path, name, template_db) for name in ("proj_a", "proj_b", "proj_t")}
    a, b = created["proj_a"], created["proj_b"]
    add_image(a, "a_cat", 1, tags=("cat", "smile"), caption="a cat", score=6.5, rating="PG", prompt="cat")
    add_image(a, "a_dog", 2, tags=("dog",))
    add_image(a, "shared", 9, tags=("cat", "outdoor"))
    add_image(b, "b_cat", 3, tags=("cat", "blue eyes"))
    # A の shared と同じ画像 (同じ pHash と属性)。B では別のタグが付いている
    add_image(b, "shared", 9, tags=("cat", "night"))
    return created


def _service(target: SyntheticProject) -> ProjectTransferService:
    return ProjectTransferService(target.session_factory(), target.root, target.name)


def _source_id(project: SyntheticProject, stem: str) -> int:
    with closing(sqlite3.connect(project.db_path)) as conn:
        row = conn.execute("SELECT id FROM images WHERE filename = ?", (f"{stem}.png",)).fetchone()
    assert row is not None
    image_id: int = row[0]
    return image_id


def _tags(project: SyntheticProject, image_id: int) -> list[str]:
    with closing(sqlite3.connect(project.db_path)) as conn:
        rows = conn.execute("SELECT tag FROM tags WHERE image_id = ? ORDER BY id", (image_id,)).fetchall()
    return [row[0] for row in rows]


# --- 完了条件 1: 横断検索と由来 ---


def test_search_across_projects_returns_hits_with_origins(projects: dict[str, SyntheticProject]) -> None:
    a, b, t = projects["proj_a"], projects["proj_b"], projects["proj_t"]
    _service(t).copy_images(a.source, [_source_id(a, "a_cat")])

    results = CrossProjectSearchService().search(
        [a.source, b.source, t.source], ImageFilterCriteria(tags=["cat"]), max_results_per_project=500
    )

    by_project = {result.project_name: result for result in results}
    assert sorted(hit.filename or "" for hit in by_project["proj_a"].hits) == ["a_cat.png", "shared.png"]
    assert sorted(hit.filename or "" for hit in by_project["proj_b"].hits) == ["b_cat.png", "shared.png"]
    assert all(hit.file_path.is_file() for result in results for hit in result.hits)
    assert all(hit.origins == [] for hit in by_project["proj_a"].hits)
    [copied] = by_project["proj_t"].hits
    [origin] = copied.origins
    assert (origin.source_project_name, origin.source_image_id, origin.source_image_uuid) == (
        "proj_a",
        _source_id(a, "a_cat"),
        "proj_a-a_cat",
    )


def test_search_refuses_source_with_old_schema(projects: dict[str, SyntheticProject]) -> None:
    a = projects["proj_a"]
    with closing(sqlite3.connect(a.db_path)) as conn:
        conn.execute("UPDATE alembic_version SET version_num = 'b1c2d3e4f5a6'")
        conn.commit()
    before = file_fingerprints(a.root)

    with pytest.raises(ReadOnlyPreconditionError) as excinfo:
        CrossProjectSearchService().search([a.source], ImageFilterCriteria(), max_results_per_project=500)

    assert excinfo.value.details["reason"] == "schema_upgrade_required"
    assert file_fingerprints(a.root) == before


# --- 完了条件 2: コピーと、同じ画像への由来の追加 ---


def test_copy_new_image_copies_files_annotations_and_origin(projects: dict[str, SyntheticProject]) -> None:
    a, t = projects["proj_a"], projects["proj_t"]
    source_id = _source_id(a, "a_cat")

    result = _service(t).copy_images(a.source, [source_id])

    [item] = result.items
    assert item.action == "copy"
    assert item.target_image_id is not None
    assert result.transfer_run_id is not None
    with closing(sqlite3.connect(t.db_path)) as conn:
        image = conn.execute(
            "SELECT uuid, stored_image_path, phash FROM images WHERE id = ?", (item.target_image_id,)
        ).fetchone()
        processed = conn.execute(
            "SELECT stored_image_path FROM processed_images WHERE image_id = ?", (item.target_image_id,)
        ).fetchall()
        caption = conn.execute(
            "SELECT caption FROM captions WHERE image_id = ?", (item.target_image_id,)
        ).fetchall()
        rating = conn.execute(
            "SELECT normalized_rating FROM ratings WHERE image_id = ?", (item.target_image_id,)
        ).fetchall()
        score = conn.execute(
            "SELECT score FROM scores WHERE image_id = ?", (item.target_image_id,)
        ).fetchall()
        prompt = conn.execute(
            "SELECT positive_prompt FROM generation_metadata WHERE image_id = ?", (item.target_image_id,)
        ).fetchall()
        origin = conn.execute(
            "SELECT source_project_name, source_image_id, source_image_uuid, transfer_run_id FROM image_origins"
        ).fetchall()
        run = conn.execute(
            "SELECT kind, source_project_name, copied_images, linked_images FROM project_transfer_runs"
        ).fetchall()
    # 新しい uuid で登録し、元の uuid は由来に残す
    assert image[0] != "proj_a-a_cat"
    stored = Path(image[1])
    assert stored.is_file() and stored.is_relative_to(t.root)
    assert (
        stored.read_bytes()
        == (a.root / "image_dataset/original_images/2026/01/01/src/a_cat.png").read_bytes()
    )
    assert (
        len(processed) == 1
        and Path(processed[0][0]).is_file()
        and Path(processed[0][0]).is_relative_to(t.root)
    )
    assert "/image_dataset/512/" in processed[0][0]
    assert _tags(t, item.target_image_id) == ["cat", "smile"]
    assert caption == [("a cat",)] and rating == [("PG",)] and score == [(6.5,)] and prompt == [("cat",)]
    assert origin == [("proj_a", source_id, "proj_a-a_cat", result.transfer_run_id)]
    assert run == [("copy_images", "proj_a", 1, 0)]
    # staging は消えている
    assert not (t.root / "image_dataset" / ".transfer_staging").exists()


def test_copy_same_image_from_second_project_links_and_unions_annotations(
    projects: dict[str, SyntheticProject],
) -> None:
    a, b, t = projects["proj_a"], projects["proj_b"], projects["proj_t"]
    service = _service(t)
    first = service.copy_images(a.source, [_source_id(a, "shared")])
    files_after_first = file_fingerprints(t.root / "image_dataset")

    second = service.copy_images(b.source, [_source_id(b, "shared")])

    [item] = second.items
    assert item.action == "link"
    assert item.target_image_id == first.items[0].target_image_id
    assert table_counts(t, ("images",))["images"] == 1
    # 画像ファイルは複製しない
    assert file_fingerprints(t.root / "image_dataset") == files_after_first
    assert _tags(t, item.target_image_id) == ["cat", "outdoor", "night"]
    with closing(sqlite3.connect(t.db_path)) as conn:
        origins = conn.execute(
            "SELECT source_project_name, source_image_uuid FROM image_origins WHERE image_id = ? ORDER BY id",
            (item.target_image_id,),
        ).fetchall()
    assert origins == [("proj_a", "proj_a-shared"), ("proj_b", "proj_b-shared")]


def test_copy_into_project_with_existing_same_image_adds_origin_only(
    projects: dict[str, SyntheticProject],
) -> None:
    a, t = projects["proj_a"], projects["proj_t"]
    existing_id = add_image(t, "mine", 9, tags=("cat", "favorite"), with_processed=False)
    before_files = file_fingerprints(t.root / "image_dataset")

    result = _service(t).copy_images(a.source, [_source_id(a, "shared")])

    assert [(i.action, i.target_image_id) for i in result.items] == [("link", existing_id)]
    assert table_counts(t, ("images",))["images"] == 1
    assert file_fingerprints(t.root / "image_dataset") == before_files
    # 既存の行を優先し、足りない (モデル, タグ) だけ足す
    assert _tags(t, existing_id) == ["cat", "favorite", "outdoor"]


def test_copy_again_is_idempotent(projects: dict[str, SyntheticProject]) -> None:
    a, t = projects["proj_a"], projects["proj_t"]
    service = _service(t)
    ids = [_source_id(a, "a_cat"), _source_id(a, "a_dog")]
    service.copy_images(a.source, ids)
    counts = table_counts(t, ("images", "tags", "image_origins", "captions"))

    again = service.copy_images(a.source, ids)

    assert [item.action for item in again.items] == ["already_linked", "already_linked"]
    assert [item.annotations_added for item in again.items] == [0, 0]
    assert table_counts(t, ("images", "tags", "image_origins", "captions")) == counts


def test_dry_run_writes_nothing(projects: dict[str, SyntheticProject]) -> None:
    a, t = projects["proj_a"], projects["proj_t"]
    counts = table_counts(t, _TARGET_TABLES)
    files = file_fingerprints(t.root)

    result = _service(t).copy_images(
        a.source, [_source_id(a, "a_cat"), _source_id(a, "a_dog")], dry_run=True
    )

    assert [(i.action, i.target_image_id) for i in result.items] == [("copy", None), ("copy", None)]
    assert result.transfer_run_id is None
    assert table_counts(t, _TARGET_TABLES) == counts
    assert file_fingerprints(t.root) == files


def test_copy_rejects_missing_source_id_without_writing(projects: dict[str, SyntheticProject]) -> None:
    a, t = projects["proj_a"], projects["proj_t"]
    counts = table_counts(t, _TARGET_TABLES)

    with pytest.raises(LookupError):
        _service(t).copy_images(a.source, [_source_id(a, "a_cat"), 9999])

    assert table_counts(t, _TARGET_TABLES) == counts


def test_copy_rejects_same_project(projects: dict[str, SyntheticProject]) -> None:
    t = projects["proj_t"]
    with pytest.raises(ValueError, match="同じプロジェクト"):
        _service(t).copy_images(t.source, [1])


# --- 完了条件 3: 複数プロジェクトの画像で版を作る ---


def _build_service(target: SyntheticProject) -> DatasetVersionBuildService:
    factory = target.session_factory()
    return DatasetVersionBuildService(factory, DatasetRepository(session_factory=factory))


def test_build_version_from_images_of_two_projects(projects: dict[str, SyntheticProject]) -> None:
    a, b, t = projects["proj_a"], projects["proj_b"], projects["proj_t"]
    service = _service(t)
    from_a = service.copy_images(a.source, [_source_id(a, "a_cat")]).items[0].target_image_id
    from_b = service.copy_images(b.source, [_source_id(b, "b_cat")]).items[0].target_image_id
    assert from_a is not None and from_b is not None
    builder = _build_service(t)
    request = BuildVersionRequest(
        dataset_name="mix",
        version_name="v1",
        dir_name="10_cats",
        image_ids=[from_a, from_b],
        trigger_word="trig",
    )

    result = builder.build(request)

    snapshot = DatasetRepository(session_factory=t.session_factory()).get_version_snapshot(
        result.version_id
    )
    assert snapshot.is_working is False
    [folder] = snapshot.folders
    assert (folder.dir_name, folder.num_repeats, folder.trigger_word) == ("10_cats", 10, "trig")
    texts = {image.image_id: image.texts[0].raw_text for image in folder.images}
    assert texts == {from_a: "trig, cat, smile", from_b: "trig, cat, blue eyes"}
    dataset_name, version_name, rows = builder.describe_version(result.version_id)
    assert (dataset_name, version_name) == ("mix", "v1")
    assert [
        (row.image_id, [(o.source_project_name, o.source_image_id) for o in row.origins]) for row in rows
    ] == [
        (from_a, [("proj_a", _source_id(a, "a_cat"))]),
        (from_b, [("proj_b", _source_id(b, "b_cat"))]),
    ]


def test_build_version_rejects_existing_version_name(projects: dict[str, SyntheticProject]) -> None:
    a, t = projects["proj_a"], projects["proj_t"]
    target_id = _service(t).copy_images(a.source, [_source_id(a, "a_cat")]).items[0].target_image_id
    assert target_id is not None
    builder = _build_service(t)
    request = BuildVersionRequest(
        dataset_name="d", version_name="v1", dir_name="1_x", image_ids=[target_id]
    )
    builder.build(request)

    with pytest.raises(DatasetConflictError):
        builder.build(request)


def test_build_version_failure_removes_version(
    projects: dict[str, SyntheticProject], monkeypatch: pytest.MonkeyPatch
) -> None:
    a, t = projects["proj_a"], projects["proj_t"]
    target_id = _service(t).copy_images(a.source, [_source_id(a, "a_cat")]).items[0].target_image_id
    assert target_id is not None
    builder = _build_service(t)

    def fail(self: DatasetRepository, dataset_id: int, extension: str = ".txt") -> None:
        raise RuntimeError("同期に失敗")

    monkeypatch.setattr(DatasetRepository, "sync_kohya_tags_for_dataset", fail)
    with pytest.raises(RuntimeError):
        builder.build(
            BuildVersionRequest(dataset_name="d", version_name="v1", dir_name="1_x", image_ids=[target_id])
        )

    assert table_counts(t, ("dataset_versions", "dataset_folders", "dataset_folder_images")) == {
        "dataset_versions": 0,
        "dataset_folders": 0,
        "dataset_folder_images": 0,
    }


# --- 完了条件 4: コピー元が変わらないこと、途中で失敗しても何も残らないこと ---


def test_sources_unchanged_by_search_copy_and_build(projects: dict[str, SyntheticProject]) -> None:
    a, b, t = projects["proj_a"], projects["proj_b"], projects["proj_t"]
    before = {name: file_fingerprints(projects[name].root) for name in ("proj_a", "proj_b")}

    CrossProjectSearchService().search(
        [a.source, b.source], ImageFilterCriteria(), max_results_per_project=500
    )
    service = _service(t)
    copied = [
        *service.copy_images(a.source, [_source_id(a, "a_cat"), _source_id(a, "shared")]).items,
        *service.copy_images(b.source, [_source_id(b, "b_cat"), _source_id(b, "shared")]).items,
    ]
    ids = list(dict.fromkeys(item.target_image_id for item in copied if item.target_image_id is not None))
    _build_service(t).build(
        BuildVersionRequest(dataset_name="d", version_name="v1", dir_name="1_x", image_ids=ids)
    )

    assert {name: file_fingerprints(projects[name].root) for name in ("proj_a", "proj_b")} == before


def _assert_target_untouched(
    target: SyntheticProject, counts: dict[str, int], files: dict[str, tuple[str, int]]
) -> None:
    assert table_counts(target, _TARGET_TABLES) == counts
    assert file_fingerprints(target.root) == files
    assert not (target.root / "image_dataset" / ".transfer_staging").exists()
    assert not (target.root / "image_dataset" / "original_images").exists()


def test_failure_while_copying_files_leaves_nothing(
    projects: dict[str, SyntheticProject], monkeypatch: pytest.MonkeyPatch
) -> None:
    a, t = projects["proj_a"], projects["proj_t"]
    counts = table_counts(t, _TARGET_TABLES)
    files = file_fingerprints(t.root)
    original_copy: Callable[[Path, Path], None] = project_transfer_service._copy_file
    calls: list[Path] = []

    def copy_then_fail(source: Path, destination: Path) -> None:
        calls.append(source)
        if len(calls) == 3:
            raise OSError("ディスクがいっぱい")
        original_copy(source, destination)

    monkeypatch.setattr(project_transfer_service, "_copy_file", copy_then_fail)
    with pytest.raises(OSError, match="ディスクがいっぱい"):
        _service(t).copy_images(a.source, [_source_id(a, "a_cat"), _source_id(a, "a_dog")])

    assert len(calls) == 3
    _assert_target_untouched(t, counts, files)


def test_failure_at_commit_removes_moved_files(
    projects: dict[str, SyntheticProject], monkeypatch: pytest.MonkeyPatch
) -> None:
    a, t = projects["proj_a"], projects["proj_t"]
    counts = table_counts(t, _TARGET_TABLES)
    files = file_fingerprints(t.root)

    def fail_commit(self: Session) -> None:
        # ファイルは最終パスへ移った後で commit が失敗する
        assert list((t.root / "image_dataset" / "original_images").rglob("*.png"))
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(Session, "commit", fail_commit)
    with pytest.raises(sqlite3.OperationalError):
        _service(t).copy_images(a.source, [_source_id(a, "a_cat"), _source_id(a, "a_dog")])
    monkeypatch.undo()

    _assert_target_untouched(t, counts, files)


def test_migrated_target_has_new_tables(projects: dict[str, SyntheticProject]) -> None:
    """合成プロジェクトの DB は本物の migration で新しい表を持つ (前提の確認)。"""
    t = projects["proj_t"]
    engine_factory = t.session_factory()
    with engine_factory() as session:
        names = {
            row[0] for row in session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }
    assert {"image_origins", "project_transfer_runs", "dataset_version_origins"} <= names


def test_search_can_skip_source_with_old_schema(projects: dict[str, SyntheticProject]) -> None:
    a, b = projects["proj_a"], projects["proj_b"]
    with closing(sqlite3.connect(a.db_path)) as conn:
        conn.execute("UPDATE alembic_version SET version_num = 'b1c2d3e4f5a6'")
        conn.commit()

    results = CrossProjectSearchService().search(
        [a.source, b.source], ImageFilterCriteria(), max_results_per_project=500, skip_unavailable=True
    )

    assert [(r.project_name, r.unavailable_reason, len(r.hits)) for r in results] == [
        ("proj_a", "schema_upgrade_required", 0),
        ("proj_b", None, 2),
    ]
