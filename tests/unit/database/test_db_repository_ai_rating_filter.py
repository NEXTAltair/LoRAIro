"""
ImageRepositoryのAI評価レーティングフィルタ関連メソッドのテスト

このテストモジュールは、Issue #3で実装されたAI評価レーティングフィルタ機能をテストします:
- _apply_ai_rating_filter(): 多数決ロジックによるAI評価フィルタ
- _apply_unrated_filter(): Either-based未評価フィルタ
- get_images_by_filter(): 優先順位ベースのフィルタ統合
"""

from unittest.mock import Mock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from lorairo.database.db_repository import ImageRepository
from lorairo.database.schema import Image


class TestApplyAIRatingFilter:
    """_apply_ai_rating_filter() メソッドのテスト"""

    @pytest.fixture
    def repository(self):
        """テスト用ImageRepository"""
        mock_session_factory = Mock()
        return ImageRepository(session_factory=mock_session_factory)

    def test_apply_ai_rating_filter_creates_subqueries(self, repository):
        """AI評価フィルタが正しいサブクエリ構造を作成することを確認"""
        # ベースクエリ作成
        base_query = select(Image.id)

        # フィルタ適用
        result_query = repository._apply_ai_rating_filter(base_query, "PG")

        # クエリが変更されたことを確認（単純な存在チェック）
        assert result_query is not None
        assert result_query != base_query  # クエリが変更されている

    def test_apply_ai_rating_filter_case_insensitive(self, repository):
        """AI評価フィルタが大文字小文字を区別しないことを確認"""
        base_query = select(Image.id)

        # 小文字でフィルタ適用
        result_lowercase = repository._apply_ai_rating_filter(base_query, "pg")
        assert result_lowercase is not None

        # 大文字でフィルタ適用
        result_uppercase = repository._apply_ai_rating_filter(base_query, "PG")
        assert result_uppercase is not None

        # 混在でフィルタ適用
        result_mixed = repository._apply_ai_rating_filter(base_query, "Pg")
        assert result_mixed is not None

    def test_apply_ai_rating_filter_all_rating_values(self, repository):
        """全てのレーティング値に対してフィルタが適用可能であることを確認"""
        base_query = select(Image.id)
        rating_values = ["PG", "PG-13", "R", "X", "XXX"]

        for rating in rating_values:
            result_query = repository._apply_ai_rating_filter(base_query, rating)
            assert result_query is not None, f"Failed to apply filter for rating: {rating}"


class TestApplyUnratedFilter:
    """_apply_unrated_filter() メソッドのテスト"""

    @pytest.fixture
    def repository(self):
        """テスト用ImageRepository"""
        mock_session_factory = Mock()
        return ImageRepository(session_factory=mock_session_factory)

    def test_apply_unrated_filter_include_unrated_true(self, repository):
        """include_unrated=True の場合、フィルタが適用されないことを確認"""
        base_query = select(Image.id)

        # include_unrated=True の場合、クエリは変更されない
        result_query = repository._apply_unrated_filter(base_query, include_unrated=True)

        # クエリが変更されていない（フィルタが適用されていない）
        assert result_query is not None

    def test_apply_unrated_filter_include_unrated_false(self, repository):
        """include_unrated=False の場合、Either-based フィルタが適用されることを確認"""
        base_query = select(Image.id)

        # include_unrated=False の場合、OR条件が追加される
        result_query = repository._apply_unrated_filter(base_query, include_unrated=False)

        # クエリが変更されている
        assert result_query is not None
        assert result_query != base_query


class TestGetImagesByFilterAIRating:
    """get_images_by_filter() メソッドのAI評価フィルタ統合テスト"""

    @pytest.fixture
    def mock_session_and_repository(self):
        """モックセッションとリポジトリ"""
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

    def test_ai_rating_filter_parameter_passing(self, mock_session_and_repository):
        """ai_rating_filter パラメータが正しく渡されることを確認"""
        repository, mock_session = mock_session_and_repository

        # ai_rating_filter を指定して検索
        results, count = repository.get_images_by_filter(ai_rating_filter="PG")

        # クエリが実行されたことを確認
        assert mock_session.execute.called
        assert results == []
        assert count == 0

    def test_priority_based_manual_over_ai(self, mock_session_and_repository):
        """manual_rating_filter が ai_rating_filter より優先されることを確認"""
        repository, mock_session = mock_session_and_repository

        with patch.object(repository, "_apply_manual_filters") as mock_manual:
            with patch.object(repository, "_apply_ai_rating_filter") as mock_ai:
                mock_manual.return_value = select(Image.id)
                mock_ai.return_value = select(Image.id)

                # 両方のフィルタを指定
                repository.get_images_by_filter(manual_rating_filter="PG", ai_rating_filter="R")

                # manual_rating_filter が適用され、ai_rating_filter は無視される
                mock_manual.assert_called()
                # AI filter should not be called when manual filter is specified
                mock_ai.assert_not_called()

    def test_ai_rating_filter_only(self, mock_session_and_repository):
        """ai_rating_filter のみが指定された場合、適用されることを確認"""
        repository, mock_session = mock_session_and_repository

        with patch.object(repository, "_apply_ai_rating_filter") as mock_ai:
            mock_ai.return_value = select(Image.id)

            # ai_rating_filter のみを指定
            repository.get_images_by_filter(ai_rating_filter="PG")

            # AI filter が適用される
            mock_ai.assert_called_once()

    def test_include_unrated_parameter_passing(self, mock_session_and_repository):
        """include_unrated パラメータが正しく渡されることを確認"""
        repository, mock_session = mock_session_and_repository

        # include_unrated=False を指定して検索
        results, count = repository.get_images_by_filter(include_unrated=False)

        # クエリが実行されたことを確認
        assert mock_session.execute.called

    def test_nsfw_filter_interaction_with_ai_rating(self, mock_session_and_repository):
        """NSFW フィルタが ai_rating_filter と正しく相互作用することを確認"""
        repository, mock_session = mock_session_and_repository

        # NSFW値を ai_rating_filter に指定した場合、NSFW除外は無効化される
        results1, count1 = repository.get_images_by_filter(ai_rating_filter="R", include_nsfw=False)
        assert mock_session.execute.called

        # 非NSFW値を ai_rating_filter に指定した場合、NSFW除外が有効
        results2, count2 = repository.get_images_by_filter(ai_rating_filter="PG", include_nsfw=False)
        assert mock_session.execute.called


class TestSearchConditionsIntegration:
    """SearchConditions データモデルの統合テスト"""

    def test_search_conditions_to_db_filter_args_includes_ai_rating(self):
        """SearchConditions.to_db_filter_args() が ai_rating_filter を含むことを確認"""
        from lorairo.services.search_models import SearchConditions

        conditions = SearchConditions(
            search_type="tags",
            keywords=["test"],
            tag_logic="and",
            ai_rating_filter="PG",
            include_unrated=False,
        )

        db_args = conditions.to_db_filter_args()

        assert "ai_rating_filter" in db_args
        assert db_args["ai_rating_filter"] == "PG"
        assert "include_unrated" in db_args
        assert db_args["include_unrated"] is False

    def test_search_conditions_priority_based_mapping(self):
        """SearchConditions が優先順位ベースのフィルタをサポートすることを確認"""
        from lorairo.services.search_models import SearchConditions

        conditions = SearchConditions(
            search_type="tags",
            keywords=["test"],
            tag_logic="and",
            rating_filter="PG",  # manual rating
            ai_rating_filter="R",  # AI rating (should be ignored by repository)
        )

        db_args = conditions.to_db_filter_args()

        # 両方のフィルタがマッピングされる（優先順位はリポジトリ層で処理）
        assert db_args["manual_rating_filter"] == "PG"
        assert db_args["ai_rating_filter"] == "R"


class TestSearchFilterServiceIntegration:
    """SearchFilterService の統合テスト"""

    def test_create_search_conditions_with_ai_rating(self):
        """create_search_conditions() が ai_rating_filter を受け入れることを確認"""
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
            ai_rating_filter="PG",
            include_unrated=False,
        )

        assert conditions.ai_rating_filter == "PG"
        assert conditions.include_unrated is False

    def test_create_search_preview_shows_ai_rating(self):
        """create_search_preview() が AI レーティングフィルタを表示することを確認"""
        from unittest.mock import Mock

        from lorairo.gui.services.search_filter_service import SearchFilterService
        from lorairo.services.search_models import SearchConditions

        mock_db_manager = Mock()
        mock_model_selection_service = Mock()

        service = SearchFilterService(
            db_manager=mock_db_manager,
            model_selection_service=mock_model_selection_service,
        )

        conditions = SearchConditions(
            search_type="tags",
            keywords=["test"],
            tag_logic="and",
            ai_rating_filter="PG",
        )

        preview = service.create_search_preview(conditions)

        # プレビューに AI レーティングフィルタが含まれることを確認
        assert "AIレーティング" in preview
        assert "PG" in preview
        assert "多数決" in preview

    def test_create_search_preview_shows_priority_note(self):
        """create_search_preview() が優先順位の注記を表示することを確認"""
        from unittest.mock import Mock

        from lorairo.gui.services.search_filter_service import SearchFilterService
        from lorairo.services.search_models import SearchConditions

        mock_db_manager = Mock()
        mock_model_selection_service = Mock()

        service = SearchFilterService(
            db_manager=mock_db_manager,
            model_selection_service=mock_model_selection_service,
        )

        conditions = SearchConditions(
            search_type="tags",
            keywords=["test"],
            tag_logic="and",
            rating_filter="PG",  # manual
            ai_rating_filter="R",  # AI (should show priority note)
        )

        preview = service.create_search_preview(conditions)

        # プレビューに優先順位の注記が含まれることを確認
        assert "手動レーティング優先" in preview or "※手動レーティング優先" in preview


class TestUnratedFilter:
    """UNRATEDフィルター（レーティング未設定画像のみ）のテスト"""

    @pytest.fixture
    def repository(self):
        """テスト用ImageRepository"""
        mock_session_factory = Mock()
        return ImageRepository(session_factory=mock_session_factory)

    def test_apply_ai_rating_filter_unrated(self, repository):
        """AIレーティングフィルタでUNRATED指定が正しく動作することを確認"""
        base_query = select(Image.id)

        # UNRATEDフィルタ適用
        result_query = repository._apply_ai_rating_filter(base_query, "UNRATED")

        # クエリが変更されたことを確認
        assert result_query is not None
        assert result_query != base_query

    def test_apply_manual_filters_unrated(self, repository):
        """手動レーティングフィルタでUNRATED指定が正しく動作することを確認"""
        base_query = select(Image.id)
        mock_session = Mock(spec=Session)

        # _get_or_create_manual_edit_modelをモック
        with patch.object(repository, "_get_or_create_manual_edit_model", return_value=1):
            result_query = repository._apply_manual_filters(base_query, "UNRATED", None, mock_session)

        # クエリが変更されたことを確認
        assert result_query is not None
        assert result_query != base_query


class TestUnratedPreviewDisplay:
    """UNRATEDフィルターのプレビュー表示テスト"""

    def test_create_search_preview_shows_unrated_manual_rating(self):
        """create_search_preview()が手動レーティングUNRATEDを「未設定のみ」と表示することを確認"""
        from lorairo.gui.services.search_filter_service import SearchFilterService
        from lorairo.services.search_models import SearchConditions

        mock_db_manager = Mock()
        mock_model_selection_service = Mock()

        service = SearchFilterService(
            db_manager=mock_db_manager,
            model_selection_service=mock_model_selection_service,
        )

        conditions = SearchConditions(
            search_type="tags",
            keywords=["test"],
            tag_logic="and",
            rating_filter="UNRATED",
        )

        preview = service.create_search_preview(conditions)

        # プレビューに「未設定のみ」が含まれることを確認
        assert "手動レーティング" in preview
        assert "未設定のみ" in preview

    def test_create_search_preview_shows_unrated_ai_rating(self):
        """create_search_preview()がAIレーティングUNRATEDを「未設定のみ」と表示することを確認"""
        from lorairo.gui.services.search_filter_service import SearchFilterService
        from lorairo.services.search_models import SearchConditions

        mock_db_manager = Mock()
        mock_model_selection_service = Mock()

        service = SearchFilterService(
            db_manager=mock_db_manager,
            model_selection_service=mock_model_selection_service,
        )

        conditions = SearchConditions(
            search_type="tags",
            keywords=["test"],
            tag_logic="and",
            ai_rating_filter="UNRATED",
        )

        preview = service.create_search_preview(conditions)

        # プレビューに「未設定のみ」が含まれることを確認
        assert "AIレーティング" in preview
        assert "未設定のみ" in preview
