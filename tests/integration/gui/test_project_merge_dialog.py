"""`ProjectMergeDialog` の GUI 統合テスト (Issue #1660, ADR 0113)。

tmp_path に 3 つのプロジェクト (統合元 A / B と、既存のデータセットを持つ統合先 T) を合成し、
本物の `ProjectManagementService` と `ProjectMergeService` で、統合元の選択 → 計画の表示 →
衝突の名前の対応の指定 → 確定までをダイアログから通す。DB は本物の migration を通したもの、
画像は本物の PNG (合成方法は tests/integration/project_transfer_fixtures.py)。
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
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
from pytestqt.qtbot import QtBot
from sqlalchemy.orm import Session

from lorairo.database.repository.dataset import DatasetRepository
from lorairo.gui.widgets import project_merge_dialog as dialog_module
from lorairo.gui.widgets.project_merge_dialog import ProjectMergeDialog
from lorairo.gui.workers import project_merge_workers
from lorairo.services.project_management_service import ProjectManagementService
from lorairo.services.project_merge_service import MergeMapping, MergePlan

pytestmark = [pytest.mark.integration, pytest.mark.gui]

_TIMEOUT_MS = 60000
_TARGET_TABLES = (
    "images",
    "tags",
    "image_origins",
    "project_transfer_runs",
    "datasets",
    "dataset_versions",
    "dataset_folders",
    "dataset_folder_images",
    "dataset_learning_texts",
    "dataset_version_origins",
)


@pytest.fixture(scope="module")
def template_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_migrated_template(tmp_path_factory.mktemp("gui_merge_template") / "image_database.db")


@pytest.fixture
def projects_dir(tmp_path: Path) -> Path:
    path = tmp_path / "projects"
    path.mkdir()
    return path


@pytest.fixture
def projects(projects_dir: Path, template_db: Path) -> dict[str, SyntheticProject]:
    created = {
        name: make_project(projects_dir, name, template_db) for name in ("proj_a", "proj_b", "proj_t")
    }
    a, b, t = created["proj_a"], created["proj_b"], created["proj_t"]

    a_cat = add_image(a, "a_cat", 1, tags=("cat", "smile"))
    a_shared = add_image(a, "shared", 9, tags=("cat", "outdoor"))
    a_v1 = add_version(a, "chara", "v1", "10_chara", [(a_cat, "a_cat", {".txt": "chara, cat"})])
    add_version(
        a,
        "chara",
        "v2",
        "10_chara",
        [(a_cat, "a_cat", {".txt": "chara, cat, smile"}), (a_shared, "shared", {".txt": "chara, outdoor"})],
        parent_version_id=a_v1,
    )
    b_dog = add_image(b, "b_dog", 3, tags=("dog",))
    # A の shared と同じ画像 (同じ pHash と属性)
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
    t_own = add_image(t, "t_own", 20, tags=("own",))
    add_version(t, "legacy", "l1", "1_legacy", [(t_own, "t_own", {".txt": "legacy"})])

    # プロジェクトの一覧 (`list_projects`) に出すためのメタデータ
    service = ProjectManagementService(projects_base_dir=projects_dir)
    for project in created.values():
        service.ensure_project_metadata(project.root)
    return created


@pytest.fixture
def messages(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    """ダイアログが出すメッセージボックスを記録する (表示はしない)。"""
    shown: dict[str, list[str]] = {"information": [], "critical": []}
    monkeypatch.setattr(
        dialog_module, "show_information", lambda _parent, title, _text: shown["information"].append(title)
    )
    monkeypatch.setattr(
        dialog_module, "show_critical", lambda _parent, title, _text: shown["critical"].append(title)
    )
    return shown


@pytest.fixture
def dialog(
    qtbot: QtBot, projects_dir: Path, projects: dict[str, SyntheticProject]
) -> Iterator[ProjectMergeDialog]:
    widget = ProjectMergeDialog(
        ProjectManagementService(projects_base_dir=projects_dir),
        current_project_root=projects["proj_t"].root,
    )
    qtbot.addWidget(widget)
    qtbot.waitUntil(lambda: not widget.is_busy and widget.source_list.count() == 3, timeout=_TIMEOUT_MS)
    yield widget
    qtbot.waitUntil(lambda: not widget.is_busy, timeout=_TIMEOUT_MS)


def _check_sources(dialog: ProjectMergeDialog, *names: str) -> None:
    for row in range(dialog.source_list.count()):
        item = dialog.source_list.item(row)
        if item.text().split()[0] in names:
            item.setCheckState(dialog_module.Qt.CheckState.Checked)


def _wait_plan(qtbot: QtBot, dialog: ProjectMergeDialog) -> MergePlan:
    qtbot.waitUntil(lambda: not dialog.is_busy and dialog.current_plan is not None, timeout=_TIMEOUT_MS)
    plan = dialog.current_plan
    assert plan is not None
    return plan


def _make_plan(qtbot: QtBot, dialog: ProjectMergeDialog) -> MergePlan:
    _check_sources(dialog, "proj_a", "proj_b")
    assert dialog.plan_button.isEnabled()
    dialog.plan_button.click()
    return _wait_plan(qtbot, dialog)


def _edit_cell(dialog: ProjectMergeDialog, source_label: str, column: int, text: str) -> None:
    table = dialog.version_table
    for row in range(table.rowCount()):
        if table.item(row, 0).text() == source_label:
            table.item(row, column).setText(text)
            return
    raise AssertionError(f"版が表にない: {source_label}")


def _stat_value(dialog: ProjectMergeDialog, object_name: str) -> str:
    tile = dialog.findChild(dialog_module.DsSummaryStat, object_name)
    assert tile is not None
    label = tile.findChild(dialog_module.QLabel, "summaryStatValue")
    assert label is not None
    return label.text()


def _versions(project: SyntheticProject, dataset: str) -> dict[str, str | None]:
    """版の名前 → parent の版の名前。"""
    with closing(sqlite3.connect(project.db_path)) as conn:
        rows = conn.execute(
            "SELECT v.name, p.name FROM dataset_versions v JOIN datasets d ON d.id = v.dataset_id "
            "LEFT JOIN dataset_versions p ON p.id = v.parent_version_id WHERE d.name = ? ORDER BY v.id",
            (dataset,),
        ).fetchall()
    return {str(name): None if parent is None else str(parent) for name, parent in rows}


def test_target_project_cannot_be_a_source(dialog: ProjectMergeDialog) -> None:
    # 統合先の既定値は現在のプロジェクト (T)
    assert dialog.target_combo.currentText() == "proj_t"
    flags = {
        dialog.source_list.item(row).text().split()[0]: dialog.source_list.item(row).flags()
        for row in range(dialog.source_list.count())
    }
    assert not flags["proj_t"] & dialog_module.Qt.ItemFlag.ItemIsEnabled
    assert flags["proj_a"] & dialog_module.Qt.ItemFlag.ItemIsEnabled

    # 統合先を A に変えると、A を選べなくなり T を選べるようになる
    _check_sources(dialog, "proj_a")
    dialog.target_combo.setCurrentText("proj_a")
    items = {
        dialog.source_list.item(row).text().split()[0]: dialog.source_list.item(row)
        for row in range(dialog.source_list.count())
    }
    assert not items["proj_a"].flags() & dialog_module.Qt.ItemFlag.ItemIsEnabled
    assert items["proj_a"].checkState() == dialog_module.Qt.CheckState.Unchecked
    assert items["proj_t"].flags() & dialog_module.Qt.ItemFlag.ItemIsEnabled
    assert not dialog.plan_button.isEnabled()


def test_confirm_is_disabled_until_dataset_rename_resolves_conflict_then_merges(
    qtbot: QtBot,
    dialog: ProjectMergeDialog,
    projects: dict[str, SyntheticProject],
    messages: dict[str, list[str]],
) -> None:
    sources_before = {name: file_fingerprints(projects[name].root) for name in ("proj_a", "proj_b")}

    plan = _make_plan(qtbot, dialog)

    assert [(c.kind, c.target_dataset) for c in plan.conflicts] == [("dataset_name", "chara")]
    assert dialog.conflict_table.rowCount() == 1
    assert dialog.version_table.rowCount() == 4
    assert _stat_value(dialog, "projectMergeStatImages") == "4"
    assert _stat_value(dialog, "projectMergeStatDuplicates") == "1"
    assert _stat_value(dialog, "projectMergeStatVersions") == "4"
    assert _stat_value(dialog, "projectMergeStatConflicts") == "1"
    assert not dialog.confirm_button.isEnabled()

    # B の chara を chara_b にする (表のセルを書き換えると計画を作り直す)
    _edit_cell(dialog, "proj_b:chara/v1", dialog_module._COL_DATASET, "chara_b")
    qtbot.waitUntil(
        lambda: not dialog.is_busy and dialog.current_plan is not None and dialog.current_plan.is_resolved,
        timeout=_TIMEOUT_MS,
    )
    assert dialog.conflict_table.rowCount() == 0
    assert _stat_value(dialog, "projectMergeStatConflicts") == "0"
    assert dialog.confirm_button.isEnabled()

    dialog.confirm_button.click()
    qtbot.waitUntil(
        lambda: dialog.merged_target_root is not None and not dialog.is_busy, timeout=_TIMEOUT_MS
    )

    target = projects["proj_t"]
    assert dialog.merged_target_root == target.root.resolve()
    assert messages == {"information": ["プロジェクトを統合しました"], "critical": []}
    assert not dialog.confirm_button.isEnabled()
    # 画像は T の 1 枚 + A の 2 枚 + B の dog 1 枚 (B の shared は A の shared にまとめる)
    assert table_counts(target, ("images",)) == {"images": 4}
    assert _versions(target, "chara") == {"v1": None, "v2": "v1"}
    assert _versions(target, "chara_b") == {"v1": None, "v2": "v1"}
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
    ]
    # 統合元は変わらない
    assert {name: file_fingerprints(projects[name].root) for name in ("proj_a", "proj_b")} == sources_before


def test_join_with_version_renames_chains_one_history(
    qtbot: QtBot,
    dialog: ProjectMergeDialog,
    projects: dict[str, SyntheticProject],
    messages: dict[str, list[str]],
) -> None:
    _make_plan(qtbot, dialog)

    # A の chara → B の chara の順に 1 つの履歴にまとめる
    dialog.join_name_edit.setText("chara")
    labels = [dialog.join_source_list.item(row).text() for row in range(dialog.join_source_list.count())]
    assert labels == ["proj_a:chara", "proj_b:chara"]
    for row in range(dialog.join_source_list.count()):
        dialog.join_source_list.item(row).setCheckState(dialog_module.Qt.CheckState.Checked)
    dialog.add_join_button.click()
    qtbot.waitUntil(lambda: not dialog.is_busy and bool(dialog.mapping.joins), timeout=_TIMEOUT_MS)
    plan = dialog.current_plan
    assert plan is not None
    assert sorted((c.kind, c.target_version) for c in plan.conflicts) == [
        ("version_name", "v1"),
        ("version_name", "v2"),
    ]
    assert dialog.join_list.count() == 1
    assert not dialog.confirm_button.isEnabled()

    _edit_cell(dialog, "proj_b:chara/v1", dialog_module._COL_VERSION, "v3")
    qtbot.waitUntil(
        lambda: not dialog.is_busy and len(dialog.mapping.version_names) == 1, timeout=_TIMEOUT_MS
    )
    assert not dialog.confirm_button.isEnabled()
    _edit_cell(dialog, "proj_b:chara/v2", dialog_module._COL_VERSION, "v4")
    plan = _wait_plan(qtbot, dialog)
    assert len(dialog.mapping.version_names) == 2
    assert plan.is_resolved
    assert dialog.confirm_button.isEnabled()

    dialog.confirm_button.click()
    qtbot.waitUntil(
        lambda: dialog.merged_target_root is not None and not dialog.is_busy, timeout=_TIMEOUT_MS
    )

    # 前の統合元の最新版 (A の v2) が次の統合元の最初の版 (B の v1 → v3) の parent になる
    assert _versions(projects["proj_t"], "chara") == {"v1": None, "v2": "v1", "v3": "v2", "v4": "v3"}


def _join(dialog: ProjectMergeDialog, name: str, labels: list[str]) -> None:
    """まとめる指定を、labels の順に並べ替えてから足す。"""
    dialog.join_name_edit.setText(name)
    for position, label in enumerate(labels):
        rows = [dialog.join_source_list.item(row).text() for row in range(dialog.join_source_list.count())]
        dialog.join_source_list.setCurrentRow(rows.index(label))
        while dialog.join_source_list.currentRow() > position:
            dialog.join_up_button.click()
    for row in range(dialog.join_source_list.count()):
        item = dialog.join_source_list.item(row)
        if item.text() in labels:
            item.setCheckState(dialog_module.Qt.CheckState.Checked)
    dialog.add_join_button.click()


def test_cyclic_history_conflict_is_shown_and_blocks_confirm(
    qtbot: QtBot, dialog: ProjectMergeDialog, projects: dict[str, SyntheticProject]
) -> None:
    """データセットをまたぐ parent と逆の順で履歴をまとめると循環し、衝突として表示する。

    A の extra/e1 の parent は A の chara/v2。extra → chara の順にまとめると v1 → e1 → v2 → v1 と循環する。
    """
    a = projects["proj_a"]
    with closing(sqlite3.connect(a.db_path)) as conn:
        a_cat = int(conn.execute("SELECT id FROM images WHERE uuid = 'proj_a-a_cat'").fetchone()[0])
        a_v2 = int(conn.execute("SELECT id FROM dataset_versions WHERE name = 'v2'").fetchone()[0])
    add_version(a, "extra", "e1", "1_extra", [(a_cat, "a_cat", {".txt": "extra"})], parent_version_id=a_v2)

    plan = _make_plan(qtbot, dialog)
    # データセットをまたぐ parent はそのまま表示する
    extra = next(v for v in plan.versions if v.source.label == "proj_a:extra/e1")
    assert dialog_module._parent_text(extra) == "proj_a:chara/v2"
    _edit_cell(dialog, "proj_b:chara/v1", dialog_module._COL_DATASET, "chara_b")
    _wait_plan(qtbot, dialog)

    _join(dialog, "chara", ["proj_a:extra", "proj_a:chara"])
    plan = _wait_plan(qtbot, dialog)

    assert [(c.kind, c.target_dataset) for c in plan.conflicts] == [("cyclic_history", "chara")]
    kinds = [dialog.conflict_table.item(row, 0).text() for row in range(dialog.conflict_table.rowCount())]
    assert kinds == ["版の親子関係が循環"]
    assert "循環" in dialog.conflict_table.item(0, 4).text()
    assert _stat_value(dialog, "projectMergeStatConflicts") == "1"
    assert not dialog.confirm_button.isEnabled()

    # 指定を外して逆の順 (chara → extra) でまとめ直すと循環しない
    dialog.join_list.setCurrentRow(0)
    dialog.remove_join_button.click()
    _wait_plan(qtbot, dialog)
    _join(dialog, "chara", ["proj_a:chara", "proj_a:extra"])
    plan = _wait_plan(qtbot, dialog)
    assert plan.is_resolved
    assert dialog.confirm_button.isEnabled()


def test_dataset_without_versions_can_be_renamed_to_resolve_conflict(
    qtbot: QtBot, dialog: ProjectMergeDialog, projects: dict[str, SyntheticProject]
) -> None:
    """版を持たないデータセットの名前の衝突も、ダイアログで名前を変えて解消できる。"""
    for name in ("proj_a", "proj_b"):
        factory = projects[name].session_factory()
        DatasetRepository(session_factory=factory).ensure_dataset("empty")
        factory.kw["bind"].dispose()

    plan = _make_plan(qtbot, dialog)
    assert ("dataset_name", "empty") in [(c.kind, c.target_dataset) for c in plan.conflicts]
    table = dialog.dataset_table
    rows = {table.item(row, 0).text(): row for row in range(table.rowCount())}
    assert {"proj_a:empty", "proj_b:empty", "proj_a:chara", "proj_b:chara"} <= set(rows)
    joinable = [dialog.join_source_list.item(row).text() for row in range(dialog.join_source_list.count())]
    assert "proj_b:empty" in joinable

    table.item(rows["proj_b:empty"], 1).setText("empty_b")
    _wait_plan(qtbot, dialog)
    rows = {table.item(row, 0).text(): row for row in range(table.rowCount())}
    table.item(rows["proj_b:chara"], 1).setText("chara_b")
    plan = _wait_plan(qtbot, dialog)

    assert plan.is_resolved
    assert dialog.confirm_button.isEnabled()


@pytest.mark.parametrize("name", ["../merged", "a/b", "..", "a\\b"])
def test_new_target_name_with_path_parts_is_rejected(
    qtbot: QtBot, dialog: ProjectMergeDialog, projects_dir: Path, name: str
) -> None:
    dialog.new_target_radio.setChecked(True)
    dialog.new_target_edit.setText(name)
    _check_sources(dialog, "proj_a", "proj_b")

    assert not dialog.plan_button.isEnabled()
    assert "プロジェクト名" in dialog.selection_hint_label.text()


@pytest.mark.parametrize("name", ["../merged", "a/b"])
def test_workers_reject_new_target_name_outside_projects_dir(
    projects_dir: Path, projects: dict[str, SyntheticProject], name: str
) -> None:
    sources = [projects["proj_a"].source]
    target = project_merge_workers.MergeTarget(name=name, root=None)
    service = ProjectManagementService(projects_base_dir=projects_dir)
    entries_before = sorted(path.name for path in projects_dir.parent.iterdir())

    with pytest.raises(ValueError, match="プロジェクト名"):
        project_merge_workers.ProjectMergePlanWorker(sources, MergeMapping(), target).execute()
    with pytest.raises(ValueError, match="プロジェクト名"):
        project_merge_workers.ProjectMergeApplyWorker(sources, MergeMapping(), target, service).execute()

    assert sorted(path.name for path in projects_dir.parent.iterdir()) == entries_before
    assert sorted(path.name for path in projects_dir.iterdir()) == ["proj_a", "proj_b", "proj_t"]


def test_apply_failure_shows_error_and_leaves_target_unchanged(
    qtbot: QtBot,
    dialog: ProjectMergeDialog,
    projects: dict[str, SyntheticProject],
    messages: dict[str, list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = projects["proj_t"]
    _make_plan(qtbot, dialog)
    _edit_cell(dialog, "proj_b:chara/v1", dialog_module._COL_DATASET, "chara_b")
    qtbot.waitUntil(lambda: dialog.confirm_button.isEnabled(), timeout=_TIMEOUT_MS)
    before = table_counts(target, _TARGET_TABLES)
    files_before = file_fingerprints(target.root / "image_dataset")

    def fail_sync(
        self: DatasetRepository, session: Session, dataset_id: int, extension: str = ".txt"
    ) -> None:
        raise RuntimeError("同期に失敗")

    monkeypatch.setattr(DatasetRepository, "sync_kohya_tags_in_session", fail_sync)
    dialog.confirm_button.click()
    qtbot.waitUntil(lambda: bool(messages["critical"]) and not dialog.is_busy, timeout=_TIMEOUT_MS)

    assert messages["critical"] == ["プロジェクトを統合できませんでした"]
    assert "同期に失敗" in dialog.status_label.text()
    assert dialog.merged_target_root is None
    assert table_counts(target, _TARGET_TABLES) == before
    assert file_fingerprints(target.root / "image_dataset") == files_before
    assert not (target.root / "image_dataset" / ".transfer_staging").exists()
    # 計画は残るので、原因を直せば確定をやり直せる
    assert dialog.confirm_button.isEnabled()


def test_new_target_project_is_created_and_removed_on_failure(
    qtbot: QtBot,
    dialog: ProjectMergeDialog,
    projects_dir: Path,
    messages: dict[str, list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog.new_target_radio.setChecked(True)
    dialog.new_target_edit.setText("merged")
    plan = _make_plan(qtbot, dialog)
    assert plan.target_project == "merged"
    _edit_cell(dialog, "proj_b:chara/v1", dialog_module._COL_DATASET, "chara_b")
    qtbot.waitUntil(lambda: dialog.confirm_button.isEnabled(), timeout=_TIMEOUT_MS)
    # 計画ではプロジェクトを作らない
    assert not any(path.name.startswith("merged_") for path in projects_dir.iterdir())

    def fail_sync(
        self: DatasetRepository, session: Session, dataset_id: int, extension: str = ".txt"
    ) -> None:
        raise RuntimeError("同期に失敗")

    with monkeypatch.context() as patch:
        patch.setattr(DatasetRepository, "sync_kohya_tags_in_session", fail_sync)
        dialog.confirm_button.click()
        qtbot.waitUntil(lambda: bool(messages["critical"]) and not dialog.is_busy, timeout=_TIMEOUT_MS)
    # 作った統合先は失敗したら消す
    assert not any(path.name.startswith("merged_") for path in projects_dir.iterdir())

    dialog.confirm_button.click()
    qtbot.waitUntil(
        lambda: dialog.merged_target_root is not None and not dialog.is_busy, timeout=_TIMEOUT_MS
    )
    created = [path for path in projects_dir.iterdir() if path.name.startswith("merged_")]
    assert len(created) == 1
    assert dialog.merged_target_root == created[0].resolve()
    merged = SyntheticProject(name="merged", root=created[0])
    assert table_counts(merged, ("images", "dataset_version_origins")) == {
        "images": 3,
        "dataset_version_origins": 4,
    }
    # 作ったプロジェクトが一覧に出る
    qtbot.waitUntil(lambda: dialog.source_list.count() == 4, timeout=_TIMEOUT_MS)


def test_worker_results_are_handled_on_gui_thread(
    qtbot: QtBot, dialog: ProjectMergeDialog, monkeypatch: pytest.MonkeyPatch
) -> None:
    threads: list[int] = []
    original = ProjectMergeDialog._set_plan

    def record(self: ProjectMergeDialog, plan: MergePlan) -> None:
        threads.append(threading.get_ident())
        original(self, plan)

    monkeypatch.setattr(ProjectMergeDialog, "_set_plan", record)
    _make_plan(qtbot, dialog)

    assert threads == [threading.main_thread().ident]


def test_dialog_cannot_be_closed_while_planning(
    qtbot: QtBot, dialog: ProjectMergeDialog, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = threading.Event()
    original = project_merge_workers.ProjectMergePlanWorker.execute

    def blocking_execute(self: project_merge_workers.ProjectMergePlanWorker) -> MergePlan:
        release.wait(30)
        return original(self)

    monkeypatch.setattr(project_merge_workers.ProjectMergePlanWorker, "execute", blocking_execute)
    dialog.show()
    _check_sources(dialog, "proj_a", "proj_b")
    dialog.plan_button.click()
    assert dialog.is_busy
    assert not dialog.close_button.isEnabled()

    dialog.reject()
    dialog.close()
    assert dialog.isVisible()

    release.set()
    _wait_plan(qtbot, dialog)
    dialog.reject()
    assert not dialog.isVisible()
