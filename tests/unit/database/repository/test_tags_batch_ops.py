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


@pytest.mark.unit
class TestReplaceTagForImagesBatch:
    def test_replaces_tag_changed(self, repo, mock_session):
        """変換元あり・変換先なし → changed。"""
        repo._build_existing_tags_map = MagicMock(return_value={123: {"bad_tag"}})
        repo._get_or_create_tag_id_external = MagicMock(return_value=42)
        mock_session.execute = MagicMock(return_value=MagicMock())
        mock_session.add = MagicMock()

        ok, results = repo.replace_tag_for_images_batch([123], "bad_tag", "good_tag")

        assert ok is True
        assert results == [(123, "changed")]
        mock_session.commit.assert_called_once()

    def test_replaces_tag_to_already_exists(self, repo, mock_session):
        """変換元あり・変換先あり → 変換元削除のみ、changed。"""
        repo._build_existing_tags_map = MagicMock(return_value={123: {"bad_tag", "good_tag"}})
        repo._get_or_create_tag_id_external = MagicMock(return_value=42)
        mock_session.execute = MagicMock(return_value=MagicMock())

        ok, results = repo.replace_tag_for_images_batch([123], "bad_tag", "good_tag")

        assert ok is True
        assert results == [(123, "changed")]

    def test_skips_when_from_tag_not_found(self, repo, mock_session):
        """変換元なし → skipped。"""
        repo._build_existing_tags_map = MagicMock(return_value={123: {"other_tag"}})

        ok, results = repo.replace_tag_for_images_batch([123], "bad_tag", "good_tag")

        assert ok is True
        assert results == [(123, "skipped")]

    def test_empty_image_ids_returns_false(self, repo, mock_session):
        """空の image_ids → (False, [])。"""
        ok, results = repo.replace_tag_for_images_batch([], "bad_tag", "good_tag")
        assert ok is False
        assert results == []

    def test_empty_from_tag_returns_false(self, repo, mock_session):
        """空の from_tag → (False, [])。"""
        ok, results = repo.replace_tag_for_images_batch([123], "", "good_tag")
        assert ok is False
        assert results == []

    def test_db_error_rolls_back_and_reraises(self, repo, mock_session):
        """DB エラー時にロールバックして再送出。"""
        from sqlalchemy.exc import SQLAlchemyError

        repo._build_existing_tags_map = MagicMock(side_effect=SQLAlchemyError("db error"))
        with pytest.raises(SQLAlchemyError):
            repo.replace_tag_for_images_batch([123], "bad_tag", "good_tag")
        mock_session.rollback.assert_called_once()


@pytest.mark.unit
class TestRestoreTagForImagesBatch:
    def test_restores_rejected_tag_returns_per_item(self, repo, mock_session):
        mock_session.execute = MagicMock(return_value=MagicMock(scalars=MagicMock(return_value=[123])))

        ok, results = repo.restore_tag_for_images_batch([123, 456], "bad_tag")

        assert ok is True
        assert (123, "changed") in results
        assert (456, "skipped") in results
        mock_session.commit.assert_called_once()

    def test_empty_image_ids_returns_false(self, repo, mock_session):
        ok, results = repo.restore_tag_for_images_batch([], "bad_tag")
        assert ok is False
        assert results == []

    def test_empty_tag_returns_false(self, repo, mock_session):
        ok, results = repo.restore_tag_for_images_batch([123], "  ")
        assert ok is False
        assert results == []

    def test_db_error_rolls_back_and_reraises(self, repo, mock_session):
        from sqlalchemy.exc import SQLAlchemyError

        mock_session.execute = MagicMock(side_effect=SQLAlchemyError("db error"))
        with pytest.raises(SQLAlchemyError):
            repo.restore_tag_for_images_batch([123], "bad_tag")
        mock_session.rollback.assert_called_once()


@pytest.mark.unit
class TestGetRejectedTags:
    def test_returns_rejected_tag_dicts(self, repo, mock_session):
        row = MagicMock(tag="bad_tag", tag_id=7, is_edited_manually=False)
        mock_session.execute = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[row])))

        result = repo.get_rejected_tags(42)

        assert result == [{"tag": "bad_tag", "tag_id": 7, "is_edited_manually": False}]

    def test_empty_when_no_rejected(self, repo, mock_session):
        mock_session.execute = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        assert repo.get_rejected_tags(42) == []
