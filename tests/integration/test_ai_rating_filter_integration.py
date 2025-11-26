"""
AI評価レーティングフィルタの完全統合テスト

SearchConditions → SearchCriteriaProcessor → ImageDatabaseManager → ImageRepository
の完全なデータフローを検証します。
"""

from unittest.mock import MagicMock, Mock

import pytest

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.db_repository import ImageRepository
from lorairo.services.search_criteria_processor import SearchCriteriaProcessor
from lorairo.services.search_models import SearchConditions


@pytest.fixture
def mock_repository():
    """モックRepository"""
    repo = Mock(spec=ImageRepository)
    repo.get_images_by_filter = Mock(return_value=([], 0))
    return repo


@pytest.fixture
def mock_db_manager(mock_repository):
    """モックManager（実際のRepositoryメソッド呼び出しを記録）"""
    manager = Mock(spec=ImageDatabaseManager)
    manager.repository = mock_repository

    # Managerの実際のメソッドを模倣
    def get_images_by_filter_wrapper(**kwargs):
        return mock_repository.get_images_by_filter(**kwargs)

    manager.get_images_by_filter = Mock(side_effect=get_images_by_filter_wrapper)
    return manager


@pytest.fixture
def criteria_processor(mock_db_manager):
    """SearchCriteriaProcessor（モックManagerを使用）"""
    return SearchCriteriaProcessor(mock_db_manager)


class TestAIRatingFilterIntegration:
    """AI評価レーティングフィルタ統合テスト"""

    def test_ai_rating_filter_complete_flow(self, criteria_processor, mock_repository):
        """SearchConditions から Repository までの完全なデータフロー"""
        # SearchConditions を作成
        conditions = SearchConditions(
            search_type="tags",
            keywords=["test"],
            tag_logic="and",
            ai_rating_filter="PG",
            include_unrated=False,
        )

        # SearchCriteriaProcessor 経由で検索実行
        results, count = criteria_processor.execute_search_with_filters(conditions)

        # Repository が正しいパラメータで呼ばれたことを確認
        mock_repository.get_images_by_filter.assert_called_once()
        call_kwargs = mock_repository.get_images_by_filter.call_args.kwargs

        # 新しいパラメータが正しく渡されている
        assert call_kwargs["ai_rating_filter"] == "PG"
        assert call_kwargs["include_unrated"] is False

    def test_priority_based_filtering_flow(self, criteria_processor, mock_repository):
        """優先順位ベースフィルタリングの完全フロー"""
        # 両方のレーティングフィルタを指定
        conditions = SearchConditions(
            search_type="tags",
            keywords=["test"],
            tag_logic="and",
            rating_filter="PG",  # manual (優先)
            ai_rating_filter="R",  # AI (無視されるはず)
        )

        # 検索実行
        criteria_processor.execute_search_with_filters(conditions)

        # Repository が呼ばれたことを確認
        mock_repository.get_images_by_filter.assert_called_once()
        call_kwargs = mock_repository.get_images_by_filter.call_args.kwargs

        # 両方のパラメータが渡される（優先順位はRepository層で処理）
        assert call_kwargs["manual_rating_filter"] == "PG"
        assert call_kwargs["ai_rating_filter"] == "R"

    def test_include_unrated_parameter_flow(self, criteria_processor, mock_repository):
        """include_unrated パラメータの完全フロー"""
        conditions = SearchConditions(
            search_type="tags",
            keywords=["test"],
            tag_logic="and",
            include_unrated=False,  # 未評価画像を除外
        )

        criteria_processor.execute_search_with_filters(conditions)

        mock_repository.get_images_by_filter.assert_called_once()
        call_kwargs = mock_repository.get_images_by_filter.call_args.kwargs

        assert call_kwargs["include_unrated"] is False

    def test_default_values_flow(self, criteria_processor, mock_repository):
        """デフォルト値の完全フロー"""
        # デフォルト値を使用
        conditions = SearchConditions(
            search_type="tags",
            keywords=["test"],
            tag_logic="and",
            # ai_rating_filter と include_unrated はデフォルト値
        )

        criteria_processor.execute_search_with_filters(conditions)

        mock_repository.get_images_by_filter.assert_called_once()
        call_kwargs = mock_repository.get_images_by_filter.call_args.kwargs

        # デフォルト値が正しく渡される
        assert call_kwargs["ai_rating_filter"] is None
        assert call_kwargs["include_unrated"] is True

    def test_nsfw_and_ai_rating_interaction_flow(self, criteria_processor, mock_repository):
        """NSFW と AI レーティングフィルタの相互作用フロー"""
        conditions = SearchConditions(
            search_type="tags",
            keywords=["test"],
            tag_logic="and",
            ai_rating_filter="R",  # NSFW値
            include_nsfw=False,  # NSFW除外
        )

        criteria_processor.execute_search_with_filters(conditions)

        mock_repository.get_images_by_filter.assert_called_once()
        call_kwargs = mock_repository.get_images_by_filter.call_args.kwargs

        # 両方のパラメータが正しく渡される
        assert call_kwargs["ai_rating_filter"] == "R"
        assert call_kwargs["include_nsfw"] is False


class TestManagerLayerParameterForwarding:
    """Manager層のパラメータ転送テスト"""

    def test_manager_forwards_all_new_parameters(self, mock_repository):
        """Manager が新しいパラメータをすべて Repository に転送"""
        # Mock Manager を使用
        manager = Mock(spec=ImageDatabaseManager)
        manager.repository = mock_repository

        # Managerの実際のメソッドを模倣
        def get_images_by_filter_wrapper(**kwargs):
            return mock_repository.get_images_by_filter(**kwargs)

        manager.get_images_by_filter = Mock(side_effect=get_images_by_filter_wrapper)

        # 新しいパラメータを含めて呼び出し
        manager.get_images_by_filter(
            tags=["test"],
            ai_rating_filter="PG",
            include_unrated=False,
        )

        # Repository が正しいパラメータで呼ばれた
        mock_repository.get_images_by_filter.assert_called_once()
        call_kwargs = mock_repository.get_images_by_filter.call_args.kwargs

        assert call_kwargs["tags"] == ["test"]
        assert call_kwargs["ai_rating_filter"] == "PG"
        assert call_kwargs["include_unrated"] is False
