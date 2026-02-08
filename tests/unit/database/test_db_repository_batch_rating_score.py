"""ImageRepositoryのバッチRating/Score更新メソッドのテスト

複数画像のRating/Scoreを一括更新する機能をテストする。
"""

from unittest.mock import MagicMock, Mock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from lorairo.database.db_repository import ImageRepository
from lorairo.database.schema import Rating, Score


class TestUpdateRatingBatch:
    """update_rating_batch メソッドのテスト"""

    @pytest.fixture
    def repository(self):
        """テスト用ImageRepository"""
        mock_session_factory = Mock()
        return ImageRepository(session_factory=mock_session_factory)

    @pytest.fixture
    def mock_session(self):
        """モックセッション"""
        session = MagicMock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        return session

    def test_empty_list_returns_false(self, repository, mock_session):
        """空リストを渡すとFalseが返る"""
        repository.session_factory.return_value = mock_session
        success, count = repository.update_rating_batch([], "PG-13", 1)
        assert success is False
        assert count == 0

    def test_empty_rating_returns_false(self, repository, mock_session):
        """空のrating値を渡すとFalseが返る"""
        repository.session_factory.return_value = mock_session
        success, count = repository.update_rating_batch([1, 2], "", 1)
        assert success is False
        assert count == 0

    def test_update_existing_ratings(self, repository, mock_session):
        """既存レコードがある場合、UPDATE される"""
        repository.session_factory.return_value = mock_session

        # 既存の Rating レコードをモック
        existing_rating_1 = Rating(
            id=1,
            image_id=100,
            model_id=1,
            raw_rating_value="PG",
            normalized_rating="PG",
        )
        existing_rating_2 = Rating(
            id=2,
            image_id=200,
            model_id=1,
            raw_rating_value="R",
            normalized_rating="R",
        )

        # select().where(Rating.image_id.in_(...)) のモック
        mock_execute_result = MagicMock()
        mock_execute_result.scalars.return_value.all.return_value = [
            existing_rating_1,
            existing_rating_2,
        ]
        mock_session.execute.return_value = mock_execute_result

        success, count = repository.update_rating_batch([100, 200], "PG-13", 2)

        assert success is True
        assert count == 2
        # 既存レコードが UPDATE されている
        assert existing_rating_1.normalized_rating == "PG-13"
        assert existing_rating_1.raw_rating_value == "PG-13"
        assert existing_rating_1.model_id == 2
        assert existing_rating_2.normalized_rating == "PG-13"
        assert existing_rating_2.raw_rating_value == "PG-13"
        assert existing_rating_2.model_id == 2
        mock_session.commit.assert_called_once()

    def test_insert_new_ratings(self, repository, mock_session):
        """既存レコードがない場合、INSERT される"""
        repository.session_factory.return_value = mock_session

        # 既存レコードなし
        mock_execute_result = MagicMock()
        mock_execute_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_execute_result

        success, count = repository.update_rating_batch([100, 200], "X", 3)

        assert success is True
        assert count == 2
        # session.add() が2回呼ばれている（INSERT）
        assert mock_session.add.call_count == 2
        mock_session.commit.assert_called_once()

    def test_mixed_update_and_insert(self, repository, mock_session):
        """既存レコードと新規レコードが混在する場合"""
        repository.session_factory.return_value = mock_session

        # image_id=100 は既存、image_id=200 は新規
        existing_rating = Rating(
            id=1,
            image_id=100,
            model_id=1,
            raw_rating_value="PG",
            normalized_rating="PG",
        )

        mock_execute_result = MagicMock()
        mock_execute_result.scalars.return_value.all.return_value = [existing_rating]
        mock_session.execute.return_value = mock_execute_result

        success, count = repository.update_rating_batch([100, 200], "XXX", 4)

        assert success is True
        assert count == 2
        # image_id=100 は UPDATE
        assert existing_rating.normalized_rating == "XXX"
        # image_id=200 は INSERT
        assert mock_session.add.call_count == 1
        mock_session.commit.assert_called_once()

    def test_transaction_failure_rolls_back(self, repository, mock_session):
        """トランザクション失敗時、全件ロールバックされる"""
        repository.session_factory.return_value = mock_session

        # commit() で例外を発生させる
        mock_session.commit.side_effect = SQLAlchemyError("DB error")

        mock_execute_result = MagicMock()
        mock_execute_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_execute_result

        with pytest.raises(SQLAlchemyError):
            repository.update_rating_batch([100, 200], "R", 1)

        mock_session.rollback.assert_called_once()


class TestUpdateScoreBatch:
    """update_score_batch メソッドのテスト"""

    @pytest.fixture
    def repository(self):
        """テスト用ImageRepository"""
        mock_session_factory = Mock()
        return ImageRepository(session_factory=mock_session_factory)

    @pytest.fixture
    def mock_session(self):
        """モックセッション"""
        session = MagicMock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        return session

    def test_empty_list_returns_false(self, repository, mock_session):
        """空リストを渡すとFalseが返る"""
        repository.session_factory.return_value = mock_session
        success, count = repository.update_score_batch([], 5.0, 1)
        assert success is False
        assert count == 0

    def test_invalid_score_returns_false(self, repository, mock_session):
        """不正なスコア値を渡すとFalseが返る"""
        repository.session_factory.return_value = mock_session

        # スコアが範囲外（0.0-10.0）
        success, count = repository.update_score_batch([1, 2], -1.0, 1)
        assert success is False
        assert count == 0

        success, count = repository.update_score_batch([1, 2], 11.0, 1)
        assert success is False
        assert count == 0

    def test_update_existing_scores(self, repository, mock_session):
        """既存レコードがある場合、UPDATE される"""
        repository.session_factory.return_value = mock_session

        # 既存の Score レコードをモック
        existing_score_1 = Score(
            id=1,
            image_id=100,
            model_id=1,
            score=5.0,
            is_edited_manually=False,
        )
        existing_score_2 = Score(
            id=2,
            image_id=200,
            model_id=1,
            score=7.5,
            is_edited_manually=False,
        )

        mock_execute_result = MagicMock()
        mock_execute_result.scalars.return_value.all.return_value = [
            existing_score_1,
            existing_score_2,
        ]
        mock_session.execute.return_value = mock_execute_result

        success, count = repository.update_score_batch([100, 200], 8.5, 2)

        assert success is True
        assert count == 2
        # 既存レコードが UPDATE されている
        assert existing_score_1.score == 8.5
        assert existing_score_1.model_id == 2
        assert existing_score_1.is_edited_manually is True
        assert existing_score_2.score == 8.5
        assert existing_score_2.model_id == 2
        assert existing_score_2.is_edited_manually is True
        mock_session.commit.assert_called_once()

    def test_insert_new_scores(self, repository, mock_session):
        """既存レコードがない場合、INSERT される"""
        repository.session_factory.return_value = mock_session

        # 既存レコードなし
        mock_execute_result = MagicMock()
        mock_execute_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_execute_result

        success, count = repository.update_score_batch([100, 200], 6.0, 3)

        assert success is True
        assert count == 2
        # session.add() が2回呼ばれている（INSERT）
        assert mock_session.add.call_count == 2
        mock_session.commit.assert_called_once()

    def test_mixed_update_and_insert(self, repository, mock_session):
        """既存レコードと新規レコードが混在する場合"""
        repository.session_factory.return_value = mock_session

        # image_id=100 は既存、image_id=200 は新規
        existing_score = Score(
            id=1,
            image_id=100,
            model_id=1,
            score=4.0,
            is_edited_manually=False,
        )

        mock_execute_result = MagicMock()
        mock_execute_result.scalars.return_value.all.return_value = [existing_score]
        mock_session.execute.return_value = mock_execute_result

        success, count = repository.update_score_batch([100, 200], 9.0, None)

        assert success is True
        assert count == 2
        # image_id=100 は UPDATE
        assert existing_score.score == 9.0
        assert existing_score.model_id is None
        # image_id=200 は INSERT
        assert mock_session.add.call_count == 1
        mock_session.commit.assert_called_once()

    def test_transaction_failure_rolls_back(self, repository, mock_session):
        """トランザクション失敗時、全件ロールバックされる"""
        repository.session_factory.return_value = mock_session

        # commit() で例外を発生させる
        mock_session.commit.side_effect = SQLAlchemyError("DB error")

        mock_execute_result = MagicMock()
        mock_execute_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_execute_result

        with pytest.raises(SQLAlchemyError):
            repository.update_score_batch([100, 200], 7.0, 1)

        mock_session.rollback.assert_called_once()
