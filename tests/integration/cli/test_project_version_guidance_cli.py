"""プロジェクト作成・版追加・画像登録の違いの案内テスト (Issue #1662)。

Typer の CliRunner で、ヘルプ・エラー・出力の案内と、既存プロジェクトへの版追加の導線を確認する。
挙動 (どのプロジェクトが選ばれるか) は変えず、案内だけを検証する。
"""

from __future__ import annotations

import json
import random
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
import typer
from PIL import Image
from typer.core import TyperGroup
from typer.testing import CliRunner

from lorairo.cli.main import app
from lorairo.services.project_management_service import ProjectManagementService
from lorairo.services.service_container import ServiceContainer

pytestmark = [pytest.mark.integration, pytest.mark.cli]

PROJECT = "guide"
REPO_ROOT = Path(__file__).resolve().parents[3]


def _save_noise_image(path: Path, seed: int) -> None:
    rng = random.Random(seed)
    image = Image.new("RGB", (64, 64))
    image.putdata([(rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(64 * 64)])
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def _flat(text: str) -> str:
    """Rich のヘルプ折り返しを無視して比較できるよう、空白を 1 つに畳む。"""
    return " ".join(text.split())


def _last_json(stdout: str) -> dict[str, object]:
    row: dict[str, object] = json.loads(stdout.strip().splitlines()[-1])
    return row


def _walk_commands(group: TyperGroup, path: tuple[str, ...] = ()) -> Iterator[tuple[str, TyperGroup]]:
    """Typer のコマンド木をたどり、(コマンドパス, コマンド) を返す。"""
    for name, sub in getattr(group, "commands", {}).items():
        if hasattr(sub, "commands"):
            yield from _walk_commands(sub, (*path, name))
        else:
            yield " ".join((*path, name)), sub


@pytest.fixture(autouse=True)
def disable_rich_color(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rich/Typer のカラー出力を無効化する (tests/unit/cli/conftest.py と同じ)。

    CI のようにカラーが強制される環境では `--dataset` が ANSI エスケープで分割され、
    ヘルプ文字列の比較が失敗する。
    """
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("TERM", "dumb")


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def projects_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    skip_alembic_upgrade_at_head: Callable[[Path], None],
) -> Path:
    """隔離したプロジェクトベースディレクトリ (lorairo_data/ の実 DB には触れない)。"""
    base = tmp_path / "projects"
    base.mkdir()
    ServiceContainer.reset_for_testing()
    monkeypatch.setenv("LORAIRO_CLI_MODE", "true")

    original_init = ProjectManagementService.__init__

    def patched_init(self: ProjectManagementService, projects_base_dir: Path | None = None) -> None:
        original_init(self, projects_base_dir=base)

    monkeypatch.setattr(ProjectManagementService, "__init__", patched_init)
    return base


@pytest.fixture
def project_dir(
    projects_dir: Path, cli_runner: CliRunner, copy_prepared_project_db: Callable[[Path], None]
) -> Path:
    """CLI で作ったプロジェクト (name=guide)。DB は準備済みの複製に置き換える。"""
    result = cli_runner.invoke(app, ["project", "create", PROJECT])
    assert result.exit_code == 0, result.output
    created = next(path for path in projects_dir.iterdir() if path.name.startswith(PROJECT))
    copy_prepared_project_db(created)
    return created


@pytest.fixture
def images_root(tmp_path: Path) -> Path:
    root = tmp_path / "loose_images"
    _save_noise_image(root / "a.png", seed=11)
    _save_noise_image(root / "b.png", seed=12)
    return root


@pytest.fixture
def kohya_root(tmp_path: Path) -> Path:
    root = tmp_path / "kohya"
    _save_noise_image(root / "10_a" / "a1.png", seed=21)
    (root / "10_a" / "a1.txt").write_bytes(b"alpha, beta")
    return root


# ---- 完了条件 1: ヘルプとドキュメントで違いを具体例付きで説明する ----


def test_project_create_help_explains_new_project_vs_dataset_import(cli_runner: CliRunner) -> None:
    """project create のヘルプが、版追加は dataset import だと具体例付きで案内する。"""
    result = cli_runner.invoke(app, ["project", "create", "--help"])
    assert result.exit_code == 0
    text = _flat(result.output)
    assert "dataset import" in text
    assert "--dataset" in text
    assert "one project per version" in text


def test_dataset_import_help_explains_adding_version_to_existing_project(cli_runner: CliRunner) -> None:
    """dataset import のヘルプが、既存プロジェクトへの版追加と project create の違いを説明する。"""
    result = cli_runner.invoke(app, ["dataset", "import", "--help"])
    assert result.exit_code == 0
    text = _flat(result.output)
    assert "project create" in text
    assert "existing project" in text
    assert "project list" in text


def test_cli_docs_explain_project_create_vs_dataset_import() -> None:
    """docs/cli.md に、プロジェクトと版の違いの節と具体例がある (生成物)。"""
    text = (REPO_ROOT / "docs" / "cli.md").read_text(encoding="utf-8")
    assert "## プロジェクトとデータセットの版" in text
    assert "lorairo-cli project create" in text
    assert "lorairo-cli dataset import" in text
    assert "images register" in text


# ---- 完了条件 2: 既存プロジェクトがある場合に版追加の導線を案内する ----


def test_project_create_existing_name_json_error_points_to_dataset_import(
    cli_runner: CliRunner, project_dir: Path
) -> None:
    """同名の project create は ALREADY_EXISTS とし、hint で dataset import による版追加を案内する。"""
    result = cli_runner.invoke(app, ["--json", "project", "create", PROJECT])
    assert result.exit_code != 0
    error = _last_json(result.stdout)
    assert error["code"] == "ALREADY_EXISTS"
    hint = str(error["hint"])
    assert "dataset import" in hint
    assert f"-p {PROJECT}" in hint
    assert "--dataset" in hint


def test_project_create_existing_name_human_error_points_to_dataset_import(
    cli_runner: CliRunner, project_dir: Path
) -> None:
    """人間向け出力でも Hint 行に dataset import の案内が出る。"""
    result = cli_runner.invoke(app, ["project", "create", PROJECT])
    assert result.exit_code != 0
    text = _flat(result.output)
    assert "Hint:" in text
    assert f"dataset import <dir> -p {PROJECT} --dataset" in text


def test_project_create_success_output_points_to_next_steps(
    cli_runner: CliRunner, projects_dir: Path
) -> None:
    """作成直後の出力 (人間向け・JSON message) が、画像登録と dataset import の違いを案内する。"""
    human = cli_runner.invoke(app, ["project", "create", "fresh"])
    assert human.exit_code == 0
    human_text = _flat(human.output)
    assert "dataset import <dir> -p fresh --dataset" in human_text
    assert "images register" in human_text

    as_json = cli_runner.invoke(app, ["--json", "project", "create", "fresh2"])
    assert as_json.exit_code == 0
    row = _last_json(as_json.stdout)
    assert row["name"] == "fresh2"
    assert "dataset import <dir> -p fresh2 --dataset" in str(row["message"])


# ---- 完了条件 3: --project の指定対象を明示し、見つからない場合は候補と確認方法を案内する ----


def test_project_option_help_states_metadata_name_everywhere() -> None:
    """全コマンドの --project のヘルプが、指定するのは name (フォルダ名ではない) だと明示する。"""
    root = typer.main.get_command(app)
    checked = 0
    for path, command in _walk_commands(root):
        for param in command.params:
            if "--project" in getattr(param, "opts", []):
                checked += 1
                text = _flat(param.help or "")
                assert "project list" in text, f"{path}: --project help lacks 'project list': {text!r}"
                assert "not a folder" in text, f"{path}: --project help lacks 'not a folder': {text!r}"
    assert checked > 20


def test_project_not_found_with_folder_name_points_to_project_name(
    cli_runner: CliRunner, projects_dir: Path, project_dir: Path, images_root: Path
) -> None:
    """フォルダ名を --project に渡すと、その name を持つプロジェクトと list を案内する。"""
    folder_name = project_dir.name
    assert folder_name != PROJECT
    result = cli_runner.invoke(app, ["--json", "images", "register", str(images_root), "-p", folder_name])
    assert result.exit_code != 0
    error = _last_json(result.stdout)
    assert error["code"] == "NOT_FOUND"
    hint = str(error["hint"])
    assert f"-p {PROJECT}" in hint
    assert "フォルダ名" in hint
    assert "project list" in hint
    details = error["details"]
    assert isinstance(details, dict)
    assert details["folder_matched_project"] == PROJECT


def test_project_not_found_with_typo_suggests_close_names(
    cli_runner: CliRunner, project_dir: Path, images_root: Path
) -> None:
    """近い名前を候補として案内する。"""
    result = cli_runner.invoke(app, ["--json", "images", "register", str(images_root), "-p", "guid"])
    assert result.exit_code != 0
    error = _last_json(result.stdout)
    assert error["code"] == "NOT_FOUND"
    assert f"もしかして: {PROJECT}" in str(error["hint"])
    details = error["details"]
    assert isinstance(details, dict)
    assert details["suggestions"] == [PROJECT]


def test_project_not_found_without_candidates_still_points_to_project_list(
    cli_runner: CliRunner, project_dir: Path, images_root: Path
) -> None:
    """近い名前が無くても、確認方法 (project list) と name を指定する旨を案内する。"""
    result = cli_runner.invoke(app, ["images", "register", str(images_root), "-p", "zzzzzz"])
    assert result.exit_code != 0
    text = _flat(result.output)
    assert "lorairo-cli project list" in text
    assert "メタデータの name" in text


# ---- 完了条件 4: images register だけでは版が作られないことを明示する ----


def test_images_register_help_states_no_dataset_version_is_created(cli_runner: CliRunner) -> None:
    """images register のヘルプが、版は作られず dataset import を使うと明示する。"""
    result = cli_runner.invoke(app, ["images", "register", "--help"])
    assert result.exit_code == 0
    text = _flat(result.output)
    assert "does not create a dataset version" in text
    assert "dataset import" in text


def test_images_register_output_states_no_dataset_version_is_created(
    cli_runner: CliRunner, project_dir: Path, images_root: Path
) -> None:
    """登録結果 (人間向け・JSON message) が、版は作られないと案内する。JSON の項目は増やさない。"""
    human = cli_runner.invoke(app, ["images", "register", str(images_root), "-p", PROJECT])
    assert human.exit_code == 0, human.output
    human_text = _flat(human.output)
    assert "No dataset version was created" in human_text
    assert f"dataset import <dir> -p {PROJECT} --dataset" in human_text

    other = images_root.parent / "other_images"
    _save_noise_image(other / "c.png", seed=13)
    as_json = cli_runner.invoke(app, ["--json", "images", "register", str(other), "-p", PROJECT])
    assert as_json.exit_code == 0, as_json.output
    row = _last_json(as_json.stdout)
    assert row["kind"] == "result"
    assert "No dataset version was created" in str(row["message"])
    assert "dataset import" in str(row["message"])


# ---- 完了条件 5: 既存プロジェクトへの版追加までの一連の導線 ----


def test_flow_duplicate_create_then_dataset_import_adds_version_to_existing_project(
    cli_runner: CliRunner, project_dir: Path, kohya_root: Path, images_root: Path
) -> None:
    """同名 create の案内に従い、同じプロジェクトへ dataset import で版を足せる (プロジェクトは増えない)。"""
    created = cli_runner.invoke(app, ["--json", "project", "create", PROJECT])
    hint = str(_last_json(created.stdout)["hint"])
    assert "dataset import" in hint

    registered = cli_runner.invoke(app, ["images", "register", str(images_root), "-p", PROJECT])
    assert registered.exit_code == 0, registered.output
    assert "No dataset version was created" in _flat(registered.output)

    for version in ("v1", "v2"):
        imported = cli_runner.invoke(
            app,
            [
                "--json",
                "dataset",
                "import",
                str(kohya_root),
                "-p",
                PROJECT,
                "--dataset",
                "ds",
                "--version",
                version,
            ],
        )
        assert imported.exit_code == 0, imported.output
        assert "version_id" in _last_json(imported.stdout)

    listed = cli_runner.invoke(app, ["--json", "project", "list"])
    items = [json.loads(line) for line in listed.stdout.splitlines() if '"kind": "item"' in line]
    assert [item["name"] for item in items] == [PROJECT]
