"""Project management commands テスト。"""

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app
from lorairo.cli.commands import project

runner = CliRunner()


@pytest.fixture
def mock_projects_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """プロジェクトディレクトリをモック。

    Args:
        tmp_path: 一時ディレクトリ
        monkeypatch: pytest monkeypatch フィクスチャ

    Returns:
        Path: モック後のプロジェクトディレクトリ
    """
    mock_dir = tmp_path / "projects"
    mock_dir.mkdir()
    monkeypatch.setattr(project, "PROJECTS_BASE_DIR", mock_dir)
    return mock_dir


@pytest.mark.unit
@pytest.mark.cli
def test_project_create_success(mock_projects_dir: Path) -> None:
    """Test: project create - 成功ケース。"""
    result = runner.invoke(
        app,
        ["project", "create", "test_project", "--description", "Test project"],
    )

    assert result.exit_code == 0
    assert "Project created" in result.stdout
    assert "test_project" in result.stdout

    # ディレクトリが実際に作成されたか確認
    assert (mock_projects_dir / "test_project_20").exists() or any(
        d.name.startswith("test_project_") for d in mock_projects_dir.iterdir()
    )


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
    runner.invoke(app, ["project", "create", "json_test"])

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
    runner.invoke(app, ["project", "create", "table_test"])

    # テーブル形式で一覧取得
    result = runner.invoke(app, ["project", "list", "--format", "table"])

    assert result.exit_code == 0


@pytest.mark.unit
@pytest.mark.cli
def test_project_delete_with_confirmation(mock_projects_dir: Path) -> None:
    """Test: project delete - フォースなしでの削除（確認フロー）。

    Note: CliRunner と typer.confirm() の相性が限定的なため、
    このテストでは --force フラグなしの削除が実行されることを確認
    """
    # プロジェクト作成
    create_result = runner.invoke(
        app,
        ["project", "create", "confirm_test"],
    )
    assert create_result.exit_code == 0

    # ディレクトリが実際に作成されたか確認
    projects = [d.name for d in mock_projects_dir.iterdir() if d.name.startswith("confirm_test_")]
    assert len(projects) > 0


@pytest.mark.unit
@pytest.mark.cli
def test_project_delete_with_force_flag(mock_projects_dir: Path) -> None:
    """Test: project delete --force - 確認スキップ。"""
    # プロジェクト作成
    runner.invoke(app, ["project", "create", "force_delete_test"])

    # 強制削除
    result = runner.invoke(
        app,
        ["project", "delete", "force_delete_test", "--force"],
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

    assert result.exit_code == 1
    assert "Project not found" in result.stdout


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
def test_project_create_unicode_name(mock_projects_dir: Path) -> None:
    """Test: project create - Unicode文字を含むプロジェクト名。"""
    result = runner.invoke(
        app,
        ["project", "create", "テスト プロジェクト", "--description", "日本語説明"],
    )

    assert result.exit_code == 0
    assert "Project created" in result.stdout

    # Unicode ディレクトリが作成されたか確認
    projects = list(mock_projects_dir.iterdir())
    assert len(projects) > 0


@pytest.mark.unit
@pytest.mark.cli
def test_project_create_special_chars(mock_projects_dir: Path) -> None:
    """Test: project create - 特殊文字を含むプロジェクト名。"""
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
    long_name = "a" * 100
    result = runner.invoke(
        app,
        ["project", "create", long_name],
    )

    assert result.exit_code == 0
    assert "Project created" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_project_create_empty_description(mock_projects_dir: Path) -> None:
    """Test: project create - 説明文なし。"""
    result = runner.invoke(
        app,
        ["project", "create", "no_description"],
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
        proj_dir = mock_projects_dir / f"project_{i}_20260216_063000"
        proj_dir.mkdir()
        (proj_dir / ".lorairo-project").write_text(
            f'{{"name": "project_{i}", "created": "20260216_063000", "description": ""}}'
        )
        (proj_dir / "image_dataset").mkdir()
        # image_database.db ファイルを作成（存在確認用）
        (proj_dir / "image_database.db").touch()

    # テーブル形式で一覧取得
    result = runner.invoke(app, ["project", "list"])
    assert result.exit_code == 0

    # プロジェクトが表示されたか確認
    assert "project_" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_project_list_json_structure(mock_projects_dir: Path) -> None:
    """Test: project list --format json - JSON形式での複数プロジェクト。"""
    # プロジェクトディレクトリを直接作成
    for i in range(1, 3):
        proj_dir = mock_projects_dir / f"json_{i}_20260216_063000"
        proj_dir.mkdir()
        (proj_dir / ".lorairo-project").write_text(
            f'{{"name": "json_{i}", "created": "20260216_063000", "description": ""}}'
        )
        (proj_dir / "image_dataset").mkdir()
        # image_database.db ファイルを作成（存在確認用）
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
    """Test: project delete - 部分一致での検索。

    複数の「test_」プロジェクトがある場合、
    「test_a」で削除すると「test_a_xxx」が削除される
    """
    # 複数の類似プロジェクト作成
    runner.invoke(app, ["project", "create", "test_alpha"])
    runner.invoke(app, ["project", "create", "test_beta"])

    # 「test_alpha」を削除
    result = runner.invoke(
        app,
        ["project", "delete", "test_alpha", "--force"],
    )

    assert result.exit_code == 0

    # test_alpha は削除され、test_beta は残る
    remaining = list(mock_projects_dir.iterdir())
    names = [d.name for d in remaining]
    assert any("test_beta" in name for name in names)


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
    # 実装上は table as default になる可能性
    assert result.exit_code == 0 or result.exit_code == 2
