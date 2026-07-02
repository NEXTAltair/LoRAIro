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

from lorairo.database.repository.image import ImageRepository
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
        mock_execute_result.scalar_one.return_value = 0
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

    def test_manual_and_ai_filters_both_applied(self, mock_session_and_repository):
        """manual / AI 両方指定時、両フィルタが AND 適用されることを確認 (Issue #604)"""
        repository, _mock_session = mock_session_and_repository

        # ADR 0035 段階 4: get_images_by_filter は新 ImageRepository (`_image_repo`) に
        # delegate しているため、internal filter helpers はそちらを mock する。
        with patch.object(repository, "_apply_manual_filters") as mock_manual:
            with patch.object(repository, "_apply_ai_rating_filter") as mock_ai:
                mock_manual.return_value = select(Image.id)
                mock_ai.return_value = select(Image.id)

                # 両方のフィルタを指定
                repository.get_images_by_filter(manual_rating_filter="PG", ai_rating_filter="R")

                # manual / AI は排他ではなく両方適用される (Issue #604: 旧実装は AI を無視していた)
                mock_manual.assert_called()
                mock_ai.assert_called_once()

    def test_ai_rating_filter_only(self, mock_session_and_repository):
        """ai_rating_filter のみが指定された場合、適用されることを確認"""
        repository, _mock_session = mock_session_and_repository

        # ADR 0035 段階 4: get_images_by_filter は新 ImageRepository (`_image_repo`) に
        # delegate しているため、internal filter helpers はそちらを mock する。
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
        _results, _count = repository.get_images_by_filter(include_unrated=False)

        # クエリが実行されたことを確認
        assert mock_session.execute.called

    def test_nsfw_filter_interaction_with_ai_rating(self, mock_session_and_repository):
        """NSFW フィルタが ai_rating_filter と正しく相互作用することを確認"""
        repository, mock_session = mock_session_and_repository

        # NSFW値を ai_rating_filter に指定した場合、NSFW除外は無効化される
        _results1, _count1 = repository.get_images_by_filter(ai_rating_filter="R", include_nsfw=False)
        assert mock_session.execute.called

        # 非NSFW値を ai_rating_filter に指定した場合、NSFW除外が有効
        _results2, _count2 = repository.get_images_by_filter(ai_rating_filter="PG", include_nsfw=False)
        assert mock_session.execute.called


class TestSearchConditionsIntegration:
    """SearchConditions データモデルの統合テスト"""

    def test_search_conditions_to_filter_criteria_includes_ai_rating(self):
        """SearchConditions.to_filter_criteria() が ai_rating_filter を含むことを確認"""
        from lorairo.services.search_models import SearchConditions

        conditions = SearchConditions(
            search_type="tags",
            keywords=["test"],
            tag_logic="and",
            ai_rating_filter="PG",
            include_unrated=False,
        )

        criteria = conditions.to_filter_criteria()

        assert criteria.ai_rating_filter == "PG"
        assert criteria.include_unrated is False

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

        criteria = conditions.to_filter_criteria()

        # 両方のフィルタがマッピングされる（優先順位はリポジトリ層で処理）
        assert criteria.manual_rating_filter == "PG"
        assert criteria.ai_rating_filter == "R"


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

    def test_create_search_preview_shows_both_rating_filters(self):
        """manual / AI 同時指定時、両方のレーティング条件を AND として表示する (Issue #604)。

        旧実装は「※手動レーティング優先」注記を表示していたが、manual と AI は
        独立に AND 結合されるようになったため優先関係はなく、注記も付けない。
        """
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
            ai_rating_filter="R",  # AI
        )

        preview = service.create_search_preview(conditions)

        # 手動・AI 両方の条件が表示される (AND)
        assert "手動レーティング: PG" in preview
        assert "AIレーティング: R" in preview
        # 優先関係はなくなったため優先注記は表示しない
        assert "手動レーティング優先" not in preview


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

        # ADR 0035 段階 4: 新 ImageRepository (`repository/image.py`) は
        # MANUAL_EDIT model lookup を `ModelRepository._get_or_create_manual_edit_model`
        # static helper に直接委譲しているため、import 元 (`lorairo.database.repository.image`)
        # の参照を mock する。
        with patch(
            "lorairo.database.repository.image.ModelRepository._get_or_create_manual_edit_model",
            return_value=1,
        ):
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


class TestRatedFilter:
    """RATEDフィルター（レーティング設定済み画像のみ）のテスト (Issue #561)"""

    @pytest.fixture
    def repository(self):
        """テスト用ImageRepository"""
        mock_session_factory = Mock()
        return ImageRepository(session_factory=mock_session_factory)

    def test_apply_ai_rating_filter_rated(self, repository):
        """AIレーティングフィルタでRATED指定が正しく動作することを確認"""
        base_query = select(Image.id)

        result_query = repository._apply_ai_rating_filter(base_query, "RATED")

        # クエリが変更されたことを確認 (has_any_ai_rating 適用)
        assert result_query is not None
        assert result_query != base_query

    def test_apply_manual_filters_rated(self, repository):
        """手動レーティングフィルタでRATED指定が正しく動作することを確認"""
        base_query = select(Image.id)
        mock_session = Mock(spec=Session)

        with patch(
            "lorairo.database.repository.image.ModelRepository._get_or_create_manual_edit_model",
            return_value=1,
        ):
            result_query = repository._apply_manual_filters(base_query, "RATED", None, mock_session)

        assert result_query is not None
        assert result_query != base_query


class TestMultiSelectRatingFilter:
    """Issue #811: マルチセレクト (list[str]) レーティングフィルタのテスト。"""

    @pytest.fixture
    def repository(self):
        return ImageRepository(session_factory=Mock())

    def test_normalize_rating_filter_variants(self, repository):
        """単一値 / 複数値 / None / 空要素を共通の list[str] に正規化する。"""
        assert repository._normalize_rating_filter(None) == []
        assert repository._normalize_rating_filter("PG") == ["PG"]
        assert repository._normalize_rating_filter(["PG", "R"]) == ["PG", "R"]
        # 空文字要素は除去
        assert repository._normalize_rating_filter(["PG", ""]) == ["PG"]

    def test_rating_filter_has_nsfw(self, repository):
        """NSFW (R/X/XXX) 値の有無を単一値・複数値どちらでも判定する。"""
        assert repository._rating_filter_has_nsfw("R") is True
        assert repository._rating_filter_has_nsfw(["PG", "X"]) is True
        assert repository._rating_filter_has_nsfw(["PG", "PG-13"]) is False
        assert repository._rating_filter_has_nsfw(None) is False

    def test_build_ai_rating_condition_list(self, repository):
        """AI レーティング複数値で条件式が生成される (None は条件なし)。"""
        assert repository._build_ai_rating_condition(["PG", "R"]) is not None
        assert repository._build_ai_rating_condition(None) is None
        assert repository._build_ai_rating_condition([]) is None

    def test_build_ai_rating_condition_mixed_sentinel(self, repository):
        """通常値 + 番兵 (UNRATED) の併用でも条件式が生成される。"""
        assert repository._build_ai_rating_condition(["PG", "UNRATED"]) is not None

    def test_apply_ai_rating_filter_list_changes_query(self, repository):
        """_apply_ai_rating_filter は複数値で query を変更する。"""
        base_query = select(Image.id)
        result = repository._apply_ai_rating_filter(base_query, ["PG", "R"])
        assert result is not None
        assert result != base_query

    def test_build_manual_rating_condition_list(self, repository):
        """手動レーティング複数値で条件式が生成される。"""
        mock_session = Mock(spec=Session)
        with patch(
            "lorairo.database.repository.image.ModelRepository._get_or_create_manual_edit_model",
            return_value=1,
        ):
            condition = repository._build_manual_rating_condition(["PG", "R"], mock_session)
            assert condition is not None
            assert repository._build_manual_rating_condition(None, mock_session) is None

    def test_get_images_by_filter_multi_and(self, repository_with_mock_session):
        """manual / AI 複数値 + AND 結合 (既定) でクエリが実行される。"""
        repository, mock_session = repository_with_mock_session
        with patch(
            "lorairo.database.repository.image.ModelRepository._get_or_create_manual_edit_model",
            return_value=1,
        ):
            results, count = repository.get_images_by_filter(
                manual_rating_filter=["PG", "R"], ai_rating_filter=["X"]
            )
        assert mock_session.execute.called
        assert results == []
        assert count == 0

    def test_get_images_by_filter_multi_or(self, repository_with_mock_session):
        """manual / AI 両方指定 + rating_combine='or' で OR 合成パスが実行される。"""
        repository, mock_session = repository_with_mock_session
        with patch(
            "lorairo.database.repository.image.ModelRepository._get_or_create_manual_edit_model",
            return_value=1,
        ):
            _results, count = repository.get_images_by_filter(
                manual_rating_filter=["PG"], ai_rating_filter=["R"], rating_combine="or"
            )
        assert mock_session.execute.called
        assert count == 0

    @pytest.fixture
    def repository_with_mock_session(self):
        mock_session = Mock(spec=Session)
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=None)
        mock_execute_result = Mock()
        mock_execute_result.scalar_one.return_value = 0
        mock_execute_result.scalars = Mock(return_value=Mock(all=Mock(return_value=[])))
        mock_session.execute = Mock(return_value=mock_execute_result)
        return ImageRepository(session_factory=mock_session_factory), mock_session


class TestMultiSelectRatingDataModels:
    """Issue #811: ImageFilterCriteria / SearchConditions の list 受け入れと結合。"""

    def test_filter_criteria_accepts_list_and_combine(self):
        """ImageFilterCriteria が list と rating_combine を保持し to_dict に含める。"""
        from lorairo.database.filter_criteria import ImageFilterCriteria

        criteria = ImageFilterCriteria(
            manual_rating_filter=["PG", "R"],
            ai_rating_filter=["X"],
            rating_combine="or",
        )
        assert criteria.manual_rating_filter == ["PG", "R"]
        assert criteria.rating_combine == "or"
        d = criteria.to_dict()
        assert d["ai_rating_filter"] == ["X"]
        assert d["rating_combine"] == "or"

    def test_filter_criteria_default_combine_is_and(self):
        """rating_combine の既定は 'and' (後方互換: 従来の AND 挙動)。"""
        from lorairo.database.filter_criteria import ImageFilterCriteria

        assert ImageFilterCriteria().rating_combine == "and"

    def test_search_conditions_list_to_filter_criteria(self):
        """SearchConditions の list レーティングが criteria に伝播する。"""
        from lorairo.services.search_models import SearchConditions

        conditions = SearchConditions(
            search_type="tags",
            keywords=["test"],
            tag_logic="and",
            rating_filter=["PG", "R"],
            ai_rating_filter=["X"],
            rating_combine="or",
        )
        criteria = conditions.to_filter_criteria()
        assert criteria.manual_rating_filter == ["PG", "R"]
        assert criteria.ai_rating_filter == ["X"]
        assert criteria.rating_combine == "or"

    def test_search_conditions_single_value_still_works(self):
        """後方互換: 単一 str レーティングも従来どおり criteria に伝播する。"""
        from lorairo.services.search_models import SearchConditions

        conditions = SearchConditions(
            search_type="tags",
            keywords=["test"],
            tag_logic="and",
            rating_filter="PG",
        )
        criteria = conditions.to_filter_criteria()
        assert criteria.manual_rating_filter == "PG"
        assert criteria.rating_combine == "and"


class TestMultiSelectPreviewDisplay:
    """Issue #811: マルチセレクト / OR 結合のプレビュー表示テスト。"""

    def _make_service(self):
        from lorairo.gui.services.search_filter_service import SearchFilterService

        return SearchFilterService(db_manager=Mock(), model_selection_service=Mock())

    def test_preview_shows_multi_select_or_join(self):
        """複数選択は ' / ' 区切りで表示される。"""
        from lorairo.services.search_models import SearchConditions

        service = self._make_service()
        conditions = SearchConditions(
            search_type="tags", keywords=[], tag_logic="and", rating_filter=["PG", "R"]
        )
        preview = service.create_search_preview(conditions)
        assert "手動レーティング: PG / R" in preview

    def test_preview_shows_or_combine_note(self):
        """manual / AI 両方指定 + OR 結合時に結合注記を表示する。"""
        from lorairo.services.search_models import SearchConditions

        service = self._make_service()
        conditions = SearchConditions(
            search_type="tags",
            keywords=[],
            tag_logic="and",
            rating_filter=["PG"],
            ai_rating_filter=["R"],
            rating_combine="or",
        )
        preview = service.create_search_preview(conditions)
        assert "いずれか (OR)" in preview

    def test_preview_no_or_note_for_and(self):
        """既定 (AND) では OR 結合注記を表示しない。"""
        from lorairo.services.search_models import SearchConditions

        service = self._make_service()
        conditions = SearchConditions(
            search_type="tags",
            keywords=[],
            tag_logic="and",
            rating_filter=["PG"],
            ai_rating_filter=["R"],
        )
        preview = service.create_search_preview(conditions)
        assert "いずれか (OR)" not in preview


class TestRatedPreviewDisplay:
    """RATEDフィルターのプレビュー表示テスト (Issue #561)"""

    def _make_service(self):
        from lorairo.gui.services.search_filter_service import SearchFilterService

        return SearchFilterService(db_manager=Mock(), model_selection_service=Mock())

    def test_create_search_preview_shows_rated_manual_rating(self):
        """手動レーティングRATEDを「レーティング済み」と表示することを確認"""
        from lorairo.services.search_models import SearchConditions

        service = self._make_service()
        conditions = SearchConditions(
            search_type="tags", keywords=[], tag_logic="and", rating_filter="RATED"
        )

        preview = service.create_search_preview(conditions)

        assert "手動レーティング" in preview
        assert "レーティング済み" in preview

    def test_create_search_preview_shows_rated_ai_rating(self):
        """AIレーティングRATEDを「レーティング済み」と表示し多数決注記を付けないことを確認"""
        from lorairo.services.search_models import SearchConditions

        service = self._make_service()
        conditions = SearchConditions(
            search_type="tags", keywords=[], tag_logic="and", ai_rating_filter="RATED"
        )

        preview = service.create_search_preview(conditions)

        assert "AIレーティング" in preview
        assert "レーティング済み" in preview
        # 「レーティングあり」判定に多数決は適用されない
        assert "多数決" not in preview
