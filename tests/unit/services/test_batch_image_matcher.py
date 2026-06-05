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
        result = matcher.match_all(
            [
                "H:\\lora\\images\\0262_1227",
                "H:\\lora\\images\\0263_1228.jpg",
            ]
        )

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


class TestBatchImageMatcherPhash:
    """ADR 0062: ``ph:{phash}:le:{long_edge}`` 形式 custom_id の pHash 照合テスト。"""

    @pytest.fixture()
    def mock_repository(self) -> MagicMock:
        repo = MagicMock()
        # (pHash, 長辺) 複合キー → image_id 群。同一 pHash aaaa が 1024 と 512 の 2 解像度で共存。
        repo.find_image_ids_by_phash_long_edge.return_value = {
            ("aaaaaaaaaaaaaaaa", 1024): [10],
            ("aaaaaaaaaaaaaaaa", 512): [11],
            ("bbbbbbbbbbbbbbbb", 768): [20],
        }
        repo.get_all_image_filename_index.return_value = {"0262_1227": 1}
        return repo

    def test_phash_custom_ids_matched_by_phash_and_long_edge(self, mock_repository: MagicMock) -> None:
        """pHash 完全一致かつ長辺解像度一致で image_id に解決される。"""
        matcher = BatchImageMatcher(mock_repository)
        result = matcher.match_all(["ph:aaaaaaaaaaaaaaaa:le:1024", "ph:bbbbbbbbbbbbbbbb:le:768"])

        assert result.matched == {
            "ph:aaaaaaaaaaaaaaaa:le:1024": 10,
            "ph:bbbbbbbbbbbbbbbb:le:768": 20,
        }
        assert result.unmatched == []
        mock_repository.find_image_ids_by_phash_long_edge.assert_called_once_with(
            {"aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"}
        )
        mock_repository.get_all_image_filename_index.assert_not_called()

    def test_phash_custom_id_disambiguates_same_phash_by_long_edge(
        self, mock_repository: MagicMock
    ) -> None:
        """Codex #646 P2: 同一 pHash・別解像度が DB に共存しても長辺で正しく解決する。"""
        matcher = BatchImageMatcher(mock_repository)
        result = matcher.match_all(["ph:aaaaaaaaaaaaaaaa:le:512", "ph:aaaaaaaaaaaaaaaa:le:1024"])

        # le:512 -> image_id 11、le:1024 -> image_id 10 と区別される。
        assert result.matched == {
            "ph:aaaaaaaaaaaaaaaa:le:512": 11,
            "ph:aaaaaaaaaaaaaaaa:le:1024": 10,
        }
        assert result.unmatched == []

    def test_phash_custom_id_unmatched_when_long_edge_absent(self, mock_repository: MagicMock) -> None:
        """pHash は一致するが長辺が DB に無い場合は誤マッチさせず unmatched。"""
        matcher = BatchImageMatcher(mock_repository)
        # aaaa は 1024/512 のみ存在。le:256 は無い。
        result = matcher.match_all(["ph:aaaaaaaaaaaaaaaa:le:256"])

        assert result.matched == {}
        assert result.unmatched == ["ph:aaaaaaaaaaaaaaaa:le:256"]

    def test_phash_custom_id_unmatched_when_phash_absent(self, mock_repository: MagicMock) -> None:
        """DB に無い pHash は unmatched になる。"""
        matcher = BatchImageMatcher(mock_repository)
        result = matcher.match_all(["ph:cccccccccccccccc:le:512"])

        assert result.matched == {}
        assert result.unmatched == ["ph:cccccccccccccccc:le:512"]

    def test_phash_custom_id_records_duplicate_materials_as_ambiguous(
        self, mock_repository: MagicMock
    ) -> None:
        """Codex #646 round3: 同一素材の重複登録は代表を matched、全件を ambiguous に残す。"""
        mock_repository.find_image_ids_by_phash_long_edge.return_value = {
            ("aaaaaaaaaaaaaaaa", 1024): [10, 30, 42],
        }
        matcher = BatchImageMatcher(mock_repository)
        result = matcher.match_all(["ph:aaaaaaaaaaaaaaaa:le:1024"])

        # 代表は昇順先頭。重複登録は ambiguous に保持され取りこぼさない。
        assert result.matched == {"ph:aaaaaaaaaaaaaaaa:le:1024": 10}
        assert result.ambiguous == {"ph:aaaaaaaaaaaaaaaa:le:1024": [10, 30, 42]}
        assert result.unmatched == []

    def test_mixed_phash_and_stem_custom_ids(self, mock_repository: MagicMock) -> None:
        """pHash 形式と stem 形式が混在しても各方式で照合する。"""
        matcher = BatchImageMatcher(mock_repository)
        result = matcher.match_all(["ph:aaaaaaaaaaaaaaaa:le:1024", "0262_1227", "unknown"])

        assert result.matched == {"ph:aaaaaaaaaaaaaaaa:le:1024": 10, "0262_1227": 1}
        assert result.unmatched == ["unknown"]
