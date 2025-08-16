# tests/unit/services/test_search_criteria_processor.py

from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from lorairo.gui.services.search_filter_service import FilterConditions, SearchConditions
from lorairo.services.search_criteria_processor import SearchCriteriaProcessor


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
        """基本的な検索実行テスト"""
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
        mock_db_manager.get_images_by_filter.assert_called_once()

    def test_separate_search_and_filter_conditions_with_keywords(self, processor):
        """キーワード付き条件分離テスト"""
        conditions = SearchConditions(
            search_type="tags",
            keywords=["tag1", "tag2"],
            tag_logic="and",
            resolution_filter="1024x1024",
            aspect_ratio_filter="正方形 (1:1)",
            date_filter_enabled=True,
            date_range_start=datetime(2023, 1, 1),
            date_range_end=datetime(2023, 12, 31),
            only_untagged=False,
            only_uncaptioned=True,
        )

        search_cond, filter_cond = processor.separate_search_and_filter_conditions(conditions)

        # DB検索条件の確認
        assert "keywords" in search_cond
        assert search_cond["keywords"] == ["tag1", "tag2"]
        assert search_cond.get("only_uncaptioned") is True

        # フロントエンドフィルター条件の確認
        assert filter_cond.aspect_ratio == "正方形 (1:1)"
        assert filter_cond.date_range is not None

    def test_separate_search_and_filter_conditions_no_keywords(self, processor):
        """キーワードなし条件分離テスト"""
        conditions = SearchConditions(search_type="tags", keywords=[], tag_logic="and", only_untagged=True)

        search_cond, filter_cond = processor.separate_search_and_filter_conditions(conditions)

        # キーワードがない場合の確認
        assert "keywords" not in search_cond or not search_cond["keywords"]
        assert search_cond.get("only_untagged") is True

    def test_process_resolution_filter_valid(self, processor):
        """有効な解像度フィルター処理テスト"""
        conditions = SearchConditions(
            search_type="tags", keywords=["test"], tag_logic="and", resolution_filter="1920x1080"
        )

        result = processor.process_resolution_filter(conditions)

        assert "min_width" in result
        assert "min_height" in result
        assert result["min_width"] == 1920
        assert result["min_height"] == 1080

    def test_process_resolution_filter_invalid(self, processor):
        """無効な解像度フィルター処理テスト"""
        conditions = SearchConditions(
            search_type="tags", keywords=["test"], tag_logic="and", resolution_filter="invalid_format"
        )

        result = processor.process_resolution_filter(conditions)

        # 無効な形式の場合は空の辞書が返される
        assert result == {}

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
        # 擬似的にtagsプロパティを設定
        conditions.tags = ["tag1", "tag2"]

        result = processor.apply_tagged_filter_logic(conditions)

        assert result["tags"] == ["tag1", "tag2"]
        assert result["tag_operator"] == "or"

    def test_apply_tagged_filter_logic_no_tags(self, processor):
        """タグなしフィルターロジック適用テスト"""
        conditions = SearchConditions(search_type="tags", keywords=[], tag_logic="and")
        # 擬似的にtagsプロパティを設定
        conditions.tags = None

        result = processor.apply_tagged_filter_logic(conditions)

        # tagsがNoneの場合は空の辞書
        assert "tags" not in result or not result.get("tags")

    def test_convert_to_db_query_conditions(self, processor):
        """DB条件変換テスト"""
        search_conditions = {
            "keywords": ["test", "tag"],
            "tag_operator": "AND",
            "min_width": 1024,
            "max_height": 2048,
            "annotation_status": "completed",
        }

        result = processor._convert_to_db_query_conditions(search_conditions)

        # Noneでない値がすべて含まれることを確認
        assert result["keywords"] == ["test", "tag"]
        assert result["tag_operator"] == "AND"
        assert result["min_width"] == 1024
        assert result["max_height"] == 2048
        assert result["annotation_status"] == "completed"

    def test_convert_to_db_query_conditions_with_none_values(self, processor):
        """None値を含むDB条件変換テスト"""
        search_conditions = {
            "keywords": ["test"],
            "invalid_field": None,
            "empty_field": "",
            "valid_field": "value",
        }

        result = processor._convert_to_db_query_conditions(search_conditions)

        # None値は除外される
        assert "invalid_field" not in result
        # 空文字は含まれる
        assert result["empty_field"] == ""
        assert result["valid_field"] == "value"

    def test_apply_frontend_filters_aspect_ratio(self, processor):
        """アスペクト比フロントエンドフィルター適用テスト"""
        images = [
            {"width": 1000, "height": 1000},  # 1:1
            {"width": 1920, "height": 1080},  # 16:9
            {"width": 800, "height": 800},  # 1:1
        ]

        filter_conditions = FilterConditions(aspect_ratio="正方形 (1:1)")

        result = processor._apply_frontend_filters(images, filter_conditions)

        # 正方形(1:1)画像のみ残る
        assert len(result) == 2
        assert result[0]["width"] == 1000
        assert result[1]["width"] == 800

    def test_apply_frontend_filters_date_range(self, processor):
        """日付範囲フロントエンドフィルター適用テスト"""
        images = [
            {"created_at": "2023-01-15T00:00:00Z"},  # 範囲内
            {"created_at": "2022-12-01T00:00:00Z"},  # 範囲外
            {"created_at": "2023-06-15T00:00:00Z"},  # 範囲内
        ]

        filter_conditions = FilterConditions(date_range=(datetime(2023, 1, 1), datetime(2023, 12, 31)))

        result = processor._apply_frontend_filters(images, filter_conditions)

        # 範囲内の画像のみ残る
        assert len(result) == 2

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
        mock_db_manager.check_image_has_annotation.side_effect = lambda img_id: img_id in [1, 3]

        result = processor.filter_images_by_annotation_status(images, "annotated")

        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 3

    def test_filter_images_by_annotation_status_not_annotated(self, processor, mock_db_manager):
        """未アノテーション画像フィルタリングテスト"""
        images = [{"id": 1}, {"id": 2}, {"id": 3}]

        # id=2のみ未アノテーション
        mock_db_manager.check_image_has_annotation.side_effect = lambda img_id: img_id != 2

        result = processor.filter_images_by_annotation_status(images, "not_annotated")

        assert len(result) == 1
        assert result[0]["id"] == 2

    def test_filter_images_by_annotation_status_all(self, processor, mock_db_manager):
        """全画像フィルタリングテスト"""
        images = [{"id": 1}, {"id": 2}, {"id": 3}]

        result = processor.filter_images_by_annotation_status(images, "all")

        assert len(result) == 3
        # check_image_has_annotationは呼ばれない
        mock_db_manager.check_image_has_annotation.assert_not_called()

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

    @patch("lorairo.services.search_criteria_processor.logger")
    def test_separate_search_and_filter_conditions_error_handling(self, mock_logger, processor):
        """条件分離エラーハンドリングテスト"""
        # 不正な条件オブジェクトを作成
        invalid_conditions = None

        # エラーが再発生することを確認
        with pytest.raises(Exception):
            processor.separate_search_and_filter_conditions(invalid_conditions)

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
        """エンドツーエンド検索実行テスト"""
        # モック画像データ
        mock_images = [
            {"id": 1, "width": 1024, "height": 1024, "created_at": "2023-06-15T00:00:00Z"},
            {"id": 2, "width": 1920, "height": 1080, "created_at": "2023-07-20T00:00:00Z"},
            {"id": 3, "width": 512, "height": 512, "created_at": "2022-12-01T00:00:00Z"},
        ]
        mock_db_manager.get_images_by_filter.return_value = (mock_images, 3)

        # 複合検索条件
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

        # データベース検索が呼ばれることを確認
        mock_db_manager.get_images_by_filter.assert_called_once()

        # フロントエンドフィルターが適用され、条件に合う画像のみ残ることを確認
        # 正方形かつ2023年の画像：id=1のみ
        assert count == 1
        assert len(results) == 1
        assert results[0]["id"] == 1
