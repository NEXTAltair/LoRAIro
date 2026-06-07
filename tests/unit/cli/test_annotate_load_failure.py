"""Annotation image-load failure classification テスト (Issue #537)。

画像ロード失敗の分類 (FATAL vs SKIP) を検証する。

- メモリ/リソース枯渇 (`MemoryError` / `errno.ENOMEM`) は致命 → exit_code == 1。
- 破損/読み込み失敗 (一般 `OSError` / `UnidentifiedImageError`) は skip され、
  他に正常画像があれば継続 → exit_code == 0。
"""

import errno
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image, UnidentifiedImageError
from typer.testing import CliRunner

from lorairo.cli.commands.annotate import (
    ImageLoadMemoryError,
    LoadFailureAction,
    _classify_load_failure,
    _load_batch_images,
)
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
def project_with_images(mock_projects_dir: Path) -> list[Path]:
    """3 枚のテスト画像を持つプロジェクトを作成する。"""
    result = runner.invoke(app, ["project", "create", "fail_dataset"])
    assert result.exit_code == 0

    project_dirs = list(mock_projects_dir.iterdir())
    project_dir = next(d for d in project_dirs if d.name.startswith("fail_dataset_"))

    image_dataset_dir = project_dir / "image_dataset" / "processed_images"
    image_dataset_dir.mkdir(parents=True, exist_ok=True)

    image_files: list[Path] = []
    for i in range(3):
        img = Image.new("RGB", (32, 32), color=(i * 40, 0, 0))
        img_path = image_dataset_dir / f"fail_image_{i}.jpg"
        img.save(img_path)
        image_files.append(img_path)
    return image_files


def _build_container(image_files: list[Path]) -> MagicMock:
    """画像レコードを返すモック ServiceContainer を構築する。"""
    mock_container = MagicMock()
    mock_annotator = MagicMock()
    mock_config = MagicMock()
    mock_config.get_setting.return_value = "test_key"

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
    mock_container.annotation_save_service.save_annotation_results.side_effect = lambda results, **_kwargs: (
        AnnotationSaveResult(
            success_count=len(results),
            skip_count=0,
            error_count=0,
            total_count=len(results),
        )
    )
    return mock_container


# ===== _classify_load_failure unit tests =====


@pytest.mark.unit
@pytest.mark.cli
def test_classify_memory_error_is_fatal() -> None:
    """MemoryError は FATAL に分類される。"""
    assert _classify_load_failure(MemoryError("out of memory")) is LoadFailureAction.FATAL


@pytest.mark.unit
@pytest.mark.cli
def test_classify_enomem_oserror_is_fatal() -> None:
    """errno.ENOMEM の OSError は FATAL に分類される。"""
    exc = OSError(errno.ENOMEM, "Cannot allocate memory")
    assert _classify_load_failure(exc) is LoadFailureAction.FATAL


@pytest.mark.unit
@pytest.mark.cli
def test_classify_generic_oserror_is_skip() -> None:
    """ENOMEM 以外の OSError は SKIP に分類される。"""
    exc = OSError(errno.ENOENT, "No such file")
    assert _classify_load_failure(exc) is LoadFailureAction.SKIP


@pytest.mark.unit
@pytest.mark.cli
def test_classify_unidentified_image_error_is_skip() -> None:
    """UnidentifiedImageError (破損画像) は SKIP に分類される。"""
    assert _classify_load_failure(UnidentifiedImageError("bad image")) is LoadFailureAction.SKIP


# ===== _load_batch_images behavior =====


@pytest.mark.unit
@pytest.mark.cli
def test_load_batch_raises_on_memory_error(
    project_with_images: list[Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """ロード中 MemoryError 発生で ImageLoadMemoryError を raise する。"""

    def _raise_memory(*args, **kwargs):
        raise MemoryError("simulated OOM")

    monkeypatch.setattr("lorairo.cli.commands.annotate.Image.open", _raise_memory)

    records = [{"id": 1, "phash": "p", "stored_image_path": str(project_with_images[0])}]
    with pytest.raises(ImageLoadMemoryError):
        _load_batch_images(records)


# ===== End-to-end CLI exit code =====


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.annotate.get_service_container")
def test_run_memory_error_exits_nonzero(
    mock_get_container: MagicMock,
    project_with_images: list[Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """画像ロード中 MemoryError → 致命扱いで exit_code == 1。

    Exit code 期待値: 1 (致命的ロード失敗)。
    """
    mock_container = _build_container(project_with_images)
    mock_get_container.return_value = mock_container

    def _raise_memory(*args, **kwargs):
        raise MemoryError("simulated OOM")

    monkeypatch.setattr("lorairo.cli.commands.annotate.Image.open", _raise_memory)

    result = runner.invoke(
        app,
        ["annotate", "run", "--project", "fail_dataset", "--model", "gpt-4o-mini"],
    )

    assert result.exit_code == 1, result.stdout
    assert "Memory/resource exhaustion" in result.stderr
    # 致命扱いなので annotate は呼ばれない。
    assert mock_container.annotator_library.annotate.call_count == 0


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.annotate.get_service_container")
def test_run_enomem_oserror_exits_nonzero(
    mock_get_container: MagicMock,
    project_with_images: list[Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """画像ロード中 OSError(ENOMEM) → 致命扱いで exit_code == 1。

    Exit code 期待値: 1 (致命的ロード失敗)。
    """
    mock_container = _build_container(project_with_images)
    mock_get_container.return_value = mock_container

    def _raise_enomem(*args, **kwargs):
        raise OSError(errno.ENOMEM, "Cannot allocate memory")

    monkeypatch.setattr("lorairo.cli.commands.annotate.Image.open", _raise_enomem)

    result = runner.invoke(
        app,
        ["annotate", "run", "--project", "fail_dataset", "--model", "gpt-4o-mini"],
    )

    assert result.exit_code == 1, result.stdout
    assert "Memory/resource exhaustion" in result.stderr


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.annotate.get_service_container")
def test_run_corrupted_image_skipped_others_continue(
    mock_get_container: MagicMock,
    project_with_images: list[Path],
) -> None:
    """破損画像 (一般 OSError/UnidentifiedImageError) は skip し、残りで継続。

    1 枚目を破損させても、残り 2 枚が正常なら annotation 継続。
    Exit code 期待値: 0 (致命でない skip)。
    """
    # 1 枚目を破損させる (UnidentifiedImageError を誘発)。
    project_with_images[0].write_bytes(b"not an image")

    mock_container = _build_container(project_with_images)
    mock_get_container.return_value = mock_container

    result = runner.invoke(
        app,
        ["annotate", "run", "--project", "fail_dataset", "--model", "gpt-4o-mini"],
    )

    assert result.exit_code == 0, result.stdout
    # 破損 1 枚 skip + 正常 2 枚ロード。
    assert "Loaded 2 image(s) (1 failed)" in result.stdout
    # annotate は正常画像で 1 回呼ばれる。
    assert mock_container.annotator_library.annotate.call_count == 1
