# tests/unit/services/test_search_criteria_processor.py

from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from lorairo.services.search_criteria_processor import SearchCriteriaProcessor
from lorairo.services.search_models import FilterConditions, SearchConditions


class TestSearchCriteriaProcessor:
    """SearchCriteriaProcessor のユニットテスト"""

    @pytest.fixture
    def mock_db_manager(self):
        """モックデータベースマネージャー"""
        mock_db = Mock()
        mock_db.get_images_by_filter.return_value = ([], 0)
        mock_db.check_image_has_annotation.return_value = False
        return mock_db

    @pytest.fixture
    def processor(self, mock_db_manager):
        """テスト用SearchCriteriaProcessor"""
        return SearchCriteriaProcessor(mock_db_manager)

    def test_initialization(self, processor, mock_db_manager):
        """初期化テスト"""
        assert processor.db_manager == mock_db_manager

    def test_execute_search_with_filters_basic(self, processor, mock_db_manager):
        """基本的な検索実行テスト（直接呼び出し方式）"""
        # モック設定
        mock_images = [{"id": 1, "width": 1024, "height": 768}, {"id": 2, "width": 512, "height": 512}]
        mock_db_manager.get_images_by_filter.return_value = (mock_images, 2)

        # 検索条件作成
        conditions = SearchConditions(search_type="tags", keywords=["test", "tag"], tag_logic="and")

        # 検索実行
        results, count = processor.execute_search_with_filters(conditions)

        # 結果検証
        assert len(results) == 2
        assert count == 2
        assert results[0]["id"] == 1
        assert results[1]["id"] == 2

        # DB呼び出しの引数を厳密に検証
        expected_db_args = conditions.to_db_filter_args()
        mock_db_manager.get_images_by_filter.assert_called_once_with(**expected_db_args)

    def test_search_conditions_to_db_filter_args(self, processor):
        """SearchConditions.to_db_filter_args() のテスト"""
        conditions = SearchConditions(
            search_type="tags",
            keywords=["tag1", "tag2"],
            tag_logic="and",
            resolution_filter="1024x1024",
            only_untagged=False,
        )

        db_args = conditions.to_db_filter_args()

        # DB引数の確認
        assert db_args["tags"] == ["tag1", "tag2"]
        assert db_args["caption"] is None
        assert db_args["resolution"] == 1024  # max(1024, 1024)
        assert db_args["use_and"] is True
        assert db_args["include_untagged"] is False
        assert db_args["start_date"] is None
        assert db_args["end_date"] is None

    def test_process_date_filter_with_dates(self, processor):
        """日付フィルター処理テスト"""
        start_date = datetime(2023, 1, 1)
        end_date = datetime(2023, 12, 31)

        conditions = SearchConditions(
            search_type="tags",
            keywords=["test"],
            tag_logic="and",
            date_filter_enabled=True,
            date_range_start=start_date,
            date_range_end=end_date,
        )

        result = processor.process_date_filter(conditions)

        assert "start_date" in result
        assert "end_date" in result
        assert result["start_date"] == start_date
        assert result["end_date"] == end_date

    def test_process_date_filter_no_dates(self, processor):
        """日付なしフィルター処理テスト"""
        conditions = SearchConditions(search_type="tags", keywords=["test"], tag_logic="and")

        result = processor.process_date_filter(conditions)

        # 日付が設定されていない場合は空の辞書
        assert result == {}

    def test_apply_untagged_filter_untagged_only(self, processor):
        """未タグ付きのみフィルター適用テスト"""
        conditions = SearchConditions(
            search_type="tags", keywords=["test"], tag_logic="and", only_untagged=True
        )

        result = processor.apply_untagged_filter(conditions)

        assert result.get("has_tags") is False

    def test_apply_untagged_filter_tagged_only(self, processor):
        """タグ付きのみフィルター適用テスト"""
        conditions = SearchConditions(
            search_type="tags", keywords=["test"], tag_logic="and", only_untagged=False
        )
        # 擬似的にtagged_onlyを設定
        conditions.tagged_only = True

        result = processor.apply_untagged_filter(conditions)

        assert result.get("has_tags") is True

    def test_apply_tagged_filter_logic_with_tags(self, processor):
        """タグ付きフィルターロジック適用テスト"""
        conditions = SearchConditions(search_type="tags", keywords=["tag1", "tag2"], tag_logic="or")

        result = processor.apply_tagged_filter_logic(conditions)

        assert result["tags"] == ["tag1", "tag2"]
        assert result["tag_operator"] == "or"

    def test_apply_tagged_filter_logic_no_tags(self, processor):
        """タグなしフィルターロジック適用テスト"""
        conditions = SearchConditions(search_type="tags", keywords=[], tag_logic="and")

        result = processor.apply_tagged_filter_logic(conditions)

        # keywordsが空の場合は空の辞書
        assert "tags" not in result or not result.get("tags")

    def test_apply_simple_frontend_filters_aspect_ratio(self, processor):
        """シンプルフロントエンドフィルター適用テスト（アスペクト比）"""
        images = [
            {"width": 1000, "height": 1000},  # 1:1
            {"width": 1920, "height": 1080},  # 16:9
            {"width": 800, "height": 800},  # 1:1
        ]

        conditions = SearchConditions(
            search_type="tags", keywords=["test"], tag_logic="and", aspect_ratio_filter="正方形 (1:1)"
        )

        result = processor._apply_simple_frontend_filters(images, conditions)

        # 正方形(1:1)画像のみ残る
        assert len(result) == 2
        assert result[0]["width"] == 1000
        assert result[1]["width"] == 800

    def test_apply_simple_frontend_filters_basic(self, processor):
        """シンプルフロントエンドフィルター基本テスト"""
        images = [
            {"width": 1000, "height": 1000},
            {"width": 1920, "height": 1080},
        ]

        conditions = SearchConditions(search_type="tags", keywords=["test"], tag_logic="and")

        result = processor._apply_simple_frontend_filters(images, conditions)

        # フィルター条件がない場合は全画像が残る
        assert len(result) == 2

    def test_apply_simple_frontend_filters_with_duplicate_exclusion(self, processor):
        """重複除外フィルター統合テスト（Issue #6）"""
        images = [
            {"id": 1, "phash": "abc123", "width": 1024, "height": 768},
            {"id": 2, "phash": "abc123", "width": 1024, "height": 768},  # 重複
            {"id": 3, "phash": "def456", "width": 512, "height": 512},
        ]

        conditions = SearchConditions(
            search_type="tags",
            keywords=[],
            tag_logic="and",
            exclude_duplicates=True,
        )

        result = processor._apply_simple_frontend_filters(images, conditions)

        # 検証: 重複が除外され、最初の画像のみ保持
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 3

    def test_filter_by_aspect_ratio_square(self, processor):
        """正方形アスペクト比フィルタリングテスト"""
        images = [
            {"width": 1024, "height": 1024},  # 正方形
            {"width": 1920, "height": 1080},  # 横長
            {"width": 512, "height": 512},  # 正方形
        ]

        result = processor._filter_by_aspect_ratio(images, "正方形 (1:1)")

        assert len(result) == 2
        assert all(img["width"] == img["height"] for img in result)

    def test_filter_by_aspect_ratio_landscape_16_9(self, processor):
        """16:9フィルターで16:9画像のみ残ることを確認"""
        images = [
            {"id": 1, "width": 1920, "height": 1080},  # 16:9
            {"id": 2, "width": 1600, "height": 1200},  # 4:3
            {"id": 3, "width": 1080, "height": 1920},  # 9:16
        ]

        result = processor._filter_by_aspect_ratio(images, "風景 (16:9)")

        assert len(result) == 1
        assert result[0]["id"] == 1

    def test_filter_by_aspect_ratio_landscape_4_3(self, processor):
        """4:3フィルターで16:9を混在させないことを確認"""
        images = [
            {"id": 1, "width": 1920, "height": 1080},  # 16:9
            {"id": 2, "width": 1600, "height": 1200},  # 4:3
            {"id": 3, "width": 1080, "height": 1920},  # 9:16
        ]

        result = processor._filter_by_aspect_ratio(images, "風景 (4:3)")

        assert len(result) == 1
        assert result[0]["id"] == 2

    def test_filter_by_aspect_ratio_no_filter(self, processor):
        """アスペクト比フィルターなしテスト"""
        images = [{"width": 1024, "height": 1024}, {"width": 1920, "height": 1080}]

        result = processor._filter_by_aspect_ratio(images, "全て")

        # フィルターなしの場合は全画像が残る
        assert len(result) == 2

    def test_filter_by_date_range_with_range(self, processor):
        """日付範囲フィルタリングテスト"""
        images = [
            {"created_at": "2023-06-15T00:00:00Z"},  # 範囲内
            {"created_at": "2022-12-01T00:00:00Z"},  # 範囲外
            {"modified_at": "2023-03-15T00:00:00Z"},  # modified_atで範囲内
        ]

        date_filter = {"start_date": datetime(2023, 1, 1), "end_date": datetime(2023, 12, 31)}

        result = processor._filter_by_date_range(images, date_filter)

        assert len(result) == 2

    def test_filter_by_date_range_no_filter(self, processor):
        """日付範囲フィルターなしテスト"""
        images = [{"created_at": "2023-06-15T00:00:00Z"}, {"created_at": "2022-12-01T00:00:00Z"}]

        result = processor._filter_by_date_range(images, None)

        # フィルターなしの場合は全画像が残る
        assert len(result) == 2

    def test_filter_images_by_annotation_status_annotated(self, processor, mock_db_manager):
        """アノテーション済み画像フィルタリングテスト"""
        images = [{"id": 1}, {"id": 2}, {"id": 3}]

        # id=1,3はアノテーション済み、id=2は未アノテーション
        mock_db_manager.get_annotated_image_ids.return_value = {1, 3}

        result = processor.filter_images_by_annotation_status(images, "annotated")

        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 3
        # バッチメソッドが1回だけ呼ばれること
        mock_db_manager.get_annotated_image_ids.assert_called_once_with([1, 2, 3])

    def test_filter_images_by_annotation_status_not_annotated(self, processor, mock_db_manager):
        """未アノテーション画像フィルタリングテスト"""
        images = [{"id": 1}, {"id": 2}, {"id": 3}]

        # id=1,3はアノテーション済み → id=2のみ未アノテーション
        mock_db_manager.get_annotated_image_ids.return_value = {1, 3}

        result = processor.filter_images_by_annotation_status(images, "not_annotated")

        assert len(result) == 1
        assert result[0]["id"] == 2

    def test_filter_images_by_annotation_status_all(self, processor, mock_db_manager):
        """全画像フィルタリングテスト"""
        images = [{"id": 1}, {"id": 2}, {"id": 3}]

        result = processor.filter_images_by_annotation_status(images, "all")

        assert len(result) == 3
        # get_annotated_image_idsは呼ばれない
        mock_db_manager.get_annotated_image_ids.assert_not_called()

    def test_parse_resolution_value_valid(self, processor):
        """有効な解像度文字列解析テスト"""
        assert processor._parse_resolution_value("1920x1080") == (1920, 1080)
        assert processor._parse_resolution_value("512x512") == (512, 512)
        assert processor._parse_resolution_value("2048x1024") == (2048, 1024)

    def test_parse_resolution_value_invalid(self, processor):
        """無効な解像度文字列解析テスト"""
        assert processor._parse_resolution_value("invalid") == (None, None)
        assert processor._parse_resolution_value("1920x") == (None, None)
        assert processor._parse_resolution_value("x1080") == (None, None)
        assert processor._parse_resolution_value("") == (None, None)
        assert processor._parse_resolution_value(None) == (None, None)

    @patch("lorairo.services.search_criteria_processor.logger")
    def test_execute_search_with_filters_error_handling(self, mock_logger, processor, mock_db_manager):
        """検索実行エラーハンドリングテスト"""
        # データベースエラーを発生させる
        mock_db_manager.get_images_by_filter.side_effect = Exception("Database error")

        conditions = SearchConditions(search_type="tags", keywords=["test"], tag_logic="and")

        # エラーが再発生することを確認
        with pytest.raises(Exception, match="Database error"):
            processor.execute_search_with_filters(conditions)

        # エラーログが出力されることを確認
        mock_logger.error.assert_called_once()


class TestSearchCriteriaProcessorIntegration:
    """SearchCriteriaProcessor の統合テスト"""

    @pytest.fixture
    def mock_db_manager(self):
        """統合テスト用モックデータベースマネージャー"""
        mock_db = Mock()
        return mock_db

    @pytest.fixture
    def processor(self, mock_db_manager):
        """統合テスト用SearchCriteriaProcessor"""
        return SearchCriteriaProcessor(mock_db_manager)

    def test_end_to_end_search_execution(self, processor, mock_db_manager):
        """エンドツーエンド検索実行テスト（直接呼び出し方式）"""
        # モック画像データ
        mock_images = [
            {"id": 1, "width": 1024, "height": 1024, "created_at": "2023-06-15T00:00:00Z"},
            {"id": 2, "width": 1920, "height": 1080, "created_at": "2023-07-20T00:00:00Z"},
        ]
        mock_db_manager.get_images_by_filter.return_value = (mock_images, 2)

        # 直接呼び出し用検索条件
        conditions = SearchConditions(
            search_type="tags",
            keywords=["anime", "girl"],
            tag_logic="and",
            resolution_filter="1024x1024",
            aspect_ratio_filter="正方形 (1:1)",
            date_filter_enabled=True,
            date_range_start=datetime(2023, 1, 1),
            date_range_end=datetime(2023, 12, 31),
        )

        # 検索実行
        results, count = processor.execute_search_with_filters(conditions)

        # DB呼び出しの引数を厳密に検証
        expected_db_args = conditions.to_db_filter_args()
        mock_db_manager.get_images_by_filter.assert_called_once_with(**expected_db_args)

        # フロントエンドフィルター適用後の結果確認
        assert count == 1  # 正方形のみ
        assert len(results) == 1
        assert results[0]["id"] == 1


class TestDuplicateExclusionFilter:
    """重複除外フィルターのユニットテスト（Issue #6）"""

    @pytest.fixture
    def mock_db_manager(self):
        """モックデータベースマネージャー"""
        return Mock()

    @pytest.fixture
    def processor(self, mock_db_manager):
        """テスト用SearchCriteriaProcessor"""
        return SearchCriteriaProcessor(mock_db_manager)

    def test_filter_by_duplicate_exclusion_basic(self, processor):
        """基本的な重複除外テスト"""
        # テストデータ: 重複あり（同じphash）
        images = [
            {"id": 1, "phash": "abc123", "width": 1024, "height": 768},
            {"id": 2, "phash": "abc123", "width": 1024, "height": 768},  # 重複
            {"id": 3, "phash": "def456", "width": 512, "height": 512},
        ]

        result = processor._filter_by_duplicate_exclusion(images)

        # 検証: 重複は除外され、最初の画像のみ保持
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 3

    def test_filter_by_duplicate_exclusion_empty_list(self, processor):
        """空リスト処理テスト"""
        images = []

        result = processor._filter_by_duplicate_exclusion(images)

        # 検証: 空リストはそのまま返却
        assert len(result) == 0
        assert result == []

    def test_filter_by_duplicate_exclusion_no_duplicates(self, processor):
        """重複なしケーステスト"""
        images = [
            {"id": 1, "phash": "abc123", "width": 1024, "height": 768},
            {"id": 2, "phash": "def456", "width": 512, "height": 512},
            {"id": 3, "phash": "ghi789", "width": 800, "height": 600},
        ]

        result = processor._filter_by_duplicate_exclusion(images)

        # 検証: 全画像保持
        assert len(result) == 3
        assert result == images

    def test_filter_by_duplicate_exclusion_all_duplicates(self, processor):
        """全て重複ケーステスト"""
        images = [
            {"id": 1, "phash": "abc123", "width": 1024, "height": 768},
            {"id": 2, "phash": "abc123", "width": 1024, "height": 768},
            {"id": 3, "phash": "abc123", "width": 1024, "height": 768},
        ]

        result = processor._filter_by_duplicate_exclusion(images)

        # 検証: 1枚のみ保持
        assert len(result) == 1
        assert result[0]["id"] == 1

    def test_filter_by_duplicate_exclusion_single_image(self, processor):
        """単一画像テスト"""
        images = [{"id": 1, "phash": "abc123", "width": 1024, "height": 768}]

        result = processor._filter_by_duplicate_exclusion(images)

        # 検証: そのまま保持
        assert len(result) == 1
        assert result[0]["id"] == 1

    def test_filter_by_duplicate_exclusion_partial_duplicates(self, processor):
        """部分重複テスト"""
        images = [
            {"id": 1, "phash": "abc123", "width": 1024, "height": 768},
            {"id": 2, "phash": "abc123", "width": 1024, "height": 768},  # 重複グループ1
            {"id": 3, "phash": "def456", "width": 512, "height": 512},
            {"id": 4, "phash": "def456", "width": 512, "height": 512},  # 重複グループ2
            {"id": 5, "phash": "ghi789", "width": 800, "height": 600},  # ユニーク
        ]

        result = processor._filter_by_duplicate_exclusion(images)

        # 検証: 各グループから1枚ずつ保持
        assert len(result) == 3
        assert result[0]["id"] == 1
        assert result[1]["id"] == 3
        assert result[2]["id"] == 5

    def test_filter_by_duplicate_exclusion_performance(self, processor):
        """性能テスト（10,000画像で < 500ms）"""
        import time

        # テストデータ生成: 10,000画像（50%重複）
        test_images = []
        for i in range(5000):
            # 重複ペア
            phash = f"phash_{i:06d}"
            test_images.append({"id": i * 2, "phash": phash, "width": 1024, "height": 1024})
            test_images.append({"id": i * 2 + 1, "phash": phash, "width": 1024, "height": 1024})

        start = time.perf_counter()
        result = processor._filter_by_duplicate_exclusion(test_images)
        elapsed = (time.perf_counter() - start) * 1000  # ms

        # 検証: 期待される結果数
        assert len(result) == 5000, f"Expected 5000, got {len(result)}"

        # 性能要件検証
        assert elapsed < 500, f"Performance requirement failed: {elapsed:.2f}ms > 500ms"
