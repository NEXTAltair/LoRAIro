"""複数プロジェクトを版履歴ごと統合する service の統合テスト (Issue #1660, ADR 0113)。

tmp_path に 3 つのプロジェクト (統合元 A / B と、既存のデータセットを持つ統合先 T) を合成する。
DB は本物の migration を通したもの、画像は本物の PNG。合成データには、2 つの統合元にある同じ画像、
同名のデータセットと版、版の親子の連なり、同じ画像に `.txt` と `.caption` の両方が付いたフォルダを入れる。
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from project_transfer_fixtures import (
    SyntheticProject,
    add_image,
    add_version,
    build_migrated_template,
    file_fingerprints,
    make_project,
    table_counts,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from lorairo.database.repository.dataset import DatasetRepository
from lorairo.database.schema import KOHYA_DATASET_LITELLM_ID, Model, Tag
from lorairo.services import project_transfer_service
from lorairo.services.kohya_dataset_export_service import KohyaDatasetExportService
from lorairo.services.project_merge_service import (
    MergeMapping,
    MergeMappingError,
    ProjectMergeService,
    SourceDatasetRef,
    SourceVersionRef,
    UnresolvedMergeConflictError,
)

pytestmark = pytest.mark.integration

_TARGET_TABLES = (
    "images",
    "processed_images",
    "tags",
    "captions",
    "image_origins",
    "project_transfer_runs",
    "datasets",
    "dataset_versions",
    "dataset_folders",
    "dataset_folder_images",
    "dataset_learning_texts",
    "dataset_version_origins",
    "training_configs",
    "models",
)

A_CHARA = SourceDatasetRef("proj_a", "chara")
B_CHARA = SourceDatasetRef("proj_b", "chara")


@pytest.fixture(scope="module")
def template_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_migrated_template(tmp_path_factory.mktemp("merge_template") / "image_database.db")


@pytest.fixture
def projects(tmp_path: Path, template_db: Path) -> dict[str, SyntheticProject]:
    created = {name: make_project(tmp_path, name, template_db) for name in ("proj_a", "proj_b", "proj_t")}
    a, b, t = created["proj_a"], created["proj_b"], created["proj_t"]

    a_cat = add_image(a, "a_cat", 1, tags=("cat", "smile"), caption="a cat")
    a_shared = add_image(a, "shared", 9, tags=("cat", "outdoor"))
    a_v1 = add_version(a, "chara", "v1", "10_chara", [(a_cat, "a_cat", {".txt": "chara, cat"})])
    add_version(
        a,
        "chara",
        "v2",
        "10_chara",
        [
            (a_cat, "a_cat", {".txt": "chara, cat, smile"}),
            # 同じ画像に .txt と .caption の両方
            (a_shared, "shared", {".txt": "chara, outdoor", ".caption": "a cat outdoors"}),
        ],
        parent_version_id=a_v1,
    )

    b_dog = add_image(b, "b_dog", 3, tags=("dog",))
    # A の shared と同じ画像 (同じ pHash と属性)。B では別のタグが付いている
    b_shared = add_image(b, "shared", 9, tags=("cat", "night"))
    b_v1 = add_version(b, "chara", "v1", "5_chara", [(b_dog, "b_dog", {".txt": "chara, dog"})])
    add_version(
        b,
        "chara",
        "v2",
        "5_chara",
        [(b_dog, "b_dog", {".txt": "chara, dog"}), (b_shared, "shared", {".txt": "chara, night"})],
        parent_version_id=b_v1,
    )
    add_version(b, "style", "s1", "1_style", [(b_dog, "b_dog", {".txt": "style"})])

    t_own = add_image(t, "t_own", 20, tags=("own",))
    add_version(t, "legacy", "l1", "1_legacy", [(t_own, "t_own", {".txt": "legacy"})])
    return created


def _service(target: SyntheticProject) -> ProjectMergeService:
    return ProjectMergeService(target.session_factory(), target.root, target.name)


def _sources(projects: dict[str, SyntheticProject]) -> list[project_transfer_service.SourceProject]:
    return [projects["proj_a"].source, projects["proj_b"].source]


def _rows(project: SyntheticProject, sql: str, *params: object) -> list[tuple[object, ...]]:
    with closing(sqlite3.connect(project.db_path)) as conn:
        return [tuple(row) for row in conn.execute(sql, params).fetchall()]


def _versions(project: SyntheticProject, dataset: str) -> dict[str, tuple[int, str | None]]:
    """版の名前 → (版 ID, parent の版の名前)。"""
    rows = _rows(
        project,
        "SELECT v.id, v.name, p.name FROM dataset_versions v JOIN datasets d ON d.id = v.dataset_id "
        "LEFT JOIN dataset_versions p ON p.id = v.parent_version_id WHERE d.name = ? ORDER BY v.id",
        dataset,
    )
    return {
        str(name): (int(str(vid)), None if parent is None else str(parent)) for vid, name, parent in rows
    }


def _image_dataset_files(project: SyntheticProject) -> dict[str, tuple[str, int]]:
    return file_fingerprints(project.root / "image_dataset")


def test_plan_shows_images_duplicates_versions_and_conflicts(projects: dict[str, SyntheticProject]) -> None:
    target = projects["proj_t"]
    before = table_counts(target, _TARGET_TABLES)

    plan = _service(target).plan(_sources(projects))

    assert [(s.source_project, s.images, s.copy, s.link) for s in plan.images] == [
        ("proj_a", 2, 2, 0),
        ("proj_b", 2, 1, 1),
    ]
    # B の shared は A の shared に 1 枚にまとめる
    assert [(d.source_project, d.merged_into_project) for d in plan.duplicates] == [("proj_b", "proj_a")]
    assert [(v.source.label, v.target_dataset, v.target_version) for v in plan.versions] == [
        ("proj_a:chara/v1", "chara", "v1"),
        ("proj_a:chara/v2", "chara", "v2"),
        ("proj_b:chara/v1", "chara", "v1"),
        ("proj_b:chara/v2", "chara", "v2"),
        ("proj_b:style/s1", "style", "s1"),
    ]
    assert [(c.kind, c.target_dataset, c.sources) for c in plan.conflicts] == [
        ("dataset_name", "chara", ("proj_a:chara", "proj_b:chara"))
    ]
    assert not plan.is_resolved
    template = plan.mapping_template()
    assert {"source_project": "proj_b", "source_dataset": "chara", "target_dataset": "chara"} in template[
        "datasets"
    ]
    # 計画は何も書かない
    assert table_counts(target, _TARGET_TABLES) == before
    assert not (target.root / "image_dataset" / ".transfer_staging").exists()


def test_apply_refuses_unresolved_conflicts_and_writes_nothing(
    projects: dict[str, SyntheticProject],
) -> None:
    target = projects["proj_t"]
    before = table_counts(target, _TARGET_TABLES)
    files_before = _image_dataset_files(target)

    with pytest.raises(UnresolvedMergeConflictError) as excinfo:
        _service(target).apply(_sources(projects))

    assert [(c.kind, c.target_dataset) for c in excinfo.value.conflicts] == [("dataset_name", "chara")]
    assert table_counts(target, _TARGET_TABLES) == before
    assert _image_dataset_files(target) == files_before


def test_apply_with_dataset_rename_merges_images_tags_and_versions(
    projects: dict[str, SyntheticProject],
) -> None:
    target = projects["proj_t"]
    mapping = MergeMapping(dataset_names={B_CHARA: "chara_b"})

    result = _service(target).apply(_sources(projects), mapping)

    # 画像: T の 1 枚 + A の 2 枚 + B の dog (B の shared は A の shared にまとめる)
    assert _rows(target, "SELECT count(*) FROM images") == [(4,)]
    shared_id = result.image_ids[("proj_a", 2)]
    assert result.image_ids[("proj_b", 2)] == shared_id
    tags = {
        str(row[0])
        for row in _rows(
            target,
            "SELECT t.tag FROM tags t JOIN models m ON m.id = t.model_id "
            "WHERE t.image_id = ? AND m.litellm_model_id = ?",
            shared_id,
            "wd/tagger-v3",
        )
    }
    assert tags == {"cat", "outdoor", "night"}
    origins = _rows(target, "SELECT source_project_name FROM image_origins WHERE image_id = ?", shared_id)
    assert sorted(str(row[0]) for row in origins) == ["proj_a", "proj_b"]

    # 版: 親子の連なりを保つ。既存のデータセットは変えない
    assert _versions(target, "chara") == {
        "v1": (result.version_ids[SourceVersionRef("proj_a", "chara", "v1")], None),
        "v2": (result.version_ids[SourceVersionRef("proj_a", "chara", "v2")], "v1"),
    }
    assert {name: parent for name, (_, parent) in _versions(target, "chara_b").items()} == {
        "v1": None,
        "v2": "v1",
    }
    assert {name: parent for name, (_, parent) in _versions(target, "legacy").items()} == {"l1": None}
    # A の v2 と B の v2 は同じ統合先の画像を指す
    folder_images = _rows(
        target,
        "SELECT v.id FROM dataset_folder_images fi JOIN dataset_folders f ON f.id = fi.folder_id "
        "JOIN dataset_versions v ON v.id = f.version_id WHERE fi.image_id = ? ORDER BY v.id",
        shared_id,
    )
    assert [int(str(row[0])) for row in folder_images] == [
        result.version_ids[SourceVersionRef("proj_a", "chara", "v2")],
        result.version_ids[SourceVersionRef("proj_b", "chara", "v2")],
    ]
    # .txt と .caption の両方を引き継ぐ
    texts = _rows(
        target,
        "SELECT lt.extension, lt.raw_text FROM dataset_learning_texts lt "
        "JOIN dataset_folder_images fi ON fi.id = lt.folder_image_id "
        "JOIN dataset_folders f ON f.id = fi.folder_id WHERE f.version_id = ? AND fi.file_stem = 'shared' "
        "ORDER BY lt.extension",
        result.version_ids[SourceVersionRef("proj_a", "chara", "v2")],
    )
    assert texts == [(".caption", "a cat outdoors"), (".txt", "chara, outdoor")]
    kinds = _rows(target, "SELECT DISTINCT kind FROM project_transfer_runs")
    assert kinds == [("merge_project",)]
    assert set(result.transfer_run_ids) == {"proj_a", "proj_b"}
    assert not (target.root / "image_dataset" / ".transfer_staging").exists()


def test_version_origins_can_be_listed_from_target(projects: dict[str, SyntheticProject]) -> None:
    target = projects["proj_t"]
    result = _service(target).apply(_sources(projects), MergeMapping(dataset_names={B_CHARA: "chara_b"}))

    origins = DatasetRepository(session_factory=target.session_factory()).list_version_origins()

    assert [
        (
            o.dataset_name,
            o.version_name,
            o.source_project_name,
            o.source_dataset_name,
            o.source_version_name,
        )
        for o in origins
    ] == [
        ("chara", "v1", "proj_a", "chara", "v1"),
        ("chara", "v2", "proj_a", "chara", "v2"),
        ("chara_b", "v1", "proj_b", "chara", "v1"),
        ("chara_b", "v2", "proj_b", "chara", "v2"),
        ("style", "s1", "proj_b", "style", "s1"),
    ]
    by_version = {o.version_id: o for o in origins}
    b_v2 = by_version[result.version_ids[SourceVersionRef("proj_b", "chara", "v2")]]
    source_ids = _rows(projects["proj_b"], "SELECT id FROM dataset_versions WHERE name = 'v2'")
    assert b_v2.source_version_id == source_ids[0][0]
    assert b_v2.transfer_run_id == result.transfer_run_ids["proj_b"]


def test_join_requires_version_names_then_chains_parents(projects: dict[str, SyntheticProject]) -> None:
    target = projects["proj_t"]
    joined = MergeMapping(joins={"chara": [A_CHARA, B_CHARA]})

    plan = _service(target).plan(_sources(projects), joined)
    assert sorted((c.kind, c.target_version) for c in plan.conflicts) == [
        ("version_name", "v1"),
        ("version_name", "v2"),
    ]

    mapping = MergeMapping(
        joins={"chara": [A_CHARA, B_CHARA]},
        version_names={
            SourceVersionRef("proj_b", "chara", "v1"): "v3",
            SourceVersionRef("proj_b", "chara", "v2"): "v4",
        },
    )
    resolved = _service(target).plan(_sources(projects), mapping)
    assert resolved.is_resolved
    b_root = next(v for v in resolved.versions if v.target_version == "v3")
    assert b_root.joined_parent
    assert b_root.parent is not None and (b_root.parent.source_project, b_root.parent.version) == (
        "proj_a",
        "v2",
    )

    _service(target).apply(_sources(projects), mapping)

    # 前の統合元の最新版 (A の v2) が次の統合元の最初の版 (B の v1 → v3) の parent になる
    assert {name: parent for name, (_, parent) in _versions(target, "chara").items()} == {
        "v1": None,
        "v2": "v1",
        "v3": "v2",
        "v4": "v3",
    }
    # 最新版は v4。KOHYA_DATASET のタグは最新版の学習テキストに揃う (ADR 0104)
    factory = target.session_factory()
    with factory() as session:
        kohya_id = session.execute(
            select(Model.id).where(Model.litellm_model_id == KOHYA_DATASET_LITELLM_ID)
        ).scalar_one()
        shared_id = session.execute(select(Tag.image_id).where(Tag.tag == "outdoor").limit(1)).scalar_one()
        kohya_tags = set(
            session.execute(
                select(Tag.tag).where(Tag.image_id == shared_id, Tag.model_id == kohya_id)
            ).scalars()
        )
    assert kohya_tags == {"chara", "night"}


def test_join_into_existing_target_dataset_continues_its_history(
    projects: dict[str, SyntheticProject],
) -> None:
    target = projects["proj_t"]
    mapping = MergeMapping(
        dataset_names={B_CHARA: "chara_b"},
        joins={"legacy": [SourceDatasetRef("proj_b", "style")]},
    )

    _service(target).apply(_sources(projects), mapping)

    assert {name: parent for name, (_, parent) in _versions(target, "legacy").items()} == {
        "l1": None,
        "s1": "l1",
    }
    assert _rows(target, "SELECT count(*) FROM datasets WHERE name = 'style'") == [(0,)]


def test_existing_target_dataset_name_is_a_conflict(projects: dict[str, SyntheticProject]) -> None:
    plan = _service(projects["proj_t"]).plan(
        _sources(projects), MergeMapping(dataset_names={B_CHARA: "legacy"})
    )

    assert [(c.kind, c.target_dataset, c.sources) for c in plan.conflicts] == [
        ("dataset_exists", "legacy", ("(target)", "proj_b:chara"))
    ]


def test_two_working_versions_in_one_dataset_is_a_conflict(projects: dict[str, SyntheticProject]) -> None:
    a, b = projects["proj_a"], projects["proj_b"]
    add_version(a, "chara", "wip_a", "10_chara", [], is_working=True)
    add_version(b, "chara", "wip_b", "5_chara", [], is_working=True)
    mapping = MergeMapping(
        joins={"chara": [A_CHARA, B_CHARA]},
        version_names={
            SourceVersionRef("proj_b", "chara", "v1"): "v3",
            SourceVersionRef("proj_b", "chara", "v2"): "v4",
        },
    )

    plan = _service(projects["proj_t"]).plan(_sources(projects), mapping)

    assert [(c.kind, c.sources) for c in plan.conflicts] == [
        ("multiple_working_versions", ("proj_a:chara/wip_a", "proj_b:chara/wip_b"))
    ]
    with pytest.raises(UnresolvedMergeConflictError):
        _service(projects["proj_t"]).apply(_sources(projects), mapping)


@pytest.mark.parametrize("failure", ["file_copy", "tag_sync", "commit"])
def test_failure_midway_leaves_no_rows_or_files_in_target(
    projects: dict[str, SyntheticProject], monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    target = projects["proj_t"]
    before = table_counts(target, _TARGET_TABLES)
    files_before = _image_dataset_files(target)

    if failure == "file_copy":
        original_copy = project_transfer_service._copy_file
        calls = {"n": 0}

        def copy_then_fail(source: Path, destination: Path) -> None:
            calls["n"] += 1
            if calls["n"] > 3:
                raise OSError("ディスクがいっぱい")
            original_copy(source, destination)

        monkeypatch.setattr(project_transfer_service, "_copy_file", copy_then_fail)
        expected: type[Exception] = OSError
    elif failure == "tag_sync":

        def fail_sync(
            self: DatasetRepository, session: Session, dataset_id: int, extension: str = ".txt"
        ) -> None:
            raise RuntimeError("同期に失敗")

        monkeypatch.setattr(DatasetRepository, "sync_kohya_tags_in_session", fail_sync)
        expected = RuntimeError
    else:

        def fail_commit(self: Session) -> None:
            raise sqlite3.OperationalError("database is locked")

        monkeypatch.setattr(Session, "commit", fail_commit)
        expected = sqlite3.OperationalError

    with pytest.raises(expected):
        _service(target).apply(_sources(projects), MergeMapping(dataset_names={B_CHARA: "chara_b"}))

    assert table_counts(target, _TARGET_TABLES) == before
    assert _image_dataset_files(target) == files_before
    assert not (target.root / "image_dataset" / ".transfer_staging").exists()


def test_sources_are_not_changed_by_plan_and_apply(projects: dict[str, SyntheticProject]) -> None:
    sources_before = {name: file_fingerprints(projects[name].root) for name in ("proj_a", "proj_b")}
    mapping = MergeMapping(dataset_names={B_CHARA: "chara_b"})

    _service(projects["proj_t"]).plan(_sources(projects), mapping)
    _service(projects["proj_t"]).apply(_sources(projects), mapping)

    assert {name: file_fingerprints(projects[name].root) for name in ("proj_a", "proj_b")} == sources_before


def test_merged_versions_can_be_exported_to_kohya(
    projects: dict[str, SyntheticProject], tmp_path: Path
) -> None:
    target = projects["proj_t"]
    result = _service(target).apply(_sources(projects), MergeMapping(dataset_names={B_CHARA: "chara_b"}))
    exporter = KohyaDatasetExportService(DatasetRepository(session_factory=target.session_factory()))

    mixed = exporter.export_version(
        result.version_ids[SourceVersionRef("proj_a", "chara", "v2")], tmp_path / "out_a"
    )
    plain = exporter.export_version(
        result.version_ids[SourceVersionRef("proj_b", "chara", "v2")], tmp_path / "out_b"
    )

    folder_a = tmp_path / "out_a" / "10_chara"
    assert sorted(path.name for path in folder_a.iterdir()) == [
        "a_cat.png",
        "a_cat.txt",
        "shared.caption",
        "shared.png",
        "shared.txt",
    ]
    assert (folder_a / "shared.caption").read_text(encoding="utf-8") == "a cat outdoors"
    assert mixed.image_count == 2
    assert plain.image_count == 2
    assert (tmp_path / "out_b" / "5_chara" / "shared.txt").read_text(encoding="utf-8") == "chara, night"
    # まとめた 1 枚を 2 つの版が使う。書き出した画像は同じ内容
    assert (folder_a / "shared.png").read_bytes() == (
        tmp_path / "out_b" / "5_chara" / "shared.png"
    ).read_bytes()


def test_rejects_target_as_source_and_duplicate_sources(projects: dict[str, SyntheticProject]) -> None:
    service = _service(projects["proj_t"])

    with pytest.raises(ValueError, match="統合先と同じ"):
        service.plan([projects["proj_a"].source, projects["proj_t"].source])
    with pytest.raises(ValueError, match="重複"):
        service.plan([projects["proj_a"].source, projects["proj_a"].source])


def test_rejects_mapping_for_unknown_dataset_or_version(projects: dict[str, SyntheticProject]) -> None:
    service = _service(projects["proj_t"])

    with pytest.raises(MergeMappingError, match="データセットがありません"):
        service.plan(_sources(projects), MergeMapping(dataset_names={SourceDatasetRef("proj_a", "x"): "y"}))
    with pytest.raises(MergeMappingError, match="版がありません"):
        service.plan(
            _sources(projects),
            MergeMapping(version_names={SourceVersionRef("proj_a", "chara", "v9"): "z"}),
        )


def test_mapping_round_trips_through_template(projects: dict[str, SyntheticProject]) -> None:
    service = _service(projects["proj_t"])
    mapping = MergeMapping(
        joins={"chara": [A_CHARA, B_CHARA]},
        version_names={
            SourceVersionRef("proj_b", "chara", "v1"): "v3",
            SourceVersionRef("proj_b", "chara", "v2"): "v4",
        },
    )
    template = service.plan(_sources(projects), mapping).mapping_template()

    again = service.plan(_sources(projects), MergeMapping.from_json_dict(template))

    assert again.is_resolved
    assert [(v.source.label, v.target_dataset, v.target_version) for v in again.versions][2:4] == [
        ("proj_b:chara/v1", "chara", "v3"),
        ("proj_b:chara/v2", "chara", "v4"),
    ]


def test_plan_into_new_project_writes_nothing(
    projects: dict[str, SyntheticProject], tmp_path: Path
) -> None:
    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))

    plan = ProjectMergeService.plan_into_new_project(
        _sources(projects), MergeMapping(dataset_names={B_CHARA: "chara_b"}), "merged"
    )

    assert plan.is_resolved
    assert plan.target_project == "merged"
    assert [(s.copy, s.link) for s in plan.images] == [(2, 0), (1, 1)]
    after = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    assert [p for p in after if not p.endswith(("-shm", "-wal"))] == [
        p for p in before if not p.endswith(("-shm", "-wal"))
    ]


def test_union_of_same_image_keeps_records_of_different_times(
    projects: dict[str, SyntheticProject],
) -> None:
    """同じ画像のキャプションは値と created_at で重複を除き、時点の違う同じ値の記録は残す (ADR 0112)。"""
    rows = {
        "proj_a": [("same", "2026-01-01 00:00:00")],
        "proj_b": [("same", "2026-01-01 00:00:00"), ("same", "2026-02-01 00:00:00")],
    }
    for name, captions in rows.items():
        with closing(sqlite3.connect(projects[name].db_path)) as conn:
            for caption, created in captions:
                conn.execute(
                    "INSERT INTO captions (image_id, model_id, caption, existing, created_at, updated_at) "
                    "VALUES (2, NULL, ?, 0, ?, ?)",
                    (caption, created, created),
                )
            conn.commit()

    target = projects["proj_t"]
    result = _service(target).apply(_sources(projects), MergeMapping(dataset_names={B_CHARA: "chara_b"}))

    shared_id = result.image_ids[("proj_a", 2)]
    kept = _rows(
        target,
        "SELECT caption, created_at FROM captions WHERE image_id = ? ORDER BY created_at",
        shared_id,
    )
    assert [(str(c), str(t)[:10]) for c, t in kept] == [("same", "2026-01-01"), ("same", "2026-02-01")]


def _source_version_id(project: SyntheticProject, dataset: str, version: str) -> int:
    rows = _rows(
        project,
        "SELECT v.id FROM dataset_versions v JOIN datasets d ON d.id = v.dataset_id "
        "WHERE d.name = ? AND v.name = ?",
        dataset,
        version,
    )
    return int(str(rows[0][0]))


def _parent_of(project: SyntheticProject, dataset: str, version: str) -> tuple[str, str] | None:
    """統合先の版の parent を (データセット名, 版の名前) で返す。"""
    rows = _rows(
        project,
        "SELECT pd.name, p.name FROM dataset_versions v JOIN datasets d ON d.id = v.dataset_id "
        "LEFT JOIN dataset_versions p ON p.id = v.parent_version_id "
        "LEFT JOIN datasets pd ON pd.id = p.dataset_id WHERE d.name = ? AND v.name = ?",
        dataset,
        version,
    )
    dataset_name, version_name = rows[0]
    return None if version_name is None else (str(dataset_name), str(version_name))


def test_parent_in_another_dataset_is_kept(projects: dict[str, SyntheticProject]) -> None:
    """別のデータセットの版を parent にした版 (`dataset import --parent-version`) も親子関係を保つ。"""
    b = projects["proj_b"]
    b_dog = int(str(_rows(b, "SELECT id FROM images WHERE filename = 'b_dog.png'")[0][0]))
    add_version(
        b,
        "style",
        "s2",
        "1_style",
        [(b_dog, "b_dog", {".txt": "style, dog"})],
        parent_version_id=_source_version_id(b, "chara", "v2"),
    )
    target = projects["proj_t"]

    plan = _service(target).plan(_sources(projects), MergeMapping(dataset_names={B_CHARA: "chara_b"}))
    s2 = next(v for v in plan.versions if v.source.label == "proj_b:style/s2")
    assert s2.parent is not None
    assert (s2.parent.source_project, s2.parent.dataset, s2.parent.version) == ("proj_b", "chara", "v2")
    assert not s2.joined_parent

    _service(target).apply(_sources(projects), MergeMapping(dataset_names={B_CHARA: "chara_b"}))

    assert _parent_of(target, "style", "s2") == ("chara_b", "v2")
    assert _parent_of(target, "style", "s1") is None


def test_parent_in_another_dataset_is_kept_with_joined_histories(
    projects: dict[str, SyntheticProject],
) -> None:
    """履歴をまとめても、別のデータセットにある parent は対応する統合先の版を指す。"""
    b = projects["proj_b"]
    b_dog = int(str(_rows(b, "SELECT id FROM images WHERE filename = 'b_dog.png'")[0][0]))
    add_version(
        b,
        "style",
        "s2",
        "1_style",
        [(b_dog, "b_dog", {".txt": "style, dog"})],
        parent_version_id=_source_version_id(b, "chara", "v2"),
    )
    target = projects["proj_t"]
    mapping = MergeMapping(
        joins={"chara": [A_CHARA, B_CHARA], "legacy": [SourceDatasetRef("proj_b", "style")]},
        version_names={
            SourceVersionRef("proj_b", "chara", "v1"): "v3",
            SourceVersionRef("proj_b", "chara", "v2"): "v4",
        },
    )

    _service(target).apply(_sources(projects), mapping)

    # style の最初の版 (s1) は既存の legacy の最新版に続き、s2 は B の chara/v2 (統合先の chara/v4) を指す
    assert _parent_of(target, "legacy", "s1") == ("legacy", "l1")
    assert _parent_of(target, "legacy", "s2") == ("chara", "v4")
    assert _parent_of(target, "chara", "v3") == ("chara", "v2")


def test_join_that_would_make_a_cycle_is_a_conflict(projects: dict[str, SyntheticProject]) -> None:
    """データセットをまたぐ parent と逆の順で履歴をまとめると循環するので、衝突にして確定しない。

    A の extra/e1 の parent は A の chara/v2。extra → chara の順にまとめると、chara の最初の版 v1 の
    parent が extra の最新版 e1 になり、v1 → e1 → v2 → v1 と循環する。
    """
    a = projects["proj_a"]
    a_cat = int(str(_rows(a, "SELECT id FROM images WHERE filename = 'a_cat.png'")[0][0]))
    add_version(
        a,
        "extra",
        "e1",
        "1_extra",
        [(a_cat, "a_cat", {".txt": "extra"})],
        parent_version_id=_source_version_id(a, "chara", "v2"),
    )
    target = projects["proj_t"]
    before = table_counts(target, _TARGET_TABLES)
    mapping = MergeMapping(
        dataset_names={B_CHARA: "chara_b"},
        joins={"chara": [SourceDatasetRef("proj_a", "extra"), A_CHARA]},
    )

    plan = _service(target).plan(_sources(projects), mapping)

    assert [(c.kind, c.target_dataset) for c in plan.conflicts] == [("cyclic_history", "chara")]
    conflict = plan.conflicts[0]
    assert set(conflict.sources) == {"proj_a:chara/v1", "proj_a:extra/e1", "proj_a:chara/v2"}
    assert "循環" in conflict.message
    with pytest.raises(UnresolvedMergeConflictError):
        _service(target).apply(_sources(projects), mapping)
    assert table_counts(target, _TARGET_TABLES) == before

    # 逆の順 (chara → extra) なら循環しない
    ordered = MergeMapping(
        dataset_names={B_CHARA: "chara_b"},
        joins={"chara": [A_CHARA, SourceDatasetRef("proj_a", "extra")]},
    )
    assert _service(target).plan(_sources(projects), ordered).is_resolved
