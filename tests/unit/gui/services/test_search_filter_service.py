# tests/unit/gui/services/test_search_filter_service.py

from datetime import datetime

import pytest

from lorairo.gui.services.search_filter_service import SearchFilterService
from lorairo.services.search_models import SearchConditions


class TestSearchConditions:
    """SearchConditions データクラスのテスト"""

    def test_search_conditions_creation(self):
        """SearchConditions の基本作成テスト"""
        conditions = SearchConditions(
            search_type="tags",
            keywords=["tag1", "tag2"],
            tag_logic="and",
            excluded_keywords=["tag3"],
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
        # カスタム解像度機能削除済み
        assert conditions.aspect_ratio_filter is None
        assert conditions.date_filter_enabled is False
        assert conditions.date_range_start is None
        assert conditions.date_range_end is None
        assert conditions.only_untagged is False
        assert conditions.only_uncaptioned is False
        assert conditions.exclude_duplicates is False
        # Rating filter defaults
        assert conditions.include_nsfw is True  # 後方互換性のため True
        assert conditions.rating_filter is None
        assert conditions.include_unrated is True

    def test_search_conditions_with_rating_filter(self):
        """SearchConditions のRatingフィルター付き作成テスト"""
        conditions = SearchConditions(
            search_type="tags",
            keywords=["tag1"],
            tag_logic="and",
            include_nsfw=False,
            rating_filter="PG",
            include_unrated=False,
        )

        assert conditions.include_nsfw is False
        assert conditions.rating_filter == "PG"
        assert conditions.include_unrated is False

    def test_to_filter_criteria_with_rating(self):
        """to_filter_criteria() のRatingフィルター変換テスト"""
        conditions = SearchConditions(
            search_type="tags",
            keywords=["tag1", "tag2"],
            tag_logic="and",
            excluded_keywords=["tag3"],
            include_nsfw=False,
            rating_filter="PG-13",
        )

        criteria = conditions.to_filter_criteria()

        assert criteria.include_nsfw is False
        assert criteria.manual_rating_filter == "PG-13"
        assert criteria.tags == ["tag1", "tag2"]
        assert criteria.excluded_tags == ["tag3"]
        assert criteria.use_and is True


class TestSearchFilterService:
    """SearchFilterService のユニットテスト"""

    @pytest.fixture
    def service(self):
        """テスト用SearchFilterService"""
        from unittest.mock import Mock

        mock_db_manager = Mock()
        mock_model_selection_service = Mock()
        return SearchFilterService(
            db_manager=mock_db_manager, model_selection_service=mock_model_selection_service
        )

    def test_initialization(self, service):
        """初期化テスト"""
        assert service.current_conditions is None

    def test_parse_search_input_tags(self, service):
        """タグ検索入力解析テスト"""
        # 基本的なカンマ区切り
        keywords, excluded_keywords = service.parse_search_input("tag1, tag2, tag3")
        assert keywords == ["tag1", "tag2", "tag3"]
        assert excluded_keywords == []

        # スペース込みタグ
        keywords, excluded_keywords = service.parse_search_input("1girl, long hair, blue eyes")
        assert keywords == ["1girl", "long hair", "blue eyes"]
        assert excluded_keywords == []

        # 空のタグ除去
        keywords, excluded_keywords = service.parse_search_input("tag1, , tag3, ")
        assert keywords == ["tag1", "tag3"]
        assert excluded_keywords == []

    def test_parse_search_input_caption(self, service):
        """キャプション検索入力解析テスト"""
        # カンマ区切りキャプション
        keywords, excluded_keywords = service.parse_search_input(
            "beautiful scene, landscape view, mountain scenery"
        )
        assert keywords == ["beautiful scene", "landscape view", "mountain scenery"]
        assert excluded_keywords == []

        # 余分なスペース処理（単一キーワード）
        keywords, excluded_keywords = service.parse_search_input("  single keyword  ")
        assert keywords == ["single keyword"]
        assert excluded_keywords == []

    def test_parse_search_input_empty(self, service):
        """空の検索入力テスト"""
        keywords, excluded_keywords = service.parse_search_input("")
        assert keywords == []
        assert excluded_keywords == []

        keywords, excluded_keywords = service.parse_search_input("   ")
        assert keywords == []
        assert excluded_keywords == []

    def test_parse_search_input_with_exclusion(self, service):
        """除外検索入力解析テスト"""
        keywords, excluded_keywords = service.parse_search_input("1girl, -1boy, blue_eyes, -smile")

        assert keywords == ["1girl", "blue_eyes"]
        assert excluded_keywords == ["1boy", "smile"]

    def test_create_search_conditions_basic(self, service):
        """基本的な検索条件作成テスト"""
        keywords, excluded_keywords = service.parse_search_input("tag1, tag2")
        conditions = service.create_search_conditions(
            search_type="tags",
            keywords=keywords,
            excluded_keywords=excluded_keywords,
            tag_logic="and",
            resolution_filter="1024x1024",
            aspect_ratio_filter="1:1 (正方形)",
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
        assert conditions.resolution_filter == "1024x1024"
        assert conditions.aspect_ratio_filter == "1:1 (正方形)"
        assert conditions.date_filter_enabled is False
        assert service.current_conditions == conditions

    def test_create_search_conditions_with_dates(self, service):
        """日付付き検索条件作成テスト"""
        start_date = datetime(2023, 1, 1)
        end_date = datetime(2023, 12, 31)
        keywords, excluded_keywords = service.parse_search_input("test")

        conditions = service.create_search_conditions(
            search_type="caption",
            keywords=keywords,
            excluded_keywords=excluded_keywords,
            tag_logic="or",
            resolution_filter="1024x1024",
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

    def test_create_search_preview_comprehensive(self, service):
        """包括的な検索プレビュー作成テスト"""
        conditions = SearchConditions(
            search_type="tags",
            keywords=["1girl", "long hair"],
            excluded_keywords=["1boy"],
            tag_logic="and",
            resolution_filter="1024x1024",
            aspect_ratio_filter="1:1 (正方形)",
            date_filter_enabled=True,
            date_range_start=datetime(2023, 1, 1),
            date_range_end=datetime(2023, 12, 31),
            only_untagged=True,
            only_uncaptioned=False,
            exclude_duplicates=True,
        )

        preview = service.create_search_preview(conditions)

        assert "キーワード: 1girl AND long hair (tags)" in preview
        assert "除外キーワード: 1boy" in preview
        assert "解像度: 1024x1024" in preview
        assert "アスペクト比: 1:1 (正方形)" in preview
        assert "日付範囲: 開始: 2023-01-01, 終了: 2023-12-31" in preview
        assert "未タグ付きのみ" in preview
        assert "重複除外" in preview

    def test_create_search_preview_with_rating_filter(self, service):
        """Ratingフィルター付き検索プレビュー作成テスト"""
        conditions = SearchConditions(
            search_type="tags",
            keywords=["1girl"],
            tag_logic="and",
            rating_filter="PG",
            include_nsfw=False,
            include_unrated=False,
        )

        preview = service.create_search_preview(conditions)

        assert "レーティング: PG" in preview
        assert "NSFW除外" in preview
        assert "未評価除外" in preview

    def test_create_search_preview_empty(self, service):
        """空の検索プレビュー作成テスト"""
        conditions = SearchConditions(search_type="tags", keywords=[], tag_logic="and")

        preview = service.create_search_preview(conditions)
        assert preview == "すべての画像"

    def test_get_available_resolutions(self, service):
        """利用可能解像度取得テスト（LoRA最適化版）"""
        resolutions = service.get_available_resolutions()

        expected = [
            "512x512",  # レガシーSD1.5
            "1024x1024",  # SDXL標準（メイン）
            "1280x720",  # 16:9横長
            "720x1280",  # 9:16縦長
            "1920x1080",  # フルHD
            "1536x1536",  # SDXL高解像度
        ]

        assert resolutions == expected

    def test_get_available_aspect_ratios(self, service):
        """利用可能アスペクト比取得テスト"""
        ratios = service.get_available_aspect_ratios()

        expected = [
            "1:1 (正方形)",
            "4:3 (標準)",
            "16:9 (ワイド)",
            "3:2 (一眼レフ)",
            "2:3 (ポートレート)",
            "9:16 (縦長ワイド)",
        ]

        assert ratios == expected

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
        from unittest.mock import Mock

        mock_model_selection_service = Mock()
        return SearchFilterService(
            db_manager=mock_db_manager, model_selection_service=mock_model_selection_service
        )

    def test_initialization_with_db_manager(self, service_with_db, mock_db_manager):
        """データベースマネージャー付き初期化テスト"""
        assert service_with_db.db_manager == mock_db_manager
        assert service_with_db.current_conditions is None


class TestSearchFilterServiceValidateUiInputs:
    """SearchFilterService.validate_ui_inputs のユニットテスト

    検索条件未指定時の警告は BDD 対象外（内部ロジック）のため unit テストで代替する。
    """

    @pytest.fixture
    def service(self):
        from unittest.mock import Mock

        return SearchFilterService(db_manager=Mock(), model_selection_service=Mock())

    def test_validate_ui_inputs_no_conditions_returns_warning(self, service):
        """検索条件未指定時は警告を返し is_valid は True"""
        result = service.validate_ui_inputs({"keywords": []})

        assert result.is_valid is True
        assert result.warnings is not None
        assert any("検索条件が指定されていません" in w for w in result.warnings)
        assert result.errors == []

    def test_validate_ui_inputs_with_keywords_no_warning(self, service):
        """キーワード指定時は警告を出さない"""
        result = service.validate_ui_inputs({"keywords": ["1girl"]})

        assert result.is_valid is True
        assert result.warnings == []
        assert result.errors == []

    def test_validate_ui_inputs_only_untagged_suppresses_warning(self, service):
        """キーワードが無くても only_untagged 指定時は警告を出さない"""
        result = service.validate_ui_inputs({"keywords": [], "only_untagged": True})

        assert result.is_valid is True
        assert result.warnings == []

    def test_validate_ui_inputs_resolution_filter_suppresses_warning(self, service):
        """キーワードが無くても resolution_filter 指定時は警告を出さない"""
        result = service.validate_ui_inputs({"keywords": [], "resolution_filter": "1024x1024"})

        assert result.is_valid is True
        assert result.warnings == []

    def test_validate_ui_inputs_invalid_date_range_returns_error(self, service):
        """開始日付が終了日付より後の場合はエラーを返し is_valid は False"""
        result = service.validate_ui_inputs(
            {
                "keywords": ["tag"],
                "date_filter_enabled": True,
                "date_range_start": datetime(2023, 12, 31),
                "date_range_end": datetime(2023, 1, 1),
            }
        )

        assert result.is_valid is False
        assert result.errors is not None
        assert any("開始日付は終了日付より前" in e for e in result.errors)

    def test_validate_ui_inputs_valid_date_range_no_error(self, service):
        """開始日付が終了日付より前の場合はエラーを出さない"""
        result = service.validate_ui_inputs(
            {
                "keywords": ["tag"],
                "date_filter_enabled": True,
                "date_range_start": datetime(2023, 1, 1),
                "date_range_end": datetime(2023, 12, 31),
            }
        )

        assert result.is_valid is True
        assert result.errors == []


class TestSearchFilterServiceGetEstimatedCount:
    """SearchFilterService.get_estimated_count のユニットテスト"""

    def test_get_estimated_count_returns_db_count(self):
        """DB マネージャーの件数をそのまま返す"""
        from unittest.mock import Mock

        mock_db_manager = Mock()
        mock_db_manager.get_images_count_only.return_value = 42
        service = SearchFilterService(db_manager=mock_db_manager, model_selection_service=Mock())
        conditions = SearchConditions(search_type="tags", keywords=["1girl"], tag_logic="and")

        count = service.get_estimated_count(conditions)

        assert count == 42
        mock_db_manager.get_images_count_only.assert_called_once()

    def test_get_estimated_count_passes_filter_criteria(self):
        """to_filter_criteria() の結果が criteria 引数として渡される"""
        from unittest.mock import Mock

        mock_db_manager = Mock()
        mock_db_manager.get_images_count_only.return_value = 0
        service = SearchFilterService(db_manager=mock_db_manager, model_selection_service=Mock())
        conditions = SearchConditions(
            search_type="tags", keywords=["cat"], tag_logic="and", excluded_keywords=["dog"]
        )

        service.get_estimated_count(conditions)

        _, kwargs = mock_db_manager.get_images_count_only.call_args
        criteria = kwargs["criteria"]
        assert criteria.tags == ["cat"]
        assert criteria.excluded_tags == ["dog"]

    def test_get_estimated_count_returns_zero_on_error(self):
        """DB エラー時は 0 を返す（例外を伝播しない）"""
        from unittest.mock import Mock

        mock_db_manager = Mock()
        mock_db_manager.get_images_count_only.side_effect = RuntimeError("DB error")
        service = SearchFilterService(db_manager=mock_db_manager, model_selection_service=Mock())
        conditions = SearchConditions(search_type="tags", keywords=["tag"], tag_logic="and")

        count = service.get_estimated_count(conditions)

        assert count == 0


class TestSearchFilterServiceAnnotation:
    """SearchFilterService のアノテーション系機能テスト（Phase 2拡張）"""

    @pytest.fixture
    def mock_db_manager(self):
        """モックデータベースマネージャー"""
        from unittest.mock import Mock

        return Mock()

    def test_annotation_model_filter_service_is_not_exposed(self, mock_db_manager):
        """SearchFilterService はモデル一覧互換ラッパーを公開しない。"""
        from unittest.mock import Mock

        mock_model_selection_service = Mock()
        service = SearchFilterService(
            db_manager=mock_db_manager, model_selection_service=mock_model_selection_service
        )

        assert not hasattr(service, "get_annotation_models_list")
        assert not hasattr(service, "validate_annotation_settings")
