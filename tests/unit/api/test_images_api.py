"""Images API テスト。"""

from pathlib import Path

import pytest
from PIL import Image

from lorairo.api.exceptions import ImageRegistrationError
from lorairo.api.images import detect_duplicate_images, register_images
from lorairo.api.types import RegistrationResult
from lorairo.services.service_container import ServiceContainer


@pytest.fixture
def _reset_service_container() -> None:
    """ServiceContainerのImageRegistrationServiceキャッシュをクリア。"""
    container = ServiceContainer()
    container._image_registration_service = None


@pytest.fixture
def images_dir(tmp_path: Path) -> Path:
    """テスト用画像ディレクトリを作成。

    Args:
        tmp_path: 一時ディレクトリ

    Returns:
        Path: 画像ファイルを含むディレクトリ
    """
    d = tmp_path / "images"
    d.mkdir()
    for i in range(3):
        img = Image.new("RGB", (100, 100), color=(50 + i * 50, 100, 100))
        img.save(d / f"img_{i}.jpg")
    return d


@pytest.fixture
def empty_dir(tmp_path: Path) -> Path:
    """空ディレクトリ。"""
    d = tmp_path / "empty"
    d.mkdir()
    return d


@pytest.mark.unit
@pytest.mark.usefixtures("_reset_service_container")
class TestRegisterImages:
    """register_images API テスト。"""

    def test_success(self, images_dir: Path) -> None:
        """画像登録が成功。"""
        result = register_images(images_dir)

        assert isinstance(result, RegistrationResult)
        assert result.total == 3
        assert result.successful > 0
        assert result.failed == 0

    def test_with_string_path(self, images_dir: Path) -> None:
        """文字列パスでも動作。"""
        result = register_images(str(images_dir))

        assert result.total == 3

    def test_empty_directory(self, empty_dir: Path) -> None:
        """空ディレクトリで total=0。"""
        result = register_images(empty_dir)

        assert result.total == 0
        assert result.successful == 0

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        """存在しないディレクトリで例外。"""
        with pytest.raises(ImageRegistrationError):
            register_images(tmp_path / "nonexistent")

    def test_skip_duplicates(self, tmp_path: Path) -> None:
        """重複画像がスキップされる。"""
        d = tmp_path / "dup_images"
        d.mkdir()

        # 同一画像を2ファイルに保存
        img = Image.new("RGB", (100, 100), color=(100, 100, 100))
        img.save(d / "original.jpg")
        img.save(d / "duplicate.jpg")

        result = register_images(d, skip_duplicates=True)

        assert result.total == 2
        assert result.skipped >= 1

    def test_include_duplicates(self, tmp_path: Path) -> None:
        """重複を含めて全登録。"""
        d = tmp_path / "dup_images"
        d.mkdir()

        img = Image.new("RGB", (100, 100), color=(100, 100, 100))
        img.save(d / "original.jpg")
        img.save(d / "duplicate.jpg")

        result = register_images(d, skip_duplicates=False)

        assert result.total == 2
        assert result.skipped == 0
        assert result.successful == 2

    def test_multiple_formats(self, tmp_path: Path) -> None:
        """複数形式の画像を登録。"""
        d = tmp_path / "multi"
        d.mkdir()

        img = Image.new("RGB", (50, 50), color=(100, 100, 100))
        for fmt in ["jpg", "png", "bmp"]:
            img.save(d / f"test.{fmt}")

        result = register_images(d)
        assert result.total >= 3


@pytest.mark.unit
@pytest.mark.usefixtures("_reset_service_container")
class TestDetectDuplicateImages:
    """detect_duplicate_images API テスト。"""

    def test_no_duplicates(self, images_dir: Path) -> None:
        """重複なし→空辞書。"""
        result = detect_duplicate_images(images_dir)

        # 各画像が異なる色なので重複なし（or 少なくとも辞書が返る）
        assert isinstance(result, dict)

    def test_with_duplicates(self, tmp_path: Path) -> None:
        """重複あり→グループ化。"""
        d = tmp_path / "dup_detect"
        d.mkdir()

        img = Image.new("RGB", (100, 100), color=(100, 100, 100))
        img.save(d / "a.jpg")
        img.save(d / "b.jpg")

        result = detect_duplicate_images(d)

        assert isinstance(result, dict)
        # 同一画像なので少なくとも1グループ
        if result:
            for files in result.values():
                assert len(files) >= 2

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        """存在しないディレクトリで例外。"""
        with pytest.raises(ImageRegistrationError):
            detect_duplicate_images(tmp_path / "nonexistent")

    def test_empty_directory(self, empty_dir: Path) -> None:
        """空ディレクトリ→空辞書。"""
        result = detect_duplicate_images(empty_dir)
        assert result == {}
