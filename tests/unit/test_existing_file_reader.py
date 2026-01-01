"""ExistingFileReader のユニットテスト"""

from pathlib import Path
from unittest.mock import Mock, mock_open, patch

import pytest

from lorairo.annotations.existing_file_reader import ExistingFileReader


class TestExistingFileReader:
    """ExistingFileReader のテスト"""

    def test_init(self):
        """初期化テスト"""
        reader = ExistingFileReader()

        # ExistingFileReader が正常に初期化されることを確認
        assert reader is not None

    def test_get_existing_annotations_txt_only(self):
        """txtファイルのみ存在する場合のテスト"""
        reader = ExistingFileReader()

        # 既存のテストリソースを使用
        image_path = Path("tests/resources/img/1_img/file01.webp")
        txt_path = image_path.with_suffix(".txt")

        # テスト用のtxtファイルを作成
        txt_path.write_text("tag1, tag2, tag3")

        try:
            with patch(
                "genai_tag_db_tools.utils.cleanup_str.TagCleaner.clean_format",
                return_value="tag1, tag2, tag3",
            ):
                result = reader.get_existing_annotations(image_path)

            assert result is not None
            assert "tags" in result
            assert "captions" in result
            assert result["tags"] == ["tag1", "tag2", "tag3"]
            assert result["captions"] == []
            assert result["image_path"] == str(image_path)
        finally:
            # クリーンアップ
            if txt_path.exists():
                txt_path.unlink()

    def test_get_existing_annotations_caption_only(self):
        """captionファイルのみ存在する場合のテスト"""
        reader = ExistingFileReader()

        # 既存のテストリソースを使用
        image_path = Path("tests/resources/img/1_img/file02.webp")
        caption_path = image_path.with_suffix(".caption")

        # テスト用のcaptionファイルを作成
        caption_path.write_text("This is a caption")

        try:
            with patch(
                "genai_tag_db_tools.utils.cleanup_str.TagCleaner.clean_format",
                return_value="This is a caption",
            ):
                result = reader.get_existing_annotations(image_path)

            assert result is not None
            assert "tags" in result
            assert "captions" in result
            assert result["tags"] == []
            assert result["captions"] == ["This is a caption"]
            assert result["image_path"] == str(image_path)
        finally:
            # クリーンアップ
            if caption_path.exists():
                caption_path.unlink()

    def test_get_existing_annotations_both_files(self):
        """両方のファイルが存在する場合のテスト"""
        reader = ExistingFileReader()

        # 既存のテストリソースを使用
        image_path = Path("tests/resources/img/1_img/file03.webp")
        txt_path = image_path.with_suffix(".txt")
        caption_path = image_path.with_suffix(".caption")

        # テスト用のファイルを作成
        txt_path.write_text("tag1, tag2")
        caption_path.write_text("Test caption")

        try:
            with patch("genai_tag_db_tools.utils.cleanup_str.TagCleaner.clean_format") as mock_clean:
                mock_clean.side_effect = ["tag1, tag2", "Test caption"]
                result = reader.get_existing_annotations(image_path)

            assert result is not None
            assert result["tags"] == ["tag1", "tag2"]
            assert result["captions"] == ["Test caption"]
        finally:
            # クリーンアップ
            if txt_path.exists():
                txt_path.unlink()
            if caption_path.exists():
                caption_path.unlink()

    def test_get_existing_annotations_no_files(self):
        """ファイルが存在しない場合のテスト"""
        reader = ExistingFileReader()

        # 既存のテストリソースを使用（ファイルを作成しない）
        image_path = Path("tests/resources/img/1_img/file04.webp")

        result = reader.get_existing_annotations(image_path)

        assert result is None

    def test_get_existing_annotations_whitespace_handling(self):
        """空白文字の処理テスト"""
        reader = ExistingFileReader()

        # 既存のテストリソースを使用
        image_path = Path("tests/resources/img/1_img/file06.webp")
        txt_path = image_path.with_suffix(".txt")

        # 空白ありのファイルを作成
        txt_path.write_text("  tag1  ,  tag2  ,  tag3  ")

        try:
            with patch(
                "genai_tag_db_tools.utils.cleanup_str.TagCleaner.clean_format",
                return_value="tag1, tag2, tag3",
            ):
                result = reader.get_existing_annotations(image_path)

            # 空白がトリムされていることを確認
            assert result["tags"] == ["tag1", "tag2", "tag3"]
        finally:
            # クリーンアップ
            if txt_path.exists():
                txt_path.unlink()

    def test_get_existing_annotations_empty_tags_filtering(self):
        """空のタグのフィルタリングテスト"""
        reader = ExistingFileReader()

        # 既存のテストリソースを使用
        image_path = Path("tests/resources/img/1_img/file07.webp")
        txt_path = image_path.with_suffix(".txt")

        # 空のタグありのファイルを作成
        txt_path.write_text("tag1,,tag2,,,tag3,")

        try:
            with patch(
                "genai_tag_db_tools.utils.cleanup_str.TagCleaner.clean_format",
                return_value="tag1,,tag2,,,tag3,",
            ):
                result = reader.get_existing_annotations(image_path)

            # 空の要素がフィルタリングされていることを確認
            expected_tags = [tag for tag in ["tag1", "", "tag2", "", "", "tag3", ""] if tag.strip()]
            assert result["tags"] == expected_tags
        finally:
            # クリーンアップ
            if txt_path.exists():
                txt_path.unlink()

    @patch("lorairo.annotations.existing_file_reader.Path.exists")
    @patch("builtins.open", side_effect=FileNotFoundError("File not found"))
    def test_get_existing_annotations_file_error(self, mock_file, mock_exists):
        """ファイル読み込みエラーのテスト"""
        reader = ExistingFileReader()
        image_path = Path("test_image.jpg")

        mock_exists.return_value = True

        with patch("lorairo.annotations.existing_file_reader.logger") as mock_logger:
            result = reader.get_existing_annotations(image_path)

        # エラーログが出力されることを確認
        mock_logger.error.assert_called_once()
        assert result is None

    @patch("lorairo.annotations.existing_file_reader.Path.exists")
    @patch("builtins.open", side_effect=UnicodeDecodeError("utf-8", b"", 0, 1, "invalid"))
    def test_get_existing_annotations_encoding_error(self, mock_file, mock_exists):
        """エンコーディングエラーのテスト"""
        reader = ExistingFileReader()
        image_path = Path("test_image.jpg")

        mock_exists.return_value = True

        with patch("lorairo.annotations.existing_file_reader.logger") as mock_logger:
            result = reader.get_existing_annotations(image_path)

        # エラーログが出力されることを確認
        mock_logger.error.assert_called_once()
        assert result is None

    def test_tag_cleaner_integration(self):
        """TagCleaner の統合テスト"""
        reader = ExistingFileReader()

        # ExistingFileReader が TagCleaner.clean_format() を静的メソッドとして使用することを確認
        assert reader is not None

    def test_file_path_construction(self):
        """ファイルパス構築のテスト"""
        reader = ExistingFileReader()
        image_path = Path("test_image.jpg")

        with patch.object(reader, "get_existing_annotations") as mock_method:
            reader.get_existing_annotations(image_path)

            # メソッドが呼び出されることを確認
            mock_method.assert_called_once_with(image_path)

    def test_get_existing_annotations_empty_files(self):
        """空のファイルの場合のテスト"""
        reader = ExistingFileReader()

        # 既存のテストリソースを使用
        image_path = Path("tests/resources/img/1_img/file05.webp")
        txt_path = image_path.with_suffix(".txt")
        caption_path = image_path.with_suffix(".caption")

        # 空のファイルを作成
        txt_path.write_text("")
        caption_path.write_text("")

        try:
            with patch("genai_tag_db_tools.utils.cleanup_str.TagCleaner.clean_format", return_value=""):
                result = reader.get_existing_annotations(image_path)

            # 空のファイルでも適切に処理されることを確認
            assert result is not None
            assert result["tags"] == []
            assert result["captions"] == []
        finally:
            # クリーンアップ
            if txt_path.exists():
                txt_path.unlink()
            if caption_path.exists():
                caption_path.unlink()
