# tests/unit/gui/services/test_search_filter_service.py

from datetime import datetime
from unittest.mock import patch

import pytest

from lorairo.gui.services.search_filter_service import (
    FilterConditions,
    SearchConditions,
    SearchFilterService,
)


class TestSearchConditions:
    """SearchConditions データクラスのテスト"""

    def test_search_conditions_creation(self):
        """SearchConditions の基本作成テスト"""
        conditions = SearchConditions(
            search_type="tags",
            keywords=["tag1", "tag2"],
            tag_logic="and",
            resolution_filter="1024x1024",
            aspect_ratio_filter="正方形 (1:1)",
            date_filter_enabled=True,
            date_range_start=datetime(2023, 1, 1),
            date_range_end=datetime(2023, 12, 31),
            only_untagged=True,
            only_uncaptioned=False,
            exclude_duplicates=True,
        )

        assert conditions.search_type == "tags"
        assert conditions.keywords == ["tag1", "tag2"]
        assert conditions.tag_logic == "and"
        assert conditions.resolution_filter == "1024x1024"
        assert conditions.aspect_ratio_filter == "正方形 (1:1)"
        assert conditions.date_filter_enabled is True
        assert conditions.only_untagged is True
        assert conditions.only_uncaptioned is False
        assert conditions.exclude_duplicates is True

    def test_search_conditions_defaults(self):
        """SearchConditions のデフォルト値テスト"""
        conditions = SearchConditions(search_type="caption", keywords=["keyword"], tag_logic="or")

        assert conditions.resolution_filter is None
        assert conditions.custom_width is None
        assert conditions.custom_height is None
        assert conditions.aspect_ratio_filter is None
        assert conditions.date_filter_enabled is False
        assert conditions.date_range_start is None
        assert conditions.date_range_end is None
        assert conditions.only_untagged is False
        assert conditions.only_uncaptioned is False
        assert conditions.exclude_duplicates is False


class TestFilterConditions:
    """FilterConditions データクラスのテスト"""

    def test_filter_conditions_creation(self):
        """FilterConditions の基本作成テスト"""
        conditions = FilterConditions(
            resolution=(1920, 1080),
            aspect_ratio="風景 (16:9)",
            date_range=(datetime(2023, 1, 1), datetime(2023, 12, 31)),
            only_untagged=True,
            only_uncaptioned=False,
            exclude_duplicates=True,
        )

        assert conditions.resolution == (1920, 1080)
        assert conditions.aspect_ratio == "風景 (16:9)"
        assert conditions.date_range == (datetime(2023, 1, 1), datetime(2023, 12, 31))
        assert conditions.only_untagged is True
        assert conditions.only_uncaptioned is False
        assert conditions.exclude_duplicates is True

    def test_filter_conditions_defaults(self):
        """FilterConditions のデフォルト値テスト"""
        conditions = FilterConditions()

        assert conditions.resolution is None
        assert conditions.aspect_ratio is None
        assert conditions.date_range is None
        assert conditions.only_untagged is False
        assert conditions.only_uncaptioned is False
        assert conditions.exclude_duplicates is False


class TestSearchFilterService:
    """SearchFilterService のユニットテスト"""

    @pytest.fixture
    def service(self):
        """テスト用SearchFilterService"""
        from unittest.mock import Mock

        mock_db_manager = Mock()
        return SearchFilterService(db_manager=mock_db_manager)

    def test_initialization(self, service):
        """初期化テスト"""
        assert service.current_conditions is None

    def test_parse_search_input_tags(self, service):
        """タグ検索入力解析テスト"""
        # 基本的なカンマ区切り
        keywords = service.parse_search_input("tag1, tag2, tag3", "tags", "and")
        assert keywords == ["tag1", "tag2", "tag3"]

        # スペース込みタグ
        keywords = service.parse_search_input("1girl, long hair, blue eyes", "tags", "and")
        assert keywords == ["1girl", "long hair", "blue eyes"]

        # 空のタグ除去
        keywords = service.parse_search_input("tag1, , tag3, ", "tags", "and")
        assert keywords == ["tag1", "tag3"]

    def test_parse_search_input_caption(self, service):
        """キャプション検索入力解析テスト"""
        # スペース区切り
        keywords = service.parse_search_input("beautiful landscape mountain", "caption", "and")
        assert keywords == ["beautiful", "landscape", "mountain"]

        # 余分なスペース処理
        keywords = service.parse_search_input("  word1   word2  word3  ", "caption", "and")
        assert keywords == ["word1", "word2", "word3"]

    def test_parse_search_input_empty(self, service):
        """空の検索入力テスト"""
        keywords = service.parse_search_input("", "tags", "and")
        assert keywords == []

        keywords = service.parse_search_input("   ", "caption", "or")
        assert keywords == []

    def test_create_search_conditions_basic(self, service):
        """基本的な検索条件作成テスト"""
        conditions = service.create_search_conditions(
            search_text="tag1, tag2",
            search_type="tags",
            tag_logic="and",
            resolution_filter="全て",
            custom_width="",
            custom_height="",
            aspect_ratio_filter="全て",
            date_filter_enabled=False,
            date_range_start=None,
            date_range_end=None,
            only_untagged=False,
            only_uncaptioned=False,
            exclude_duplicates=False,
        )

        assert conditions.search_type == "tags"
        assert conditions.keywords == ["tag1", "tag2"]
        assert conditions.tag_logic == "and"
        assert conditions.resolution_filter is None  # "全て" -> None
        assert conditions.aspect_ratio_filter is None  # "全て" -> None
        assert conditions.date_filter_enabled is False
        assert service.current_conditions == conditions

    def test_create_search_conditions_custom_resolution(self, service):
        """カスタム解像度付き検索条件作成テスト"""
        conditions = service.create_search_conditions(
            search_text="test",
            search_type="tags",
            tag_logic="and",
            resolution_filter="カスタム...",
            custom_width="1920",
            custom_height="1080",
            aspect_ratio_filter="全て",
            date_filter_enabled=False,
            date_range_start=None,
            date_range_end=None,
            only_untagged=False,
            only_uncaptioned=False,
            exclude_duplicates=False,
        )

        assert conditions.resolution_filter == "カスタム..."
        assert conditions.custom_width == 1920
        assert conditions.custom_height == 1080

    def test_create_search_conditions_invalid_custom_resolution(self, service):
        """無効なカスタム解像度処理テスト"""
        with patch("lorairo.gui.services.search_filter_service.logger") as mock_logger:
            conditions = service.create_search_conditions(
                search_text="test",
                search_type="tags",
                tag_logic="and",
                resolution_filter="カスタム...",
                custom_width="invalid",
                custom_height="1080",
                aspect_ratio_filter="全て",
                date_filter_enabled=False,
                date_range_start=None,
                date_range_end=None,
                only_untagged=False,
                only_uncaptioned=False,
                exclude_duplicates=False,
            )

            # 幅の警告ログが出力されたことを確認
            mock_logger.warning.assert_called_with("Invalid custom width: invalid")
            # 幅は無効でNone、高さは有効で1080
            assert conditions.custom_width is None
            assert conditions.custom_height == 1080

    def test_create_search_conditions_with_dates(self, service):
        """日付付き検索条件作成テスト"""
        start_date = datetime(2023, 1, 1)
        end_date = datetime(2023, 12, 31)

        conditions = service.create_search_conditions(
            search_text="test",
            search_type="caption",
            tag_logic="or",
            resolution_filter="1024x1024",
            custom_width="",
            custom_height="",
            aspect_ratio_filter="正方形 (1:1)",
            date_filter_enabled=True,
            date_range_start=start_date,
            date_range_end=end_date,
            only_untagged=True,
            only_uncaptioned=True,
            exclude_duplicates=True,
        )

        assert conditions.date_filter_enabled is True
        assert conditions.date_range_start == start_date
        assert conditions.date_range_end == end_date
        assert conditions.only_untagged is True
        assert conditions.only_uncaptioned is True
        assert conditions.exclude_duplicates is True

    def test_separate_search_and_filter_conditions_basic(self, service):
        """基本的な検索・フィルター条件分離テスト"""
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
            exclude_duplicates=True,
        )

        search_cond, filter_cond = service.separate_search_and_filter_conditions(conditions)

        # 検索条件
        assert search_cond["search_type"] == "tags"
        assert search_cond["keywords"] == ["tag1", "tag2"]
        assert search_cond["tag_logic"] == "and"
        assert search_cond["only_untagged"] is False
        assert search_cond["only_uncaptioned"] is True

        # フィルター条件
        assert filter_cond["resolution"] == (1024, 1024)
        assert filter_cond["aspect_ratio"] == "正方形 (1:1)"
        assert filter_cond["date_range"] == (datetime(2023, 1, 1), datetime(2023, 12, 31))
        assert filter_cond["exclude_duplicates"] is True

    def test_separate_search_and_filter_conditions_custom_resolution(self, service):
        """カスタム解像度の検索・フィルター条件分離テスト"""
        conditions = SearchConditions(
            search_type="caption",
            keywords=["test"],
            tag_logic="or",
            resolution_filter="カスタム...",
            custom_width=1920,
            custom_height=1080,
        )

        search_cond, filter_cond = service.separate_search_and_filter_conditions(conditions)

        assert filter_cond["resolution"] == (1920, 1080)

    def test_separate_search_and_filter_conditions_no_keywords(self, service):
        """キーワードなしの検索・フィルター条件分離テスト"""
        conditions = SearchConditions(search_type="tags", keywords=[], tag_logic="and", only_untagged=True)

        search_cond, filter_cond = service.separate_search_and_filter_conditions(conditions)

        # キーワードがない場合は検索条件にsearch_type等が含まれない
        assert "search_type" not in search_cond
        assert "keywords" not in search_cond
        assert "tag_logic" not in search_cond
        assert search_cond["only_untagged"] is True

    def test_create_search_preview_comprehensive(self, service):
        """包括的な検索プレビュー作成テスト"""
        conditions = SearchConditions(
            search_type="tags",
            keywords=["1girl", "long hair"],
            tag_logic="and",
            resolution_filter="1024x1024",
            aspect_ratio_filter="正方形 (1:1)",
            date_filter_enabled=True,
            date_range_start=datetime(2023, 1, 1),
            date_range_end=datetime(2023, 12, 31),
            only_untagged=True,
            only_uncaptioned=False,
            exclude_duplicates=True,
        )

        preview = service.create_search_preview(conditions)

        assert "tags: 1girl, long hair (すべて含む)" in preview
        assert "解像度: 1024x1024" in preview
        assert "アスペクト比: 正方形 (1:1)" in preview
        assert "日付: 2023-01-01 ～ 2023-12-31" in preview
        assert "オプション: 未タグ画像のみ, 重複除外" in preview

    def test_create_search_preview_custom_resolution(self, service):
        """カスタム解像度のプレビュー作成テスト"""
        conditions = SearchConditions(
            search_type="caption",
            keywords=["beautiful"],
            tag_logic="or",
            resolution_filter="カスタム...",
            custom_width=1920,
            custom_height=1080,
        )

        preview = service.create_search_preview(conditions)

        assert "caption: beautiful (いずれか含む)" in preview
        assert "解像度: 1920x1080" in preview

    def test_create_search_preview_empty(self, service):
        """空の検索プレビュー作成テスト"""
        conditions = SearchConditions(search_type="tags", keywords=[], tag_logic="and")

        preview = service.create_search_preview(conditions)
        assert preview == "検索条件なし"

    def test_get_available_resolutions(self, service):
        """利用可能解像度取得テスト"""
        resolutions = service.get_available_resolutions()

        expected = [
            "全て",
            "512x512",
            "1024x1024",
            "1024x768",
            "768x1024",
            "1920x1080",
            "1080x1920",
            "2048x2048",
            "カスタム...",
        ]

        assert resolutions == expected

    def test_get_available_aspect_ratios(self, service):
        """利用可能アスペクト比取得テスト"""
        ratios = service.get_available_aspect_ratios()

        expected = [
            "全て",
            "正方形 (1:1)",
            "風景 (16:9)",
            "縦長 (9:16)",
            "風景 (4:3)",
            "縦長 (3:4)",
        ]

        assert ratios == expected

    def test_parse_resolution_string_valid(self, service):
        """有効な解像度文字列解析テスト"""
        assert service._parse_resolution_string("1024x768") == (1024, 768)
        assert service._parse_resolution_string("1920x1080") == (1920, 1080)
        assert service._parse_resolution_string("512x512") == (512, 512)

    def test_parse_resolution_string_invalid(self, service):
        """無効な解像度文字列解析テスト"""
        with patch("lorairo.gui.services.search_filter_service.logger") as mock_logger:
            # "x"が含まれていない場合はログ出力されない
            result = service._parse_resolution_string("invalid_format")
            assert result is None
            # この場合はログ出力されない（"x"がないため）

            # "x"が含まれているが無効な数値の場合はログ出力される
            result = service._parse_resolution_string("1024xabc")
            assert result is None
            # この場合はログ出力される
            mock_logger.warning.assert_called_with("Failed to parse resolution string: 1024xabc")

    def test_clear_conditions(self, service):
        """検索条件クリアテスト"""
        # 条件を設定
        service.current_conditions = SearchConditions(
            search_type="tags", keywords=["test"], tag_logic="and"
        )

        # クリア
        service.clear_conditions()
        assert service.current_conditions is None

    def test_get_current_conditions(self, service):
        """現在の検索条件取得テスト"""
        # 初期状態
        assert service.get_current_conditions() is None

        # 条件設定後
        conditions = SearchConditions(search_type="tags", keywords=["test"], tag_logic="and")
        service.current_conditions = conditions

        assert service.get_current_conditions() == conditions


class TestSearchFilterServiceDatabase:
    """SearchFilterService のデータベース統合機能テスト"""

    @pytest.fixture
    def mock_db_manager(self):
        """モックデータベースマネージャー"""
        from unittest.mock import Mock

        return Mock()

    @pytest.fixture
    def service_with_db(self, mock_db_manager):
        """データベースマネージャー付きSearchFilterService"""
        return SearchFilterService(db_manager=mock_db_manager)

    def test_initialization_with_db_manager(self, service_with_db, mock_db_manager):
        """データベースマネージャー付き初期化テスト"""
        assert service_with_db.db_manager == mock_db_manager
        assert service_with_db.current_conditions is None

    def test_execute_search_with_filters_success(self, service_with_db, mock_db_manager):
        """検索実行成功テスト"""
        # モックデータベースマネージャーの設定
        mock_images = [
            {"id": 1, "width": 1024, "height": 768, "created_at": "2023-01-01T00:00:00Z"},
            {"id": 2, "width": 512, "height": 512, "created_at": "2023-06-01T00:00:00Z"},
        ]
        mock_db_manager.get_images_by_filter.return_value = (mock_images, 2)

        # 検索条件作成
        conditions = SearchConditions(search_type="tags", keywords=["test"], tag_logic="and")

        # 検索実行
        results, count = service_with_db.execute_search_with_filters(conditions)

        # 結果検証
        assert len(results) == 2
        assert count == 2
        assert results[0]["id"] == 1
        assert results[1]["id"] == 2

        # データベースマネージャーが正しく呼ばれたことを確認
        mock_db_manager.get_images_by_filter.assert_called_once()

    def test_get_directory_images_success(self, service_with_db, mock_db_manager):
        """ディレクトリ内画像取得成功テスト"""
        from pathlib import Path

        # モック設定
        test_path = Path("/test/directory")
        mock_image_ids = [1, 2, 3]
        mock_metadata = [
            {"id": 1, "name": "image1.jpg"},
            {"id": 2, "name": "image2.jpg"},
            {"id": 3, "name": "image3.jpg"},
        ]

        mock_db_manager.get_image_ids_from_directory.return_value = mock_image_ids
        mock_db_manager.get_image_metadata.side_effect = lambda img_id: {
            "id": img_id,
            "name": f"image{img_id}.jpg",
        }

        # 実行
        results = service_with_db.get_directory_images(test_path)

        # 検証
        assert len(results) == 3
        assert all("id" in img and "name" in img for img in results)
        mock_db_manager.get_image_ids_from_directory.assert_called_once_with(test_path)
        assert mock_db_manager.get_image_metadata.call_count == 3

    def test_get_dataset_status_with_images(self, service_with_db, mock_db_manager):
        """画像ありデータセット状態取得テスト"""
        mock_db_manager.get_total_image_count.return_value = 100

        status = service_with_db.get_dataset_status()

        assert status["total_images"] == 100
        assert status["status"] == "ready"

    def test_get_dataset_status_empty(self, service_with_db, mock_db_manager):
        """空データセット状態取得テスト"""
        mock_db_manager.get_total_image_count.return_value = 0

        status = service_with_db.get_dataset_status()

        assert status["total_images"] == 0
        assert status["status"] == "empty"

    def test_process_resolution_filter(self, service_with_db):
        """解像度フィルター処理テスト"""
        conditions = {"resolution_filter": "1024x1024", "other": "value"}

        result = service_with_db.process_resolution_filter(conditions)

        assert result["resolution"] == 1024
        assert result["other"] == "value"
        assert "resolution_filter" in result  # 元の条件も保持

    def test_process_resolution_filter_all(self, service_with_db):
        """解像度フィルター「全て」処理テスト"""
        conditions = {"resolution_filter": "全て", "other": "value"}

        result = service_with_db.process_resolution_filter(conditions)

        assert "resolution" not in result
        assert result["other"] == "value"

    def test_process_date_filter(self, service_with_db):
        """日付フィルター処理テスト"""
        start_date = datetime(2023, 1, 1)
        end_date = datetime(2023, 12, 31)
        conditions = {"date_filter_enabled": True, "date_range": (start_date, end_date), "other": "value"}

        result = service_with_db.process_date_filter(conditions)

        assert result["start_date"] == "2023-01-01T00:00:00"
        assert result["end_date"] == "2023-12-31T00:00:00"
        assert result["other"] == "value"

    def test_apply_untagged_filter(self, service_with_db):
        """未タグフィルター適用テスト"""
        conditions = {"only_untagged": True, "tags": ["test"], "use_and": True, "other": "value"}

        result = service_with_db.apply_untagged_filter(conditions)

        assert result["include_untagged"] is True
        assert "tags" not in result  # タグ条件は削除される
        assert "use_and" not in result  # AND条件も削除される
        assert result["other"] == "value"

    def test_apply_tagged_filter_logic_with_conditions(self, service_with_db):
        """条件ありタグ付きフィルターロジック適用テスト"""
        conditions = {"tags": ["test"], "other": "value"}

        result = service_with_db.apply_tagged_filter_logic(conditions)

        assert result["include_untagged"] is False
        assert result["tags"] == ["test"]
        assert result["other"] == "value"

    def test_apply_tagged_filter_logic_without_conditions(self, service_with_db):
        """条件なしタグ付きフィルターロジック適用テスト"""
        conditions = {"other": "value"}

        result = service_with_db.apply_tagged_filter_logic(conditions)

        assert result["include_untagged"] is True
        assert result["other"] == "value"

    def test_parse_resolution_value(self, service_with_db):
        """解像度値解析テスト"""
        assert service_with_db._parse_resolution_value("512x512") == 512
        assert service_with_db._parse_resolution_value("1024x768") == 1024
        assert service_with_db._parse_resolution_value("2048x2048") == 2048
        assert service_with_db._parse_resolution_value("unknown") == 0

    def test_filter_by_aspect_ratio_square(self, service_with_db):
        """正方形アスペクト比フィルターテスト"""
        images = [
            {"width": 1000, "height": 1000},  # 正方形
            {"width": 1024, "height": 768},  # 風景
            {"width": 512, "height": 512},  # 正方形
        ]

        result = service_with_db._filter_by_aspect_ratio(images, "正方形 (1:1)")

        assert len(result) == 2
        assert result[0]["width"] == 1000
        assert result[1]["width"] == 512

    def test_filter_by_aspect_ratio_all(self, service_with_db):
        """全てアスペクト比フィルターテスト"""
        images = [
            {"width": 1000, "height": 1000},
            {"width": 1024, "height": 768},
        ]

        result = service_with_db._filter_by_aspect_ratio(images, "全て")

        assert len(result) == 2  # 全ての画像が残る

    def test_filter_by_date_range(self, service_with_db):
        """日付範囲フィルターテスト"""
        images = [
            {"created_at": "2023-01-15T00:00:00Z"},  # 範囲内
            {"created_at": "2022-12-31T00:00:00Z"},  # 範囲外（前）
            {"created_at": "2023-06-15T00:00:00Z"},  # 範囲内
            {"created_at": "2024-01-01T00:00:00Z"},  # 範囲外（後）
        ]

        start_date = datetime(2023, 1, 1)
        end_date = datetime(2023, 12, 31)

        result = service_with_db._filter_by_date_range(images, start_date, end_date)

        assert len(result) == 2
        assert result[0]["created_at"] == "2023-01-15T00:00:00Z"
        assert result[1]["created_at"] == "2023-06-15T00:00:00Z"


class TestSearchFilterServiceAnnotation:
    """SearchFilterService のアノテーション系機能テスト（Phase 2拡張）"""

    @pytest.fixture
    def mock_db_manager(self):
        """モックデータベースマネージャー"""
        from unittest.mock import Mock

        return Mock()

    @pytest.fixture
    def mock_annotator_adapter(self):
        """モックAnnotatorLibAdapter"""
        from unittest.mock import Mock

        adapter = Mock()
        # デフォルトのモデルメタデータ
        adapter.get_available_models_with_metadata.return_value = [
            {
                "name": "gpt-4-vision-preview",
                "provider": "openai",
                "requires_api_key": True,
                "estimated_size_gb": None,
            },
            {
                "name": "wd-v1-4-swinv2-tagger-v3",
                "provider": "local",
                "requires_api_key": False,
                "estimated_size_gb": 1.2,
            },
            {
                "name": "clip-aesthetic-score",
                "provider": "local",
                "requires_api_key": False,
                "estimated_size_gb": 0.5,
            },
        ]
        return adapter

    @pytest.fixture
    def service_with_annotation(self, mock_db_manager, mock_annotator_adapter):
        """アノテーション機能付きSearchFilterService"""
        return SearchFilterService(db_manager=mock_db_manager, annotator_adapter=mock_annotator_adapter)

    def test_get_annotation_models_list_success(self, service_with_annotation, mock_annotator_adapter):
        """アノテーションモデル一覧取得成功テスト"""
        # 実行
        models = service_with_annotation.get_annotation_models_list()

        # 検証
        assert len(models) == 3

        # GPT-4モデル検証
        gpt4_model = next((m for m in models if "gpt-4" in m["name"]), None)
        assert gpt4_model is not None
        assert gpt4_model["provider"] == "openai"
        assert gpt4_model["is_local"] is False
        assert "caption" in gpt4_model["capabilities"]
        assert "tags" in gpt4_model["capabilities"]

        # タガーモデル検証
        tagger_model = next((m for m in models if "tagger" in m["name"]), None)
        assert tagger_model is not None
        assert tagger_model["provider"] == "local"
        assert tagger_model["is_local"] is True
        assert tagger_model["capabilities"] == ["tags"]

        # AnnotatorLibAdapterが呼ばれたことを確認
        mock_annotator_adapter.get_available_models_with_metadata.assert_called_once()

    def test_get_annotation_models_list_no_adapter(self, mock_db_manager):
        """AnnotatorLibAdapterなしでのモデル一覧取得テスト"""
        service = SearchFilterService(db_manager=mock_db_manager)

        models = service.get_annotation_models_list()

        assert models == []

    def test_filter_models_by_criteria_providers(self, service_with_annotation):
        """プロバイダー別モデルフィルタリングテスト"""
        # 元モデルリスト取得
        all_models = service_with_annotation.get_annotation_models_list()

        # Web APIモデルのみフィルタリング
        web_models = service_with_annotation.filter_models_by_criteria(
            models=all_models, function_types=["caption", "tags", "scores"], providers=["web_api"]
        )

        assert len(web_models) == 1
        assert web_models[0]["provider"] == "openai"
        assert web_models[0]["is_local"] is False

        # ローカルモデルのみフィルタリング
        local_models = service_with_annotation.filter_models_by_criteria(
            models=all_models, function_types=["caption", "tags", "scores"], providers=["local"]
        )

        assert len(local_models) == 2
        assert all(m["is_local"] for m in local_models)

    def test_filter_models_by_criteria_functions(self, service_with_annotation):
        """機能別モデルフィルタリングテスト"""
        all_models = service_with_annotation.get_annotation_models_list()

        # タグ機能のみ
        tag_models = service_with_annotation.filter_models_by_criteria(
            models=all_models, function_types=["tags"], providers=["web_api", "local"]
        )

        # GPT-4とタガーモデルが対象
        assert len(tag_models) == 2

        # スコア機能のみ
        score_models = service_with_annotation.filter_models_by_criteria(
            models=all_models, function_types=["scores"], providers=["web_api", "local"]
        )

        # CLIPモデルのみが対象
        assert len(score_models) == 1
        assert "clip" in score_models[0]["name"]

    def test_validate_annotation_settings_success(self, service_with_annotation):
        """アノテーション設定検証成功テスト"""
        settings = {
            "selected_models": ["gpt-4-vision-preview", "wd-v1-4-swinv2-tagger-v3"],
            "selected_function_types": ["caption", "tags"],
            "selected_providers": ["web_api", "local"],
            "use_low_resolution": False,
            "batch_mode": True,
        }

        result = service_with_annotation.validate_annotation_settings(settings)

        assert result.is_valid is True
        assert result.settings == settings
        assert result.error_message is None

    def test_validate_annotation_settings_no_models(self, service_with_annotation):
        """モデル未選択時の設定検証テスト"""
        settings = {
            "selected_models": [],
            "selected_function_types": ["caption"],
            "selected_providers": ["web_api"],
        }

        result = service_with_annotation.validate_annotation_settings(settings)

        assert result.is_valid is False
        assert "選択されたモデルがありません" in result.error_message

    def test_validate_annotation_settings_no_functions(self, service_with_annotation):
        """機能未選択時の設定検証テスト"""
        settings = {
            "selected_models": ["gpt-4-vision-preview"],
            "selected_function_types": [],
            "selected_providers": ["web_api"],
        }

        result = service_with_annotation.validate_annotation_settings(settings)

        assert result.is_valid is False
        assert "選択された機能タイプがありません" in result.error_message

    def test_infer_model_capabilities_multimodal_llm(self, service_with_annotation):
        """マルチモーダルLLMの機能推定テスト"""
        model_data = {"name": "gpt-4-vision-preview", "provider": "openai"}

        capabilities = service_with_annotation.infer_model_capabilities(model_data)

        assert "caption" in capabilities
        assert "tags" in capabilities

    def test_infer_model_capabilities_tagger(self, service_with_annotation):
        """タガーモデルの機能推定テスト"""
        model_data = {"name": "wd-v1-4-swinv2-tagger-v3", "provider": "local"}

        capabilities = service_with_annotation.infer_model_capabilities(model_data)

        assert capabilities == ["tags"]

    def test_infer_model_capabilities_scorer(self, service_with_annotation):
        """スコアリングモデルの機能推定テスト"""
        model_data = {"name": "clip-aesthetic-score", "provider": "local"}

        capabilities = service_with_annotation.infer_model_capabilities(model_data)

        assert capabilities == ["scores"]
