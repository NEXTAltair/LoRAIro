"""AnnotationRunner ユニットテスト

annotation_runner.py の全コードパスをカバーする。
Qt非依存クラスのため @pytest.mark.unit を付与する。
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from lorairo.annotation.annotation_runner import AnnotationRunner

# ---- フィクスチャ ----


@pytest.fixture
def mock_adapter() -> MagicMock:
    """AnnotatorLibraryAdapter のモック。annotate が pHash→結果辞書を返す。"""
    adapter = MagicMock()
    adapter.annotate.return_value = {"abc123def456": {"tags": ["cat"], "captions": []}}
    return adapter


@pytest.fixture
def logic(mock_adapter: MagicMock) -> AnnotationRunner:
    """AnnotationRunner インスタンス（モックアダプター注入済み）。"""
    return AnnotationRunner(annotator_adapter=mock_adapter)


@pytest.fixture
def test_image_dir() -> Path:
    """テスト用画像ディレクトリのパスを返す。"""
    return Path(__file__).parent.parent.parent / "resources" / "img" / "1_img"


@pytest.fixture
def test_image_path(test_image_dir: Path) -> Path:
    """テスト用画像のパスを返す（存在しない場合はスキップ）。"""
    image_path = test_image_dir / "file01.webp"
    if not image_path.exists():
        pytest.skip(f"テスト用画像が見つかりません: {image_path}")
    return image_path


# ---- 正常系: execute_annotation ----


@pytest.mark.unit
def test_execute_annotation_calls_adapter_with_correct_args(
    logic: AnnotationRunner, mock_adapter: MagicMock, test_image_path: Path
) -> None:
    """execute_annotation が adapter.annotate を正しい引数で呼ぶことを確認する。"""
    image_paths = [str(test_image_path)]
    model_ids = ["openai/gpt-4o"]

    logic.execute_annotation(image_paths, model_ids)

    mock_adapter.annotate.assert_called_once()
    call_kwargs = mock_adapter.annotate.call_args.kwargs
    assert call_kwargs["litellm_model_ids"] == model_ids
    assert call_kwargs["phash_list"] is None
    # images はリストで PIL.Image インスタンスを含む
    assert isinstance(call_kwargs["images"], list)
    assert len(call_kwargs["images"]) == 1
    assert isinstance(call_kwargs["images"][0], Image.Image)


@pytest.mark.unit
def test_execute_annotation_returns_adapter_result(
    logic: AnnotationRunner, mock_adapter: MagicMock, test_image_path: Path
) -> None:
    """execute_annotation が adapter.annotate の戻り値をそのまま返すことを確認する。"""
    image_paths = [str(test_image_path)]
    model_ids = ["openai/gpt-4o"]

    result = logic.execute_annotation(image_paths, model_ids)

    # adapter.annotate の戻り値と同一オブジェクトが返されることを確認
    assert result is mock_adapter.annotate.return_value


# ---- phash_list あり ----


@pytest.mark.unit
def test_execute_annotation_passes_phash_list_to_adapter(
    logic: AnnotationRunner, mock_adapter: MagicMock, test_image_path: Path
) -> None:
    """phash_list を渡したとき adapter.annotate に正しく転送されることを確認する。"""
    image_paths = [str(test_image_path)]
    model_ids = ["openai/gpt-4o"]
    phash_list = ["aabbccdd11223344"]

    logic.execute_annotation(image_paths, model_ids, phash_list=phash_list)

    call_kwargs = mock_adapter.annotate.call_args.kwargs
    assert call_kwargs["phash_list"] == phash_list


# ---- _load_images: FileNotFoundError ----


@pytest.mark.unit
def test_load_images_raises_file_not_found_for_missing_path(logic: AnnotationRunner) -> None:
    """存在しないパスを渡すと FileNotFoundError が raise されることを確認する。"""
    nonexistent = "/nonexistent/path/to/image.png"

    with pytest.raises(FileNotFoundError, match="画像ファイルが見つかりません"):
        logic.execute_annotation([nonexistent], ["some-model"])


# ---- _load_images: ValueError（壊れたファイル）----


@pytest.mark.unit
def test_load_images_raises_value_error_for_corrupt_file(logic: AnnotationRunner, tmp_path: Path) -> None:
    """壊れたファイルを渡すと ValueError が raise されることを確認する。"""
    # 無効な画像データのファイルを作成
    corrupt_file = tmp_path / "corrupt.png"
    corrupt_file.write_bytes(b"this is not a valid image content at all")

    with pytest.raises(ValueError, match="画像読み込みエラー"):
        logic.execute_annotation([str(corrupt_file)], ["some-model"])


# ---- adapter.annotate が Exception → re-raise ----


@pytest.mark.unit
def test_execute_annotation_reraises_adapter_exception(
    logic: AnnotationRunner, mock_adapter: MagicMock, test_image_path: Path
) -> None:
    """adapter.annotate が Exception を raise すると同一例外が re-raise されることを確認する。"""
    mock_adapter.annotate.side_effect = RuntimeError("test error from adapter")
    image_paths = [str(test_image_path)]
    model_ids = ["openai/gpt-4o"]

    with pytest.raises(RuntimeError, match="test error from adapter"):
        logic.execute_annotation(image_paths, model_ids)


# ---- 空の image_paths ----


@pytest.mark.unit
def test_execute_annotation_with_empty_image_paths(
    logic: AnnotationRunner, mock_adapter: MagicMock
) -> None:
    """空の image_paths を渡しても例外なく結果が返ることを確認する。"""
    mock_adapter.annotate.return_value = {}

    result = logic.execute_annotation([], ["some-model"])

    assert result == {}
    # 空リストで annotate が呼ばれること
    mock_adapter.annotate.assert_called_once()
    call_kwargs = mock_adapter.annotate.call_args.kwargs
    assert call_kwargs["images"] == []


# ---- 複数画像 ----


@pytest.mark.unit
def test_execute_annotation_with_multiple_images(
    logic: AnnotationRunner, mock_adapter: MagicMock, test_image_dir: Path
) -> None:
    """複数の画像パスを渡すと全て読み込まれて adapter.annotate に渡されることを確認する。"""
    image_paths_p = sorted(test_image_dir.glob("*.webp"))[:3]
    if len(image_paths_p) < 3:
        pytest.skip("テスト用画像が3枚未満です")

    image_paths = [str(p) for p in image_paths_p]
    mock_adapter.annotate.return_value = {}

    logic.execute_annotation(image_paths, ["some-model"])

    call_kwargs = mock_adapter.annotate.call_args.kwargs
    assert len(call_kwargs["images"]) == 3
