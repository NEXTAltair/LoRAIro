"""`project merge` / `project merge-show` の CLI 統合テスト (Issue #1660, ADR 0113)。

`project create` で 3 つのプロジェクト (統合元 src_a / src_b、統合先 dst) を作り、本物の migration を
通した DB の複製と本物の画像ファイルで、Typer の CliRunner から各コマンドを通す。統合元には、
同じ画像、同名のデータセットと版、版の親子の連なり、`.txt` と `.caption` の両方が付いた画像を入れる。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
from project_transfer_fixtures import (
    SyntheticProject,
    add_image,
    add_version,
    build_migrated_template,
    file_fingerprints,
)
from typer.testing import CliRunner, Result

from lorairo.cli.main import app
from lorairo.services.project_management_service import ProjectManagementService
from lorairo.services.service_container import ServiceContainer

pytestmark = [pytest.mark.integration, pytest.mark.cli]


@pytest.fixture(scope="module")
def migrated_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_migrated_template(tmp_path_factory.mktemp("cli_merge_template") / "image_database.db")


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def projects_dir(tmp_path: Path) -> Path:
    path = tmp_path / "projects"
    path.mkdir()
    return path


@pytest.fixture
def projects(
    projects_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    runner: CliRunner,
    migrated_template: Path,
    skip_alembic_upgrade_at_head: Callable[[Path], None],
) -> dict[str, SyntheticProject]:
    ServiceContainer.reset_for_testing()
    monkeypatch.setenv("LORAIRO_CLI_MODE", "true")
    original_init = ProjectManagementService.__init__

    def patched_init(self: ProjectManagementService, projects_base_dir: Path | None = None) -> None:
        original_init(self, projects_base_dir=projects_dir)

    monkeypatch.setattr(ProjectManagementService, "__init__", patched_init)
    created: dict[str, SyntheticProject] = {}
    for name in ("src_a", "src_b", "dst"):
        result = runner.invoke(app, ["project", "create", name])
        assert result.exit_code == 0, result.stdout
        root = next(path for path in projects_dir.iterdir() if path.name.startswith(f"{name}_"))
        (root / "image_database.db").write_bytes(migrated_template.read_bytes())
        created[name] = SyntheticProject(name=name, root=root)
    a, b = created["src_a"], created["src_b"]
    a_cat = add_image(a, "a_cat", 1, tags=("cat", "smile"))
    a_shared = add_image(a, "shared", 9, tags=("cat", "outdoor"))
    a_v1 = add_version(a, "chara", "v1", "10_chara", [(a_cat, "a_cat", {".txt": "chara, cat"})])
    add_version(
        a,
        "chara",
        "v2",
        "10_chara",
        [
            (a_cat, "a_cat", {".txt": "chara, cat"}),
            (a_shared, "shared", {".txt": "chara, outdoor", ".caption": "a cat outdoors"}),
        ],
        parent_version_id=a_v1,
    )
    b_dog = add_image(b, "b_dog", 3, tags=("dog",))
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
    return created


def _invoke(runner: CliRunner, *args: str) -> Result:
    return runner.invoke(app, ["--json", *args])


def _lines(result: Result) -> list[dict[str, Any]]:
    return [json.loads(line) for line in result.stdout.strip().splitlines()]


def _ok_lines(result: Result) -> list[dict[str, Any]]:
    assert result.exit_code == 0, result.stdout + result.stderr
    return _lines(result)


def _items(result: Result, entry: str) -> list[dict[str, Any]]:
    return [line for line in _ok_lines(result) if line["kind"] == "item" and line.get("entry") == entry]


def _count(project: SyntheticProject, table: str) -> int:
    with closing(sqlite3.connect(project.db_path)) as conn:
        count: int = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    return count


def _merge(runner: CliRunner, *args: str) -> Result:
    return _invoke(runner, "project", "merge", "src_a", "src_b", *args)


def test_plan_shows_conflicts_and_mapping_template_without_writing(
    runner: CliRunner, projects: dict[str, SyntheticProject]
) -> None:
    dst = projects["dst"]
    before = file_fingerprints(dst.root / "image_dataset") if (dst.root / "image_dataset").exists() else {}

    plan = _merge(runner, "--into", "dst")

    conflicts = _items(plan, "conflict")
    assert [(c["conflict"], c["target_dataset"], c["sources"]) for c in conflicts] == [
        ("dataset_name", "chara", ["src_a:chara", "src_b:chara"])
    ]
    assert [(d["source_project"], d["merged_into_project"]) for d in _items(plan, "duplicate")] == [
        ("src_b", "src_a")
    ]
    result = _ok_lines(plan)[-1]
    assert result["dry_run"] is True
    assert result["resolved"] is False
    assert result["images"] == 4
    assert {"datasets", "versions", "joins"} <= set(result["mapping_template"])
    assert _count(dst, "images") == 0
    assert _count(dst, "datasets") == 0
    after = file_fingerprints(dst.root / "image_dataset") if (dst.root / "image_dataset").exists() else {}
    assert after == before


def test_confirm_is_refused_while_conflicts_remain(
    runner: CliRunner, projects: dict[str, SyntheticProject]
) -> None:
    refused = _merge(runner, "--into", "dst", "--confirm")

    assert refused.exit_code != 0
    error = _lines(refused)[-1]
    assert error["kind"] == "error"
    assert error["code"] == "INVALID_INPUT"
    assert error["details"]["conflicts"][0]["target_dataset"] == "chara"
    assert _count(projects["dst"], "images") == 0
    assert _count(projects["dst"], "project_transfer_runs") == 0


def test_confirm_with_dataset_rename_and_merge_show(
    runner: CliRunner, projects: dict[str, SyntheticProject]
) -> None:
    sources_before = {name: file_fingerprints(projects[name].root) for name in ("src_a", "src_b")}

    merged = _merge(runner, "--into", "dst", "--map-dataset", "src_b:chara=chara_b", "--confirm")

    result = _ok_lines(merged)[-1]
    assert result["dry_run"] is False
    assert result["versions"] == 4
    assert _count(projects["dst"], "images") == 3
    shown = _invoke(runner, "project", "merge-show", "-p", "dst")
    rows = [line for line in _ok_lines(shown) if line["kind"] == "item"]
    assert [(r["dataset"], r["version"], r["source_project"], r["source_version"]) for r in rows] == [
        ("chara", "v1", "src_a", "v1"),
        ("chara", "v2", "src_a", "v2"),
        ("chara_b", "v1", "src_b", "v1"),
        ("chara_b", "v2", "src_b", "v2"),
    ]
    by_name = {(r["dataset"], r["version"]): r for r in rows}
    assert by_name[("chara_b", "v2")]["parent_version_id"] == by_name[("chara_b", "v1")]["version_id"]
    assert {name: file_fingerprints(projects[name].root) for name in ("src_a", "src_b")} == sources_before


def test_join_with_mapping_file_chains_history(
    runner: CliRunner, projects: dict[str, SyntheticProject], tmp_path: Path
) -> None:
    plan = _merge(runner, "--into", "dst", "--join-dataset", "chara=src_a:chara,src_b:chara")
    template = _ok_lines(plan)[-1]["mapping_template"]
    assert [c["conflict"] for c in _items(plan, "conflict")] == ["version_name", "version_name"]
    for entry in template["versions"]:
        if entry["source_project"] == "src_b":
            entry["target_version"] = {"v1": "v3", "v2": "v4"}[entry["source_version"]]
    mapping_file = tmp_path / "mapping.json"
    mapping_file.write_text(json.dumps(template), encoding="utf-8")

    merged = _merge(runner, "--into", "dst", "--mapping-file", str(mapping_file), "--confirm")
    assert _ok_lines(merged)[-1]["versions"] == 4

    rows = [
        line
        for line in _ok_lines(_invoke(runner, "project", "merge-show", "-p", "dst"))
        if line["kind"] == "item"
    ]
    ids = {r["version"]: r["version_id"] for r in rows}
    parents = {r["version"]: r["parent_version_id"] for r in rows}
    assert parents == {"v1": None, "v2": ids["v1"], "v3": ids["v2"], "v4": ids["v3"]}


def test_create_new_target_project(
    runner: CliRunner, projects: dict[str, SyntheticProject], projects_dir: Path
) -> None:
    plan = _merge(runner, "--into", "merged", "--create", "--map-dataset", "src_b:chara=chara_b")
    assert _ok_lines(plan)[-1]["resolved"] is True
    # 計画ではプロジェクトを作らない
    assert not any(path.name.startswith("merged_") for path in projects_dir.iterdir())

    merged = _merge(
        runner, "--into", "merged", "--create", "--map-dataset", "src_b:chara=chara_b", "--confirm"
    )

    assert _ok_lines(merged)[-1]["images"] == 4
    root = next(path for path in projects_dir.iterdir() if path.name.startswith("merged_"))
    target = SyntheticProject(name="merged", root=root)
    assert _count(target, "images") == 3
    assert _count(target, "dataset_version_origins") == 4


def test_create_failure_removes_new_project(
    runner: CliRunner, projects: dict[str, SyntheticProject], projects_dir: Path
) -> None:
    failed = _merge(runner, "--into", "merged", "--create", "--confirm")

    assert failed.exit_code != 0
    assert not any(path.name.startswith("merged_") for path in projects_dir.iterdir())


def test_human_output_shows_plan_and_next_step(
    runner: CliRunner, projects: dict[str, SyntheticProject], monkeypatch: pytest.MonkeyPatch
) -> None:
    # CI ではカラーが強制される
    monkeypatch.setenv("GITHUB_ACTIONS", "true")

    plan = runner.invoke(app, ["project", "merge", "src_a", "src_b", "-p", "dst"])

    assert plan.exit_code == 0, plan.stdout
    assert "conflict" in plan.stdout
    assert "--map-dataset" in plan.stdout
    assert "Nothing was written" in plan.stdout
    shown = runner.invoke(app, ["project", "merge-show", "-p", "dst"])
    assert shown.exit_code == 0, shown.stdout
    assert "No merged versions" in shown.stdout


def test_rejects_target_as_source_and_bad_mapping(
    runner: CliRunner, projects: dict[str, SyntheticProject]
) -> None:
    same = _invoke(runner, "project", "merge", "src_a", "dst", "--into", "dst")
    assert same.exit_code != 0
    assert _lines(same)[-1]["code"] == "INVALID_INPUT"

    bad = _merge(runner, "--into", "dst", "--map-dataset", "src_b:chara")
    assert bad.exit_code != 0
    assert _lines(bad)[-1]["code"] == "INVALID_INPUT"

    unknown = _merge(runner, "--into", "dst", "--map-dataset", "src_b:nothing=x")
    assert unknown.exit_code != 0
    assert _lines(unknown)[-1]["code"] == "INVALID_INPUT"
