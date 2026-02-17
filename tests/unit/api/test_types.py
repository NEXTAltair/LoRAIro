"""API types テスト。"""

from datetime import datetime
from pathlib import Path

import pytest

from lorairo.api.types import (
    AnnotationResult,
    DuplicateInfo,
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
