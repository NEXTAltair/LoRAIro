"""プロジェクト横断の検索・画像コピー・版作成の CLI 統合テスト (Issue #1661, ADR 0112)。

`project create` で 3 つのプロジェクト (コピー元 src_a / src_b、取り込み先 dst) を作り、本物の migration を
通した DB の複製と本物の画像ファイルで、Typer の CliRunner から各コマンドを通す。
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
    return build_migrated_template(tmp_path_factory.mktemp("cli_transfer_template") / "image_database.db")


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def projects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runner: CliRunner,
    migrated_template: Path,
    skip_alembic_upgrade_at_head: Callable[[Path], None],
) -> dict[str, SyntheticProject]:
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
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
    add_image(a, "a_cat", 1, tags=("cat", "smile"), caption="a cat")
    add_image(a, "shared", 9, tags=("cat", "outdoor"))
    add_image(b, "b_cat", 3, tags=("cat", "blue eyes"))
    add_image(b, "shared", 9, tags=("cat", "night"))
    return created


def _invoke(runner: CliRunner, *args: str) -> Result:
    return runner.invoke(app, ["--json", *args])


def _lines(result: Result) -> list[dict[str, Any]]:
    assert result.exit_code == 0, result.stdout + result.stderr
    return [json.loads(line) for line in result.stdout.strip().splitlines()]


def _items(result: Result) -> list[dict[str, Any]]:
    return [line for line in _lines(result) if line["kind"] == "item"]


def _result(result: Result) -> dict[str, Any]:
    return _lines(result)[-1]


def _source_id(project: SyntheticProject, stem: str) -> int:
    with closing(sqlite3.connect(project.db_path)) as conn:
        image_id: int = conn.execute(
            "SELECT id FROM images WHERE filename = ?", (f"{stem}.png",)
        ).fetchone()[0]
    return image_id


def _count(project: SyntheticProject, table: str) -> int:
    with closing(sqlite3.connect(project.db_path)) as conn:
        count: int = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    return count


def test_search_copy_origins_and_build_version_end_to_end(
    runner: CliRunner, projects: dict[str, SyntheticProject]
) -> None:
    a, b, dst = projects["src_a"], projects["src_b"], projects["dst"]
    sources_before = {name: file_fingerprints(projects[name].root) for name in ("src_a", "src_b")}

    # 1. 横断検索: 両方のプロジェクトから cat の画像が見つかり、由来 (まだ無い) が出る
    search = _invoke(
        runner, "images", "search-projects", "--projects", "src_a,src_b", "--query", '{"tags":["cat"]}'
    )
    hits = _items(search)
    assert sorted((hit["project"], hit["filename"]) for hit in hits) == [
        ("src_a", "a_cat.png"),
        ("src_a", "shared.png"),
        ("src_b", "b_cat.png"),
        ("src_b", "shared.png"),
    ]
    assert all(hit["origins"] == [] for hit in hits)
    assert _result(search)["projects"] == {"src_a": 2, "src_b": 2}

    # 2. --confirm なしは計画だけで何も書かない
    a_ids = f"{_source_id(a, 'a_cat')},{_source_id(a, 'shared')}"
    plan = _invoke(runner, "images", "copy", "-p", "dst", "--from-project", "src_a", "--image-ids", a_ids)
    assert [item["action"] for item in _items(plan)] == ["copy", "copy"]
    assert _result(plan)["dry_run"] is True
    assert _count(dst, "images") == 0

    copied = _invoke(
        runner, "images", "copy", "-p", "dst", "--from-project", "src_a", "--image-ids", a_ids, "--confirm"
    )
    assert [item["action"] for item in _items(copied)] == ["copy", "copy"]
    assert _result(copied)["copied"] == 2
    b_ids = f"{_source_id(b, 'b_cat')},{_source_id(b, 'shared')}"
    linked = _invoke(
        runner, "images", "copy", "-p", "dst", "--from-project", "src_b", "--image-ids", b_ids, "--confirm"
    )
    assert [item["action"] for item in _items(linked)] == ["copy", "link"]
    assert _count(dst, "images") == 3
    target_ids = [item["target_image_id"] for item in [*_items(copied), *_items(linked)]]
    shared_id = target_ids[1]
    assert target_ids[3] == shared_id

    # 3. 由来の確認: 同じ画像には 2 つのプロジェクトの由来が付く
    origins = _items(_invoke(runner, "images", "origins", str(shared_id), "-p", "dst"))
    assert [(o["source_project"], o["source_image_id"]) for o in origins[0]["origins"]] == [
        ("src_a", _source_id(a, "shared")),
        ("src_b", _source_id(b, "shared")),
    ]

    # 4. 複数プロジェクト由来の画像で版を作り、画像・タグ・参照元を確認する
    ids_csv = ",".join(str(i) for i in dict.fromkeys(target_ids))
    build_args = ["dataset", "build-version", "-p", "dst", "--dataset", "mix", "--version", "v1"]
    build_args += ["--folder", "10_cats", "--image-ids", ids_csv]
    planned = _invoke(runner, *build_args)
    assert _result(planned)["dry_run"] is True
    assert _count(dst, "dataset_versions") == 0
    built = _result(_invoke(runner, *build_args, "--confirm"))
    version_id = built["version_id"]
    assert built["images"] == 3

    shown = _invoke(runner, "dataset", "origins", str(version_id), "-p", "dst")
    rows = _items(shown)
    assert [row["text"] for row in rows] == ["cat, smile", "cat, outdoor, night", "cat, blue eyes"]
    assert [[o["source_project"] for o in row["origins"]] for row in rows] == [
        ["src_a"],
        ["src_a", "src_b"],
        ["src_b"],
    ]
    assert _result(shown)["source_projects"] == ["src_a", "src_b"]

    # コピー元の DB と画像は変わらない
    assert {name: file_fingerprints(projects[name].root) for name in ("src_a", "src_b")} == sources_before


def test_search_projects_refuses_old_schema_source(
    runner: CliRunner, projects: dict[str, SyntheticProject]
) -> None:
    a = projects["src_a"]
    with closing(sqlite3.connect(a.db_path)) as conn:
        conn.execute("UPDATE alembic_version SET version_num = 'b1c2d3e4f5a6'")
        conn.commit()
    before = file_fingerprints(a.root)

    result = _invoke(runner, "images", "search-projects", "--projects", "src_a", "--query", "{}")

    assert result.exit_code != 0
    assert "schema_upgrade_required" in result.stdout + result.stderr
    assert file_fingerprints(a.root) == before


def test_copy_rejects_dry_run_with_confirm(
    runner: CliRunner, projects: dict[str, SyntheticProject]
) -> None:
    result = _invoke(
        runner, "images", "copy", "1", "-p", "dst", "--from-project", "src_a", "--dry-run", "--confirm"
    )

    assert result.exit_code != 0
    assert _count(projects["dst"], "images") == 0


def test_search_all_projects_skips_old_schema_source(
    runner: CliRunner, projects: dict[str, SyntheticProject]
) -> None:
    a = projects["src_a"]
    with closing(sqlite3.connect(a.db_path)) as conn:
        conn.execute("UPDATE alembic_version SET version_num = 'b1c2d3e4f5a6'")
        conn.commit()

    result = _invoke(runner, "images", "search-projects", "--all-projects", "--query", '{"tags":["cat"]}')

    summary = _result(result)
    assert summary["skipped_projects"] == {"src_a": "schema_upgrade_required"}
    assert sorted(item["project"] for item in _items(result)) == ["src_b", "src_b"]
