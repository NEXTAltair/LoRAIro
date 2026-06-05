"""
ImageRepositoryのアノテーション関連メソッドのテスト
"""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from lorairo.database.repository.image import ImageRepository
from lorairo.database.repository.model import ModelRepository
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
        image.score_labels = []
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

        # Mock scores (Issue #626: model 名で表示尺度変換するため model.name を実値にする)
        score1 = Mock(spec=Score)
        score1.id = 1
        score1.score = 0.85
        score1.model_id = "test_model"
        score1.model = Mock()
        score1.model.name = "cafe_aesthetic"
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
        image.score_labels = []
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
            "score_labels": [],
            "ratings": [],
            "rating_value": "",  # Issue #4: Rating値は文字列型
            # ADR 0029: derived view。score 系が空なので tier="no score"
            "quality_summary": {
                "mapping_version": "quality-tier-v1",
                "tier": "no score",
                "is_unanimous": False,
                "known_count": 0,
                "unknown_count": 0,
                "no_score": True,
                "votes": [],
            },
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
        # Issue #626: cafe_aesthetic raw 0.85 を区分線形で 0-10 化 (knots (0.5,6.0)-(1.0,8.0))
        # → ratio=(0.85-0.5)/0.5=0.7, 6.0 + 0.7 * 2.0 = 7.4
        assert result["score_value"] == pytest.approx(7.4)

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
        image.score_labels = []
        image.ratings = []

        result = repository._format_annotations_for_metadata(image)

        assert len(result["tags"]) == 1
        assert result["tags_text"] == "test_tag"
        assert len(result["captions"]) == 0
        assert result["caption_text"] == ""
        assert len(result["scores"]) == 0
        assert result["score_value"] == 0.0
        assert len(result["score_labels"]) == 0
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
        image.score_labels = []
        image.ratings = []

        result = repository._format_annotations_for_metadata(image)

        assert len(result["tags"]) == 2
        assert result["tags"][0]["tag"] == "tag1"
        assert result["tags"][1]["tag"] == "tag2"
        assert result["tags"][0]["confidence_score"] == 0.95
        assert result["tags"][1]["confidence_score"] == 0.85
        assert result["tags_text"] == "tag1, tag2"

    def test_format_annotations_includes_quality_summary(self, repository):
        """ADR 0029: score_labels がある場合、quality_summary が derived 計算される。

        GUI のメタデータ経路 (SelectedImageDetailsWidget) も _format_annotations_for_metadata
        を経由するため、quality tier badge が機能するには本経路での計算が必須 (PR #297 Codex P1)。
        """
        from types import SimpleNamespace

        image = Mock(spec=Image)
        image.tags = []
        image.captions = []
        image.scores = []
        image.ratings = []
        image.score_labels = [
            SimpleNamespace(
                id=1,
                image_id=100,
                model_id=42,
                label="aesthetic",
                is_edited_manually=False,
                created_at=datetime(2026, 5, 19, 10, 0, 0),
                updated_at=datetime(2026, 5, 19, 10, 0, 0),
                model=SimpleNamespace(name="aesthetic_shadow_v2"),
            )
        ]

        result = repository._format_annotations_for_metadata(image)

        assert "quality_summary" in result
        assert result["quality_summary"]["tier"] == "best quality"
        assert result["quality_summary"]["known_count"] == 1
        assert result["quality_summary"]["is_unanimous"] is True


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

        mock_result.scalars.return_value.all.return_value = [mock_image]
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
        mock_proc_image.id = 100  # processed_images.id
        mock_proc_image.image_id = 1  # images.id (FK)
        mock_proc_image.resolution = 1024
        mock_proc_image.__table__ = Mock()
        # Create proper column mocks with string names
        id_column = Mock()
        id_column.name = "id"
        image_id_column = Mock()
        image_id_column.name = "image_id"
        resolution_column = Mock()
        resolution_column.name = "resolution"

        mock_proc_image.__table__.columns = [id_column, image_id_column, resolution_column]

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
                # Create proper mock chain for scalars().all()
                mock_scalars = Mock()
                mock_scalars.all.return_value = [mock_orig_image]
                mock_result.scalars.return_value = mock_scalars
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

    def test_format_score_label_annotation(self):
        """スコアラベルアノテーション (ADR 0028) のフォーマット - model 名と組で返ること。"""
        sl = Mock()
        sl.id = 5
        sl.label = "very aesthetic"
        sl.model_id = 42
        sl.is_edited_manually = False
        sl.created_at = datetime(2026, 5, 18)
        sl.updated_at = datetime(2026, 5, 18)
        sl.model = Mock()
        sl.model.name = "aesthetic_shadow_v1"

        result = ImageRepository._format_score_label_annotation(sl)
        assert result["id"] == 5
        assert result["label"] == "very aesthetic"
        assert result["model_id"] == 42
        # ADR 0028: model 名を常に含める
        assert result["model"] == "aesthetic_shadow_v1"
        assert result["is_edited_manually"] is False

    def test_format_score_label_annotation_no_model_relationship(self):
        """model relationship が None の場合は 'Unknown' が埋まる。"""
        sl = Mock()
        sl.id = 6
        sl.label = "aesthetic"
        sl.model_id = 99
        sl.is_edited_manually = False
        sl.created_at = datetime(2026, 5, 18)
        sl.updated_at = datetime(2026, 5, 18)
        sl.model = None

        result = ImageRepository._format_score_label_annotation(sl)
        assert result["model"] == "Unknown"


# ==============================================================================
# Test _apply_simple_field_updates
# ==============================================================================


class TestApplySimpleFieldUpdates:
    """update_modelから抽出された_apply_simple_field_updatesのテスト"""

    def test_no_changes_when_all_none(self):
        """全引数Noneの場合は変更なし。"""
        model = Mock()
        result = ModelRepository._apply_simple_field_updates(model, None, None, None, None, None)
        assert result is False

    def test_updates_changed_field(self):
        """値が異なるフィールドのみ更新される。"""
        model = Mock()
        model.provider = "old_provider"
        model.litellm_model_id = "old-id"
        model.estimated_size_gb = None
        model.requires_api_key = None
        model.discontinued_at = None

        result = ModelRepository._apply_simple_field_updates(model, "new_provider", None, None, None, None)
        assert result is True
        assert model.provider == "new_provider"

    def test_no_changes_when_same_value(self):
        """値が同じ場合は変更なし。"""
        model = Mock()
        model.provider = "same_provider"

        result = ModelRepository._apply_simple_field_updates(model, "same_provider", None, None, None, None)
        assert result is False


def _score_row(
    score: float,
    model_name: str,
    is_manual: bool,
    created_at: datetime,
    model_id: int = 1,
) -> Mock:
    """_derive_display_score 用の Score 行モックを作る。"""
    row = Mock(spec=Score)
    row.score = score
    row.is_edited_manually = is_manual
    row.created_at = created_at
    row.model_id = model_id
    row.model = Mock()
    row.model.name = model_name
    return row


class TestDeriveDisplayScore:
    """ImageRepository._derive_display_score のテスト (Issue #626)。"""

    @pytest.mark.unit
    def test_no_scores_returns_zero(self):
        image = Mock(spec=Image)
        image.scores = []
        assert ImageRepository._derive_display_score(image) == 0.0

    @pytest.mark.unit
    def test_manual_score_takes_priority(self):
        """手動行があれば、AI 行を無視して手動の生値 (0-10) を返す。"""
        image = Mock(spec=Image)
        image.scores = [
            _score_row(0.9, "aesthetic_shadow_v1", is_manual=False, created_at=datetime(2025, 1, 1)),
            _score_row(7.0, "manual", is_manual=True, created_at=datetime(2025, 1, 2)),
        ]
        assert ImageRepository._derive_display_score(image) == pytest.approx(7.0)

    @pytest.mark.unit
    def test_latest_manual_wins(self):
        image = Mock(spec=Image)
        image.scores = [
            _score_row(3.0, "manual", is_manual=True, created_at=datetime(2025, 1, 1)),
            _score_row(8.0, "manual", is_manual=True, created_at=datetime(2025, 1, 3)),
        ]
        assert ImageRepository._derive_display_score(image) == pytest.approx(8.0)

    @pytest.mark.unit
    def test_single_ai_score_calibrated(self):
        """AI 行が 1 つなら calibrate された値を返す (cafe 0.5 → 6.0)。"""
        image = Mock(spec=Image)
        image.scores = [
            _score_row(0.5, "cafe_aesthetic", is_manual=False, created_at=datetime(2025, 1, 1)),
        ]
        assert ImageRepository._derive_display_score(image) == pytest.approx(6.0)

    @pytest.mark.unit
    def test_multiple_ai_models_averaged(self):
        """複数 model の calibrate 値を平均する。"""
        image = Mock(spec=Image)
        image.scores = [
            # cafe 0.5 → 6.0
            _score_row(0.5, "cafe_aesthetic", is_manual=False, created_at=datetime(2025, 1, 1), model_id=1),
            # shadow hq 0.45 → 8.0
            _score_row(
                0.45, "aesthetic_shadow_v1", is_manual=False, created_at=datetime(2025, 1, 1), model_id=2
            ),
        ]
        # (6.0 + 8.0) / 2 = 7.0
        assert ImageRepository._derive_display_score(image) == pytest.approx(7.0)

    @pytest.mark.unit
    def test_legacy_two_rows_same_model_uses_latest(self):
        """legacy で同一 model に 2 行ある場合は最新行を採用する (best-effort 近似)。"""
        image = Mock(spec=Image)
        image.scores = [
            # 古い lq 行 (legacy で残った complement)
            _score_row(0.2, "cafe_aesthetic", is_manual=False, created_at=datetime(2025, 1, 1), model_id=5),
            # 新しい positive 行
            _score_row(0.5, "cafe_aesthetic", is_manual=False, created_at=datetime(2025, 1, 2), model_id=5),
        ]
        # 最新行 0.5 のみを採用 → cafe 0.5 → 6.0
        assert ImageRepository._derive_display_score(image) == pytest.approx(6.0)
