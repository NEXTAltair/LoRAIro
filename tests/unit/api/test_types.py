"""API types テスト。"""

from datetime import datetime
from pathlib import Path

import pytest

from lorairo.api.types import (
    AnnotationResult,
    DuplicateInfo,
    ExportCriteria,
    ExportResult,
    ProjectInfo,
    RegistrationResult,
    TagInfo,
    TagSearchResult,
)


@pytest.mark.unit
class TestProjectInfo:
    """ProjectInfo テスト。"""

    def test_creation(self, tmp_path: Path) -> None:
        """正常に生成できる。"""
        info = ProjectInfo(
            name="test",
            path=tmp_path,
            created=datetime.now(),
            description="desc",
            image_count=10,
        )
        assert info.name == "test"
        assert info.image_count == 10

    def test_optional_description(self, tmp_path: Path) -> None:
        """description は省略可能。"""
        info = ProjectInfo(
            name="test",
            path=tmp_path,
            created=datetime.now(),
            image_count=0,
        )
        assert info.description is None


@pytest.mark.unit
class TestRegistrationResult:
    """RegistrationResult テスト。"""

    def test_creation(self) -> None:
        """正常に生成できる。"""
        result = RegistrationResult(
            total=10,
            successful=8,
            failed=1,
            skipped=1,
        )
        assert result.total == 10
        assert result.successful == 8
        assert result.error_details is None

    def test_with_error_details(self) -> None:
        """エラー詳細を含めて生成。"""
        result = RegistrationResult(
            total=5,
            successful=3,
            failed=2,
            skipped=0,
            error_details=["error1", "error2"],
        )
        assert len(result.error_details) == 2


@pytest.mark.unit
class TestAnnotationResult:
    """AnnotationResult テスト。"""

    def test_creation(self) -> None:
        """正常に生成できる。"""
        result = AnnotationResult(
            image_count=5,
            successful_annotations=3,
            failed_annotations=2,
            results=None,
        )
        assert result.image_count == 5
        assert result.results is None


@pytest.mark.unit
class TestExportResult:
    """ExportResult テスト。"""

    def test_creation(self, tmp_path: Path) -> None:
        """正常に生成できる。"""
        result = ExportResult(
            output_path=tmp_path,
            file_count=10,
            total_size=1024,
            format_type="txt",
            resolution=512,
        )
        assert result.file_count == 10
        assert result.format_type == "txt"


@pytest.mark.unit
class TestDuplicateInfo:
    """DuplicateInfo テスト。"""

    def test_creation(self) -> None:
        """正常に生成できる。"""
        info = DuplicateInfo(
            file_path=Path("/a.jpg"),
            existing_id=42,
            similarity=1.0,
        )
        assert info.file_path == Path("/a.jpg")
        assert info.existing_id == 42
        assert info.similarity == 1.0


@pytest.mark.unit
class TestTagInfo:
    """TagInfo テスト。"""

    def test_creation(self) -> None:
        """正常に生成できる。"""
        info = TagInfo(name="cat", type_name="general", count=42)
        assert info.name == "cat"
        assert info.count == 42


@pytest.mark.unit
class TestTagSearchResult:
    """TagSearchResult テスト。"""

    def test_creation(self) -> None:
        """正常に生成できる。"""
        result = TagSearchResult(
            query="cat",
            matches=["cat", "catgirl"],
            count=2,
        )
        assert result.count == 2
        assert result.matches[0] == "cat"


@pytest.mark.unit
class TestExportCriteria:
    """ExportCriteria テスト。"""

    def test_has_any_filter_empty(self) -> None:
        """フィルタ条件なし → False。"""
        criteria = ExportCriteria()
        assert criteria.has_any_filter() is False

    def test_has_any_filter_with_tag_filter(self) -> None:
        """tag_filter 指定 → True。"""
        criteria = ExportCriteria(tag_filter=["cat"])
        assert criteria.has_any_filter() is True

    def test_has_any_filter_with_excluded_tags(self) -> None:
        """excluded_tags 指定 → True。"""
        criteria = ExportCriteria(excluded_tags=["nsfw"])
        assert criteria.has_any_filter() is True

    def test_has_any_filter_with_caption(self) -> None:
        """caption 指定 → True。"""
        criteria = ExportCriteria(caption="a girl")
        assert criteria.has_any_filter() is True

    def test_has_any_filter_with_manual_rating(self) -> None:
        """manual_rating 指定 → True。"""
        criteria = ExportCriteria(manual_rating="PG")
        assert criteria.has_any_filter() is True

    def test_has_any_filter_with_ai_rating(self) -> None:
        """ai_rating 指定 → True。"""
        criteria = ExportCriteria(ai_rating="PG-13")
        assert criteria.has_any_filter() is True

    def test_has_any_filter_with_score_min(self) -> None:
        """score_min 指定 → True（0.0 でも有効）。"""
        criteria = ExportCriteria(score_min=0.0)
        assert criteria.has_any_filter() is True

    def test_has_any_filter_with_score_max(self) -> None:
        """score_max 指定 → True。"""
        criteria = ExportCriteria(score_max=8.0)
        assert criteria.has_any_filter() is True

    def test_has_any_filter_include_nsfw_alone_is_false(self) -> None:
        """include_nsfw のみはフィルタとして扱わない → False。"""
        criteria = ExportCriteria(include_nsfw=True)
        assert criteria.has_any_filter() is False

    def test_has_any_filter_empty_tag_filter_is_false(self) -> None:
        """空リストの tag_filter はフィルタなしと同じ → False。"""
        criteria = ExportCriteria(tag_filter=[])
        assert criteria.has_any_filter() is False

    def test_has_any_filter_empty_caption_string_is_false(self) -> None:
        """空文字列の caption はフィルタとして無効 → False。"""
        criteria = ExportCriteria(caption="")
        assert criteria.has_any_filter() is False

    def test_has_any_filter_empty_manual_rating_string_is_false(self) -> None:
        """空文字列の manual_rating はフィルタとして無効 → False。"""
        criteria = ExportCriteria(manual_rating="")
        assert criteria.has_any_filter() is False

    def test_has_any_filter_empty_ai_rating_string_is_false(self) -> None:
        """空文字列の ai_rating はフィルタとして無効 → False。"""
        criteria = ExportCriteria(ai_rating="")
        assert criteria.has_any_filter() is False

    def test_has_any_filter_score_min_zero_is_true(self) -> None:
        """score_min=0.0 は有効なフィルタ → True（falsy だが is not None で判定）。"""
        criteria = ExportCriteria(score_min=0.0)
        assert criteria.has_any_filter() is True

    def test_has_any_filter_tag_filter_with_only_empty_string_is_false(self) -> None:
        """tag_filter=[""] はリスト非空だが有効要素なし → False。"""
        criteria = ExportCriteria(tag_filter=[""])
        assert criteria.has_any_filter() is False

    def test_has_any_filter_tag_filter_with_only_whitespace_is_false(self) -> None:
        """tag_filter=["   "] は空白のみで有効要素なし → False。"""
        criteria = ExportCriteria(tag_filter=["   "])
        assert criteria.has_any_filter() is False

    def test_has_any_filter_tag_filter_with_valid_and_blank_entries_is_true(self) -> None:
        """tag_filter=["cat", ""] は有効要素が1つでもあれば → True。"""
        criteria = ExportCriteria(tag_filter=["cat", ""])
        assert criteria.has_any_filter() is True

    def test_has_any_filter_excluded_tags_with_only_blank_is_false(self) -> None:
        """excluded_tags=["", " "] は有効要素なし → False。"""
        criteria = ExportCriteria(excluded_tags=["", " "])
        assert criteria.has_any_filter() is False

    def test_has_any_filter_whitespace_only_caption_is_false(self) -> None:
        """caption="   " は空白のみで無効 → False。"""
        criteria = ExportCriteria(caption="   ")
        assert criteria.has_any_filter() is False

    def test_has_any_filter_whitespace_only_manual_rating_is_false(self) -> None:
        """manual_rating="  " は空白のみで無効 → False。"""
        criteria = ExportCriteria(manual_rating="  ")
        assert criteria.has_any_filter() is False

    def test_has_any_filter_whitespace_only_ai_rating_is_false(self) -> None:
        """ai_rating=" " は空白のみで無効 → False。"""
        criteria = ExportCriteria(ai_rating=" ")
        assert criteria.has_any_filter() is False
