"""
ImageRepositoryのスコアフィルタ関連メソッドのテスト

このテストモジュールは、スコアフィルタ機能をテストします:
- _apply_score_filter(): スコア範囲によるフィルタ
- get_images_by_filter(): スコアフィルタ統合
"""

from unittest.mock import Mock

import pytest
from sqlalchemy import select

from lorairo.database.db_repository import ImageRepository
from lorairo.database.schema import Image


class TestApplyScoreFilter:
    """_apply_score_filter() メソッドのテスト"""

    @pytest.fixture
    def repository(self):
        """テスト用ImageRepository"""
        mock_session_factory = Mock()
        return ImageRepository(session_factory=mock_session_factory)

    def test_apply_score_filter_with_min_and_max(self, repository):
        """スコアフィルタが最小値と最大値の両方を適用することを確認"""
        base_query = select(Image.id)

        # スコア範囲 3.0-7.5 でフィルタ適用
        result_query = repository._apply_score_filter(base_query, score_min=3.0, score_max=7.5)

        # クエリが変更されたことを確認
        assert result_query is not None
        assert result_query != base_query

    def test_apply_score_filter_with_min_only(self, repository):
        """最小値のみが指定された場合のフィルタ適用を確認"""
        base_query = select(Image.id)

        # 最小値のみ指定
        result_query = repository._apply_score_filter(base_query, score_min=5.0, score_max=None)

        # クエリが変更されたことを確認
        assert result_query is not None
        assert result_query != base_query

    def test_apply_score_filter_with_max_only(self, repository):
        """最大値のみが指定された場合のフィルタ適用を確認"""
        base_query = select(Image.id)

        # 最大値のみ指定
        result_query = repository._apply_score_filter(base_query, score_min=None, score_max=8.0)

        # クエリが変更されたことを確認
        assert result_query is not None
        assert result_query != base_query

    def test_apply_score_filter_no_filter(self, repository):
        """両方Noneの場合、フィルタが適用されないことを確認"""
        base_query = select(Image.id)

        # 両方None
        result_query = repository._apply_score_filter(base_query, score_min=None, score_max=None)

        # クエリが変更されていない
        assert result_query == base_query

    def test_apply_score_filter_full_range(self, repository):
        """全範囲（0.0-10.0）でフィルタが適用可能であることを確認"""
        base_query = select(Image.id)

        # 全範囲でフィルタ適用
        result_query = repository._apply_score_filter(base_query, score_min=0.0, score_max=10.0)

        # クエリが変更されたことを確認
        assert result_query is not None
        assert result_query != base_query


class TestGetImagesByFilterScoreIntegration:
    """get_images_by_filter() メソッドのスコアフィルタ統合テスト"""

    @pytest.fixture
    def mock_session_and_repository(self):
        """モックセッションとリポジトリ"""
        from unittest.mock import Mock

        from sqlalchemy.orm import Session

        mock_session = Mock(spec=Session)
        mock_session_factory = Mock(return_value=mock_session)

        # Mock __enter__ and __exit__ for context manager
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=None)

        # Mock execute to return empty result
        mock_execute_result = Mock()
        mock_execute_result.scalars = Mock(return_value=Mock(all=Mock(return_value=[])))
        mock_session.execute = Mock(return_value=mock_execute_result)

        repository = ImageRepository(session_factory=mock_session_factory)
        return repository, mock_session

    def test_score_filter_parameter_passing(self, mock_session_and_repository):
        """score_min/score_max パラメータが正しく渡されることを確認"""
        repository, mock_session = mock_session_and_repository

        # スコアフィルタを指定して検索
        results, count = repository.get_images_by_filter(score_min=3.0, score_max=7.5)

        # クエリが実行されたことを確認
        assert mock_session.execute.called
        assert results == []
        assert count == 0

    def test_score_filter_only_min(self, mock_session_and_repository):
        """score_min のみが指定された場合、適用されることを確認"""
        repository, mock_session = mock_session_and_repository

        results, count = repository.get_images_by_filter(score_min=5.0)

        # クエリが実行されたことを確認
        assert mock_session.execute.called

    def test_score_filter_only_max(self, mock_session_and_repository):
        """score_max のみが指定された場合、適用されることを確認"""
        repository, mock_session = mock_session_and_repository

        results, count = repository.get_images_by_filter(score_max=8.0)

        # クエリが実行されたことを確認
        assert mock_session.execute.called


class TestSearchConditionsIntegration:
    """SearchConditions データモデルのスコアフィルタ統合テスト"""

    def test_search_conditions_to_db_filter_args_includes_score(self):
        """SearchConditions.to_db_filter_args() が score_min/score_max を含むことを確認"""
        from lorairo.services.search_models import SearchConditions

        conditions = SearchConditions(
            search_type="tags",
            keywords=["test"],
            tag_logic="and",
            score_min=3.0,
            score_max=7.5,
        )

        db_args = conditions.to_db_filter_args()

        assert "score_min" in db_args
        assert db_args["score_min"] == 3.0
        assert "score_max" in db_args
        assert db_args["score_max"] == 7.5


class TestSearchFilterServiceIntegration:
    """SearchFilterService の統合テスト"""

    def test_create_search_conditions_with_score(self):
        """create_search_conditions() が score_min/score_max を受け入れることを確認"""
        from unittest.mock import Mock

        from lorairo.gui.services.search_filter_service import SearchFilterService

        mock_db_manager = Mock()
        mock_model_selection_service = Mock()

        service = SearchFilterService(
            db_manager=mock_db_manager,
            model_selection_service=mock_model_selection_service,
        )

        conditions = service.create_search_conditions(
            search_type="tags",
            keywords=["test"],
            tag_logic="and",
            score_min=3.0,
            score_max=7.5,
        )

        assert conditions.score_min == 3.0
        assert conditions.score_max == 7.5
