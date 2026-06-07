"""Image management commands テスト。"""

import json
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

    if result.exit_code != 0:
        import traceback as _tb

        print(f"--- stdout ---\n{result.stdout}")
        if result.exception:
            _tb.print_exception(type(result.exception), result.exception, result.exception.__traceback__)
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
    assert "not found" in result.output


@pytest.mark.unit
@pytest.mark.cli
def test_images_register_nonexistent_project(mock_projects_dir: Path, test_images_dir: Path) -> None:
    """Test: images register - プロジェクトが存在しない場合。"""
    result = runner.invoke(
        app,
        ["images", "register", str(test_images_dir), "--project", "nonexistent"],
    )

    assert result.exit_code == 1
    assert "見つかりません" in result.output


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
    """Test: images list - デフォルトは件数のみを表示する。"""
    runner.invoke(app, ["project", "create", "test-project"])
    runner.invoke(app, ["images", "register", str(test_images_dir), "--project", "test-project"])

    result = runner.invoke(app, ["images", "list", "--project", "test-project"])

    assert result.exit_code == 0
    assert "image(s) found in project: test-project" in result.stdout
    assert "ID" not in result.stdout
    assert "Filename" not in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_images_list_fetch_outputs_plain_id_path_rows(mock_projects_dir: Path) -> None:
    """Test: images list --fetch - human output は image_id<TAB>file_path の plain 行。"""
    runner.invoke(app, ["project", "create", "test-project"])

    fake_records = [
        {
            "image_id": 1,
            "file_path": "/path/img.jpg",
        },
    ]
    with patch("lorairo.cli.commands.images.get_service_container") as mock_get_container:
        mock_container = MagicMock()
        mock_container.db_manager.image_repo.get_images_count_only.return_value = 1
        mock_container.db_manager.image_repo.get_image_list_page.return_value = (fake_records, 1)
        mock_get_container.return_value = mock_container

        result = runner.invoke(app, ["images", "list", "--project", "test-project", "--fetch"])

    assert result.exit_code == 0
    assert result.stdout == "1\t/path/img.jpg\n"


@pytest.mark.unit
@pytest.mark.cli
def test_images_list_fetch_json_outputs_items_and_result_meta(mock_projects_dir: Path) -> None:
    """Test: images list --fetch --json - item 行と件数メタを出力する。"""
    runner.invoke(app, ["project", "create", "test-project"])

    fake_records = [
        {
            "image_id": 1,
            "file_path": "/path/img.jpg",
        },
    ]
    with patch("lorairo.cli.commands.images.get_service_container") as mock_get_container:
        mock_container = MagicMock()
        mock_container.db_manager.image_repo.get_images_count_only.return_value = 1
        mock_container.db_manager.image_repo.get_image_list_page.return_value = (fake_records, 1)
        mock_get_container.return_value = mock_container

        result = runner.invoke(
            app, ["--json", "images", "list", "--project", "test-project", "--fetch", "--limit", "1"]
        )

    assert result.exit_code == 0
    lines = [json.loads(line) for line in result.stdout.splitlines()]
    assert lines[0] == {"kind": "item", "image_id": 1, "file_path": "/path/img.jpg"}
    assert lines[1]["kind"] == "result"
    assert lines[1]["count"] == 1
    assert lines[1]["total"] == 1
    assert lines[1]["limit"] == 1
    assert lines[1]["offset"] == 0
    assert lines[1]["has_more"] is False


@pytest.mark.unit
@pytest.mark.cli
def test_images_list_count_first_json_uses_total_not_count(mock_projects_dir: Path) -> None:
    """Test: count-first --json は count=0 + total=N に語義を統一する (#664)。"""
    runner.invoke(app, ["project", "create", "test-project"])

    with patch("lorairo.cli.commands.images.get_service_container") as mock_get_container:
        mock_container = MagicMock()
        mock_container.db_manager.image_repo.get_images_count_only.return_value = 42
        mock_get_container.return_value = mock_container

        result = runner.invoke(app, ["--json", "images", "list", "--project", "test-project"])

    assert result.exit_code == 0
    lines = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(lines) == 1
    assert lines[0]["kind"] == "result"
    # count はこの応答の item 行数 (0)、総ヒット数は total に載る。
    assert lines[0]["count"] == 0
    assert lines[0]["total"] == 42
    # count-first は item を一切出さない。
    mock_container.db_manager.image_repo.get_image_list_page.assert_not_called()


@pytest.mark.unit
@pytest.mark.cli
def test_images_list_fetch_total_over_cap_errors_before_items(mock_projects_dir: Path) -> None:
    """Test: images list --fetch - total 500 超は RESULT_SET_TOO_LARGE で item を出さない。"""
    runner.invoke(app, ["project", "create", "test-project"])

    with patch("lorairo.cli.commands.images.get_service_container") as mock_get_container:
        mock_container = MagicMock()
        mock_container.db_manager.image_repo.get_images_count_only.return_value = 501
        mock_get_container.return_value = mock_container

        result = runner.invoke(app, ["--json", "images", "list", "--project", "test-project", "--fetch"])

    assert result.exit_code == 2
    lines = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(lines) == 1
    assert lines[0]["kind"] == "error"
    assert lines[0]["code"] == "RESULT_SET_TOO_LARGE"
    assert lines[0]["details"] == {"limit": 500, "matched": 501}
    mock_container.db_manager.image_repo.get_image_list_page.assert_not_called()


@pytest.mark.unit
@pytest.mark.cli
def test_images_list_fetch_total_over_cap_errors_non_json(mock_projects_dir: Path) -> None:
    """Test: images list --fetch (non-JSON) - total 500 超は exit_code 2 でエラーを表示する。"""
    runner.invoke(app, ["project", "create", "test-project"])

    with patch("lorairo.cli.commands.images.get_service_container") as mock_get_container:
        mock_container = MagicMock()
        mock_container.db_manager.image_repo.get_images_count_only.return_value = 501
        mock_get_container.return_value = mock_container

        result = runner.invoke(app, ["images", "list", "--project", "test-project", "--fetch"])

    assert result.exit_code == 2
    # non-JSON モードではエラーメッセージが日本語で stderr に出る
    combined = result.stdout + result.stderr
    assert "501" in combined
    assert "500" in combined
    mock_container.db_manager.image_repo.get_image_list_page.assert_not_called()


@pytest.mark.unit
@pytest.mark.cli
def test_images_list_reflects_update_tags(mock_projects_dir: Path, test_images_dir: Path) -> None:
    """Test: images update 後も images list の count が取得できる。"""
    runner.invoke(app, ["project", "create", "test-project"])
    runner.invoke(app, ["images", "register", str(test_images_dir), "--project", "test-project"])
    runner.invoke(app, ["images", "update", "--project", "test-project", "--tags", "cat,dog"])

    result = runner.invoke(app, ["images", "list", "--project", "test-project"])

    assert result.exit_code == 0
    assert "image(s) found in project: test-project" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_images_list_no_images_shows_message(mock_projects_dir: Path) -> None:
    """Test: images list - 画像未登録時は適切なメッセージを表示する。"""
    runner.invoke(app, ["project", "create", "test-project"])

    result = runner.invoke(app, ["images", "list", "--project", "test-project"])

    assert result.exit_code == 0
    assert "0 image(s) found" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_images_list_fetch_with_limit_and_offset(mock_projects_dir: Path) -> None:
    """Test: images list --fetch --limit/--offset - criteria に pushdown する。"""
    runner.invoke(app, ["project", "create", "test-project"])

    fake_records = [
        {
            "image_id": 2,
            "file_path": "/path/image2.jpg",
        }
    ]
    with patch("lorairo.cli.commands.images.get_service_container") as mock_get_container:
        mock_container = MagicMock()
        mock_container.db_manager.image_repo.get_images_count_only.return_value = 3
        mock_container.db_manager.image_repo.get_image_list_page.return_value = (fake_records, 3)
        mock_get_container.return_value = mock_container

        result = runner.invoke(
            app,
            ["images", "list", "--project", "test-project", "--fetch", "--limit", "1", "--offset", "1"],
        )

    assert result.exit_code == 0
    criteria = mock_container.db_manager.image_repo.get_image_list_page.call_args.args[0]
    assert criteria.limit == 1
    assert criteria.offset == 1
    assert result.stdout == "2\t/path/image2.jpg\n"


@pytest.mark.unit
@pytest.mark.cli
def test_images_list_unrated_passes_only_unrated_criteria(mock_projects_dir: Path) -> None:
    """Test: images list --unrated は rating 未保存画像のみに絞る criteria を渡す。"""
    runner.invoke(app, ["project", "create", "test-project"])

    with patch("lorairo.cli.commands.images.get_service_container") as mock_get_container:
        mock_container = MagicMock()
        mock_container.db_manager.image_repo.get_images_count_only.return_value = 1
        mock_get_container.return_value = mock_container

        result = runner.invoke(app, ["images", "list", "--project", "test-project", "--unrated"])

    assert result.exit_code == 0
    criteria = mock_container.db_manager.image_repo.get_images_count_only.call_args.args[0]
    assert criteria.include_nsfw is True
    assert criteria.only_unrated is True
    assert "without ratings" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_images_list_nonexistent_project(mock_projects_dir: Path) -> None:
    """Test: images list - 存在しないプロジェクトはエラー。"""
    result = runner.invoke(app, ["images", "list", "--project", "nonexistent"])

    assert result.exit_code == 1
    assert "見つかりません" in result.output


@pytest.mark.unit
@pytest.mark.cli
def test_images_update_help() -> None:
    """Test: images update --help - ヘルプ表示。"""
    result = runner.invoke(app, ["images", "update", "--help"])

    assert result.exit_code == 0
    assert "Add tags to images" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_images_update_no_tags_exits_code2(mock_projects_dir: Path) -> None:
    """Test: images update - --tags なしはexit code 2。"""
    runner.invoke(app, ["project", "create", "test-project"])
    result = runner.invoke(app, ["images", "update", "--project", "test-project"])
    assert result.exit_code == 2
    assert "At least one update operation" in result.output


@pytest.mark.unit
@pytest.mark.cli
def test_images_update_nonexistent_project(mock_projects_dir: Path) -> None:
    """Test: images update - 存在しないプロジェクトはエラー。"""
    result = runner.invoke(app, ["images", "update", "--project", "nonexistent", "--tags", "cat"])
    assert result.exit_code == 1
    assert "見つかりません" in result.output


@pytest.mark.unit
@pytest.mark.cli
def test_images_update_no_images_in_project(mock_projects_dir: Path) -> None:
    """Test: images update - プロジェクト内に画像がない場合は警告表示。"""
    runner.invoke(app, ["project", "create", "test-project"])
    with patch("lorairo.cli.commands.images.get_service_container") as mock_get_container:
        mock_container = MagicMock()
        mock_container.db_manager.image_repo.get_images_by_filter.return_value = ([], 0)
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
        mock_container.db_manager.image_repo.get_images_by_filter.return_value = (fake_records, 3)
        mock_container.db_manager.annotation_repo.add_tag_to_images_batch.return_value = (True, 3)
        mock_get_container.return_value = mock_container
        result = runner.invoke(app, ["images", "update", "--project", "test-project", "--tags", "cat,dog"])
    assert result.exit_code == 0
    assert "Update Summary" in result.stdout
    assert mock_container.db_manager.annotation_repo.add_tag_to_images_batch.call_count == 2


@pytest.mark.unit
@pytest.mark.cli
def test_images_update_with_image_id(mock_projects_dir: Path) -> None:
    """Test: images update --image-id - 特定画像へのタグ追加。"""
    runner.invoke(app, ["project", "create", "test-project"])
    with patch("lorairo.cli.commands.images.get_service_container") as mock_get_container:
        mock_container = MagicMock()
        mock_container.db_manager.image_repo.get_image_metadata.return_value = {
            "id": 42,
            "filename": "a.jpg",
        }
        mock_container.db_manager.annotation_repo.add_tag_to_images_batch.return_value = (True, 1)
        mock_get_container.return_value = mock_container
        result = runner.invoke(
            app,
            ["images", "update", "--project", "test-project", "--tags", "cat", "--image-id", "42"],
        )
    assert result.exit_code == 0
    assert "Update Summary" in result.stdout
    mock_container.db_manager.annotation_repo.add_tag_to_images_batch.assert_called_once_with(
        [42], "cat", None
    )


@pytest.mark.unit
@pytest.mark.cli
def test_images_update_image_id_not_found(mock_projects_dir: Path) -> None:
    """Test: images update --image-id - 存在しない画像IDはエラー。"""
    runner.invoke(app, ["project", "create", "test-project"])
    with patch("lorairo.cli.commands.images.get_service_container") as mock_get_container:
        mock_container = MagicMock()
        mock_container.db_manager.image_repo.get_image_metadata.return_value = None
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
    # ImageNotFoundError → NOT_FOUND exit 1。メッセージは例外 str (stderr)。
    assert result.exit_code == 1
    assert "9999" in result.output


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


@pytest.mark.unit
@pytest.mark.cli
def test_images_register_single_file_success(mock_projects_dir: Path, tmp_path: Path) -> None:
    """Test: images register - 単一ファイルパスで登録が成功する。"""
    runner.invoke(app, ["project", "create", "test-project"])

    img = Image.new("RGB", (100, 100), color=(100, 100, 100))
    img_path = tmp_path / "test.jpg"
    img.save(img_path)

    result = runner.invoke(app, ["images", "register", str(img_path), "--project", "test-project"])

    assert result.exit_code == 0
    assert "Registration Summary" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_images_register_unsupported_file_format(mock_projects_dir: Path, tmp_path: Path) -> None:
    """Test: images register - サポート外形式のファイルはエラー。"""
    runner.invoke(app, ["project", "create", "test-project"])

    txt_path = tmp_path / "test.txt"
    txt_path.write_text("not an image")

    result = runner.invoke(app, ["images", "register", str(txt_path), "--project", "test-project"])

    assert result.exit_code == 1
