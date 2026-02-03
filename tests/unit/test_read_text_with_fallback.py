"""read_text_with_fallback ユーティリティ関数のテスト。"""

import pytest

from lorairo.utils.tools import read_text_with_fallback


class TestReadTextWithFallback:
    """read_text_with_fallback のテストケース。"""

    def test_utf8_file_reads_normally(self, tmp_path: pytest.TempPathFactory) -> None:
        """UTF-8ファイルは通常通り読み込める。"""
        f = tmp_path / "test.txt"
        f.write_text("hello, world", encoding="utf-8")
        assert read_text_with_fallback(f) == "hello, world"

    def test_utf8_japanese_reads_normally(self, tmp_path: pytest.TempPathFactory) -> None:
        """UTF-8の日本語テキストを正常に読み込める。"""
        f = tmp_path / "test.txt"
        content = "1girl, 黒髪, 制服"
        f.write_text(content, encoding="utf-8")
        assert read_text_with_fallback(f) == content

    def test_shift_jis_fallback(self, tmp_path: pytest.TempPathFactory) -> None:
        """Shift_JISファイルをフォールバックで読み込める。"""
        f = tmp_path / "test.txt"
        content = "1girl, 黒髪, 制服"
        f.write_bytes(content.encode("shift_jis"))
        result = read_text_with_fallback(f)
        assert "黒髪" in result

    def test_euc_jp_fallback(self, tmp_path: pytest.TempPathFactory) -> None:
        """EUC-JPファイルをフォールバックで読み込める。"""
        f = tmp_path / "test.txt"
        content = "1girl, 東京タワー"
        f.write_bytes(content.encode("euc-jp"))
        result = read_text_with_fallback(f)
        assert "東京タワー" in result

    def test_latin1_fallback(self, tmp_path: pytest.TempPathFactory) -> None:
        """Latin-1ファイルをフォールバックで読み込める。"""
        f = tmp_path / "test.txt"
        content = "café résumé"
        f.write_bytes(content.encode("latin-1"))
        result = read_text_with_fallback(f)
        assert "café" in result

    def test_file_not_found_raises(self, tmp_path: pytest.TempPathFactory) -> None:
        """存在しないファイルはFileNotFoundErrorを送出する。"""
        f = tmp_path / "nonexistent.txt"
        with pytest.raises(FileNotFoundError):
            read_text_with_fallback(f)

    def test_empty_file(self, tmp_path: pytest.TempPathFactory) -> None:
        """空ファイルは空文字列を返す。"""
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")
        assert read_text_with_fallback(f) == ""

    def test_custom_encodings(self, tmp_path: pytest.TempPathFactory) -> None:
        """カスタムエンコーディングリストを指定できる。"""
        f = tmp_path / "test.txt"
        content = "テスト"
        f.write_bytes(content.encode("shift_jis"))
        # UTF-8のみ指定 → 失敗
        with pytest.raises(UnicodeDecodeError):
            read_text_with_fallback(f, encodings=("utf-8",))
        # Shift_JIS含む → 成功
        result = read_text_with_fallback(f, encodings=("utf-8", "shift_jis"))
        assert result == content
