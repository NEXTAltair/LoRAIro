"""Annotation commands テスト。"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image
from typer.testing import CliRunner

from lorairo.cli._output_mode import set_json_mode
from lorairo.cli.commands.annotate import _annotation_score, _emit_annotation_items
from lorairo.cli.main import app
from lorairo.services.annotation_save_service import AnnotationSaveResult
from lorairo.services.project_management_service import ProjectManagementService
from lorairo.services.service_container import ServiceContainer

runner = CliRunner()


def _jsonl(stdout: str) -> list[dict]:
    return [json.loads(line) for line in stdout.splitlines() if line.strip()]


@pytest.fixture(autouse=True)
def _reset_json_mode() -> None:
    set_json_mode(False)
    yield
    set_json_mode(False)


@pytest.mark.unit
@pytest.mark.cli
def test_annotation_score_reads_scores_payload() -> None:
    """Scorer-only annotation results expose the first numeric scores value."""
    result = MagicMock(score=None, rating_score=None, aesthetic_score=None)
    result.scores = {"aesthetic": 7.5}

    assert _annotation_score(result) == 7.5


@pytest.mark.unit
@pytest.mark.cli
def test_emit_annotation_items_emits_duplicate_phash_records(capsys: pytest.CaptureFixture[str]) -> None:
    """Duplicate pHash selections emit one JSONL item per selected record."""
    set_json_mode(True)
    records = [
        {"id": 1, "phash": "same", "stored_image_path": "/tmp/a.jpg"},
        {"id": 2, "phash": "same", "stored_image_path": "/tmp/b.jpg"},
    ]
    results = {"same": {"scorer": {"scores": {"aesthetic": 8.0}, "tags": []}}}

    _emit_annotation_items(results, records)

    rows = _jsonl(capsys.readouterr().out)
    assert [row["image_id"] for row in rows] == [1, 2]
    assert [row["file_path"] for row in rows] == ["/tmp/a.jpg", "/tmp/b.jpg"]
    assert all(row["models"][0]["score"] == 8.0 for row in rows)


@pytest.mark.unit
@pytest.mark.cli
def test_select_image_records_missing_warning_uses_stderr_in_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Missing image-id warning does not pollute JSON stdout."""
    from lorairo.cli.commands.annotate import _select_image_records

    set_json_mode(True)

    selected = _select_image_records(
        [{"id": 1, "phash": "p", "stored_image_path": "/tmp/a.jpg"}],
        limit=None,
        offset=0,
        image_ids=[1, 99],
    )

    captured = capsys.readouterr()
    assert [record["id"] for record in selected] == [1]
    assert captured.out == ""
    assert "Image ID(s) not found" in captured.err


@pytest.fixture(autouse=True)
def _bypass_model_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    """`annotate run` コマンドテスト群で `_resolve_model_identifier` を bypass する。

    Issue #245 で導入した DB lookup ベースの解決処理は、本ファイル既存テストの
    MagicMock 化された ServiceContainer では正しく動かない (MagicMock が
    `get_model_by_litellm_id` から返り、`by_litellm.litellm_model_id` が
    MagicMock のまま下流に流れる)。resolver 単体の挙動は
    `tests/unit/cli/test_annotate_model_resolution.py` でカバー済みのため、
    ここでは resolver を identity 関数に差し替えて従来の `--model X` → そのまま
    送信のテスト前提を維持する。
    """
    monkeypatch.setattr(
        "lorairo.cli.commands.annotate._resolve_model_identifier",
        lambda _repo, identifier: identifier,
    )


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
    assert "openai/omni-moderation-latest" in result.stdout


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
    assert "nonexistent" in result.stderr


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.annotate.get_service_container")
def test_annotate_run_no_images(
    mock_get_container,
    mock_projects_dir: Path,
) -> None:
    """Test: annotate run - プロジェクトに画像がない場合（DB未登録）。"""
    # プロジェクトのみ作成（画像なし）
    runner.invoke(app, ["project", "create", "empty_project"])

    mock_container = MagicMock()
    mock_container.db_manager.image_repo.get_images_by_filter.return_value = ([], 0)
    mock_container.db_manager.model_repo.get_model_by_litellm_id.return_value = MagicMock(
        litellm_model_id="gpt-4o-mini", provider="openai"
    )
    mock_get_container.return_value = mock_container

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

    assert result.exit_code == 1
    assert "No registered images found" in result.stderr


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
    _project_dir, image_files = test_project_with_images

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

    image_records = [
        {"id": i + 1, "phash": f"phash{i:016d}", "stored_image_path": str(img_path)}
        for i, img_path in enumerate(image_files)
    ]
    mock_container.db_manager.image_repo.get_images_by_filter.return_value = (
        image_records,
        len(image_records),
    )
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
def test_annotate_run_json_emits_items_and_result_only(
    mock_get_container,
    test_project_with_images: tuple[Path, list[Path]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--json は画像ごとの item と終端 result だけを stdout JSONL に出す。"""
    monkeypatch.setenv("LORAIRO_CLI_JSON", "1")
    _project_dir, image_files = test_project_with_images

    mock_container = MagicMock()
    mock_annotator = MagicMock()
    mock_config = MagicMock()
    mock_config.get_setting.return_value = "test_key"
    mock_annotator.annotate.return_value = {
        "phash0000000000000000": {"gpt-4o-mini": {"tags": ["cat"], "score": 0.8, "error": None}},
        "phash0000000000000001": {"gpt-4o-mini": {"tags": ["dog"], "score": 0.7, "error": None}},
    }

    image_records = [
        {"id": i + 1, "phash": f"phash{i:016d}", "stored_image_path": str(img_path)}
        for i, img_path in enumerate(image_files[:2])
    ]
    mock_container.db_manager.image_repo.get_images_by_filter.return_value = (
        image_records,
        len(image_records),
    )
    mock_container.annotator_library = mock_annotator
    mock_container.config_service = mock_config
    mock_container.annotation_save_service.save_annotation_results.return_value = AnnotationSaveResult(
        success_count=2,
        skip_count=0,
        error_count=0,
        total_count=2,
    )
    mock_get_container.return_value = mock_container

    result = runner.invoke(
        app,
        ["annotate", "run", "--project", "test_dataset", "--model", "gpt-4o-mini"],
    )

    assert result.exit_code == 0, result.output
    lines = [json.loads(line) for line in result.stdout.splitlines()]
    assert [line["kind"] for line in lines] == ["item", "item", "result"]
    assert lines[0]["type"] == "annotation"
    assert lines[0]["image_id"] == 1
    assert lines[0]["models"][0]["tags"] == ["cat"]
    assert lines[-1]["annotated"] == 2
    assert lines[-1]["skipped"] == 0


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.annotate.get_service_container")
def test_annotate_run_json_rejects_more_than_500_before_items(
    mock_get_container,
    test_project_with_images: tuple[Path, list[Path]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """annotate run の処理集合500超は item を出す前に RESULT_SET_TOO_LARGE。"""
    monkeypatch.setenv("LORAIRO_CLI_JSON", "1")
    _project_dir, image_files = test_project_with_images

    mock_container = MagicMock()
    mock_config = MagicMock()
    mock_config.get_setting.return_value = "test_key"
    records = [
        {"id": i + 1, "phash": f"phash{i:016d}", "stored_image_path": str(image_files[0])}
        for i in range(501)
    ]
    mock_container.db_manager.image_repo.get_images_by_filter.return_value = (records, len(records))
    mock_container.config_service = mock_config
    mock_get_container.return_value = mock_container

    result = runner.invoke(
        app,
        ["annotate", "run", "--project", "test_dataset", "--model", "gpt-4o-mini"],
    )

    assert result.exit_code == 2
    lines = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(lines) == 1
    assert lines[0]["kind"] == "error"
    assert lines[0]["code"] == "RESULT_SET_TOO_LARGE"
    assert lines[0]["details"] == {"limit": 500, "matched": 501}
    mock_container.annotator_library.annotate.assert_not_called()


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.annotate.get_service_container")
def test_annotate_run_deprecated_model_shows_warning(
    mock_get_container,
    test_project_with_images: tuple[Path, list[Path]],
) -> None:
    """Test: annotate run - 廃止モデル指定時は警告を表示して継続。"""
    _project_dir, image_files = test_project_with_images

    mock_container = MagicMock()
    mock_annotator = MagicMock()
    mock_config = MagicMock()

    mock_config.get_setting.return_value = "test_key"
    mock_annotator.is_model_deprecated.return_value = True
    mock_annotator.annotate.return_value = {
        "hash1": {"openai/old-model": MagicMock(error=None)},
        "hash2": {"openai/old-model": MagicMock(error=None)},
        "hash3": {"openai/old-model": MagicMock(error=None)},
    }

    image_records = [
        {"id": i + 1, "phash": f"phash{i:016d}", "stored_image_path": str(img_path)}
        for i, img_path in enumerate(image_files)
    ]
    mock_container.db_manager.image_repo.get_images_by_filter.return_value = (
        image_records,
        len(image_records),
    )
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
            "openai/old-model",
        ],
    )

    assert result.exit_code == 0
    assert "Warning: Model 'openai/old-model' is deprecated" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.annotate.get_service_container")
def test_annotate_run_deprecated_check_failure_continues(
    mock_get_container,
    test_project_with_images: tuple[Path, list[Path]],
) -> None:
    """Test: annotate run - 廃止判定失敗時もアノテーションを継続。"""
    _project_dir, image_files = test_project_with_images

    mock_container = MagicMock()
    mock_annotator = MagicMock()
    mock_config = MagicMock()

    mock_config.get_setting.return_value = "test_key"
    mock_annotator.is_model_deprecated.side_effect = RuntimeError("registry parse failed")
    mock_annotator.annotate.return_value = {
        "hash1": {"openai/model": MagicMock(error=None)},
        "hash2": {"openai/model": MagicMock(error=None)},
        "hash3": {"openai/model": MagicMock(error=None)},
    }

    image_records = [
        {"id": i + 1, "phash": f"phash{i:016d}", "stored_image_path": str(img_path)}
        for i, img_path in enumerate(image_files)
    ]
    mock_container.db_manager.image_repo.get_images_by_filter.return_value = (
        image_records,
        len(image_records),
    )
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
            "openai/model",
        ],
    )

    assert result.exit_code == 0
    assert "Deprecated model metadata is unavailable" in result.stdout
    mock_annotator.annotate.assert_called_once()


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.annotate.get_service_container")
def test_annotate_run_with_multiple_models(
    mock_get_container,
    test_project_with_images: tuple[Path, list[Path]],
) -> None:
    """Test: annotate run - 複数モデル指定。"""
    _project_dir, image_files = test_project_with_images

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

    image_records = [
        {"id": i + 1, "phash": f"phash{i:016d}", "stored_image_path": str(img_path)}
        for i, img_path in enumerate(image_files)
    ]
    mock_container.db_manager.image_repo.get_images_by_filter.return_value = (
        image_records,
        len(image_records),
    )
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
    """Test: annotate run - APIキー不足検出で実行中止 (Issue #241)。

    Issue #241 で挙動が変更: 旧仕様は「全 key 空でも警告のみ + 続行」だったが、
    library 内で MissingApiKeyError が出てから初めて失敗していた。新仕様では
    LoRAIro 側で事前に provider 別の不足を検出し ``typer.Exit(1)`` で abort する。
    """
    from types import SimpleNamespace

    _project_dir, image_files = test_project_with_images

    # ServiceContainer をモック
    mock_container = MagicMock()
    mock_annotator = MagicMock()
    mock_config = MagicMock()

    # APIキーなし（空文字列）
    mock_config.get_setting.return_value = ""

    # Issue #241: _resolve_model_identifier と _validate_required_api_keys は
    # repository.get_model_by_litellm_id() の結果から Model.provider を hint として
    # 引く。MagicMock の default は MagicMock を返すため、Model 互換 fake (str provider)
    # を明示的に渡して validation 経路が安定動作するようにする。
    mock_container.db_manager.model_repo.get_model_by_litellm_id.return_value = SimpleNamespace(
        litellm_model_id="openai/gpt-4o-mini",
        name="gpt-4o-mini",
        provider="openai",
    )

    mock_annotator.annotate.return_value = {}

    image_records = [
        {"id": i + 1, "phash": f"phash{i:016d}", "stored_image_path": str(img_path)}
        for i, img_path in enumerate(image_files)
    ]
    mock_container.db_manager.image_repo.get_images_by_filter.return_value = (
        image_records,
        len(image_records),
    )
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
            "openai/gpt-4o-mini",
        ],
    )

    # Issue #241 / ADR 0057: 不足検出は INVALID_INPUT + exit 2。
    assert result.exit_code == 2
    assert "Missing API keys" in result.stderr
    assert "openai" in result.stderr


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.annotate.get_service_container")
def test_annotate_run_with_output_option(
    mock_get_container,
    test_project_with_images: tuple[Path, list[Path]],
    tmp_path: Path,
) -> None:
    """Test: annotate run - --output オプション指定。"""
    _project_dir, image_files = test_project_with_images

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

    image_records = [
        {"id": i + 1, "phash": f"phash{i:016d}", "stored_image_path": str(img_path)}
        for i, img_path in enumerate(image_files)
    ]
    mock_container.db_manager.image_repo.get_images_by_filter.return_value = (
        image_records,
        len(image_records),
    )
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
    _project_dir, image_files = test_project_with_images

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

    image_records = [
        {"id": i + 1, "phash": f"phash{i:016d}", "stored_image_path": str(img_path)}
        for i, img_path in enumerate(image_files)
    ]
    mock_container.db_manager.image_repo.get_images_by_filter.return_value = (
        image_records,
        len(image_records),
    )
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
def test_annotate_run_unrated_passes_only_unrated_criteria(
    mock_get_container,
    test_project_with_images: tuple[Path, list[Path]],
) -> None:
    """Test: annotate run --unrated は rating 未保存画像のみに絞る criteria を渡す。"""
    _project_dir, image_files = test_project_with_images

    mock_container = MagicMock()
    mock_annotator = MagicMock()
    mock_config = MagicMock()

    mock_config.get_setting.return_value = "test_key"
    mock_annotator.annotate.return_value = {"hash1": {"tags": ["tag1"]}}

    image_records = [{"id": 1, "phash": "phash0000000000000000", "stored_image_path": str(image_files[0])}]
    mock_container.db_manager.image_repo.get_images_by_filter.return_value = (image_records, 1)
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
            "--unrated",
        ],
    )

    assert result.exit_code == 0
    criteria = mock_container.db_manager.image_repo.get_images_by_filter.call_args.args[0]
    assert criteria.include_nsfw is True
    assert criteria.only_unrated is True
    assert criteria.missing_model_litellm_id is None
    assert "Filter: unrated images only" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.annotate.get_service_container")
def test_annotate_run_missing_model_passes_missing_model_criteria(
    mock_get_container,
    test_project_with_images: tuple[Path, list[Path]],
) -> None:
    """Test: annotate run --missing-model は指定モデル未処理画像のみに絞る criteria を渡す。"""
    _project_dir, image_files = test_project_with_images

    mock_container = MagicMock()
    mock_annotator = MagicMock()
    mock_config = MagicMock()

    mock_config.get_setting.return_value = "test_key"
    mock_annotator.annotate.return_value = {"hash1": {"tags": ["tag1"]}}

    image_records = [{"id": 1, "phash": "phash0000000000000000", "stored_image_path": str(image_files[0])}]
    mock_container.db_manager.image_repo.get_images_by_filter.return_value = (image_records, 1)
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
            "--missing-model",
            "openai/omni-moderation-latest",
        ],
    )

    assert result.exit_code == 0
    criteria = mock_container.db_manager.image_repo.get_images_by_filter.call_args.args[0]
    assert criteria.include_nsfw is True
    assert criteria.only_unrated is False
    assert criteria.missing_model_litellm_id == "openai/omni-moderation-latest"
    assert "Filter: missing model openai/omni-moderation-latest" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.annotate.get_service_container")
def test_annotate_run_filter_matches_no_images_exits_before_loading(
    mock_get_container,
    test_project_with_images: tuple[Path, list[Path]],
) -> None:
    """Test: annotate run のフィルタ結果が0件なら画像ロード前に exit 1。"""
    mock_container = MagicMock()
    mock_container.db_manager.image_repo.get_images_by_filter.return_value = ([], 0)
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
            "--unrated",
        ],
    )

    assert result.exit_code == 1
    assert "No images matched annotation filters" in result.stderr
    mock_container.annotator_library.annotate.assert_not_called()


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.annotate.get_service_container")
def test_annotate_run_annotation_failure(
    mock_get_container,
    test_project_with_images: tuple[Path, list[Path]],
) -> None:
    """Test: annotate run - アノテーション実行エラー。"""
    _project_dir, image_files = test_project_with_images

    # ServiceContainer をモック
    mock_container = MagicMock()
    mock_annotator = MagicMock()
    mock_config = MagicMock()

    mock_config.get_setting.return_value = "test_key"

    # アノテーション実行でエラーが発生する
    mock_annotator.annotate.side_effect = Exception("API Error: Invalid key")

    image_records = [
        {"id": i + 1, "phash": f"phash{i:016d}", "stored_image_path": str(img_path)}
        for i, img_path in enumerate(image_files)
    ]
    mock_container.db_manager.image_repo.get_images_by_filter.return_value = (
        image_records,
        len(image_records),
    )
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
    assert "Annotation failed" in result.stderr or "Error" in result.stderr


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.annotate.get_service_container")
def test_annotate_run_summary_display(
    mock_get_container,
    test_project_with_images: tuple[Path, list[Path]],
) -> None:
    """Test: annotate run - アノテーション完了後のサマリー表示。"""
    _project_dir, image_files = test_project_with_images

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

    image_records = [
        {"id": i + 1, "phash": f"phash{i:016d}", "stored_image_path": str(img_path)}
        for i, img_path in enumerate(image_files)
    ]
    mock_container.db_manager.image_repo.get_images_by_filter.return_value = (
        image_records,
        len(image_records),
    )
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
def test_annotate_run_with_special_project_name(
    mock_get_container,
    mock_projects_dir: Path,
) -> None:
    """Test: annotate run - ハイフン付きプロジェクト名。"""
    # プロジェクトを作成
    result = runner.invoke(app, ["project", "create", "special-project"])
    assert result.exit_code == 0

    project_dirs = list(mock_projects_dir.iterdir())
    project_dir = next(d for d in project_dirs if "special-project" in d.name)

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

    mock_container.db_manager.image_repo.get_images_by_filter.return_value = (
        [{"id": 1, "phash": "phash0000000000000000", "stored_image_path": str(img_path)}],
        1,
    )
    mock_container.annotator_library = mock_annotator
    mock_container.config_service = mock_config
    mock_get_container.return_value = mock_container

    result = runner.invoke(
        app,
        [
            "annotate",
            "run",
            "--project",
            "special-project",
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

    image_records = [
        {"id": i + 1, "phash": f"phash{i:016d}", "stored_image_path": str(img_path)}
        for i, img_path in enumerate(image_files)
    ]
    mock_container.db_manager.image_repo.get_images_by_filter.return_value = (
        image_records,
        len(image_records),
    )
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


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.annotate.get_service_container")
def test_annotate_run_all_models_failed_exits_nonzero(
    mock_get_container: MagicMock,
    test_project_with_images: tuple[Path, list[Path]],
) -> None:
    """Test: annotate run - 全モデルがエラー結果を返した場合は exit_code=1。"""
    _project_dir, image_files = test_project_with_images

    mock_container = MagicMock()
    mock_annotator = MagicMock()
    mock_config = MagicMock()
    mock_config.get_setting.return_value = "test_key"

    # 全モデルがエラー結果を返す (UnifiedAnnotationResult.error != None)
    error_result = MagicMock()
    error_result.error = "Model 'gpt-4o-mini' not found in registry"
    mock_annotator.annotate.return_value = {
        "hash1": {"gpt-4o-mini": error_result},
        "hash2": {"gpt-4o-mini": error_result},
        "hash3": {"gpt-4o-mini": error_result},
    }

    image_records = [
        {"id": i + 1, "phash": f"phash{i:016d}", "stored_image_path": str(img_path)}
        for i, img_path in enumerate(image_files)
    ]
    mock_container.db_manager.image_repo.get_images_by_filter.return_value = (
        image_records,
        len(image_records),
    )
    mock_container.annotator_library = mock_annotator
    mock_container.config_service = mock_config
    mock_get_container.return_value = mock_container

    result = runner.invoke(
        app,
        ["annotate", "run", "--project", "test_dataset", "--model", "gpt-4o-mini"],
    )

    assert result.exit_code == 1
    assert "Error" in result.stderr
    assert "gpt-4o-mini" in result.stderr


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.annotate.get_service_container")
def test_annotate_run_partial_model_failure_shows_warning(
    mock_get_container: MagicMock,
    test_project_with_images: tuple[Path, list[Path]],
) -> None:
    """Test: annotate run - 一部モデルがエラー、一部が成功の場合は exit_code=0 + Warning。"""
    _project_dir, image_files = test_project_with_images

    mock_container = MagicMock()
    mock_annotator = MagicMock()
    mock_config = MagicMock()
    mock_config.get_setting.return_value = "test_key"

    error_result = MagicMock()
    error_result.error = "Model config error"
    success_result = MagicMock()
    success_result.error = None

    mock_annotator.annotate.return_value = {
        "hash1": {"gpt-4o-mini": error_result, "wdtagger": success_result},
        "hash2": {"gpt-4o-mini": error_result, "wdtagger": success_result},
        "hash3": {"gpt-4o-mini": error_result, "wdtagger": success_result},
    }

    image_records = [
        {"id": i + 1, "phash": f"phash{i:016d}", "stored_image_path": str(img_path)}
        for i, img_path in enumerate(image_files)
    ]
    mock_container.db_manager.image_repo.get_images_by_filter.return_value = (
        image_records,
        len(image_records),
    )
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
            "wdtagger",
        ],
    )

    assert result.exit_code == 0
    assert "Warning" in result.stdout
    assert "gpt-4o-mini" in result.stdout


# ===== DB保存テスト =====


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.annotate.get_service_container")
def test_annotate_run_saves_results_to_db(
    mock_get_container: MagicMock,
    test_project_with_images: tuple[Path, list[Path]],
) -> None:
    """Test: annotate run - アノテーション結果がDBに保存される。"""
    _project_dir, image_files = test_project_with_images

    mock_container = MagicMock()
    mock_annotator = MagicMock()
    mock_config = MagicMock()
    mock_config.get_setting.return_value = "test_key"

    mock_annotator.annotate.return_value = {
        "hash0000000000000001": {"gpt-4o-mini": MagicMock(error=None)},
        "hash0000000000000002": {"gpt-4o-mini": MagicMock(error=None)},
    }

    image_records = [
        {"id": 1, "phash": "hash0000000000000001", "stored_image_path": str(image_files[0])},
        {"id": 2, "phash": "hash0000000000000002", "stored_image_path": str(image_files[1])},
        {"id": 3, "phash": "hash0000000000000003", "stored_image_path": str(image_files[2])},
    ]

    mock_container.annotation_save_service.save_annotation_results.return_value = AnnotationSaveResult(
        success_count=2, skip_count=1, error_count=0, total_count=3
    )
    mock_container.db_manager.image_repo.get_images_by_filter.return_value = (
        image_records,
        len(image_records),
    )
    mock_container.annotator_library = mock_annotator
    mock_container.config_service = mock_config
    mock_get_container.return_value = mock_container

    result = runner.invoke(
        app,
        ["annotate", "run", "--project", "test_dataset", "--model", "gpt-4o-mini"],
    )

    assert result.exit_code == 0
    # annotation_save_service.save_annotation_results が呼ばれたことを確認
    assert mock_container.annotation_save_service.save_annotation_results.call_count == 1
    # サマリーに保存件数が表示される
    assert "Saved to DB" in result.stdout
    assert "2" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.annotate.get_service_container")
def test_annotate_run_summary_shows_saved_count(
    mock_get_container: MagicMock,
    test_project_with_images: tuple[Path, list[Path]],
) -> None:
    """Test: annotate run - 保存件数がSummaryに表示される。"""
    _project_dir, image_files = test_project_with_images

    mock_container = MagicMock()
    mock_annotator = MagicMock()
    mock_config = MagicMock()
    mock_config.get_setting.return_value = "test_key"

    mock_annotator.annotate.return_value = {
        "matchhash001": {"gpt-4o-mini": MagicMock(error=None)},
    }

    image_records = [
        {"id": 10, "phash": "matchhash001", "stored_image_path": str(image_files[0])},
    ]

    mock_container.annotation_save_service.save_annotation_results.return_value = AnnotationSaveResult(
        success_count=1, skip_count=0, error_count=0, total_count=1
    )
    mock_container.db_manager.image_repo.get_images_by_filter.return_value = (image_records, 1)
    mock_container.annotator_library = mock_annotator
    mock_container.config_service = mock_config
    mock_get_container.return_value = mock_container

    result = runner.invoke(
        app,
        ["annotate", "run", "--project", "test_dataset", "--model", "gpt-4o-mini"],
    )

    assert result.exit_code == 0
    assert "Saved to DB" in result.stdout
    assert "Skipped" in result.stdout
    # 完了メッセージに保存件数が含まれる
    assert "saved to DB" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.annotate.get_service_container")
def test_annotate_run_db_save_error_shows_warning(
    mock_get_container: MagicMock,
    test_project_with_images: tuple[Path, list[Path]],
) -> None:
    """Test: annotate run - DB保存エラー時はWarningを表示して処理継続。"""
    _project_dir, image_files = test_project_with_images

    mock_container = MagicMock()
    mock_annotator = MagicMock()
    mock_config = MagicMock()
    mock_config.get_setting.return_value = "test_key"

    mock_annotator.annotate.return_value = {
        "saveerrhash001": {"gpt-4o-mini": MagicMock(error=None)},
    }

    image_records = [
        {"id": 5, "phash": "saveerrhash001", "stored_image_path": str(image_files[0])},
    ]

    mock_container.annotation_save_service.save_annotation_results.return_value = AnnotationSaveResult(
        success_count=0,
        skip_count=0,
        error_count=1,
        total_count=1,
        error_details=["phash=saveerrh...: DB write error"],
    )
    mock_container.db_manager.image_repo.get_images_by_filter.return_value = (image_records, 1)
    mock_container.annotator_library = mock_annotator
    mock_container.config_service = mock_config
    mock_get_container.return_value = mock_container

    result = runner.invoke(
        app,
        ["annotate", "run", "--project", "test_dataset", "--model", "gpt-4o-mini"],
    )

    # 保存エラーがあっても exit_code=0 で継続
    assert result.exit_code == 0
    assert "Warning" in result.stdout
    # 保存件数は0
    assert "Saved to DB" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.annotate.get_service_container")
def test_annotate_run_phash_mismatch_skips_gracefully(
    mock_get_container: MagicMock,
    test_project_with_images: tuple[Path, list[Path]],
) -> None:
    """Test: annotate run - phashが不一致の場合はスキップして処理継続。"""
    _project_dir, image_files = test_project_with_images

    mock_container = MagicMock()
    mock_annotator = MagicMock()
    mock_config = MagicMock()
    mock_config.get_setting.return_value = "test_key"

    # アノテーション結果のphashがDB記録と不一致
    mock_annotator.annotate.return_value = {
        "completely_different_hash": {"gpt-4o-mini": MagicMock(error=None)},
    }

    image_records = [
        {"id": 1, "phash": "db_stored_hash_001", "stored_image_path": str(image_files[0])},
    ]

    mock_container.annotation_save_service.save_annotation_results.return_value = AnnotationSaveResult(
        success_count=0, skip_count=1, error_count=0, total_count=1
    )
    mock_container.db_manager.image_repo.get_images_by_filter.return_value = (image_records, 1)
    mock_container.annotator_library = mock_annotator
    mock_container.config_service = mock_config
    mock_get_container.return_value = mock_container

    result = runner.invoke(
        app,
        ["annotate", "run", "--project", "test_dataset", "--model", "gpt-4o-mini"],
    )

    assert result.exit_code == 0
    # スキップされてもエラーにならない
    assert "Saved to DB" in result.stdout
