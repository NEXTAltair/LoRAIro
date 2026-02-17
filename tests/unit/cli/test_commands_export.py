"""Dataset export commands テスト。"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app
from lorairo.services.project_management_service import ProjectManagementService
from lorairo.services.service_container import ServiceContainer

runner = CliRunner()


@pytest.fixture
def mock_projects_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """ProjectManagementService のプロジェクトディレクトリをモック。

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

    original_init = ProjectManagementService.__init__

    def patched_init(self: ProjectManagementService, projects_base_dir: Path | None = None) -> None:
        original_init(self, projects_base_dir=mock_dir)

    monkeypatch.setattr(ProjectManagementService, "__init__", patched_init)

    return mock_dir


def create_mock_service_container() -> MagicMock:
    """Create a mock ServiceContainer.

    Returns:
        MagicMock: Mocked service container
    """
    mock_container = MagicMock()

    # mock image_repository
    mock_image_repository = MagicMock()
    mock_image_repository.get_images_by_filter.return_value = (
        [
            {"id": 1, "name": "image1.jpg"},
            {"id": 2, "name": "image2.jpg"},
            {"id": 3, "name": "image3.jpg"},
        ],
        3,
    )
    mock_container.image_repository = mock_image_repository

    # mock export_service - return the output path
    mock_export_service = MagicMock()

    def export_filtered_dataset_side_effect(image_ids, output_path, **kwargs):
        return output_path

    mock_export_service.export_filtered_dataset.side_effect = export_filtered_dataset_side_effect
    mock_container.dataset_export_service = mock_export_service

    return mock_container


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.export.get_service_container")
def test_export_create_txt_format(
    mock_get_container,
    mock_projects_dir: Path,
    tmp_path: Path,
) -> None:
    """Test: export create --format txt - TXT フォーマットでのエクスポート。"""
    mock_container = create_mock_service_container()
    mock_get_container.return_value = mock_container

    # プロジェクト作成
    runner.invoke(app, ["project", "create", "test-project"])

    # エクスポート実行
    output_dir = tmp_path / "export"
    result = runner.invoke(
        app,
        [
            "export",
            "create",
            "--project",
            "test-project",
            "--output",
            str(output_dir),
            "--format",
            "txt",
        ],
    )

    assert result.exit_code == 0
    assert "Found 3 image(s)" in result.stdout
    assert "Export Summary" in result.stdout
    assert "Export completed successfully" in result.stdout
    assert "txt" in result.stdout.lower()


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.export.get_service_container")
def test_export_create_json_format(
    mock_get_container,
    mock_projects_dir: Path,
    tmp_path: Path,
) -> None:
    """Test: export create --format json - JSON フォーマットでのエクスポート。"""
    mock_container = create_mock_service_container()
    mock_get_container.return_value = mock_container

    # プロジェクト作成
    runner.invoke(app, ["project", "create", "test-project"])

    # エクスポート実行
    output_dir = tmp_path / "export"
    result = runner.invoke(
        app,
        [
            "export",
            "create",
            "--project",
            "test-project",
            "--output",
            str(output_dir),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    assert "Found 3 image(s)" in result.stdout
    assert "json" in result.stdout.lower()


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.export.get_service_container")
def test_export_create_with_custom_resolution(
    mock_get_container,
    mock_projects_dir: Path,
    tmp_path: Path,
) -> None:
    """Test: export create --resolution - カスタム解像度指定。"""
    mock_container = create_mock_service_container()
    mock_get_container.return_value = mock_container

    # プロジェクト作成
    runner.invoke(app, ["project", "create", "test-project"])

    # エクスポート実行（解像度1024指定）
    output_dir = tmp_path / "export"
    result = runner.invoke(
        app,
        [
            "export",
            "create",
            "--project",
            "test-project",
            "--output",
            str(output_dir),
            "--format",
            "txt",
            "--resolution",
            "1024",
        ],
    )

    assert result.exit_code == 0
    assert "1024" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.export.get_service_container")
def test_export_create_output_directory_auto_creation(
    mock_get_container,
    mock_projects_dir: Path,
    tmp_path: Path,
) -> None:
    """Test: export create - 出力ディレクトリ自動作成。"""
    mock_container = create_mock_service_container()
    mock_get_container.return_value = mock_container

    # プロジェクト作成
    runner.invoke(app, ["project", "create", "test-project"])

    # 存在しない出力ディレクトリを指定
    output_dir = tmp_path / "nonexistent" / "export"
    result = runner.invoke(
        app,
        [
            "export",
            "create",
            "--project",
            "test-project",
            "--output",
            str(output_dir),
            "--format",
            "txt",
        ],
    )

    assert result.exit_code == 0
    assert "Export completed successfully" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.export.get_service_container")
def test_export_create_nonexistent_project(
    mock_get_container,
    mock_projects_dir: Path,
    tmp_path: Path,
) -> None:
    """Test: export create - 無効なプロジェクト名。"""
    mock_container = create_mock_service_container()
    mock_get_container.return_value = mock_container

    output_dir = tmp_path / "export"
    result = runner.invoke(
        app,
        [
            "export",
            "create",
            "--project",
            "nonexistent-project",
            "--output",
            str(output_dir),
            "--format",
            "txt",
        ],
    )

    assert result.exit_code == 1
    assert "Project not found" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.export.get_service_container")
def test_export_create_no_images(
    mock_get_container,
    mock_projects_dir: Path,
    tmp_path: Path,
) -> None:
    """Test: export create - プロジェクトに画像がない場合。"""
    # ServiceContainer をモック（画像が0件）
    mock_container = MagicMock()
    mock_image_repository = MagicMock()
    mock_image_repository.get_images_by_filter.return_value = ([], 0)
    mock_container.image_repository = mock_image_repository
    mock_container.dataset_export_service = MagicMock()
    mock_get_container.return_value = mock_container

    # プロジェクト作成
    runner.invoke(app, ["project", "create", "test-project"])

    output_dir = tmp_path / "export"
    result = runner.invoke(
        app,
        [
            "export",
            "create",
            "--project",
            "test-project",
            "--output",
            str(output_dir),
            "--format",
            "txt",
        ],
    )

    assert result.exit_code == 0
    assert "No images found" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.export.get_service_container")
def test_export_create_invalid_format(
    mock_get_container,
    mock_projects_dir: Path,
    tmp_path: Path,
) -> None:
    """Test: export create - 無効なフォーマット。"""
    mock_container = create_mock_service_container()
    mock_container.dataset_export_service.export_filtered_dataset.side_effect = ValueError(
        "Unsupported format_type: invalid"
    )
    mock_get_container.return_value = mock_container

    # プロジェクト作成
    runner.invoke(app, ["project", "create", "test-project"])

    output_dir = tmp_path / "export"
    result = runner.invoke(
        app,
        [
            "export",
            "create",
            "--project",
            "test-project",
            "--output",
            str(output_dir),
            "--format",
            "invalid",
        ],
    )

    assert result.exit_code == 1
    assert "Invalid export format" in result.stdout or "Error" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_export_create_help() -> None:
    """Test: export create --help - ヘルプ表示。"""
    result = runner.invoke(app, ["export", "create", "--help"])

    assert result.exit_code == 0
    assert "--project" in result.stdout
    assert "--output" in result.stdout
    assert "--format" in result.stdout
    assert "--resolution" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_export_help() -> None:
    """Test: export --help - エクスポートコマンドヘルプ。"""
    result = runner.invoke(app, ["export", "--help"])

    assert result.exit_code == 0
    assert "Dataset export commands" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.export.get_service_container")
def test_export_create_default_format(
    mock_get_container,
    mock_projects_dir: Path,
    tmp_path: Path,
) -> None:
    """Test: export create - デフォルトフォーマット (txt)。"""
    mock_container = create_mock_service_container()
    mock_get_container.return_value = mock_container

    # プロジェクト作成
    runner.invoke(app, ["project", "create", "test-project"])

    # format オプションなしで実行（デフォルトはtxt）
    output_dir = tmp_path / "export"
    result = runner.invoke(
        app,
        [
            "export",
            "create",
            "--project",
            "test-project",
            "--output",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0
    assert "Export completed successfully" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.export.get_service_container")
def test_export_create_default_resolution(
    mock_get_container,
    mock_projects_dir: Path,
    tmp_path: Path,
) -> None:
    """Test: export create - デフォルト解像度 (512)。"""
    mock_container = create_mock_service_container()
    mock_get_container.return_value = mock_container

    # プロジェクト作成
    runner.invoke(app, ["project", "create", "test-project"])

    # resolution オプションなしで実行（デフォルトは512）
    output_dir = tmp_path / "export"
    result = runner.invoke(
        app,
        [
            "export",
            "create",
            "--project",
            "test-project",
            "--output",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0
    assert "512" in result.stdout
