"""
ImageRepository のエラーレコード関連メソッドのテスト
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, Mock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from lorairo.database.db_repository import ImageRepository
from lorairo.database.schema import ErrorRecord, Image


class TestSaveErrorRecord:
    """save_error_record メソッドのテスト"""

    @pytest.fixture
    def repository(self):
        """テスト用ImageRepository"""
        mock_session_factory = MagicMock()
        return ImageRepository(session_factory=mock_session_factory)

    def test_save_error_record_with_all_fields(self, repository):
        """全フィールドを持つエラーレコードの保存"""
        mock_session = Mock()
        mock_record = Mock(spec=ErrorRecord)
        mock_record.id = 1
        repository.session_factory.return_value.__enter__.return_value = mock_session

        error_id = repository.save_error_record(
            operation_type="annotation",
            error_type="API error",
            error_message="Test error",
            image_id=100,
            stack_trace="Stack trace here",
            file_path="/path/to/file.jpg",
            model_name="gpt-4",
        )

        assert mock_session.add.called
        assert mock_session.flush.called
        assert mock_session.commit.called

    def test_save_error_record_minimal_fields(self, repository):
        """最小フィールドのみでのエラーレコード保存"""
        mock_session = Mock()
        mock_record = Mock(spec=ErrorRecord)
        mock_record.id = 2
        repository.session_factory.return_value.__enter__.return_value = mock_session

        error_id = repository.save_error_record(
            operation_type="annotation",
            error_type="API error",
            error_message="Test error",
        )

        assert mock_session.add.called
        assert mock_session.commit.called

    def test_save_error_record_database_error(self, repository):
        """データベースエラー時の例外処理"""
        mock_session = Mock()
        mock_session.add.side_effect = SQLAlchemyError("DB Error")
        repository.session_factory.return_value.__enter__.return_value = mock_session

        with pytest.raises(SQLAlchemyError):
            repository.save_error_record(
                operation_type="annotation",
                error_type="API error",
                error_message="Test error",
            )

        assert mock_session.rollback.called


class TestGetErrorCountUnresolved:
    """get_error_count_unresolved メソッドのテスト"""

    @pytest.fixture
    def repository(self):
        """テスト用ImageRepository"""
        mock_session_factory = MagicMock()
        return ImageRepository(session_factory=mock_session_factory)

    def test_get_error_count_all_operations(self, repository):
        """全操作種別の未解決エラー件数取得"""
        mock_session = Mock()
        mock_session.execute.return_value.scalar.return_value = 5
        repository.session_factory.return_value.__enter__.return_value = mock_session

        count = repository.get_error_count_unresolved()

        assert count == 5
        assert mock_session.execute.called

    def test_get_error_count_specific_operation(self, repository):
        """特定操作種別の未解決エラー件数取得"""
        mock_session = Mock()
        mock_session.execute.return_value.scalar.return_value = 3
        repository.session_factory.return_value.__enter__.return_value = mock_session

        count = repository.get_error_count_unresolved(operation_type="annotation")

        assert count == 3

    def test_get_error_count_no_errors(self, repository):
        """エラーが存在しない場合"""
        mock_session = Mock()
        mock_session.execute.return_value.scalar.return_value = None
        repository.session_factory.return_value.__enter__.return_value = mock_session

        count = repository.get_error_count_unresolved()

        assert count == 0


class TestGetErrorImageIds:
    """get_error_image_ids メソッドのテスト"""

    @pytest.fixture
    def repository(self):
        """テスト用ImageRepository"""
        mock_session_factory = MagicMock()
        return ImageRepository(session_factory=mock_session_factory)

    def test_get_error_image_ids_unresolved(self, repository):
        """未解決エラー画像ID取得"""
        mock_session = Mock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = [1, 2, 3]
        repository.session_factory.return_value.__enter__.return_value = mock_session

        image_ids = repository.get_error_image_ids(resolved=False)

        assert image_ids == [1, 2, 3]
        assert mock_session.execute.called

    def test_get_error_image_ids_resolved(self, repository):
        """解決済みエラー画像ID取得"""
        mock_session = Mock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = [4, 5]
        repository.session_factory.return_value.__enter__.return_value = mock_session

        image_ids = repository.get_error_image_ids(resolved=True)

        assert image_ids == [4, 5]

    def test_get_error_image_ids_with_operation_type(self, repository):
        """特定操作種別のエラー画像ID取得"""
        mock_session = Mock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = [1, 2]
        repository.session_factory.return_value.__enter__.return_value = mock_session

        image_ids = repository.get_error_image_ids(operation_type="annotation", resolved=False)

        assert image_ids == [1, 2]

    def test_get_error_image_ids_filter_none_values(self, repository):
        """None値を除外"""
        mock_session = Mock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = [
            1,
            None,
            2,
            None,
            3,
        ]
        repository.session_factory.return_value.__enter__.return_value = mock_session

        image_ids = repository.get_error_image_ids(resolved=False)

        assert image_ids == [1, 2, 3]


class TestGetImagesByIds:
    """get_images_by_ids メソッドのテスト"""

    @pytest.fixture
    def repository(self):
        """テスト用ImageRepository"""
        mock_session_factory = MagicMock()
        return ImageRepository(session_factory=mock_session_factory)

    def test_get_images_by_ids_empty_list(self, repository):
        """空のIDリストでの取得"""
        result = repository.get_images_by_ids([])

        assert result == []

    def test_get_images_by_ids_with_annotations(self, repository):
        """アノテーション情報を含む画像取得"""
        mock_session = Mock()
        mock_image = Mock(spec=Image)
        mock_image.id = 1
        mock_image.__table__ = Mock()
        mock_image.__table__.columns = []
        mock_image.tags = []
        mock_image.captions = []
        mock_image.scores = []
        mock_image.ratings = []

        mock_session.execute.return_value.unique.return_value.scalars.return_value.all.return_value = [
            mock_image
        ]
        repository.session_factory.return_value.__enter__.return_value = mock_session

        with patch.object(repository, "_format_annotations_for_metadata", return_value={}):
            images = repository.get_images_by_ids([1])

        assert len(images) == 1
        assert mock_session.execute.called


class TestGetErrorRecords:
    """get_error_records メソッドのテスト"""

    @pytest.fixture
    def repository(self):
        """テスト用ImageRepository"""
        mock_session_factory = MagicMock()
        return ImageRepository(session_factory=mock_session_factory)

    def test_get_error_records_all(self, repository):
        """全エラーレコード取得"""
        mock_session = Mock()
        mock_records = [Mock(spec=ErrorRecord) for _ in range(3)]
        mock_session.execute.return_value.scalars.return_value.all.return_value = mock_records
        repository.session_factory.return_value.__enter__.return_value = mock_session

        records = repository.get_error_records()

        assert len(records) == 3
        assert mock_session.execute.called

    def test_get_error_records_with_filters(self, repository):
        """フィルタ付きエラーレコード取得"""
        mock_session = Mock()
        mock_records = [Mock(spec=ErrorRecord) for _ in range(2)]
        mock_session.execute.return_value.scalars.return_value.all.return_value = mock_records
        repository.session_factory.return_value.__enter__.return_value = mock_session

        records = repository.get_error_records(
            operation_type="annotation", resolved=False, limit=10, offset=0
        )

        assert len(records) == 2

    def test_get_error_records_pagination(self, repository):
        """ページネーション機能のテスト"""
        mock_session = Mock()
        mock_records = [Mock(spec=ErrorRecord) for _ in range(5)]
        mock_session.execute.return_value.scalars.return_value.all.return_value = mock_records
        repository.session_factory.return_value.__enter__.return_value = mock_session

        records = repository.get_error_records(limit=5, offset=10)

        assert len(records) == 5


class TestMarkErrorResolved:
    """mark_error_resolved メソッドのテスト"""

    @pytest.fixture
    def repository(self):
        """テスト用ImageRepository"""
        mock_session_factory = MagicMock()
        return ImageRepository(session_factory=mock_session_factory)

    def test_mark_error_resolved_success(self, repository):
        """エラー解決マークの成功"""
        mock_session = Mock()
        mock_record = Mock(spec=ErrorRecord)
        mock_record.resolved_at = None
        mock_session.get.return_value = mock_record
        repository.session_factory.return_value.__enter__.return_value = mock_session

        repository.mark_error_resolved(error_id=1)

        assert mock_record.resolved_at is not None
        assert mock_session.commit.called

    def test_mark_error_resolved_not_found(self, repository):
        """存在しないエラーIDの場合"""
        mock_session = Mock()
        mock_session.get.return_value = None
        repository.session_factory.return_value.__enter__.return_value = mock_session

        repository.mark_error_resolved(error_id=999)

        assert not mock_session.commit.called

    def test_mark_error_resolved_database_error(self, repository):
        """データベースエラー時の例外処理"""
        mock_session = Mock()
        mock_record = Mock(spec=ErrorRecord)
        mock_session.get.return_value = mock_record
        mock_session.commit.side_effect = SQLAlchemyError("DB Error")
        repository.session_factory.return_value.__enter__.return_value = mock_session

        with pytest.raises(SQLAlchemyError):
            repository.mark_error_resolved(error_id=1)

        assert mock_session.rollback.called


class TestGetSession:
    """get_session メソッドのテスト"""

    @pytest.fixture
    def repository(self):
        """テスト用ImageRepository"""
        mock_session_factory = MagicMock()
        return ImageRepository(session_factory=mock_session_factory)

    def test_get_session_returns_session(self, repository):
        """セッション取得の確認"""
        mock_session = Mock()
        repository.session_factory.return_value = mock_session

        session = repository.get_session()

        assert session == mock_session
        assert repository.session_factory.called
