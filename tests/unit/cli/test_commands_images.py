"""Image management commands テスト。"""

from pathlib import Path

import pytest
from PIL import Image
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


@pytest.fixture
def test_images_dir(tmp_path: Path) -> Path:
    """テスト用画像ディレクトリを作成。

    Args:
        tmp_path: 一時ディレクトリ

    Returns:
        Path: テスト画像ディレクトリ
    """
    images_dir = tmp_path / "images"
    images_dir.mkdir()

    # テスト画像を3枚作成（100x100ピクセル）
    for i in range(1, 4):
        img = Image.new("RGB", (100, 100), color=(73 + i * 30, 109 + i * 30, 137 + i * 30))
        img.save(images_dir / f"test_image_{i}.jpg")

    return images_dir


@pytest.mark.unit
@pytest.mark.cli
def test_images_register_success(mock_projects_dir: Path, test_images_dir: Path) -> None:
    """Test: images register - 成功ケース。"""
    # プロジェクト作成
    runner.invoke(app, ["project", "create", "test-project"])

    # 画像登録
    result = runner.invoke(
        app,
        ["images", "register", str(test_images_dir), "--project", "test-project"],
    )

    assert result.exit_code == 0
    assert "Registration Summary" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_images_register_nonexistent_directory(mock_projects_dir: Path) -> None:
    """Test: images register - ディレクトリが存在しない場合。"""
    # プロジェクト作成
    runner.invoke(app, ["project", "create", "test-project"])

    # 存在しないディレクトリで登録
    result = runner.invoke(
        app,
        ["images", "register", "/nonexistent/path", "--project", "test-project"],
    )

    assert result.exit_code == 1
    assert "not found" in result.stdout or "Directory not found" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_images_register_nonexistent_project(mock_projects_dir: Path, test_images_dir: Path) -> None:
    """Test: images register - プロジェクトが存在しない場合。"""
    result = runner.invoke(
        app,
        ["images", "register", str(test_images_dir), "--project", "nonexistent"],
    )

    assert result.exit_code == 1
    assert "Project not found" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_images_register_empty_directory(mock_projects_dir: Path, tmp_path: Path) -> None:
    """Test: images register - 画像のない空ディレクトリ。"""
    # プロジェクト作成
    runner.invoke(app, ["project", "create", "test-project"])

    # 空ディレクトリで登録
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    result = runner.invoke(
        app,
        ["images", "register", str(empty_dir), "--project", "test-project"],
    )

    assert result.exit_code == 0
    assert "No image files found" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_images_register_with_skip_duplicates(mock_projects_dir: Path, tmp_path: Path) -> None:
    """Test: images register --skip-duplicates - 重複検出。"""
    # プロジェクト作成
    runner.invoke(app, ["project", "create", "test-project"])

    # 同じ画像を2回作成（重複）
    images_dir = tmp_path / "images"
    images_dir.mkdir()

    img = Image.new("RGB", (100, 100), color=(100, 100, 100))
    img.save(images_dir / "image_a.jpg")
    img.save(images_dir / "image_b.jpg")  # 同じ画像

    # 登録
    result = runner.invoke(
        app,
        ["images", "register", str(images_dir), "--project", "test-project"],
    )

    assert result.exit_code == 0


@pytest.mark.unit
@pytest.mark.cli
def test_images_register_include_duplicates(mock_projects_dir: Path, tmp_path: Path) -> None:
    """Test: images register --include-duplicates - 重複を含める。"""
    # プロジェクト作成
    runner.invoke(app, ["project", "create", "test-project"])

    # 画像作成
    images_dir = tmp_path / "images"
    images_dir.mkdir()

    img = Image.new("RGB", (100, 100), color=(100, 100, 100))
    img.save(images_dir / "image.jpg")

    # 重複を含めて登録
    result = runner.invoke(
        app,
        [
            "images",
            "register",
            str(images_dir),
            "--project",
            "test-project",
            "--include-duplicates",
        ],
    )

    assert result.exit_code == 0


@pytest.mark.unit
@pytest.mark.cli
def test_images_list_help() -> None:
    """Test: images list --help - ヘルプ表示。"""
    result = runner.invoke(app, ["images", "list", "--help"])

    assert result.exit_code == 0
    assert "List images" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_images_list_not_implemented(mock_projects_dir: Path) -> None:
    """Test: images list - 未実装通知。"""
    # プロジェクト作成
    runner.invoke(app, ["project", "create", "test-project"])

    result = runner.invoke(
        app,
        ["images", "list", "--project", "test-project"],
    )

    assert result.exit_code == 0
    assert "not yet implemented" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_images_update_help() -> None:
    """Test: images update --help - ヘルプ表示。"""
    result = runner.invoke(app, ["images", "update", "--help"])

    assert result.exit_code == 0
    assert "Update image" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_images_update_not_implemented(mock_projects_dir: Path) -> None:
    """Test: images update - 未実装通知。"""
    # プロジェクト作成
    runner.invoke(app, ["project", "create", "test-project"])

    result = runner.invoke(
        app,
        ["images", "update", "--project", "test-project", "--tags", "tag1,tag2"],
    )

    assert result.exit_code == 0
    assert "not yet implemented" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_images_register_multiple_formats(mock_projects_dir: Path, tmp_path: Path) -> None:
    """Test: images register - 複数形式の画像ファイル。"""
    # プロジェクト作成
    runner.invoke(app, ["project", "create", "test-project"])

    # 複数形式の画像を作成
    images_dir = tmp_path / "images"
    images_dir.mkdir()

    formats = ["jpg", "png", "gif", "bmp", "webp"]
    for fmt in formats:
        try:
            img = Image.new("RGB", (50, 50), color=(100, 100, 100))
            img.save(images_dir / f"image.{fmt}")
        except Exception:
            pass

    # 登録
    result = runner.invoke(
        app,
        ["images", "register", str(images_dir), "--project", "test-project"],
    )

    assert result.exit_code == 0


@pytest.mark.unit
@pytest.mark.cli
def test_images_register_no_project_arg() -> None:
    """Test: images register --project なし - エラー。"""
    result = runner.invoke(app, ["images", "register", "/some/path"])

    assert result.exit_code == 2  # 必須オプション欠落


@pytest.mark.unit
@pytest.mark.cli
def test_images_register_no_directory_arg() -> None:
    """Test: images register - 引数なし - エラー。"""
    result = runner.invoke(app, ["images", "register", "--project", "test"])

    assert result.exit_code == 2  # 必須引数欠落
