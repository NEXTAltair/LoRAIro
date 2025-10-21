# tests/unit/gui/services/test_search_filter_service.py

from datetime import datetime
from unittest.mock import patch

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

    def test_to_db_filter_args_with_rating(self):
        """to_db_filter_args() のRatingフィルター変換テスト"""
        conditions = SearchConditions(
            search_type="tags",
            keywords=["tag1", "tag2"],
            tag_logic="and",
            include_nsfw=False,
            rating_filter="PG-13",
        )

        db_args = conditions.to_db_filter_args()

        assert db_args["include_nsfw"] is False
        assert db_args["manual_rating_filter"] == "PG-13"
        assert db_args["tags"] == ["tag1", "tag2"]
        assert db_args["use_and"] is True


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
        keywords = service.parse_search_input("tag1, tag2, tag3")
        assert keywords == ["tag1", "tag2", "tag3"]

        # スペース込みタグ
        keywords = service.parse_search_input("1girl, long hair, blue eyes")
        assert keywords == ["1girl", "long hair", "blue eyes"]

        # 空のタグ除去
        keywords = service.parse_search_input("tag1, , tag3, ")
        assert keywords == ["tag1", "tag3"]

    def test_parse_search_input_caption(self, service):
        """キャプション検索入力解析テスト"""
        # カンマ区切りキャプション
        keywords = service.parse_search_input("beautiful scene, landscape view, mountain scenery")
        assert keywords == ["beautiful scene", "landscape view", "mountain scenery"]

        # 余分なスペース処理（単一キーワード）
        keywords = service.parse_search_input("  single keyword  ")
        assert keywords == ["single keyword"]

    def test_parse_search_input_empty(self, service):
        """空の検索入力テスト"""
        keywords = service.parse_search_input("")
        assert keywords == []

        keywords = service.parse_search_input("   ")
        assert keywords == []

    def test_create_search_conditions_basic(self, service):
        """基本的な検索条件作成テスト"""
        keywords = service.parse_search_input("tag1, tag2")
        conditions = service.create_search_conditions(
            search_type="tags",
            keywords=keywords,
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
        keywords = service.parse_search_input("test")

        conditions = service.create_search_conditions(
            search_type="caption",
            keywords=keywords,
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


class TestSearchFilterServiceAnnotation:
    """SearchFilterService のアノテーション系機能テスト（Phase 2拡張）"""

    @pytest.fixture
    def mock_db_manager(self):
        """モックデータベースマネージャー"""
        from unittest.mock import Mock

        return Mock()

    def test_get_annotation_models_list_modernized(self, mock_db_manager):
        """現代化されたSearchFilterServiceでのモデル一覧取得テスト"""
        from unittest.mock import Mock

        # NullModelRegistryを使用する現代化されたSearchFilterService
        mock_model_selection_service = Mock()
        service = SearchFilterService(
            db_manager=mock_db_manager, model_selection_service=mock_model_selection_service
        )

        models = service.get_annotation_models_list()

        # NullModelRegistryでは空リストが返される
        assert models == []
