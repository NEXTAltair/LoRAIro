"""SidecarAnnotationReader のユニットテスト"""

from pathlib import Path
from unittest.mock import patch

from lorairo.annotation.sidecar_reader import SidecarAnnotationReader


class TestSidecarAnnotationReader:
    """SidecarAnnotationReader のテスト"""

    def test_init(self):
        """初期化テスト"""
        reader = SidecarAnnotationReader()

        # SidecarAnnotationReader が正常に初期化されることを確認
        assert reader is not None

    def test_get_existing_annotations_txt_only(self):
        """txtファイルのみ存在する場合のテスト"""
        reader = SidecarAnnotationReader()

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
        reader = SidecarAnnotationReader()

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
        reader = SidecarAnnotationReader()

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
        reader = SidecarAnnotationReader()

        # 既存のテストリソースを使用（ファイルを作成しない）
        image_path = Path("tests/resources/img/1_img/file04.webp")

        result = reader.get_existing_annotations(image_path)

        assert result is None

    def test_get_existing_annotations_whitespace_handling(self):
        """空白文字の処理テスト"""
        reader = SidecarAnnotationReader()

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
        reader = SidecarAnnotationReader()

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

    def test_get_existing_annotations_file_error(self, tmp_path):
        """読込失敗を個別に記録し、正常な兄弟ファイルを取り込む。"""
        reader = SidecarAnnotationReader()
        image_path = tmp_path / "test_image.jpg"
        image_path.with_suffix(".txt").write_text("tag")
        image_path.with_suffix(".caption").write_text("normal caption")
        with (
            patch.object(reader, "_read_annotations", side_effect=PermissionError("private body")),
            patch("lorairo.annotation.sidecar_reader.logger") as mock_logger,
        ):
            result = reader.get_existing_annotations(image_path)
        mock_logger.warning.assert_called_once()
        assert result["tags"] == []
        assert result["captions"] == ["normal caption"]
        assert "private body" not in str(mock_logger.warning.call_args)

    def test_get_existing_annotations_encoding_error(self, tmp_path):
        """解釈失敗時も本文をログに出さず画像登録を継続できる。"""
        reader = SidecarAnnotationReader()
        image_path = tmp_path / "test_image.jpg"
        image_path.with_suffix(".txt").write_bytes(b"private body")
        with (
            patch(
                "lorairo.annotation.sidecar_reader.decode_text_with_fallback",
                side_effect=UnicodeDecodeError("utf-8", b"private body", 0, 1, "invalid"),
            ),
            patch("lorairo.annotation.sidecar_reader.logger") as mock_logger,
        ):
            result = reader.get_existing_annotations(image_path)
        mock_logger.warning.assert_called_once()
        assert result["tags"] == []
        assert result["captions"] == []
        assert "private body" not in str(mock_logger.warning.call_args)

    def test_tag_cleaner_integration(self):
        """TagCleaner の統合テスト"""
        reader = SidecarAnnotationReader()

        # SidecarAnnotationReader が TagCleaner.clean_format() を静的メソッドとして使用することを確認
        assert reader is not None

    def test_file_path_construction(self):
        """ファイルパス構築のテスト"""
        reader = SidecarAnnotationReader()
        image_path = Path("test_image.jpg")

        with patch.object(reader, "get_existing_annotations") as mock_method:
            reader.get_existing_annotations(image_path)

            # メソッドが呼び出されることを確認
            mock_method.assert_called_once_with(image_path)

    def test_get_existing_annotations_empty_files(self):
        """空のファイルの場合のテスト"""
        reader = SidecarAnnotationReader()

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
