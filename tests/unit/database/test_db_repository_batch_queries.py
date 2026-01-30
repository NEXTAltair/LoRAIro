"""ImageRepositoryのバッチクエリメソッドのテスト

N+1クエリ解消のために追加されたバッチメソッドをテストする。
"""

from unittest.mock import MagicMock, Mock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from lorairo.database.db_repository import ImageRepository
from lorairo.database.schema import Caption, Image, Model, Tag


class TestGetImagesMetadataBatch:
    """get_images_metadata_batch メソッドのテスト"""

    @pytest.fixture
    def repository(self):
        """テスト用ImageRepository"""
        mock_session_factory = Mock()
        return ImageRepository(session_factory=mock_session_factory)

    def test_empty_list_returns_empty(self, repository):
        """空リストを渡すと空リストが返る"""
        result = repository.get_images_metadata_batch([])
        assert result == []

    def test_calls_fetch_filtered_metadata(self, repository):
        """_fetch_filtered_metadata を resolution=0 で呼び出す"""
        mock_session = MagicMock()
        repository.session_factory.return_value.__enter__ = Mock(return_value=mock_session)
        repository.session_factory.return_value.__exit__ = Mock(return_value=False)

        expected = [{"id": 1, "filename": "a.jpg"}, {"id": 2, "filename": "b.jpg"}]
        with patch.object(repository, "_fetch_filtered_metadata", return_value=expected) as mock_fetch:
            result = repository.get_images_metadata_batch([1, 2])

        mock_fetch.assert_called_once_with(mock_session, [1, 2], resolution=0)
        assert result == expected

    def test_chunking_splits_large_input(self, repository):
        """BATCH_CHUNK_SIZE を超える入力がチャンク分割される"""
        repository.BATCH_CHUNK_SIZE = 3  # テスト用に小さくする
        mock_session = MagicMock()
        repository.session_factory.return_value.__enter__ = Mock(return_value=mock_session)
        repository.session_factory.return_value.__exit__ = Mock(return_value=False)

        # 各チャンクで異なる結果を返す
        with patch.object(
            repository,
            "_fetch_filtered_metadata",
            side_effect=[
                [{"id": 1}, {"id": 2}, {"id": 3}],
                [{"id": 4}, {"id": 5}],
            ],
        ) as mock_fetch:
            result = repository.get_images_metadata_batch([1, 2, 3, 4, 5])

        assert mock_fetch.call_count == 2
        assert len(result) == 5

    def test_propagates_sqlalchemy_error(self, repository):
        """SQLAlchemyError が伝播する"""
        mock_session = MagicMock()
        repository.session_factory.return_value.__enter__ = Mock(return_value=mock_session)
        repository.session_factory.return_value.__exit__ = Mock(return_value=False)

        with patch.object(
            repository,
            "_fetch_filtered_metadata",
            side_effect=SQLAlchemyError("test"),
        ):
            with pytest.raises(SQLAlchemyError):
                repository.get_images_metadata_batch([1])


class TestGetAnnotatedImageIds:
    """get_annotated_image_ids メソッドのテスト"""

    @pytest.fixture
    def repository(self):
        """テスト用ImageRepository"""
        mock_session_factory = Mock()
        return ImageRepository(session_factory=mock_session_factory)

    def test_empty_list_returns_empty_set(self, repository):
        """空リストを渡すと空セットが返る"""
        result = repository.get_annotated_image_ids([])
        assert result == set()

    def test_returns_annotated_ids_as_set(self, repository):
        """アノテーション済みIDをsetで返す"""
        mock_session = MagicMock()
        repository.session_factory.return_value.__enter__ = Mock(return_value=mock_session)
        repository.session_factory.return_value.__exit__ = Mock(return_value=False)

        # scalars().all() が [1, 3] を返す（ID 2 はアノテーション無し）
        mock_session.execute.return_value.scalars.return_value.all.return_value = [1, 3]

        result = repository.get_annotated_image_ids([1, 2, 3])
        assert result == {1, 3}

    def test_chunking_merges_results(self, repository):
        """チャンク分割結果がsetにマージされる"""
        repository.BATCH_CHUNK_SIZE = 2
        mock_session = MagicMock()
        repository.session_factory.return_value.__enter__ = Mock(return_value=mock_session)
        repository.session_factory.return_value.__exit__ = Mock(return_value=False)

        # 2回のexecute呼び出しで異なる結果を返す
        call_count = [0]

        def mock_execute(_stmt):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalars.return_value.all.return_value = [1, 2]
            else:
                result.scalars.return_value.all.return_value = [4]
            return result

        mock_session.execute.side_effect = mock_execute

        result = repository.get_annotated_image_ids([1, 2, 3, 4, 5])
        assert result == {1, 2, 4}
        assert mock_session.execute.call_count == 3  # ceil(5/2) = 3 chunks

    def test_propagates_sqlalchemy_error(self, repository):
        """SQLAlchemyError が伝播する"""
        mock_session = MagicMock()
        repository.session_factory.return_value.__enter__ = Mock(return_value=mock_session)
        repository.session_factory.return_value.__exit__ = Mock(return_value=False)
        mock_session.execute.side_effect = SQLAlchemyError("test")

        with pytest.raises(SQLAlchemyError):
            repository.get_annotated_image_ids([1])


class TestFindImageIdsByPhashes:
    """find_image_ids_by_phashes メソッドのテスト"""

    @pytest.fixture
    def repository(self):
        """テスト用ImageRepository"""
        mock_session_factory = Mock()
        return ImageRepository(session_factory=mock_session_factory)

    def test_empty_set_returns_empty_dict(self, repository):
        """空セットを渡すと空dictが返る"""
        result = repository.find_image_ids_by_phashes(set())
        assert result == {}

    def test_returns_phash_to_id_mapping(self, repository):
        """pHash→IDのマッピングを返す"""
        mock_session = MagicMock()
        repository.session_factory.return_value.__enter__ = Mock(return_value=mock_session)
        repository.session_factory.return_value.__exit__ = Mock(return_value=False)

        # execute().all() が Row-like オブジェクトを返す
        row1 = Mock()
        row1.phash = "abc123"
        row1.id = 1
        row2 = Mock()
        row2.phash = "def456"
        row2.id = 2
        mock_session.execute.return_value.all.return_value = [row1, row2]

        result = repository.find_image_ids_by_phashes({"abc123", "def456", "missing"})
        assert result == {"abc123": 1, "def456": 2}

    def test_chunking_merges_results(self, repository):
        """チャンク分割結果がdictにマージされる"""
        repository.BATCH_CHUNK_SIZE = 2
        mock_session = MagicMock()
        repository.session_factory.return_value.__enter__ = Mock(return_value=mock_session)
        repository.session_factory.return_value.__exit__ = Mock(return_value=False)

        # 2回のexecute呼び出しで異なる結果を返す
        call_count = [0]

        def mock_execute(_stmt):
            call_count[0] += 1
            row1 = Mock()
            row2 = Mock()
            result = MagicMock()
            if call_count[0] == 1:
                row1.phash = "aaa"
                row1.id = 1
                row2.phash = "bbb"
                row2.id = 2
                result.all.return_value = [row1, row2]
            else:
                row1.phash = "ccc"
                row1.id = 3
                result.all.return_value = [row1]
            return result

        mock_session.execute.side_effect = mock_execute

        result = repository.find_image_ids_by_phashes({"aaa", "bbb", "ccc"})
        assert result == {"aaa": 1, "bbb": 2, "ccc": 3}
        assert mock_session.execute.call_count == 2  # ceil(3/2) = 2 chunks

    def test_propagates_sqlalchemy_error(self, repository):
        """SQLAlchemyError が伝播する"""
        mock_session = MagicMock()
        repository.session_factory.return_value.__enter__ = Mock(return_value=mock_session)
        repository.session_factory.return_value.__exit__ = Mock(return_value=False)
        mock_session.execute.side_effect = SQLAlchemyError("test")

        with pytest.raises(SQLAlchemyError):
            repository.find_image_ids_by_phashes({"abc"})


class TestGetModelsByNames:
    """get_models_by_names メソッドのテスト"""

    @pytest.fixture
    def repository(self):
        """テスト用ImageRepository"""
        mock_session_factory = Mock()
        return ImageRepository(session_factory=mock_session_factory)

    def test_empty_set_returns_empty_dict(self, repository):
        """空セットを渡すと空dictが返る"""
        result = repository.get_models_by_names(set())
        assert result == {}

    def test_returns_name_to_model_mapping(self, repository):
        """モデル名→Modelのマッピングを返す"""
        mock_session = MagicMock()
        repository.session_factory.return_value.__enter__ = Mock(return_value=mock_session)
        repository.session_factory.return_value.__exit__ = Mock(return_value=False)

        model1 = Mock(spec=Model)
        model1.name = "gpt4"
        model2 = Mock(spec=Model)
        model2.name = "claude"
        mock_session.execute.return_value.scalars.return_value.all.return_value = [
            model1,
            model2,
        ]

        result = repository.get_models_by_names({"gpt4", "claude"})
        assert result == {"gpt4": model1, "claude": model2}

    def test_missing_name_not_in_result(self, repository):
        """存在しないモデル名は結果に含まれない"""
        mock_session = MagicMock()
        repository.session_factory.return_value.__enter__ = Mock(return_value=mock_session)
        repository.session_factory.return_value.__exit__ = Mock(return_value=False)

        model1 = Mock(spec=Model)
        model1.name = "gpt4"
        mock_session.execute.return_value.scalars.return_value.all.return_value = [model1]

        result = repository.get_models_by_names({"gpt4", "unknown"})
        assert "gpt4" in result
        assert "unknown" not in result
