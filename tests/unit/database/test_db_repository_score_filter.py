"""
ImageRepositoryのスコアフィルタ関連メソッドのテスト

このテストモジュールは、スコアフィルタ機能をテストします:
- _apply_display_score_filter(): 表示側と同じ集約スコアによる範囲フィルタ (Issue #1026)
- _representative_display_score(): フィルタ判定用の代表スコア導出
- get_images_by_filter() / get_images_count_only(): スコアフィルタ統合
"""

import uuid
from datetime import datetime
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from lorairo.database.filter_criteria import ImageFilterCriteria
from lorairo.database.repository.image import ImageRepository
from lorairo.database.schema import Image

# ---------------------------------------------------------------------------
# Helpers (Issue #1026: 集約スコアフィルタの回帰テスト用 in-memory DB)
# ---------------------------------------------------------------------------


@pytest.fixture
def memory_session_factory():
    """in-memory SQLite セッションファクトリ（schema 全テーブル）。"""
    from lorairo.database.schema import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(engine)


@pytest.fixture
def score_repository(memory_session_factory):
    """in-memory DB を使う ImageRepository。"""
    return ImageRepository(session_factory=memory_session_factory)


def _make_model(session, name: str) -> int:
    """テスト用 Model を1件作成し ID を返す。"""
    from lorairo.database.schema import Model

    model = Model(name=name, litellm_model_id=f"{name}-{uuid.uuid4().hex[:8]}")
    session.add(model)
    session.flush()
    return model.id


def _make_image_with_scores(
    session_factory,
    scores: list[tuple[float, str, bool]],
) -> int:
    """Image を1件作成し、指定の Score 行 (生値, model 名, is_edited_manually) を紐づける。

    Score.display_score 列には旧 SQL フィルタが参照していた per-row 表示値を入れて
    おき、集約フィルタが per-row ではなく代表スコアで判定することを検証できるように
    する (Issue #1026)。生値 → display_score は calibrate_to_display で算出する。
    """
    from lorairo.database.schema import Image, Score
    from lorairo.domain.score_scaler import calibrate_to_display

    with session_factory() as session:
        uid = uuid.uuid4().hex
        img = Image(
            uuid=uid,
            phash=f"aa{uid[:10]}",
            original_image_path=f"/tmp/{uid}.png",
            stored_image_path=f"/tmp/{uid}.png",
            width=100,
            height=100,
            format="PNG",
            extension="png",
        )
        session.add(img)
        session.flush()

        for i, (raw, model_name, is_manual) in enumerate(scores):
            model_id = _make_model(session, model_name)
            display = float(raw) if is_manual else calibrate_to_display(model_name, float(raw))
            session.add(
                Score(
                    image_id=img.id,
                    model_id=model_id,
                    score=raw,
                    display_score=display,
                    is_edited_manually=is_manual,
                    created_at=datetime(2025, 1, 1 + i),
                )
            )
        session.commit()
        return img.id


# image_id=838 の実データ (Issue #1026): claude 行の per-row display=10.0 が旧 exists()
# にヒットしていたが、代表スコアは手動優先で 6.08 (範囲外)。
_ISSUE_838_SCORES = [
    (8.75, "claude-3-5-sonnet-20240620", False),  # calibrate → display 10.0
    (0.958227574825287, "cafe_aesthetic", False),  # calibrate → display ~7.83
    (6.08, "MANUAL_EDIT", True),  # 手動優先 → 代表 6.08
]


class TestDisplayScoreFilterAggregation:
    """_apply_display_score_filter() の集約スコア判定テスト (Issue #1026)。"""

    @pytest.mark.unit
    def test_manual_priority_excludes_out_of_range_per_row_hit(
        self, score_repository, memory_session_factory
    ):
        """手動 6.08 の画像は 9.11-10.0 フィルタにヒットしない (per-row display=10.0 でも除外)。"""
        image_id = _make_image_with_scores(memory_session_factory, _ISSUE_838_SCORES)

        results, count = score_repository.get_images_by_filter(
            ImageFilterCriteria(score_min=9.11, score_max=10.0)
        )

        assert count == 0
        assert image_id not in [m["id"] for m in results]

    @pytest.mark.unit
    def test_filter_and_display_use_same_aggregate(self, score_repository, memory_session_factory):
        """フィルタ判定と詳細パネル表示が同一の集約値 (代表 6.08) を通ることを固定する。"""
        image_id = _make_image_with_scores(memory_session_factory, _ISSUE_838_SCORES)

        # 表示側の集約スコア (代表値) は manual 優先で 6.08。
        with memory_session_factory() as session:
            from sqlalchemy.orm import selectinload

            from lorairo.database.schema import Score

            image = session.execute(
                select(Image)
                .where(Image.id == image_id)
                .options(selectinload(Image.scores).selectinload(Score.model))
            ).scalar_one()
            display_score = ImageRepository._derive_display_score(image)
        assert display_score == pytest.approx(6.08)

        # 表示スコア 6.08 を含む範囲ではヒットし、含まない範囲では除外される。
        assert (
            score_repository.get_images_count_only(ImageFilterCriteria(score_min=6.0, score_max=6.5)) == 1
        )
        assert (
            score_repository.get_images_count_only(ImageFilterCriteria(score_min=9.11, score_max=10.0)) == 0
        )

    @pytest.mark.unit
    def test_ai_only_uses_weighted_average_not_per_row(self, score_repository, memory_session_factory):
        """手動なし・複数 AI モデルは重み付き平均で判定する (単独行の 10.0 ではヒットしない)。"""
        # claude(→10.0) と cafe(→~7.83) の平均 ~8.916。
        image_id = _make_image_with_scores(
            memory_session_factory,
            [
                (8.75, "claude-3-5-sonnet-20240620", False),
                (0.958227574825287, "cafe_aesthetic", False),
            ],
        )

        # 集約 8.916 を含む範囲ではヒット。
        assert (
            score_repository.get_images_count_only(ImageFilterCriteria(score_min=8.5, score_max=9.0)) == 1
        )
        # claude 単独行の display=10.0 は範囲内だが、集約 8.916 は範囲外なので除外。
        assert (
            score_repository.get_images_count_only(ImageFilterCriteria(score_min=9.11, score_max=10.0)) == 0
        )
        _ = image_id

    @pytest.mark.unit
    def test_image_without_scores_is_excluded(self, score_repository, memory_session_factory):
        """スコア行が無い画像はどの範囲にもヒットしない (従来の exists() と同じ挙動)。"""
        _make_image_with_scores(memory_session_factory, [])

        assert (
            score_repository.get_images_count_only(ImageFilterCriteria(score_min=0.0, score_max=10.0)) == 0
        )

    @pytest.mark.unit
    def test_count_matches_results_length(self, score_repository, memory_session_factory):
        """count と get_images_by_filter の結果件数が一致する (ページング整合)。"""
        _make_image_with_scores(memory_session_factory, [(6.08, "MANUAL_EDIT", True)])
        _make_image_with_scores(memory_session_factory, [(3.0, "MANUAL_EDIT", True)])
        _make_image_with_scores(memory_session_factory, [(9.5, "MANUAL_EDIT", True)])

        criteria = ImageFilterCriteria(score_min=5.0, score_max=7.0)
        results, count = score_repository.get_images_by_filter(criteria)
        count_only = score_repository.get_images_count_only(criteria)

        assert count == 1  # 6.08 のみ該当
        assert len(results) == count
        assert count_only == count

    @pytest.mark.unit
    def test_no_score_filter_returns_query_unchanged(self, score_repository):
        """score_min/score_max ともに None のときはクエリを変更しない。"""
        base_query = select(Image.id)
        with score_repository.session_factory() as session:
            result = score_repository._apply_display_score_filter(session, base_query, None, None)
        assert result is base_query


class TestRepresentativeDisplayScore:
    """_representative_display_score() の代表スコア導出テスト (Issue #1026)。"""

    @pytest.mark.unit
    def test_no_scores_returns_none(self):
        """スコア行が無い場合は None (表示側 0.0 と区別する)。"""
        image = Mock(spec=Image)
        image.scores = []
        assert ImageRepository._representative_display_score(image) is None

    @pytest.mark.unit
    def test_manual_takes_priority(self):
        """手動行があれば手動生値を代表値として返す。"""
        from lorairo.database.schema import Score

        manual = Mock(spec=Score)
        manual.score = 6.08
        manual.is_edited_manually = True
        manual.created_at = datetime(2025, 1, 2)
        manual.model_id = 1
        manual.model = Mock()
        manual.model.name = "MANUAL_EDIT"
        image = Mock(spec=Image)
        image.scores = [manual]
        assert ImageRepository._representative_display_score(image) == pytest.approx(6.08)


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
        mock_execute_result.scalar_one.return_value = 0
        mock_execute_result.scalars = Mock(return_value=Mock(all=Mock(return_value=[])))
        mock_session.execute = Mock(return_value=mock_execute_result)

        repository = ImageRepository(session_factory=mock_session_factory)
        return repository, mock_session

    def test_score_filter_parameter_passing(self, mock_session_and_repository):
        """score_min/score_max パラメータが正しく渡されることを確認"""
        repository, mock_session = mock_session_and_repository

        # スコアフィルタを指定して検索
        results, count = repository.get_images_by_filter(ImageFilterCriteria(score_min=3.0, score_max=7.5))

        # クエリが実行されたことを確認
        assert mock_session.execute.called
        assert results == []
        assert count == 0

    def test_score_filter_only_min(self, mock_session_and_repository):
        """score_min のみが指定された場合、適用されることを確認"""
        repository, mock_session = mock_session_and_repository

        _results, _count = repository.get_images_by_filter(ImageFilterCriteria(score_min=5.0))

        # クエリが実行されたことを確認
        assert mock_session.execute.called

    def test_score_filter_only_max(self, mock_session_and_repository):
        """score_max のみが指定された場合、適用されることを確認"""
        repository, mock_session = mock_session_and_repository

        _results, _count = repository.get_images_by_filter(ImageFilterCriteria(score_max=8.0))

        # クエリが実行されたことを確認
        assert mock_session.execute.called


class TestSearchConditionsIntegration:
    """SearchConditions データモデルのスコアフィルタ統合テスト"""

    def test_search_conditions_to_filter_criteria_includes_score(self):
        """SearchConditions.to_filter_criteria() が score_min/score_max を含むことを確認"""
        from lorairo.services.search_models import SearchConditions

        conditions = SearchConditions(
            search_type="tags",
            keywords=["test"],
            tag_logic="and",
            score_min=3.0,
            score_max=7.5,
        )

        criteria = conditions.to_filter_criteria()

        assert criteria.score_min == 3.0
        assert criteria.score_max == 7.5


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


class TestGetImagesCountOnly:
    """get_images_count_only() メソッドのテスト"""

    @pytest.fixture
    def mock_session_and_repository(self):
        from sqlalchemy.orm import Session

        mock_session = Mock(spec=Session)
        mock_session_factory = Mock(return_value=mock_session)

        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=None)

        count_result = Mock()
        count_result.scalar_one = Mock(return_value=3)
        # _apply_display_score_filter が候補 id を取得する経路も stub する (Issue #1026)。
        count_result.scalars = Mock(return_value=Mock(all=Mock(return_value=[])))
        mock_session.execute = Mock(return_value=count_result)

        repository = ImageRepository(session_factory=mock_session_factory)
        return repository

    def test_get_images_count_only_returns_count(self, mock_session_and_repository):
        repository = mock_session_and_repository

        count = repository.get_images_count_only(ImageFilterCriteria(score_min=3.0, score_max=7.5))

        assert count == 3


class TestSearchFilterServiceEstimatedCount:
    """SearchFilterService.get_estimated_count() のテスト"""

    def test_get_estimated_count_delegates_to_db_manager(self):
        from lorairo.gui.services.search_filter_service import SearchFilterService

        mock_db_manager = Mock()
        mock_db_manager.get_images_count_only.return_value = 42
        mock_model_selection_service = Mock()

        service = SearchFilterService(
            db_manager=mock_db_manager,
            model_selection_service=mock_model_selection_service,
        )

        conditions = service.create_search_conditions(
            search_type="tags",
            keywords=["test"],
            tag_logic="and",
        )

        assert service.get_estimated_count(conditions) == 42
        mock_db_manager.get_images_count_only.assert_called_once()


class TestSearchConditionsExcludedTags:
    """SearchConditions の除外タグ機能テスト"""

    def test_search_conditions_to_filter_criteria_includes_excluded_tags(self):
        """SearchConditions.to_filter_criteria() が excluded_tags を含むことを確認"""
        from lorairo.services.search_models import SearchConditions

        conditions = SearchConditions(
            search_type="tags",
            keywords=["1girl"],
            tag_logic="and",
            excluded_keywords=["1boy"],
        )

        criteria = conditions.to_filter_criteria()

        assert criteria.excluded_tags == ["1boy"]


class TestApplyTagFilterExcludeIntegration:
    """_apply_tag_filter() の除外タグ統合テスト"""

    @pytest.fixture
    def repository(self):
        from unittest.mock import Mock

        mock_session_factory = Mock()
        return ImageRepository(session_factory=mock_session_factory)

    def test_apply_tag_filter_with_excluded_tags(self, repository):
        """除外タグ指定時にクエリが更新されることを確認"""
        from sqlalchemy import select

        from lorairo.database.schema import Image

        base_query = select(Image.id)

        result_query = repository._apply_tag_filter(
            base_query,
            tags=["1girl"],
            excluded_tags=["1boy"],
            use_and=True,
            include_untagged=False,
        )

        assert result_query is not None
        assert result_query != base_query

    def test_apply_tag_filter_only_excluded_tags(self, repository):
        """除外タグのみ指定時もクエリが更新されることを確認"""
        from sqlalchemy import select

        from lorairo.database.schema import Image

        base_query = select(Image.id)

        result_query = repository._apply_tag_filter(
            base_query,
            tags=None,
            excluded_tags=["nsfw"],
            use_and=True,
            include_untagged=False,
        )

        assert result_query is not None
        assert result_query != base_query
