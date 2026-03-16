"""BatchImageMatcherのユニットテスト。"""

from unittest.mock import MagicMock

import pytest

from lorairo.services.batch_image_matcher import BatchImageMatcher, ImageMatchResult


class TestExtractStem:
    """BatchImageMatcher.extract_stem()のテスト。"""

    @pytest.mark.parametrize(
        ("custom_id", "expected"),
        [
            ("0262_1227", "0262_1227"),
            ("H:\\lora\\images\\0262_1227", "0262_1227"),
            ("H:\\lora\\images\\0262_1227.jpg", "0262_1227"),
            ("/data/images/0262_1227", "0262_1227"),
            ("/data/images/0262_1227.png", "0262_1227"),
            ("images/0262_1227", "0262_1227"),
            ("simple_name", "simple_name"),
            ("path/to/deep/nested/image_001", "image_001"),
            ("C:\\Users\\user\\Desktop\\test.jpg", "test"),
        ],
        ids=[
            "bare-stem",
            "windows-path-no-ext",
            "windows-path-with-ext",
            "unix-path-no-ext",
            "unix-path-with-ext",
            "relative-path",
            "simple-name",
            "deep-nested",
            "windows-full-path",
        ],
    )
    def test_extract_stem(self, custom_id: str, expected: str) -> None:
        """stem抽出が正しく動作する。"""
        assert BatchImageMatcher.extract_stem(custom_id) == expected


class TestBatchImageMatcher:
    """BatchImageMatcher.match_all()のテスト。"""

    @pytest.fixture()
    def mock_repository(self) -> MagicMock:
        """モックリポジトリ。"""
        repo = MagicMock()
        repo.get_all_image_filename_index.return_value = {
            "0262_1227": 1,
            "0263_1228": 2,
            "0264_1229": 3,
        }
        return repo

    def test_all_matched(self, mock_repository: MagicMock) -> None:
        """全件マッチ。"""
        matcher = BatchImageMatcher(mock_repository)
        result = matcher.match_all(["0262_1227", "0263_1228", "0264_1229"])

        assert len(result.matched) == 3
        assert result.matched["0262_1227"] == 1
        assert result.matched["0263_1228"] == 2
        assert result.matched["0264_1229"] == 3
        assert result.unmatched == []

    def test_all_unmatched(self, mock_repository: MagicMock) -> None:
        """全件アンマッチ。"""
        matcher = BatchImageMatcher(mock_repository)
        result = matcher.match_all(["unknown_001", "unknown_002"])

        assert result.matched == {}
        assert len(result.unmatched) == 2
        assert "unknown_001" in result.unmatched
        assert "unknown_002" in result.unmatched

    def test_partial_match(self, mock_repository: MagicMock) -> None:
        """部分マッチ。"""
        matcher = BatchImageMatcher(mock_repository)
        result = matcher.match_all(["0262_1227", "unknown_001", "0264_1229"])

        assert len(result.matched) == 2
        assert result.matched["0262_1227"] == 1
        assert result.matched["0264_1229"] == 3
        assert result.unmatched == ["unknown_001"]

    def test_windows_path_custom_ids(self, mock_repository: MagicMock) -> None:
        """Windowsパス形式のcustom_idが正しくマッチする。"""
        matcher = BatchImageMatcher(mock_repository)
        result = matcher.match_all([
            "H:\\lora\\images\\0262_1227",
            "H:\\lora\\images\\0263_1228.jpg",
        ])

        assert len(result.matched) == 2
        assert result.matched["H:\\lora\\images\\0262_1227"] == 1

    def test_empty_custom_ids(self, mock_repository: MagicMock) -> None:
        """空リスト。"""
        matcher = BatchImageMatcher(mock_repository)
        result = matcher.match_all([])

        assert result.matched == {}
        assert result.unmatched == []

    def test_image_match_result_frozen(self) -> None:
        """ImageMatchResultはfrozen。"""
        result = ImageMatchResult(matched={"a": 1}, unmatched=["b"])
        with pytest.raises(AttributeError):
            result.matched = {}  # type: ignore[misc]
