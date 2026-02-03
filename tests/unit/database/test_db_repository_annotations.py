"""
ImageRepositoryのアノテーション関連メソッドのテスト
"""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from lorairo.database.db_repository import ImageRepository
from lorairo.database.schema import Caption, Image, Rating, Score, Tag


class TestFormatAnnotationsForMetadata:
    """_format_annotations_for_metadata メソッドのテスト"""

    @pytest.fixture
    def repository(self):
        """テスト用ImageRepository"""
        mock_session_factory = Mock()
        return ImageRepository(session_factory=mock_session_factory)

    @pytest.fixture
    def mock_image_empty(self):
        """アノテーションが空のMockImageオブジェクト"""
        image = Mock(spec=Image)
        image.tags = []
        image.captions = []
        image.scores = []
        image.ratings = []
        return image

    @pytest.fixture
    def mock_image_with_annotations(self):
        """各種アノテーションを持つMockImageオブジェクト"""
        image = Mock(spec=Image)

        # Mock tags
        tag1 = Mock(spec=Tag)
        tag1.id = 1
        tag1.tag = "test_tag"
        tag1.tag_id = 100
        tag1.model_id = "test_model"
        tag1.existing = True
        tag1.is_edited_manually = False
        tag1.confidence_score = 0.95
        tag1.created_at = datetime(2025, 9, 27, 10, 0, 0)
        tag1.updated_at = datetime(2025, 9, 27, 10, 0, 0)

        # Mock captions
        caption1 = Mock(spec=Caption)
        caption1.id = 1
        caption1.caption = "test caption"
        caption1.model_id = "test_model"
        caption1.existing = True
        caption1.is_edited_manually = False
        caption1.created_at = datetime(2025, 9, 27, 10, 0, 0)
        caption1.updated_at = datetime(2025, 9, 27, 10, 0, 0)

        # Mock scores
        score1 = Mock(spec=Score)
        score1.id = 1
        score1.score = 0.85
        score1.model_id = "test_model"
        score1.is_edited_manually = False
        score1.created_at = datetime(2025, 9, 27, 10, 0, 0)
        score1.updated_at = datetime(2025, 9, 27, 10, 0, 0)

        # Mock ratings
        rating1 = Mock(spec=Rating)
        rating1.id = 1
        rating1.raw_rating_value = "5"
        rating1.normalized_rating = 1.0
        rating1.model_id = "test_model"
        rating1.confidence_score = 0.90
        rating1.created_at = datetime(2025, 9, 27, 10, 0, 0)
        rating1.updated_at = datetime(2025, 9, 27, 10, 0, 0)

        image.tags = [tag1]
        image.captions = [caption1]
        image.scores = [score1]
        image.ratings = [rating1]

        return image

    def test_format_annotations_empty_image(self, repository, mock_image_empty):
        """空のアノテーションを持つImageオブジェクトのテスト"""
        result = repository._format_annotations_for_metadata(mock_image_empty)

        expected = {
            "tags": [],
            "tags_text": "",
            "captions": [],
            "caption_text": "",
            "scores": [],
            "score_value": 0.0,
            "ratings": [],
            "rating_value": "",  # Issue #4: Rating値は文字列型
        }

        assert result == expected

    def test_format_annotations_with_data(self, repository, mock_image_with_annotations):
        """各種アノテーションを持つImageオブジェクトのテスト"""
        result = repository._format_annotations_for_metadata(mock_image_with_annotations)

        # Tags検証
        assert len(result["tags"]) == 1
        assert result["tags"][0]["id"] == 1
        assert result["tags"][0]["tag"] == "test_tag"
        assert result["tags"][0]["tag_id"] == 100
        assert result["tags"][0]["model_id"] == "test_model"
        assert result["tags"][0]["existing"] is True
        assert result["tags"][0]["is_edited_manually"] is False
        assert result["tags"][0]["confidence_score"] == 0.95
        assert isinstance(result["tags"][0]["created_at"], datetime)
        assert isinstance(result["tags"][0]["updated_at"], datetime)
        assert result["tags_text"] == "test_tag"

        # Captions検証
        assert len(result["captions"]) == 1
        assert result["captions"][0]["id"] == 1
        assert result["captions"][0]["caption"] == "test caption"
        assert result["captions"][0]["model_id"] == "test_model"
        assert result["captions"][0]["existing"] is True
        assert result["captions"][0]["is_edited_manually"] is False
        assert isinstance(result["captions"][0]["created_at"], datetime)
        assert isinstance(result["captions"][0]["updated_at"], datetime)
        assert result["caption_text"] == "test caption"

        # Scores検証
        assert len(result["scores"]) == 1
        assert result["scores"][0]["id"] == 1
        assert result["scores"][0]["score"] == 0.85
        assert result["scores"][0]["model_id"] == "test_model"
        assert result["scores"][0]["is_edited_manually"] is False
        assert isinstance(result["scores"][0]["created_at"], datetime)
        assert isinstance(result["scores"][0]["updated_at"], datetime)
        assert result["score_value"] == 0.85

        # Ratings検証
        assert len(result["ratings"]) == 1
        assert result["ratings"][0]["id"] == 1
        assert result["ratings"][0]["raw_rating_value"] == "5"
        assert result["ratings"][0]["normalized_rating"] == 1.0
        assert result["ratings"][0]["model_id"] == "test_model"
        assert result["ratings"][0]["confidence_score"] == 0.90
        assert isinstance(result["ratings"][0]["created_at"], datetime)
        assert isinstance(result["ratings"][0]["updated_at"], datetime)
        assert result["rating_value"] == 1.0

    def test_format_annotations_partial_data(self, repository):
        """一部のアノテーションのみを持つImageオブジェクトのテスト"""
        image = Mock(spec=Image)

        # Tagsのみ設定
        tag1 = Mock(spec=Tag)
        tag1.id = 1
        tag1.tag = "test_tag"
        tag1.tag_id = 100
        tag1.model_id = "test_model"
        tag1.existing = True
        tag1.is_edited_manually = False
        tag1.confidence_score = 0.95
        tag1.created_at = datetime(2025, 9, 27, 10, 0, 0)
        tag1.updated_at = datetime(2025, 9, 27, 10, 0, 0)

        image.tags = [tag1]
        image.captions = []
        image.scores = []
        image.ratings = []

        result = repository._format_annotations_for_metadata(image)

        assert len(result["tags"]) == 1
        assert result["tags_text"] == "test_tag"
        assert len(result["captions"]) == 0
        assert result["caption_text"] == ""
        assert len(result["scores"]) == 0
        assert result["score_value"] == 0.0
        assert len(result["ratings"]) == 0
        assert result["rating_value"] == ""  # Issue #4: Rating値は文字列型

    def test_format_annotations_multiple_items(self, repository):
        """複数の同種アノテーションを持つImageオブジェクトのテスト"""
        image = Mock(spec=Image)

        # 複数のTagsを設定
        tag1 = Mock(spec=Tag)
        tag1.id = 1
        tag1.tag = "tag1"
        tag1.tag_id = 100
        tag1.model_id = "model1"
        tag1.existing = True
        tag1.is_edited_manually = False
        tag1.confidence_score = 0.95
        tag1.created_at = datetime(2025, 9, 27, 10, 0, 0)
        tag1.updated_at = datetime(2025, 9, 27, 10, 0, 0)

        tag2 = Mock(spec=Tag)
        tag2.id = 2
        tag2.tag = "tag2"
        tag2.tag_id = 101
        tag2.model_id = "model2"
        tag2.existing = False
        tag2.is_edited_manually = True
        tag2.confidence_score = 0.85
        tag2.created_at = datetime(2025, 9, 27, 11, 0, 0)
        tag2.updated_at = datetime(2025, 9, 27, 11, 0, 0)

        image.tags = [tag1, tag2]
        image.captions = []
        image.scores = []
        image.ratings = []

        result = repository._format_annotations_for_metadata(image)

        assert len(result["tags"]) == 2
        assert result["tags"][0]["tag"] == "tag1"
        assert result["tags"][1]["tag"] == "tag2"
        assert result["tags"][0]["confidence_score"] == 0.95
        assert result["tags"][1]["confidence_score"] == 0.85
        assert result["tags_text"] == "tag1, tag2"


class TestFetchFilteredMetadataAnnotations:
    """_fetch_filtered_metadata メソッドのアノテーション統合テスト"""

    @pytest.fixture
    def repository(self):
        """テスト用ImageRepository"""
        mock_session_factory = Mock()
        return ImageRepository(session_factory=mock_session_factory)

    def test_fetch_filtered_metadata_original_images_with_annotations(self, repository):
        """Original Image（resolution=0）でのアノテーション取得テスト"""
        mock_session = Mock()
        mock_result = Mock()

        # Mock Image with annotations
        mock_image = Mock(spec=Image)
        mock_image.id = 1
        mock_image.filename = "test.jpg"
        mock_image.__table__ = Mock()
        # Create proper column mocks with string names
        id_column = Mock()
        id_column.name = "id"
        filename_column = Mock()
        filename_column.name = "filename"

        mock_image.__table__.columns = [id_column, filename_column]

        # Mock annotations
        mock_image.tags = []
        mock_image.captions = []
        mock_image.scores = []
        mock_image.ratings = []

        mock_result.unique().scalars().all.return_value = [mock_image]
        mock_session.execute.return_value = mock_result

        with patch.object(repository, "_format_annotations_for_metadata") as mock_format:
            mock_format.return_value = {
                "tags": [{"id": 1, "tag": "test"}],
                "captions": [],
                "scores": [],
                "ratings": [],
            }

            result = repository._fetch_filtered_metadata(mock_session, [1], 0)

            assert len(result) == 1
            assert "tags" in result[0]
            assert result[0]["tags"] == [{"id": 1, "tag": "test"}]
            mock_format.assert_called_once_with(mock_image)

    def test_fetch_filtered_metadata_processed_images_with_annotations(self, repository):
        """ProcessedImage（resolution>0）でのアノテーション取得テスト"""
        mock_session = Mock()

        # Mock ProcessedImage
        mock_proc_image = Mock()
        mock_proc_image.image_id = 1
        mock_proc_image.resolution = 1024
        mock_proc_image.__table__ = Mock()
        # Create proper column mocks with string names
        image_id_column = Mock()
        image_id_column.name = "image_id"
        resolution_column = Mock()
        resolution_column.name = "resolution"

        mock_proc_image.__table__.columns = [image_id_column, resolution_column]

        # Mock Original Image with annotations
        mock_orig_image = Mock(spec=Image)
        mock_orig_image.id = 1
        mock_orig_image.tags = []
        mock_orig_image.captions = []
        mock_orig_image.scores = []
        mock_orig_image.ratings = []

        def mock_execute(stmt):
            mock_result = Mock()
            stmt_str = str(stmt)
            if "processed_image" in stmt_str.lower() or "ProcessedImage" in stmt_str:
                # Create proper mock chain for scalars().all()
                mock_scalars = Mock()
                mock_scalars.all.return_value = [mock_proc_image]
                mock_result.scalars.return_value = mock_scalars
            else:  # Original Image query with annotations
                # Create proper mock chain for unique().scalars().all()
                mock_scalars = Mock()
                mock_scalars.all.return_value = [mock_orig_image]
                mock_unique = Mock()
                mock_unique.scalars.return_value = mock_scalars
                mock_result.unique.return_value = mock_unique
            return mock_result

        mock_session.execute.side_effect = mock_execute

        with (
            patch.object(repository, "_format_annotations_for_metadata") as mock_format,
            patch.object(repository, "_filter_by_resolution") as mock_filter,
        ):
            mock_format.return_value = {
                "tags": [{"id": 1, "tag": "test"}],
                "captions": [],
                "scores": [],
                "ratings": [],
            }

            mock_filter.return_value = {
                "image_id": 1,
                "resolution": 1024,
                "tags": [{"id": 1, "tag": "test"}],
                "captions": [],
                "scores": [],
                "ratings": [],
            }

            result = repository._fetch_filtered_metadata(mock_session, [1], 1024)

            assert len(result) == 1
            assert "tags" in result[0]
            assert result[0]["tags"] == [{"id": 1, "tag": "test"}]
            mock_format.assert_called_once_with(mock_orig_image)


# ==============================================================================
# Test annotation formatter helpers
# ==============================================================================


class TestAnnotationFormatters:
    """_format_*_annotation staticメソッドのテスト"""

    def test_format_tag_annotation(self):
        """タグアノテーションのフォーマット。"""
        tag = Mock()
        tag.id = 1
        tag.tag = "cat"
        tag.tag_id = 100
        tag.model_id = 5
        tag.existing = False
        tag.is_edited_manually = True
        tag.confidence_score = 0.95
        tag.created_at = datetime(2025, 1, 1)
        tag.updated_at = datetime(2025, 1, 2)

        result = ImageRepository._format_tag_annotation(tag)
        assert result["id"] == 1
        assert result["tag"] == "cat"
        assert result["tag_id"] == 100
        assert result["confidence_score"] == 0.95

    def test_format_caption_annotation(self):
        """キャプションアノテーションのフォーマット。"""
        caption = Mock()
        caption.id = 2
        caption.caption = "A cute cat"
        caption.model_id = 5
        caption.existing = False
        caption.is_edited_manually = False
        caption.created_at = datetime(2025, 1, 1)
        caption.updated_at = datetime(2025, 1, 2)

        result = ImageRepository._format_caption_annotation(caption)
        assert result["id"] == 2
        assert result["caption"] == "A cute cat"
        assert result["is_edited_manually"] is False

    def test_format_score_annotation(self):
        """スコアアノテーションのフォーマット。"""
        score = Mock()
        score.id = 3
        score.score = 0.87
        score.model_id = 5
        score.is_edited_manually = False
        score.created_at = datetime(2025, 1, 1)
        score.updated_at = datetime(2025, 1, 2)

        result = ImageRepository._format_score_annotation(score)
        assert result["score"] == 0.87

    def test_format_rating_annotation(self):
        """レーティングアノテーションのフォーマット。"""
        rating = Mock()
        rating.id = 4
        rating.raw_rating_value = "PG"
        rating.normalized_rating = "pg"
        rating.model_id = 5
        rating.confidence_score = 0.92
        rating.created_at = datetime(2025, 1, 1)
        rating.updated_at = datetime(2025, 1, 2)

        result = ImageRepository._format_rating_annotation(rating)
        assert result["raw_rating_value"] == "PG"
        assert result["normalized_rating"] == "pg"
        assert result["confidence_score"] == 0.92


# ==============================================================================
# Test _apply_simple_field_updates
# ==============================================================================


class TestApplySimpleFieldUpdates:
    """update_modelから抽出された_apply_simple_field_updatesのテスト"""

    def test_no_changes_when_all_none(self):
        """全引数Noneの場合は変更なし。"""
        model = Mock()
        result = ImageRepository._apply_simple_field_updates(
            model, None, None, None, None, None
        )
        assert result is False

    def test_updates_changed_field(self):
        """値が異なるフィールドのみ更新される。"""
        model = Mock()
        model.provider = "old_provider"
        model.api_model_id = "old-id"
        model.estimated_size_gb = None
        model.requires_api_key = None
        model.discontinued_at = None

        result = ImageRepository._apply_simple_field_updates(
            model, "new_provider", None, None, None, None
        )
        assert result is True
        assert model.provider == "new_provider"

    def test_no_changes_when_same_value(self):
        """値が同じ場合は変更なし。"""
        model = Mock()
        model.provider = "same_provider"

        result = ImageRepository._apply_simple_field_updates(
            model, "same_provider", None, None, None, None
        )
        assert result is False
