"""プロジェクト横断の検索・コピー・由来の表示・版の作成の GUI 統合テスト (Issue #1661, ADR 0112)。

tmp_path に合成したプロジェクト (コピー元 A / B と取り込み先 T) で、本物の migration を通した DB と
本物の画像ファイルを使い、ダイアログを worker 経由で動かす。サービスはモックしない。
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest
from project_transfer_fixtures import (
    SyntheticProject,
    add_image,
    build_migrated_template,
    file_fingerprints,
    make_project,
    table_counts,
)

from lorairo.database.filter_criteria import ImageFilterCriteria
from lorairo.database.repository.dataset import DatasetRepository
from lorairo.database.repository.image_origin import ImageOriginRepository
from lorairo.gui.tab.search_tab import SearchTabWidget
from lorairo.gui.widgets import cross_project_search_dialog
from lorairo.gui.widgets.cross_project_search_dialog import CrossProjectSearchDialog
from lorairo.gui.widgets.dataset_version_build_dialog import DatasetVersionBuildDialog
from lorairo.gui.widgets.selected_image_details_widget import SelectedImageDetailsWidget
from lorairo.gui.workers.cross_project_workers import CrossProjectCopyOutcome
from lorairo.services.dataset_version_build_service import DatasetVersionBuildService
from lorairo.services.project_management_service import ProjectManagementService
from lorairo.services.project_transfer_service import ProjectTransferService

pytestmark = [pytest.mark.integration, pytest.mark.gui]

_WAIT_MS = 20000


@pytest.fixture(scope="module")
def template_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_migrated_template(tmp_path_factory.mktemp("gui_transfer_template") / "image_database.db")


def _write_metadata(project: SyntheticProject) -> None:
    (project.root / ".lorairo-project").write_text(
        json.dumps({"name": project.name, "created": "20260101_000000", "description": ""}),
        encoding="utf-8",
    )


@pytest.fixture
def projects(tmp_path: Path, template_db: Path) -> dict[str, SyntheticProject]:
    created = {name: make_project(tmp_path, name, template_db) for name in ("proj_a", "proj_b", "proj_t")}
    for project in created.values():
        _write_metadata(project)
    a, b = created["proj_a"], created["proj_b"]
    add_image(a, "a_cat", 1, tags=("cat", "smile"), caption="a cat", score=6.5, rating="PG")
    add_image(a, "a_dog", 2, tags=("dog",))
    add_image(b, "b_cat", 3, tags=("cat", "blue eyes"))
    return created


def _image_id(project: SyntheticProject, stem: str) -> int:
    with closing(sqlite3.connect(project.db_path)) as conn:
        row = conn.execute("SELECT id FROM images WHERE filename = ?", (f"{stem}.png",)).fetchone()
    assert row is not None
    image_id: int = row[0]
    return image_id


def _open_dialog(
    qtbot, projects: dict[str, SyntheticProject], criteria: ImageFilterCriteria
) -> CrossProjectSearchDialog:
    target = projects["proj_t"]
    dialog = CrossProjectSearchDialog(
        project_service=ProjectManagementService(projects_base_dir=target.root.parent),
        target_root=target.root,
        target_session_factory=target.session_factory(),
        criteria_factory=lambda: criteria,
        criteria_text="タグ: cat",
    )
    qtbot.addWidget(dialog)
    qtbot.waitUntil(lambda: dialog.project_list.count() == 2, timeout=_WAIT_MS)
    return dialog


def _search(qtbot, dialog: CrossProjectSearchDialog, names: list[str]) -> None:
    for name in names:
        dialog.set_project_checked(name)
    with qtbot.waitSignal(dialog._search_finished, timeout=_WAIT_MS):
        dialog.start_search()
    qtbot.waitUntil(lambda: dialog.search_button.isEnabled(), timeout=_WAIT_MS)


def test_search_across_projects_lists_hits_with_project_and_origin(qtbot, projects) -> None:
    """選んだプロジェクトを現在の条件で検索し、出所 (プロジェクト名) と既にある由来を表に出す。"""
    a, b = projects["proj_a"], projects["proj_b"]
    # B の画像を A へコピーしておき、A の検索結果に「B 由来」が出ることを確かめる
    ProjectTransferService(a.session_factory(), a.root, a.name).copy_images(
        b.source, [_image_id(b, "b_cat")]
    )

    dialog = _open_dialog(qtbot, projects, ImageFilterCriteria(tags=["cat"]))
    # 現在のプロジェクト (T) は検索対象に出さない
    assert sorted(dialog.project_list.item(i).text() for i in range(2)) == ["proj_a", "proj_b"]
    assert dialog.target_name == "proj_t"

    _search(qtbot, dialog, ["proj_a"])

    rows = {
        (
            dialog.result_table.item(r, 0).text(),
            dialog.result_table.item(r, 2).text(),
        ): dialog.result_table.item(r, 4).text()
        for r in range(dialog.result_table.rowCount())
    }
    assert rows == {
        ("proj_a", "a_cat.png"): "-",
        ("proj_a", "b_cat.png"): f"proj_b #{_image_id(b, 'b_cat')}",
    }


def test_copy_shows_dry_run_plan_then_copies_and_keeps_sources_unchanged(
    qtbot, projects, monkeypatch: pytest.MonkeyPatch
) -> None:
    """コピーは dry-run の計画を確認してから実行し、取り込み先に由来を残し、コピー元を変えない。"""
    a, b, t = projects["proj_a"], projects["proj_b"], projects["proj_t"]
    before = {name: file_fingerprints(p.root) for name, p in (("a", a), ("b", b))}
    plans: list[CrossProjectCopyOutcome] = []

    def confirm(parent, outcome: CrossProjectCopyOutcome, target_name: str) -> bool:
        plans.append(outcome)
        # 計画の段階では取り込み先に何も書かれていない
        assert table_counts(t, ("images", "image_origins")) == {"images": 0, "image_origins": 0}
        return True

    monkeypatch.setattr(cross_project_search_dialog, "confirm_copy_plan", confirm)

    dialog = _open_dialog(qtbot, projects, ImageFilterCriteria(tags=["cat"]))
    _search(qtbot, dialog, ["proj_a", "proj_b"])
    assert len(dialog.hits()) == 2
    dialog.select_hits([0, 1])

    with qtbot.waitSignal(dialog.images_copied, timeout=_WAIT_MS) as copied:
        dialog.start_copy()

    assert len(plans) == 1 and plans[0].dry_run is True
    assert (plans[0].count("copy"), plans[0].count("link"), plans[0].count("already_linked")) == (2, 0, 0)
    target_ids = copied.args[0]
    assert len(target_ids) == 2
    origins = ImageOriginRepository(session_factory=t.session_factory()).list_origins(target_ids)
    assert sorted((o[0].source_project_name, o[0].source_image_id) for o in origins.values()) == sorted(
        [("proj_a", _image_id(a, "a_cat")), ("proj_b", _image_id(b, "b_cat"))]
    )
    assert table_counts(t, ("images", "image_origins")) == {"images": 2, "image_origins": 2}
    # コピー元のファイル (DB と画像) のハッシュと mtime は変わらない
    assert {"a": file_fingerprints(a.root), "b": file_fingerprints(b.root)} == before


def test_copy_cancelled_at_plan_writes_nothing(qtbot, projects, monkeypatch: pytest.MonkeyPatch) -> None:
    """計画の確認で取り消したら、取り込み先に何も書かない。"""
    t = projects["proj_t"]
    monkeypatch.setattr(cross_project_search_dialog, "confirm_copy_plan", lambda *args: False)
    dialog = _open_dialog(qtbot, projects, ImageFilterCriteria())
    _search(qtbot, dialog, ["proj_a"])
    dialog.select_hits([0])

    with qtbot.waitSignal(dialog._copy_planned, timeout=_WAIT_MS):
        dialog.start_copy()

    qtbot.waitUntil(lambda: dialog.status_label.text() == "コピーをキャンセルしました", timeout=_WAIT_MS)
    assert table_counts(t, ("images", "image_origins", "project_transfer_runs")) == {
        "images": 0,
        "image_origins": 0,
        "project_transfer_runs": 0,
    }


def _copy_into_target(projects: dict[str, SyntheticProject]) -> list[int]:
    a, b, t = projects["proj_a"], projects["proj_b"], projects["proj_t"]
    service = ProjectTransferService(t.session_factory(), t.root, t.name)
    ids: list[int] = []
    for source, stem in ((a, "a_cat"), (b, "b_cat")):
        result = service.copy_images(source.source, [_image_id(source, stem)])
        ids.extend(item.target_image_id for item in result.items if item.target_image_id is not None)
    return ids


def test_details_panel_shows_origin_of_copied_image(qtbot, projects) -> None:
    """検索タブの配線で、詳細パネルにコピーした画像の元プロジェクトと元画像 ID を出す。"""
    a, t = projects["proj_a"], projects["proj_t"]
    copied_id = _copy_into_target(projects)[0]
    details = SelectedImageDetailsWidget()
    qtbot.addWidget(details)
    fake_tab = SimpleNamespace(
        _db_manager=SimpleNamespace(image_repo=SimpleNamespace(session_factory=t.session_factory())),
        _selected_image_details_widget=details,
    )

    SearchTabWidget._wire_image_origins(fake_tab)
    details._on_image_data_received({"id": copied_id, "stored_image_path": "dummy.png"})

    assert details.image_origin_widget.isHidden() is False
    assert details.image_origin_widget.text() == f"proj_a の画像 #{_image_id(a, 'a_cat')} からコピー"


def test_version_build_dialog_plans_then_builds_from_copied_images(qtbot, projects) -> None:
    """選んだ画像から、計画を見てから版を作る。計画と違う入力のままでは作れない。"""
    t = projects["proj_t"]
    image_ids = _copy_into_target(projects)
    factory = t.session_factory()
    service = DatasetVersionBuildService(factory, DatasetRepository(session_factory=factory))
    dialog = DatasetVersionBuildDialog(service, image_ids)
    qtbot.addWidget(dialog)
    dialog.dataset_edit.setText("mix")
    dialog.version_edit.setText("v1")
    dialog.folder_edit.setText("10_mix")
    assert dialog.build_button.isEnabled() is False

    with qtbot.waitSignal(dialog._plan_ready, timeout=_WAIT_MS):
        dialog.start_propose()
    qtbot.waitUntil(lambda: dialog.build_button.isEnabled(), timeout=_WAIT_MS)
    assert dialog.image_stat.value() == "2"
    assert dialog.repeat_stat.value() == "10"
    assert dialog.origin_stat.value() == "2"
    assert dialog.plan_table.rowCount() == 2
    # 計画の段階では版を書かない
    assert table_counts(t, ("dataset_versions",)) == {"dataset_versions": 0}

    dialog.version_edit.setText("v2")
    assert dialog.build_button.isEnabled() is False
    dialog.version_edit.setText("v1")
    assert dialog.build_button.isEnabled() is True

    with qtbot.waitSignal(dialog.version_built, timeout=_WAIT_MS) as built:
        dialog.start_build()

    dataset_name, version_name, rows = service.describe_version(built.args[0])
    assert (dataset_name, version_name) == ("mix", "v1")
    assert sorted(row.image_id for row in rows) == sorted(image_ids)
    assert {o.source_project_name for row in rows for o in row.origins} == {"proj_a", "proj_b"}
