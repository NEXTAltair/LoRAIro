"""Image management commands テスト。"""

from pathlib import Path
from unittest.mock import MagicMock, patch

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
def test_images_list_shows_registered_images(mock_projects_dir: Path, test_images_dir: Path) -> None:
    """Test: images list - 登録済み画像をテーブル表示する。"""
    runner.invoke(app, ["project", "create", "test-project"])
    runner.invoke(app, ["images", "register", str(test_images_dir), "--project", "test-project"])

    result = runner.invoke(app, ["images", "list", "--project", "test-project"])

    assert result.exit_code == 0
    assert "Images in project: test-project" in result.stdout
    assert "ID" in result.stdout
    assert "Filename" in result.stdout
    assert "Tags" in result.stdout
    assert "Annotated" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_images_list_displays_tag_count_from_tags_list(mock_projects_dir: Path) -> None:
    """Test: images list - tags リストの長さがそのまま Tag 列に出る。"""
    runner.invoke(app, ["project", "create", "test-project"])

    fake_records = [
        {
            "id": 1,
            "stored_image_path": "/path/img.jpg",
            "tags": [
                {"id": 1, "tag": "cat"},
                {"id": 2, "tag": "dog"},
            ],
            "captions": [],
            "scores": [],
            "ratings": [],
        },
    ]
    with patch("lorairo.cli.commands.images.get_service_container") as mock_get_container:
        mock_container = MagicMock()
        mock_container.image_repository.get_images_by_filter.return_value = (fake_records, 1)
        mock_get_container.return_value = mock_container

        result = runner.invoke(app, ["images", "list", "--project", "test-project"])

    assert result.exit_code == 0
    assert "img.jpg" in result.stdout
    # タグ件数 2 と Annotated=Yes が両方表示されることを検証
    assert "2" in result.stdout
    assert "Yes" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_images_list_annotated_yes_when_only_captions(mock_projects_dir: Path) -> None:
    """Test: images list - tags 空でも captions があれば Annotated=Yes。"""
    runner.invoke(app, ["project", "create", "test-project"])

    fake_records = [
        {
            "id": 1,
            "stored_image_path": "/path/img.jpg",
            "tags": [],
            "captions": [{"id": 1, "caption": "a cat"}],
            "scores": [],
            "ratings": [],
        },
    ]
    with patch("lorairo.cli.commands.images.get_service_container") as mock_get_container:
        mock_container = MagicMock()
        mock_container.image_repository.get_images_by_filter.return_value = (fake_records, 1)
        mock_get_container.return_value = mock_container

        result = runner.invoke(app, ["images", "list", "--project", "test-project"])

    assert result.exit_code == 0
    assert "Yes" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_images_list_no_annotation_shows_no(mock_projects_dir: Path) -> None:
    """Test: images list - 何のアノテーションも無いとき Annotated=No。"""
    runner.invoke(app, ["project", "create", "test-project"])

    fake_records = [
        {
            "id": 1,
            "stored_image_path": "/path/img.jpg",
            "tags": [],
            "captions": [],
            "scores": [],
            "ratings": [],
        },
    ]
    with patch("lorairo.cli.commands.images.get_service_container") as mock_get_container:
        mock_container = MagicMock()
        mock_container.image_repository.get_images_by_filter.return_value = (fake_records, 1)
        mock_get_container.return_value = mock_container

        result = runner.invoke(app, ["images", "list", "--project", "test-project"])

    assert result.exit_code == 0
    assert "No" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_images_list_reflects_update_tags(mock_projects_dir: Path, test_images_dir: Path) -> None:
    """Test: images update でタグを追加した後、images list が件数を反映する。"""
    runner.invoke(app, ["project", "create", "test-project"])
    runner.invoke(app, ["images", "register", str(test_images_dir), "--project", "test-project"])
    runner.invoke(app, ["images", "update", "--project", "test-project", "--tags", "cat,dog"])

    result = runner.invoke(app, ["images", "list", "--project", "test-project"])

    assert result.exit_code == 0
    # 直前に 2 タグを追加したので Annotated=Yes になっているはず
    assert "Yes" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_images_list_no_images_shows_message(mock_projects_dir: Path) -> None:
    """Test: images list - 画像未登録時は適切なメッセージを表示する。"""
    runner.invoke(app, ["project", "create", "test-project"])

    result = runner.invoke(app, ["images", "list", "--project", "test-project"])

    assert result.exit_code == 0
    assert "No images found" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_images_list_with_limit(mock_projects_dir: Path) -> None:
    """Test: images list --limit - 件数を制限して表示する。"""
    runner.invoke(app, ["project", "create", "test-project"])

    fake_records = [
        {
            "id": i,
            "stored_image_path": f"/path/image{i}.jpg",
            "tags": [],
            "captions": [],
            "scores": [],
            "ratings": [],
        }
        for i in range(1, 4)
    ]
    with patch("lorairo.cli.commands.images.get_service_container") as mock_get_container:
        mock_container = MagicMock()
        mock_container.image_repository.get_images_by_filter.return_value = (fake_records, 3)
        mock_get_container.return_value = mock_container

        result = runner.invoke(app, ["images", "list", "--project", "test-project", "--limit", "1"])

    assert result.exit_code == 0
    assert "Images in project: test-project" in result.stdout
    assert "Showing 1 of 3" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_images_list_nonexistent_project(mock_projects_dir: Path) -> None:
    """Test: images list - 存在しないプロジェクトはエラー。"""
    result = runner.invoke(app, ["images", "list", "--project", "nonexistent"])

    assert result.exit_code == 1
    assert "Project not found" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_images_update_help() -> None:
    """Test: images update --help - ヘルプ表示。"""
    result = runner.invoke(app, ["images", "update", "--help"])

    assert result.exit_code == 0
    assert "Update image" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_images_update_no_tags_exits_code2(mock_projects_dir: Path) -> None:
    """Test: images update - --tags なしはexit code 2。"""
    runner.invoke(app, ["project", "create", "test-project"])
    result = runner.invoke(app, ["images", "update", "--project", "test-project"])
    assert result.exit_code == 2
    assert "At least one update operation" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_images_update_nonexistent_project(mock_projects_dir: Path) -> None:
    """Test: images update - 存在しないプロジェクトはエラー。"""
    result = runner.invoke(app, ["images", "update", "--project", "nonexistent", "--tags", "cat"])
    assert result.exit_code == 1
    assert "Project not found" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_images_update_no_images_in_project(mock_projects_dir: Path) -> None:
    """Test: images update - プロジェクト内に画像がない場合は警告表示。"""
    runner.invoke(app, ["project", "create", "test-project"])
    with patch("lorairo.cli.commands.images.get_service_container") as mock_get_container:
        mock_container = MagicMock()
        mock_container.image_repository.get_images_by_filter.return_value = ([], 0)
        mock_get_container.return_value = mock_container
        result = runner.invoke(app, ["images", "update", "--project", "test-project", "--tags", "cat"])
    assert result.exit_code == 0
    assert "No images found" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_images_update_adds_tags_success(mock_projects_dir: Path) -> None:
    """Test: images update - タグ追加成功。"""
    runner.invoke(app, ["project", "create", "test-project"])
    fake_records = [
        {
            "id": i,
            "stored_image_path": f"/path/image{i}.jpg",
            "tags": [],
            "captions": [],
            "scores": [],
            "ratings": [],
        }
        for i in range(1, 4)
    ]
    with patch("lorairo.cli.commands.images.get_service_container") as mock_get_container:
        mock_container = MagicMock()
        mock_container.image_repository.get_images_by_filter.return_value = (fake_records, 3)
        mock_container.image_repository.add_tag_to_images_batch.return_value = (True, 3)
        mock_get_container.return_value = mock_container
        result = runner.invoke(app, ["images", "update", "--project", "test-project", "--tags", "cat,dog"])
    assert result.exit_code == 0
    assert "Update Summary" in result.stdout
    assert mock_container.image_repository.add_tag_to_images_batch.call_count == 2


@pytest.mark.unit
@pytest.mark.cli
def test_images_update_with_image_id(mock_projects_dir: Path) -> None:
    """Test: images update --image-id - 特定画像へのタグ追加。"""
    runner.invoke(app, ["project", "create", "test-project"])
    with patch("lorairo.cli.commands.images.get_service_container") as mock_get_container:
        mock_container = MagicMock()
        mock_container.image_repository.get_image_metadata.return_value = {
            "id": 42,
            "filename": "a.jpg",
        }
        mock_container.image_repository.add_tag_to_images_batch.return_value = (True, 1)
        mock_get_container.return_value = mock_container
        result = runner.invoke(
            app,
            ["images", "update", "--project", "test-project", "--tags", "cat", "--image-id", "42"],
        )
    assert result.exit_code == 0
    assert "Update Summary" in result.stdout
    mock_container.image_repository.add_tag_to_images_batch.assert_called_once_with([42], "cat", None)


@pytest.mark.unit
@pytest.mark.cli
def test_images_update_image_id_not_found(mock_projects_dir: Path) -> None:
    """Test: images update --image-id - 存在しない画像IDはエラー。"""
    runner.invoke(app, ["project", "create", "test-project"])
    with patch("lorairo.cli.commands.images.get_service_container") as mock_get_container:
        mock_container = MagicMock()
        mock_container.image_repository.get_image_metadata.return_value = None
        mock_get_container.return_value = mock_container
        result = runner.invoke(
            app,
            [
                "images",
                "update",
                "--project",
                "test-project",
                "--tags",
                "cat",
                "--image-id",
                "9999",
            ],
        )
    assert result.exit_code == 1
    assert "No image found with ID: 9999" in result.stdout


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
