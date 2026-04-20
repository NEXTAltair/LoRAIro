"""calculate_phash ユーティリティ関数のエッジケーステスト。"""

from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from lorairo.utils.tools import calculate_phash


class TestCalculatePhash:
    def test_empty_file_raises_value_error(self, tmp_path: Path) -> None:
        """0バイトファイルはValueErrorを送出する。"""
        f = tmp_path / "empty.png"
        f.write_bytes(b"")
        with pytest.raises(ValueError, match="破損"):
            calculate_phash(f)

    def test_rgba_image_is_converted(self, tmp_path: Path) -> None:
        """RGBAモード画像はRGBに変換されてハッシュ計算される。"""
        f = tmp_path / "rgba.png"
        img = Image.new("RGBA", (64, 64), (255, 0, 0, 128))
        img.save(f)
        result = calculate_phash(f)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_p_mode_image_is_converted(self, tmp_path: Path) -> None:
        """PaletteモードはRGBに変換されてハッシュ計算される。"""
        f = tmp_path / "palette.png"
        img = Image.new("P", (64, 64))
        img.save(f)
        result = calculate_phash(f)
        assert isinstance(result, str)

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        """存在しないファイルはFileNotFoundErrorを送出する。"""
        f = tmp_path / "nonexistent.png"
        with pytest.raises(FileNotFoundError):
            calculate_phash(f)

    def test_corrupted_file_raises_value_error(self, tmp_path: Path) -> None:
        """破損ファイルはValueErrorを送出する。"""
        f = tmp_path / "corrupted.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        with pytest.raises(ValueError, match="破損"):
            calculate_phash(f)

    def test_image_open_file_not_found_reraises(self, tmp_path: Path) -> None:
        """Image.openがFileNotFoundErrorを送出した場合、そのまま再送出する。"""
        f = tmp_path / "test.png"
        img = Image.new("RGB", (64, 64))
        img.save(f)

        with patch("lorairo.utils.tools.Image.open", side_effect=FileNotFoundError("file gone")):
            with pytest.raises(FileNotFoundError):
                calculate_phash(f)
