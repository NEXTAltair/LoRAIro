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

    def test_normalize_tag_filter_strips_entries(self) -> None:
        """tag_filter の各要素は strip される。"""
        criteria = ExportCriteria(tag_filter=["  cat  ", " dog"])
        assert criteria.tag_filter == ["cat", "dog"]

    def test_normalize_tag_filter_removes_blank_entries(self) -> None:
        """tag_filter の空白要素は除外される。"""
        criteria = ExportCriteria(tag_filter=["cat", "", "  ", "dog"])
        assert criteria.tag_filter == ["cat", "dog"]

    def test_normalize_tag_filter_all_blank_becomes_none(self) -> None:
        """tag_filter が全て空白のみなら None に正規化。"""
        criteria = ExportCriteria(tag_filter=["", "  "])
        assert criteria.tag_filter is None

    def test_normalize_excluded_tags_removes_blank_entries(self) -> None:
        """excluded_tags の空白要素は除外される（_apply_tag_filter で LIKE '%%' 事故防止）。"""
        criteria = ExportCriteria(excluded_tags=["nsfw", "", "  "])
        assert criteria.excluded_tags == ["nsfw"]

    def test_normalize_excluded_tags_all_blank_becomes_none(self) -> None:
        """excluded_tags が全て空白のみなら None に正規化。"""
        criteria = ExportCriteria(excluded_tags=["", "  "])
        assert criteria.excluded_tags is None

    def test_normalize_caption_strips_value(self) -> None:
        """caption は strip される。"""
        criteria = ExportCriteria(caption="  a girl  ")
        assert criteria.caption == "a girl"

    def test_normalize_caption_blank_becomes_none(self) -> None:
        """空白のみの caption は None に正規化。"""
        criteria = ExportCriteria(caption="   ")
        assert criteria.caption is None

    def test_normalize_manual_rating_uppercases(self) -> None:
        """manual_rating は DB 側の完全一致（PG/PG-13/...）に合わせて大文字化。"""
        criteria = ExportCriteria(manual_rating="pg")
        assert criteria.manual_rating == "PG"

    def test_normalize_manual_rating_strips_and_uppercases(self) -> None:
        """manual_rating は strip + 大文字化される。"""
        criteria = ExportCriteria(manual_rating="  pg-13  ")
        assert criteria.manual_rating == "PG-13"

    def test_normalize_manual_rating_blank_becomes_none(self) -> None:
        """空白のみの manual_rating は None に正規化。"""
        criteria = ExportCriteria(manual_rating="   ")
        assert criteria.manual_rating is None

    def test_normalize_ai_rating_uppercases_unrated(self) -> None:
        """ai_rating="unrated" は DB の UNRATED 分岐に合わせて大文字化。"""
        criteria = ExportCriteria(ai_rating="unrated")
        assert criteria.ai_rating == "UNRATED"

    def test_normalize_ai_rating_strips_and_uppercases(self) -> None:
        """ai_rating は strip + 大文字化される。"""
        criteria = ExportCriteria(ai_rating=" r ")
        assert criteria.ai_rating == "R"

    def test_normalize_ai_rating_blank_becomes_none(self) -> None:
        """空白のみの ai_rating は None に正規化。"""
        criteria = ExportCriteria(ai_rating="   ")
        assert criteria.ai_rating is None
