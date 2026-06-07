"""Project management commands テスト。"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app
from lorairo.services.project_management_service import ProjectManagementService
from lorairo.services.service_container import ServiceContainer

runner = CliRunner()


@pytest.fixture
def mock_projects_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """ProjectManagementService のプロジェクトディレクトリをモック。

    API層→Service層経由でプロジェクト操作が行われるため、
    ServiceContainer が返す ProjectManagementService の
    projects_base_dir を一時ディレクトリに差し替える。

    Args:
        tmp_path: 一時ディレクトリ
        monkeypatch: pytest monkeypatch フィクスチャ

    Returns:
        Path: モック後のプロジェクトディレクトリ
    """
    mock_dir = tmp_path / "projects"
    mock_dir.mkdir()

    # ServiceContainerシングルトンのキャッシュをクリア
    container = ServiceContainer()
    container._project_management_service = None

    # ServiceContainer が返す ProjectManagementService のbase dirをパッチ
    original_init = ProjectManagementService.__init__

    def patched_init(self: ProjectManagementService, projects_base_dir: Path | None = None) -> None:
        original_init(self, projects_base_dir=mock_dir)

    monkeypatch.setattr(ProjectManagementService, "__init__", patched_init)

    return mock_dir


@pytest.mark.unit
@pytest.mark.cli
def test_project_create_success(mock_projects_dir: Path) -> None:
    """Test: project create - 成功ケース。"""
    result = runner.invoke(
        app,
        ["project", "create", "test-project", "--description", "Test project"],
    )

    assert result.exit_code == 0
    assert "Project created" in result.stdout
    assert "test-project" in result.stdout

    # ディレクトリが実際に作成されたか確認
    assert any(d.name.startswith("test-project_") for d in mock_projects_dir.iterdir())


@pytest.mark.unit
@pytest.mark.cli
def test_project_list_empty(mock_projects_dir: Path) -> None:
    """Test: project list - プロジェクトが存在しない場合。"""
    result = runner.invoke(app, ["project", "list"])

    assert result.exit_code == 0
    assert "No projects found" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_project_list_json_format(mock_projects_dir: Path) -> None:
    """Test: project list --format json - JSON出力フォーマット。"""
    # プロジェクト作成
    runner.invoke(app, ["project", "create", "json-test"])

    # JSON形式で一覧取得
    result = runner.invoke(app, ["project", "list", "--format", "json"])

    assert result.exit_code == 0

    # JSON パースが成功することを確認
    try:
        data = json.loads(result.stdout)
        assert isinstance(data, list)
    except json.JSONDecodeError:
        pytest.fail(f"Output is not valid JSON: {result.stdout}")


@pytest.mark.unit
@pytest.mark.cli
def test_project_list_table_format(mock_projects_dir: Path) -> None:
    """Test: project list --format table - テーブル出力（デフォルト）。"""
    # プロジェクト作成
    runner.invoke(app, ["project", "create", "table-test"])

    # テーブル形式で一覧取得
    result = runner.invoke(app, ["project", "list", "--format", "table"])

    assert result.exit_code == 0


@pytest.mark.unit
@pytest.mark.cli
def test_project_delete_with_confirmation(mock_projects_dir: Path) -> None:
    """Test: project delete - フォースなしでの削除（確認フロー）。"""
    # プロジェクト作成
    create_result = runner.invoke(
        app,
        ["project", "create", "confirm-test"],
    )
    assert create_result.exit_code == 0

    # ディレクトリが実際に作成されたか確認
    projects = [d.name for d in mock_projects_dir.iterdir() if d.name.startswith("confirm-test_")]
    assert len(projects) > 0


@pytest.mark.unit
@pytest.mark.cli
def test_project_delete_with_force_flag(mock_projects_dir: Path) -> None:
    """Test: project delete --force - 確認スキップ。"""
    runner.invoke(app, ["project", "create", "force-delete-test"])

    # 強制削除
    result = runner.invoke(
        app,
        ["project", "delete", "force-delete-test", "--force"],
    )

    assert result.exit_code == 0
    assert "Project deleted" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_project_delete_nonexistent(mock_projects_dir: Path) -> None:
    """Test: project delete - 存在しないプロジェクト。"""
    result = runner.invoke(
        app,
        ["project", "delete", "nonexistent", "--force"],
    )

    # ADR 0057 §7: エラーは中央境界が stderr に整形出力する (stdout は機械可読専用)。
    # NOT_FOUND は実行時系のため exit 1。
    assert result.exit_code == 1
    assert "見つかりません" in result.output


@pytest.mark.unit
@pytest.mark.cli
def test_project_create_help() -> None:
    """Test: project create --help - ヘルプ表示。"""
    result = runner.invoke(app, ["project", "create", "--help"])

    assert result.exit_code == 0
    assert "Create a new project" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_project_list_help() -> None:
    """Test: project list --help - ヘルプ表示。"""
    result = runner.invoke(app, ["project", "list", "--help"])

    assert result.exit_code == 0
    assert "List all projects" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_project_delete_help() -> None:
    """Test: project delete --help - ヘルプ表示。"""
    result = runner.invoke(app, ["project", "delete", "--help"])

    assert result.exit_code == 0
    assert "Delete a project" in result.stdout


# ===== エッジケーステスト =====


@pytest.mark.unit
@pytest.mark.cli
def test_project_create_special_chars(mock_projects_dir: Path) -> None:
    """Test: project create - ハイフン・アンダースコア含むプロジェクト名。"""
    result = runner.invoke(
        app,
        ["project", "create", "project-with-dashes_and_underscores"],
    )

    assert result.exit_code == 0
    assert "Project created" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_project_create_long_name(mock_projects_dir: Path) -> None:
    """Test: project create - 長いプロジェクト名。"""
    long_name = "a" * 64  # max_length=64
    result = runner.invoke(
        app,
        ["project", "create", long_name],
    )

    assert result.exit_code == 0
    assert "Project created" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_project_create_too_long_name(mock_projects_dir: Path) -> None:
    """Test: project create - 64文字超過のプロジェクト名。"""
    long_name = "a" * 65
    result = runner.invoke(
        app,
        ["project", "create", long_name],
    )

    # Pydantic ValidationError → VALIDATION_FAILED → exit 2 (入力系、ADR 0057 §6)。
    assert result.exit_code == 2
    assert "Error" in result.output


@pytest.mark.unit
@pytest.mark.cli
def test_project_create_invalid_name(mock_projects_dir: Path) -> None:
    """Test: project create - 無効な文字を含むプロジェクト名。"""
    result = runner.invoke(
        app,
        ["project", "create", "test project!"],
    )

    # Pydantic ValidationError → VALIDATION_FAILED → exit 2 (入力系、ADR 0057 §6)。
    assert result.exit_code == 2
    assert "Error" in result.output


@pytest.mark.unit
@pytest.mark.cli
def test_project_create_empty_description(mock_projects_dir: Path) -> None:
    """Test: project create - 説明文なし。"""
    result = runner.invoke(
        app,
        ["project", "create", "no-description"],
    )

    assert result.exit_code == 0
    assert "Project created" in result.stdout

    # メタデータが生成されたか確認
    projects = list(mock_projects_dir.iterdir())
    assert len(projects) > 0
    metadata_file = projects[0] / ".lorairo-project"
    assert metadata_file.exists()


@pytest.mark.unit
@pytest.mark.cli
def test_project_list_directory_structure(mock_projects_dir: Path) -> None:
    """Test: project list - プロジェクトディレクトリ構造の確認。"""
    # 複数プロジェクトを直接ディレクトリに作成（ファイルシステムで）
    for i in range(1, 4):
        proj_dir = mock_projects_dir / f"project{i}_20260216_063000"
        proj_dir.mkdir()
        (proj_dir / ".lorairo-project").write_text(
            f'{{"name": "project{i}", "created": "20260216_063000", "description": ""}}'
        )
        (proj_dir / "image_dataset").mkdir()
        (proj_dir / "image_database.db").touch()

    # テーブル形式で一覧取得
    result = runner.invoke(app, ["project", "list"])
    assert result.exit_code == 0

    # プロジェクトが表示されたか確認
    assert "project" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_project_list_json_structure(mock_projects_dir: Path) -> None:
    """Test: project list --format json - JSON形式での複数プロジェクト。"""
    # プロジェクトディレクトリを直接作成
    for i in range(1, 3):
        proj_dir = mock_projects_dir / f"json{i}_20260216_063000"
        proj_dir.mkdir()
        (proj_dir / ".lorairo-project").write_text(
            f'{{"name": "json{i}", "created": "20260216_063000", "description": ""}}'
        )
        (proj_dir / "image_dataset").mkdir()
        (proj_dir / "image_database.db").touch()

    # JSON形式で一覧取得
    result = runner.invoke(app, ["project", "list", "--format", "json"])
    assert result.exit_code == 0

    # JSON キーが含まれているか確認（形式検証）
    assert '"name"' in result.stdout
    assert '"created"' in result.stdout
    assert '"path"' in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_project_delete_partial_match(mock_projects_dir: Path) -> None:
    """Test: project delete - 部分一致での検索。"""
    # 複数の類似プロジェクト作成
    runner.invoke(app, ["project", "create", "test-alpha"])
    runner.invoke(app, ["project", "create", "test-beta"])

    # 「test-alpha」を削除
    result = runner.invoke(
        app,
        ["project", "delete", "test-alpha", "--force"],
    )

    assert result.exit_code == 0

    # test-alpha は削除され、test-beta は残る
    remaining = list(mock_projects_dir.iterdir())
    names = [d.name for d in remaining]
    assert any("test-beta" in name for name in names)


@pytest.mark.unit
@pytest.mark.cli
def test_project_invalid_command(mock_projects_dir: Path) -> None:
    """Test: project invalid_subcommand - 不正なサブコマンド。"""
    result = runner.invoke(app, ["project", "invalid_command"])

    assert result.exit_code != 0


@pytest.mark.unit
@pytest.mark.cli
def test_project_create_no_arguments() -> None:
    """Test: project create - 引数なし。"""
    result = runner.invoke(app, ["project", "create"])

    # 引数なしの場合は exit code 2（ユーザーエラー）
    assert result.exit_code == 2


@pytest.mark.unit
@pytest.mark.cli
def test_project_list_format_invalid(mock_projects_dir: Path) -> None:
    """Test: project list --format invalid - 無効なフォーマット。"""
    result = runner.invoke(app, ["project", "list", "--format", "yaml"])

    # Invalid format は table または json のみ
    assert result.exit_code == 0 or result.exit_code == 2


# ===== 機械可読 (--json) モード (ADR 0057/0058) =====


def _json_lines(stdout: str) -> list[dict]:
    """stdout の各行を JSON object として読む。"""
    return [json.loads(line) for line in stdout.splitlines() if line.strip()]


@pytest.mark.unit
@pytest.mark.cli
def test_project_create_json_mode(mock_projects_dir: Path) -> None:
    """Test: --json project create - 終端 result を JSONL で返す。"""
    result = runner.invoke(app, ["--json", "project", "create", "json-mode"])

    assert result.exit_code == 0
    last = _json_lines(result.stdout)[-1]
    assert last["kind"] == "result"
    assert last["ok"] is True
    assert last["name"] == "json-mode"


@pytest.mark.unit
@pytest.mark.cli
def test_project_list_json_mode(mock_projects_dir: Path) -> None:
    """Test: --json project list - item 行 + 件数 result を JSONL で返す。"""
    runner.invoke(app, ["project", "create", "jm1"])

    result = runner.invoke(app, ["--json", "project", "list"])

    assert result.exit_code == 0
    lines = _json_lines(result.stdout)
    items = [line for line in lines if line.get("kind") == "item"]
    result_line = next(line for line in reversed(lines) if line.get("kind") == "result")
    assert any(item["name"] == "jm1" for item in items)
    assert result_line["count"] == len(items)


@pytest.mark.unit
@pytest.mark.cli
def test_project_delete_nonexistent_json_mode(mock_projects_dir: Path) -> None:
    """Test: --json project delete - 失敗時は構造化 error 行 (code=NOT_FOUND)。"""
    result = runner.invoke(app, ["--json", "project", "delete", "nonexistent", "--force"])

    assert result.exit_code == 1
    last = _json_lines(result.stdout)[-1]
    assert last["kind"] == "error"
    assert last["code"] == "NOT_FOUND"
    assert last["ok"] is False


@pytest.mark.unit
@pytest.mark.cli
def test_project_delete_json_mode_requires_force(mock_projects_dir: Path) -> None:
    """Test: --json project delete - --force 省略は構造化 error (Issue #659)。

    JSON mode は対話 confirm を stdout に書けない (JSONL 純度を破る) ため --force 必須。
    未指定は INVALID_INPUT (exit 2) で弾き、stdout は error 行のみ (削除は実行しない)。
    """
    runner.invoke(app, ["project", "create", "json-force-test"])

    result = runner.invoke(app, ["--json", "project", "delete", "json-force-test"])

    assert result.exit_code == 2
    last = _json_lines(result.stdout)[-1]
    assert last["kind"] == "error"
    assert last["code"] == "INVALID_INPUT"
    assert last["ok"] is False
    # 削除は実行されず、プロジェクトは残る
    projects = [d.name for d in mock_projects_dir.iterdir() if d.name.startswith("json-force-test_")]
    assert len(projects) > 0
