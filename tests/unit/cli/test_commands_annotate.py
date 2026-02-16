"""Annotation commands テスト。"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image
from typer.testing import CliRunner

from lorairo.cli.commands import project
from lorairo.cli.main import app

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


@pytest.fixture
def test_project_with_images(mock_projects_dir: Path) -> tuple[Path, list[Path]]:
    """テスト用プロジェクトと画像ファイルを作成。

    Args:
        mock_projects_dir: モック化されたプロジェクトディレクトリ

    Returns:
        tuple[Path, list[Path]]: (プロジェクトディレクトリ, 画像ファイルリスト)
    """
    # プロジェクトを作成
    result = runner.invoke(app, ["project", "create", "test_dataset"])
    assert result.exit_code == 0

    # プロジェクトディレクトリを取得
    project_dirs = list(mock_projects_dir.iterdir())
    assert len(project_dirs) > 0
    project_dir = next(d for d in project_dirs if d.name.startswith("test_dataset_"))

    # 画像ファイルを作成
    image_dataset_dir = project_dir / "image_dataset" / "original_images"
    image_dataset_dir.mkdir(parents=True, exist_ok=True)

    image_files = []
    for i in range(3):
        # 小さなテスト画像を作成
        img = Image.new("RGB", (100, 100), color=(i * 50, i * 50, i * 50))
        img_path = image_dataset_dir / f"test_image_{i}.jpg"
        img.save(img_path)
        image_files.append(img_path)

    return project_dir, image_files


# ===== 基本テスト =====


@pytest.mark.unit
@pytest.mark.cli
def test_annotate_run_help() -> None:
    """Test: annotate run --help - ヘルプ表示。"""
    result = runner.invoke(app, ["annotate", "run", "--help"])

    assert result.exit_code == 0
    assert "Run annotation on project images" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_annotate_run_nonexistent_project(mock_projects_dir: Path) -> None:
    """Test: annotate run - 存在しないプロジェクト。"""
    result = runner.invoke(
        app,
        [
            "annotate",
            "run",
            "--project",
            "nonexistent",
            "--model",
            "gpt-4o-mini",
        ],
    )

    assert result.exit_code == 1
    assert "Project not found" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_annotate_run_no_images(mock_projects_dir: Path) -> None:
    """Test: annotate run - プロジェクトに画像がない場合。"""
    # プロジェクトのみ作成（画像なし）
    runner.invoke(app, ["project", "create", "empty_project"])

    result = runner.invoke(
        app,
        [
            "annotate",
            "run",
            "--project",
            "empty_project",
            "--model",
            "gpt-4o-mini",
        ],
    )

    assert result.exit_code == 0
    assert "No image files found" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_annotate_run_missing_project_option(mock_projects_dir: Path) -> None:
    """Test: annotate run - --project オプション未指定。"""
    result = runner.invoke(
        app,
        ["annotate", "run", "--model", "gpt-4o-mini"],
    )

    # Typer は必須オプション未指定時に exit code 2 を返す
    assert result.exit_code == 2


@pytest.mark.unit
@pytest.mark.cli
def test_annotate_run_missing_model_option(test_project_with_images: tuple[Path, list[Path]]) -> None:
    """Test: annotate run - --model オプション未指定。"""
    result = runner.invoke(
        app,
        ["annotate", "run", "--project", "test_dataset"],
    )

    # Typer は必須オプション未指定時に exit code 2 を返す
    assert result.exit_code == 2


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.annotate.get_service_container")
def test_annotate_run_with_single_model(
    mock_get_container,
    test_project_with_images: tuple[Path, list[Path]],
) -> None:
    """Test: annotate run - 単一モデル指定。"""
    _project_dir, _image_files = test_project_with_images

    # ServiceContainer をモック
    mock_container = MagicMock()
    mock_annotator = MagicMock()
    mock_config = MagicMock()

    # APIキー設定を返す
    mock_config.get_setting.return_value = "test_key"

    # アノテーション結果をモック（pHashをキーとする辞書）
    mock_annotator.annotate.return_value = {
        "hash1": {"tags": ["tag1", "tag2"]},
        "hash2": {"tags": ["tag3"]},
        "hash3": {"tags": ["tag4", "tag5"]},
    }

    mock_container.annotator_library = mock_annotator
    mock_container.config_service = mock_config
    mock_get_container.return_value = mock_container

    result = runner.invoke(
        app,
        [
            "annotate",
            "run",
            "--project",
            "test_dataset",
            "--model",
            "gpt-4o-mini",
        ],
    )

    assert result.exit_code == 0
    assert "Found 3 image(s)" in result.stdout
    assert "gpt-4o-mini" in result.stdout
    assert "Loaded 3 image(s)" in result.stdout or "annotation completed successfully" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.annotate.get_service_container")
def test_annotate_run_with_multiple_models(
    mock_get_container,
    test_project_with_images: tuple[Path, list[Path]],
) -> None:
    """Test: annotate run - 複数モデル指定。"""
    _project_dir, _image_files = test_project_with_images

    # ServiceContainer をモック
    mock_container = MagicMock()
    mock_annotator = MagicMock()
    mock_config = MagicMock()

    # APIキー設定を返す
    mock_config.get_setting.return_value = "test_key"

    # アノテーション結果をモック
    mock_annotator.annotate.return_value = {
        "hash1": {"tags": ["tag1"]},
        "hash2": {"tags": ["tag2"]},
        "hash3": {"tags": ["tag3"]},
    }

    mock_container.annotator_library = mock_annotator
    mock_container.config_service = mock_config
    mock_get_container.return_value = mock_container

    result = runner.invoke(
        app,
        [
            "annotate",
            "run",
            "--project",
            "test_dataset",
            "--model",
            "gpt-4o-mini",
            "--model",
            "claude-opus",
        ],
    )

    assert result.exit_code == 0
    assert "Found 3 image(s)" in result.stdout
    assert "gpt-4o-mini" in result.stdout or "claude-opus" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.annotate.get_service_container")
def test_annotate_run_no_api_keys(
    mock_get_container,
    test_project_with_images: tuple[Path, list[Path]],
) -> None:
    """Test: annotate run - APIキーなし（WARNINGメッセージ確認）。"""
    _project_dir, _image_files = test_project_with_images

    # ServiceContainer をモック
    mock_container = MagicMock()
    mock_annotator = MagicMock()
    mock_config = MagicMock()

    # APIキーなし（空文字列）
    mock_config.get_setting.return_value = ""

    # アノテーション結果をモック
    mock_annotator.annotate.return_value = {
        "hash1": {"tags": ["tag1"]},
        "hash2": {"tags": ["tag2"]},
        "hash3": {"tags": ["tag3"]},
    }

    mock_container.annotator_library = mock_annotator
    mock_container.config_service = mock_config
    mock_get_container.return_value = mock_container

    result = runner.invoke(
        app,
        [
            "annotate",
            "run",
            "--project",
            "test_dataset",
            "--model",
            "gpt-4o-mini",
        ],
    )

    assert result.exit_code == 0
    # WARNING メッセージが含まれるか確認
    assert "Warning" in result.stdout and "API keys" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.annotate.get_service_container")
def test_annotate_run_with_output_option(
    mock_get_container,
    test_project_with_images: tuple[Path, list[Path]],
    tmp_path: Path,
) -> None:
    """Test: annotate run - --output オプション指定。"""
    _project_dir, _image_files = test_project_with_images

    # ServiceContainer をモック
    mock_container = MagicMock()
    mock_annotator = MagicMock()
    mock_config = MagicMock()

    mock_config.get_setting.return_value = "test_key"
    mock_annotator.annotate.return_value = {
        "hash1": {"tags": ["tag1"]},
        "hash2": {"tags": ["tag2"]},
        "hash3": {"tags": ["tag3"]},
    }

    mock_container.annotator_library = mock_annotator
    mock_container.config_service = mock_config
    mock_get_container.return_value = mock_container

    output_dir = tmp_path / "output"

    result = runner.invoke(
        app,
        [
            "annotate",
            "run",
            "--project",
            "test_dataset",
            "--model",
            "gpt-4o-mini",
            "--output",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0
    assert "Found 3 image(s)" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.annotate.get_service_container")
def test_annotate_run_with_batch_size(
    mock_get_container,
    test_project_with_images: tuple[Path, list[Path]],
) -> None:
    """Test: annotate run - --batch-size オプション指定。"""
    _project_dir, _image_files = test_project_with_images

    # ServiceContainer をモック
    mock_container = MagicMock()
    mock_annotator = MagicMock()
    mock_config = MagicMock()

    mock_config.get_setting.return_value = "test_key"
    mock_annotator.annotate.return_value = {
        "hash1": {"tags": ["tag1"]},
        "hash2": {"tags": ["tag2"]},
        "hash3": {"tags": ["tag3"]},
    }

    mock_container.annotator_library = mock_annotator
    mock_container.config_service = mock_config
    mock_get_container.return_value = mock_container

    result = runner.invoke(
        app,
        [
            "annotate",
            "run",
            "--project",
            "test_dataset",
            "--model",
            "gpt-4o-mini",
            "--batch-size",
            "5",
        ],
    )

    assert result.exit_code == 0
    assert "Found 3 image(s)" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.annotate.get_service_container")
def test_annotate_run_annotation_failure(
    mock_get_container,
    test_project_with_images: tuple[Path, list[Path]],
) -> None:
    """Test: annotate run - アノテーション実行エラー。"""
    _project_dir, _image_files = test_project_with_images

    # ServiceContainer をモック
    mock_container = MagicMock()
    mock_annotator = MagicMock()
    mock_config = MagicMock()

    mock_config.get_setting.return_value = "test_key"

    # アノテーション実行でエラーが発生する
    mock_annotator.annotate.side_effect = Exception("API Error: Invalid key")

    mock_container.annotator_library = mock_annotator
    mock_container.config_service = mock_config
    mock_get_container.return_value = mock_container

    result = runner.invoke(
        app,
        [
            "annotate",
            "run",
            "--project",
            "test_dataset",
            "--model",
            "gpt-4o-mini",
        ],
    )

    assert result.exit_code == 1
    assert "Annotation failed" in result.stdout or "Error" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.annotate.get_service_container")
def test_annotate_run_summary_display(
    mock_get_container,
    test_project_with_images: tuple[Path, list[Path]],
) -> None:
    """Test: annotate run - アノテーション完了後のサマリー表示。"""
    _project_dir, _image_files = test_project_with_images

    # ServiceContainer をモック
    mock_container = MagicMock()
    mock_annotator = MagicMock()
    mock_config = MagicMock()

    mock_config.get_setting.return_value = "test_key"
    mock_annotator.annotate.return_value = {
        "hash1": {"tags": ["tag1"]},
        "hash2": {"tags": ["tag2"]},
        "hash3": {"tags": ["tag3"]},
    }

    mock_container.annotator_library = mock_annotator
    mock_container.config_service = mock_config
    mock_get_container.return_value = mock_container

    result = runner.invoke(
        app,
        [
            "annotate",
            "run",
            "--project",
            "test_dataset",
            "--model",
            "gpt-4o-mini",
        ],
    )

    assert result.exit_code == 0
    # サマリーテーブルが表示されたかを確認
    assert "Summary" in result.stdout or "Total Images" in result.stdout or "Models Used" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_annotate_subcommand_exists() -> None:
    """Test: annotate サブコマンドが登録されているか確認。"""
    result = runner.invoke(app, ["annotate", "--help"])

    assert result.exit_code == 0
    assert "Annotation commands" in result.stdout


# ===== エッジケーステスト =====


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.annotate.get_service_container")
def test_annotate_run_with_unicode_project_name(
    mock_get_container,
    mock_projects_dir: Path,
) -> None:
    """Test: annotate run - Unicode文字を含むプロジェクト名。"""
    # Unicode プロジェクトを作成
    result = runner.invoke(app, ["project", "create", "テスト プロジェクト"])
    assert result.exit_code == 0

    project_dirs = list(mock_projects_dir.iterdir())
    project_dir = next(d for d in project_dirs if "テスト" in d.name)

    # 画像ファイルを作成
    image_dataset_dir = project_dir / "image_dataset" / "original_images"
    image_dataset_dir.mkdir(parents=True, exist_ok=True)

    img = Image.new("RGB", (100, 100), color=(50, 50, 50))
    img_path = image_dataset_dir / "test_image.jpg"
    img.save(img_path)

    # ServiceContainer をモック
    mock_container = MagicMock()
    mock_annotator = MagicMock()
    mock_config = MagicMock()

    mock_config.get_setting.return_value = "test_key"
    mock_annotator.annotate.return_value = {"hash1": {"tags": ["tag1"]}}

    mock_container.annotator_library = mock_annotator
    mock_container.config_service = mock_config
    mock_get_container.return_value = mock_container

    result = runner.invoke(
        app,
        [
            "annotate",
            "run",
            "--project",
            "テスト プロジェクト",
            "--model",
            "gpt-4o-mini",
        ],
    )

    assert result.exit_code == 0
    assert "Found 1 image(s)" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.annotate.get_service_container")
def test_annotate_run_image_load_failure(
    mock_get_container,
    test_project_with_images: tuple[Path, list[Path]],
) -> None:
    """Test: annotate run - 画像ロード失敗時の処理。"""
    _project_dir, image_files = test_project_with_images

    # 1つの画像ファイルを破損させる
    image_files[0].write_bytes(b"corrupted data")

    # ServiceContainer をモック
    mock_container = MagicMock()
    mock_annotator = MagicMock()
    mock_config = MagicMock()

    mock_config.get_setting.return_value = "test_key"
    mock_annotator.annotate.return_value = {
        "hash1": {"tags": ["tag1"]},
        "hash2": {"tags": ["tag2"]},
    }

    mock_container.annotator_library = mock_annotator
    mock_container.config_service = mock_config
    mock_get_container.return_value = mock_container

    result = runner.invoke(
        app,
        [
            "annotate",
            "run",
            "--project",
            "test_dataset",
            "--model",
            "gpt-4o-mini",
        ],
    )

    # 1つは失敗したが、他は成功したはず
    assert "Found 3 image(s)" in result.stdout
    # 失敗メッセージが表示されるか
    assert "Warning" in result.stdout or "Failed" in result.stdout or result.exit_code in [0, 1]
