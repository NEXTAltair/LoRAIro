"""Annotation streaming (chunk) テスト (Issue #536)。

`annotate run` がメモリ枯渇を避けるために画像レコードを `--batch-size` 単位で
ロード→アノテーション→DB 保存するストリーミング駆動になっていることを検証する。

Exit code の期待値:
  - 正常系 (1 件以上成功): exit_code == 0
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image
from typer.testing import CliRunner

from lorairo.cli.main import app
from lorairo.services.annotation_save_service import AnnotationSaveResult
from lorairo.services.project_management_service import ProjectManagementService
from lorairo.services.service_container import ServiceContainer

runner = CliRunner()


@pytest.fixture(autouse=True)
def _bypass_model_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    """`_resolve_model_identifier` を identity 関数に差し替える (既存テスト踏襲)。"""
    monkeypatch.setattr(
        "lorairo.cli.commands.annotate._resolve_model_identifier",
        lambda _repo, identifier: identifier,
    )


@pytest.fixture
def mock_projects_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """ProjectManagementService のプロジェクトディレクトリをモック。"""
    mock_dir = tmp_path / "projects"
    mock_dir.mkdir()

    container = ServiceContainer()
    container._project_management_service = None

    original_init = ProjectManagementService.__init__

    def patched_init(self: ProjectManagementService, projects_base_dir: Path | None = None) -> None:
        original_init(self, projects_base_dir=mock_dir)

    monkeypatch.setattr(ProjectManagementService, "__init__", patched_init)

    return mock_dir


@pytest.fixture
def project_with_n_images(mock_projects_dir: Path):
    """N 枚のテスト画像を持つプロジェクトを作成するファクトリ。"""

    def _make(count: int) -> list[Path]:
        result = runner.invoke(app, ["project", "create", "stream_dataset"])
        assert result.exit_code == 0

        project_dirs = list(mock_projects_dir.iterdir())
        project_dir = next(d for d in project_dirs if d.name.startswith("stream_dataset_"))

        image_dataset_dir = project_dir / "image_dataset" / "original_images"
        image_dataset_dir.mkdir(parents=True, exist_ok=True)

        image_files: list[Path] = []
        for i in range(count):
            img = Image.new("RGB", (32, 32), color=(i % 255, 0, 0))
            img_path = image_dataset_dir / f"stream_image_{i}.jpg"
            img.save(img_path)
            image_files.append(img_path)
        return image_files

    return _make


def _build_container(image_files: list[Path]) -> MagicMock:
    """画像レコードを返すモック ServiceContainer を構築する。"""
    mock_container = MagicMock()
    mock_annotator = MagicMock()
    mock_config = MagicMock()
    mock_config.get_setting.return_value = "test_key"

    # 成功結果 (error=None) を 1 モデル分返す。
    def _annotate(images, litellm_model_ids):
        return {f"hash_{idx}": {"gpt-4o-mini": MagicMock(error=None)} for idx in range(len(images))}

    mock_annotator.annotate.side_effect = _annotate

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
    mock_container.annotation_save_service.save_annotation_results.side_effect = lambda results: (
        AnnotationSaveResult(
            success_count=len(results),
            skip_count=0,
            error_count=0,
            total_count=len(results),
        )
    )
    return mock_container


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.annotate.get_service_container")
def test_streaming_multiple_chunks_calls_annotate_multiple_times(
    mock_get_container: MagicMock,
    project_with_n_images,
) -> None:
    """dataset > batch_size のとき annotate が複数回 (チャンク数分) 呼ばれる。

    7 件 / batch_size=3 → 3 チャンク (3,3,1) → annotate 3 回。
    Exit code 期待値: 0 (全件成功)。
    """
    image_files = project_with_n_images(7)
    mock_container = _build_container(image_files)
    mock_get_container.return_value = mock_container

    result = runner.invoke(
        app,
        [
            "annotate",
            "run",
            "--project",
            "stream_dataset",
            "--model",
            "gpt-4o-mini",
            "--batch-size",
            "3",
        ],
    )

    assert result.exit_code == 0, result.stdout
    # 7 件 / batch_size 3 = 3 チャンク
    assert mock_container.annotator_library.annotate.call_count == 3
    assert "Found 7 image(s)" in result.stdout
    assert "Loaded 7 image(s)" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.annotate.get_service_container")
def test_streaming_closes_images_after_each_chunk(
    mock_get_container: MagicMock,
    project_with_n_images,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """各チャンク処理後に PIL 画像が close される (メモリ解放)。

    Image.open を spy 化し、生成された各画像インスタンスの close() が
    呼ばれていることを検証する。
    Exit code 期待値: 0。
    """
    image_files = project_with_n_images(4)
    mock_container = _build_container(image_files)
    mock_get_container.return_value = mock_container

    opened_images: list[MagicMock] = []
    real_open = Image.open

    def _spy_open(*args, **kwargs):
        real_img = real_open(*args, **kwargs)
        real_img.load()
        spy = MagicMock(wraps=real_img)
        opened_images.append(spy)
        return spy

    monkeypatch.setattr("lorairo.cli.commands.annotate.Image.open", _spy_open)

    result = runner.invoke(
        app,
        [
            "annotate",
            "run",
            "--project",
            "stream_dataset",
            "--model",
            "gpt-4o-mini",
            "--batch-size",
            "2",
        ],
    )

    assert result.exit_code == 0, result.stdout
    # 全画像分の spy が生成されており、それぞれ close() が呼ばれている。
    assert len(opened_images) == 4
    for spy in opened_images:
        spy.close.assert_called_once()


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.annotate.get_service_container")
def test_streaming_single_batch_when_batch_size_ge_dataset(
    mock_get_container: MagicMock,
    project_with_n_images,
) -> None:
    """batch_size >= dataset の小規模では単一バッチ・従来挙動互換。

    3 件 / batch_size=10 → 1 チャンク → annotate 1 回。
    Exit code 期待値: 0。
    """
    image_files = project_with_n_images(3)
    mock_container = _build_container(image_files)
    mock_get_container.return_value = mock_container

    result = runner.invoke(
        app,
        [
            "annotate",
            "run",
            "--project",
            "stream_dataset",
            "--model",
            "gpt-4o-mini",
            "--batch-size",
            "10",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert mock_container.annotator_library.annotate.call_count == 1
    assert "Found 3 image(s)" in result.stdout
    assert "Loaded 3 image(s)" in result.stdout
