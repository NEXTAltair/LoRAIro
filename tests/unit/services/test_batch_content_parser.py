"""BatchContentParserのユニットテスト。"""

import pytest

from lorairo.services.batch_content_parser import BatchContentParser, ParsedAnnotationContent


class TestBatchContentParser:
    """BatchContentParser.parse()のテスト。"""

    # --- 標準フォーマット ---

    def test_standard_format_with_caption(self) -> None:
        """標準フォーマット: Tags + Caption。"""
        content = (
            "Tags: 1girl, solo, blue hair, school uniform\n\nCaption: A girl with blue hair standing alone."
        )
        result = BatchContentParser.parse(content)
        assert result.tags == ["1girl", "solo", "blue hair", "school uniform"]
        assert result.caption == "A girl with blue hair standing alone."

    def test_standard_format_without_caption(self) -> None:
        """標準フォーマット: Tagsのみ（Caption欠落）。"""
        content = "Tags: 1girl, solo, blue hair"
        result = BatchContentParser.parse(content)
        assert result.tags == ["1girl", "solo", "blue hair"]
        assert result.caption is None

    def test_standard_format_single_tag(self) -> None:
        """標準フォーマット: 1タグのみ。"""
        content = "Tags: 1girl\n\nCaption: A single character."
        result = BatchContentParser.parse(content)
        assert result.tags == ["1girl"]
        assert result.caption == "A single character."

    def test_standard_format_many_tags(self) -> None:
        """標準フォーマット: 多数タグ。"""
        tags = ", ".join([f"tag{i}" for i in range(50)])
        content = f"Tags: {tags}\n\nCaption: Many tags."
        result = BatchContentParser.parse(content)
        assert len(result.tags) == 50
        assert result.tags[0] == "tag0"
        assert result.tags[49] == "tag49"

    # --- Markdownボールドフォーマット ---

    def test_bold_format_with_caption(self) -> None:
        """Markdownボールドフォーマット: **Tags** + **Caption**。"""
        content = "**Tags**: 1girl, solo, red eyes\n\n**Caption**: A girl with red eyes."
        result = BatchContentParser.parse(content)
        assert result.tags == ["1girl", "solo", "red eyes"]
        assert result.caption == "A girl with red eyes."

    def test_bold_format_without_caption(self) -> None:
        """Markdownボールドフォーマット: Captionなし。"""
        content = "**Tags**: 1girl, solo"
        result = BatchContentParser.parse(content)
        assert result.tags == ["1girl", "solo"]
        assert result.caption is None

    # --- Markdownヘッダーフォーマット ---

    def test_header_format_with_bullet_tags(self) -> None:
        """Markdownヘッダーフォーマット: 箇条書きタグ。"""
        content = "### Tags\n- 1girl\n- solo\n- blue hair\n\n### Caption\nA girl with blue hair."
        result = BatchContentParser.parse(content)
        assert result.tags == ["1girl", "solo", "blue hair"]
        assert result.caption == "A girl with blue hair."

    def test_header_format_with_comma_tags(self) -> None:
        """Markdownヘッダーフォーマット: カンマ区切りタグ。"""
        content = "### Tags\n1girl, solo, blue hair\n\n### Caption\nDescription."
        result = BatchContentParser.parse(content)
        assert result.tags == ["1girl", "solo", "blue hair"]
        assert result.caption == "Description."

    def test_header_format_without_caption(self) -> None:
        """Markdownヘッダーフォーマット: Captionなし。"""
        content = "### Tags\n- 1girl\n- solo"
        result = BatchContentParser.parse(content)
        assert result.tags == ["1girl", "solo"]
        assert result.caption is None

    # --- エッジケース ---

    def test_tags_with_extra_whitespace(self) -> None:
        """タグ前後の余分な空白が除去される。"""
        content = "Tags:  1girl ,  solo ,  blue hair \n\nCaption: text"
        result = BatchContentParser.parse(content)
        assert result.tags == ["1girl", "solo", "blue hair"]

    def test_empty_tags_filtered(self) -> None:
        """空タグがフィルタされる。"""
        content = "Tags: 1girl,, solo, , blue hair\n\nCaption: text"
        result = BatchContentParser.parse(content)
        assert result.tags == ["1girl", "solo", "blue hair"]

    def test_frozen_dataclass(self) -> None:
        """ParsedAnnotationContentはfrozen。"""
        result = ParsedAnnotationContent(tags=["1girl"], caption="text")
        with pytest.raises(AttributeError):
            result.tags = []  # type: ignore[misc]

    # --- エラーケース ---

    def test_empty_content_raises_error(self) -> None:
        """空contentでValueError。"""
        with pytest.raises(ValueError, match="contentが空です"):
            BatchContentParser.parse("")

    def test_whitespace_only_content_raises_error(self) -> None:
        """空白のみcontentでValueError。"""
        with pytest.raises(ValueError, match="contentが空です"):
            BatchContentParser.parse("   \n\n  ")

    def test_no_tags_section_raises_error(self) -> None:
        """Tagsセクションなしでエラー。"""
        with pytest.raises(ValueError, match="タグセクションが見つかりません"):
            BatchContentParser.parse("Caption: some text here")

    def test_empty_tags_raises_error(self) -> None:
        """タグが全て空でエラー。"""
        with pytest.raises(ValueError, match="有効なタグが見つかりません"):
            BatchContentParser.parse("Tags: , , ,")


class TestBatchContentParserParametrized:
    """パラメトライズテスト。"""

    @pytest.mark.parametrize(
        ("content", "expected_tag_count", "expected_has_caption"),
        [
            ("Tags: a, b, c\n\nCaption: text", 3, True),
            ("**Tags**: a, b\n\n**Caption**: text", 2, True),
            ("### Tags\n- a\n- b\n\n### Caption\ntext", 2, True),
            ("Tags: a, b, c", 3, False),
            ("**Tags**: a", 1, False),
            ("### Tags\n- a\n- b", 2, False),
        ],
        ids=[
            "standard-with-caption",
            "bold-with-caption",
            "header-with-caption",
            "standard-no-caption",
            "bold-no-caption",
            "header-no-caption",
        ],
    )
    def test_format_variations(
        self, content: str, expected_tag_count: int, expected_has_caption: bool
    ) -> None:
        """各フォーマットのパース結果を検証。"""
        result = BatchContentParser.parse(content)
        assert len(result.tags) == expected_tag_count
        assert (result.caption is not None) == expected_has_caption
