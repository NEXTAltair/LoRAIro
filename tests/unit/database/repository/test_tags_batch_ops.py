"""AnnotationRepository タグ削除・置換バッチ操作のユニットテスト。"""

from unittest.mock import MagicMock

import pytest

from lorairo.database.repository.annotation_record import AnnotationRepository


@pytest.fixture
def mock_session():
    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    return session


@pytest.fixture
def repo(mock_session):
    repo = AnnotationRepository.__new__(AnnotationRepository)
    repo.session_factory = MagicMock(return_value=mock_session)
    return repo


@pytest.mark.unit
class TestRemoveTagFromImagesBatch:
    def test_removes_existing_tag_returns_per_item_results(self, repo, mock_session):
        repo._build_existing_tags_map = MagicMock(return_value={123: {"bad_tag"}, 456: {"bad_tag"}})
        mock_session.execute = MagicMock(return_value=MagicMock())

        ok, results = repo.remove_tag_from_images_batch([123, 456], "bad_tag")

        assert ok is True
        assert results == [(123, "changed"), (456, "changed")]
        mock_session.commit.assert_called_once()

    def test_skips_images_without_tag(self, repo, mock_session):
        repo._build_existing_tags_map = MagicMock(return_value={123: {"other_tag"}, 456: {"bad_tag"}})
        mock_session.execute = MagicMock(return_value=MagicMock())

        ok, results = repo.remove_tag_from_images_batch([123, 456], "bad_tag")

        assert ok is True
        assert (123, "skipped") in results
        assert (456, "changed") in results

    def test_empty_image_ids_returns_false(self, repo, mock_session):
        ok, results = repo.remove_tag_from_images_batch([], "bad_tag")
        assert ok is False
        assert results == []

    def test_empty_tag_returns_false(self, repo, mock_session):
        ok, results = repo.remove_tag_from_images_batch([123], "")
        assert ok is False
        assert results == []

    def test_db_error_rolls_back_and_reraises(self, repo, mock_session):
        from sqlalchemy.exc import SQLAlchemyError

        repo._build_existing_tags_map = MagicMock(side_effect=SQLAlchemyError("db error"))
        with pytest.raises(SQLAlchemyError):
            repo.remove_tag_from_images_batch([123], "bad_tag")
        mock_session.rollback.assert_called_once()
