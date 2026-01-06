# tests/unit/gui/services/test_image_db_write_service.py

from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from lorairo.gui.services.image_db_write_service import ImageDBWriteService
from lorairo.gui.widgets.annotation_data_display_widget import AnnotationData, ImageDetails


class TestImageDBWriteService:
    """ImageDBWriteService単体テスト（Phase 1-2パターン継承）"""

    @pytest.fixture
    def mock_db_manager(self):
        """テスト用モックImageDatabaseManager"""
        mock_db_manager = Mock()
        mock_db_manager.repository = Mock()
        return mock_db_manager

    @pytest.fixture
    def service(self, mock_db_manager):
        """テスト用ImageDBWriteService"""
        return ImageDBWriteService(db_manager=mock_db_manager)

    def test_constructor_with_db_manager(self, mock_db_manager):
        """コンストラクタ正常初期化（Phase 1-2パターン）"""
        service = ImageDBWriteService(db_manager=mock_db_manager)

        assert service.db_manager == mock_db_manager
        assert hasattr(service, "db_manager")

    def test_get_image_details_success(self, service, mock_db_manager):
        """画像詳細取得成功ケース"""
        from pathlib import Path

        # モック設定
        image_id = 123
        mock_image_metadata = {
            "id": 123,
            "stored_image_path": "/test/path/image.jpg",
            "width": 1024,
            "height": 768,
            "file_size": 2048000,
            "created_at": datetime(2024, 1, 15, 10, 30, 0),
        }
        mock_annotation_data = {
            "tags": [{"content": "1girl"}, {"content": "long hair"}],
            "captions": [{"content": "A beautiful anime girl"}],
            "scores": [{"value": 0.85}],
        }

        mock_db_manager.repository.get_image_metadata.return_value = mock_image_metadata
        mock_db_manager.repository.get_image_annotations.return_value = mock_annotation_data

        # 実行
        result = service.get_image_details(image_id)

        # 検証
        assert isinstance(result, ImageDetails)
        assert result.image_id == 123
        assert result.file_name == "image.jpg"
        # クロスプラットフォーム対応：パスを正規化して比較
        expected_path = str(Path("/test/path/image.jpg"))
        assert result.file_path == expected_path
        assert result.image_size == "1024x768"
        assert result.file_size == "1.95 MB"
        assert result.created_date == "2024-01-15 10:30:00"

        # AnnotationDataの検証
        assert isinstance(result.annotation_data, AnnotationData)
        assert result.annotation_data.tags == ["1girl", "long hair"]
        assert result.annotation_data.caption == "A beautiful anime girl"
        assert result.annotation_data.aesthetic_score == 0.85

        # モックメソッドの呼び出し確認
        mock_db_manager.repository.get_image_metadata.assert_called_once_with(image_id)
        mock_db_manager.repository.get_image_annotations.assert_called_once_with(image_id)

    def test_get_image_details_no_metadata(self, service, mock_db_manager):
        """画像メタデータが見つからない場合"""
        image_id = 999
        mock_db_manager.repository.get_image_metadata.return_value = None

        with patch("lorairo.gui.services.image_db_write_service.logger") as mock_logger:
            result = service.get_image_details(image_id)

            # 空のImageDetailsが返される
            assert isinstance(result, ImageDetails)
            assert result.image_id is None
            assert result.file_name == ""

            # 警告ログが出力される
            mock_logger.warning.assert_called_with(f"Image not found for ID: {image_id}")

    def test_get_annotation_data_success(self, service, mock_db_manager):
        """アノテーション取得成功ケース"""
        image_id = 456
        mock_annotations = {
            "tags": [{"content": "landscape"}, {"content": "nature"}],
            "captions": [{"content": "Beautiful mountain landscape"}],
            "scores": [{"value": 0.92}],
        }

        mock_db_manager.repository.get_image_annotations.return_value = mock_annotations

        # 実行
        result = service.get_annotation_data(image_id)

        # 検証
        assert isinstance(result, AnnotationData)
        assert result.tags == ["landscape", "nature"]
        assert result.caption == "Beautiful mountain landscape"
        assert result.aesthetic_score == 0.92
        assert result.overall_score == 0
        assert result.score_type == "Aesthetic"

        mock_db_manager.repository.get_image_annotations.assert_called_once_with(image_id)

    def test_get_annotation_data_empty(self, service, mock_db_manager):
        """アノテーションデータがない場合"""
        image_id = 789
        mock_db_manager.repository.get_image_annotations.return_value = {}

        result = service.get_annotation_data(image_id)

        # 空のAnnotationDataが返される
        assert isinstance(result, AnnotationData)
        assert result.tags == []
        assert result.caption == ""
        assert result.aesthetic_score is None
        assert result.overall_score == 0

    def test_update_rating_success(self, service, mock_db_manager):
        """Rating更新機能正常動作（プレースホルダー実装）"""
        image_id = 100
        rating = "PG"

        result = service.update_rating(image_id, rating)

        # プレースホルダー実装では常にTrueを返す
        assert result is True

    def test_update_score_success(self, service, mock_db_manager):
        """Score更新機能正常動作（プレースホルダー実装）"""
        image_id = 200
        score = 750  # 0-1000範囲

        result = service.update_score(image_id, score)

        # プレースホルダー実装では常にTrueを返す
        assert result is True

    def test_update_rating_invalid_image_id(self, service, mock_db_manager):
        """不正なimage_id指定時の適切な処理（プレースホルダー実装）"""
        invalid_image_id = -1
        rating = "R"

        # プレースホルダー実装では常にTrueを返す
        result = service.update_rating(invalid_image_id, rating)

        assert result is True

    def test_update_score_invalid_range(self, service, mock_db_manager):
        """スコア範囲外の値の処理"""
        image_id = 300
        invalid_score = 1500  # 0-1000範囲外

        with patch("lorairo.gui.services.image_db_write_service.logger") as mock_logger:
            result = service.update_score(image_id, invalid_score)

            assert result is False
            mock_logger.warning.assert_called_with(
                f"Invalid score value: {invalid_score}. Must be between 0-1000"
            )

    def test_db_connection_error_handling(self, service, mock_db_manager):
        """DB接続エラー時の例外処理"""
        image_id = 400

        # DBエラーをシミュレート
        mock_db_manager.repository.get_image_metadata.side_effect = Exception("Database connection error")

        with patch("lorairo.gui.services.image_db_write_service.logger") as mock_logger:
            result = service.get_image_details(image_id)

            # 空のImageDetailsが返される
            assert isinstance(result, ImageDetails)
            assert result.image_id is None

            # エラーログが出力される
            mock_logger.error.assert_called_with(
                f"Error fetching image details for ID {image_id}: Database connection error", exc_info=True
            )

    def test_add_tag_batch_success(self, service, mock_db_manager):
        """バッチタグ追加成功ケース"""
        image_ids = [1, 2, 3]
        tag = "landscape"

        # 新しい原子的バッチ追加メソッドのモック設定
        mock_db_manager.repository.add_tag_to_images_batch.return_value = (True, 3)
        mock_db_manager.get_manual_edit_model_id.return_value = 42

        # 実行
        result = service.add_tag_batch(image_ids, tag)

        # 検証
        assert result is True
        mock_db_manager.repository.add_tag_to_images_batch.assert_called_once_with(
            image_ids=image_ids, tag=tag, model_id=42
        )

    def test_add_tag_batch_duplicate_skip(self, service, mock_db_manager):
        """重複タグのスキップテスト"""
        image_ids = [1, 2]
        tag = "landscape"

        # 新しい原子的バッチ追加メソッドのモック設定（重複により0件追加）
        mock_db_manager.repository.add_tag_to_images_batch.return_value = (True, 0)
        mock_db_manager.get_manual_edit_model_id.return_value = 42

        # 実行
        result = service.add_tag_batch(image_ids, tag)

        # 検証: 重複のため追加件数は0だが成功扱い
        assert result is True
        mock_db_manager.repository.add_tag_to_images_batch.assert_called_once_with(
            image_ids=image_ids, tag=tag, model_id=42
        )

    def test_add_tag_batch_empty_image_ids(self, service, mock_db_manager):
        """空の画像IDリストでの呼び出し"""
        result = service.add_tag_batch([], "landscape")

        # 検証: 早期リターンで False
        assert result is False
        mock_db_manager.repository.add_tag_to_images_batch.assert_not_called()

    def test_add_tag_batch_empty_tag(self, service, mock_db_manager):
        """空タグでの呼び出し"""
        result = service.add_tag_batch([1, 2], "")

        # 検証: 早期リターンで False
        assert result is False
        mock_db_manager.repository.add_tag_to_images_batch.assert_not_called()

    def test_add_tag_batch_exception_handling(self, service, mock_db_manager):
        """例外ハンドリングテスト"""
        image_ids = [1, 2]
        tag = "landscape"

        # 例外を発生させる
        mock_db_manager.repository.add_tag_to_images_batch.side_effect = Exception("DB Error")
        mock_db_manager.get_manual_edit_model_id.return_value = 42

        # 実行
        result = service.add_tag_batch(image_ids, tag)

        # 検証: 例外発生時は False を返す
        assert result is False


class TestImageDBWriteServiceIntegration:
    """ImageDBWriteService統合テスト（Phase 1-2パターン継承）"""

    @pytest.fixture
    def mock_db_manager_complex(self):
        """複雑なシナリオ用モックImageDatabaseManager"""
        mock_db_manager = Mock()
        mock_db_manager.repository = Mock()

        # 複数画像のメタデータを設定
        def get_metadata_side_effect(image_id):
            metadata_map = {
                1: {
                    "id": 1,
                    "stored_image_path": "/dataset/images/photo1.jpg",
                    "width": 1920,
                    "height": 1080,
                    "file_size": 5242880,  # 5MB
                    "created_at": datetime(2024, 2, 1, 14, 20, 30),
                },
                2: {
                    "id": 2,
                    "stored_image_path": "/dataset/images/art2.png",
                    "width": 512,
                    "height": 512,
                    "file_size": 1048576,  # 1MB
                    "created_at": datetime(2024, 2, 2, 16, 45, 15),
                },
            }
            return metadata_map.get(image_id)

        def get_annotations_side_effect(image_id):
            annotations_map = {
                1: {
                    "tags": [{"content": "photography"}, {"content": "landscape"}, {"content": "sunset"}],
                    "captions": [{"content": "A breathtaking sunset over the mountains"}],
                    "scores": [{"value": 0.91}],
                },
                2: {
                    "tags": [{"content": "digital art"}, {"content": "anime"}, {"content": "character"}],
                    "captions": [{"content": "Anime character illustration"}],
                    "scores": [{"value": 0.78}],
                },
            }
            return annotations_map.get(image_id, {})

        mock_db_manager.repository.get_image_metadata.side_effect = get_metadata_side_effect
        mock_db_manager.repository.get_image_annotations.side_effect = get_annotations_side_effect

        return mock_db_manager

    @pytest.fixture
    def integration_service(self, mock_db_manager_complex):
        """統合テスト用ImageDBWriteService"""
        return ImageDBWriteService(db_manager=mock_db_manager_complex)

    def test_multiple_image_details_retrieval(self, integration_service):
        """複数画像詳細の連続取得テスト"""
        from pathlib import Path

        # 画像1の詳細取得
        details1 = integration_service.get_image_details(1)
        assert details1.image_id == 1
        assert details1.file_name == "photo1.jpg"
        assert details1.image_size == "1920x1080"
        assert details1.file_size == "5.00 MB"
        assert details1.annotation_data.tags == ["photography", "landscape", "sunset"]

        # 画像2の詳細取得
        details2 = integration_service.get_image_details(2)
        assert details2.image_id == 2
        assert details2.file_name == "art2.png"
        assert details2.image_size == "512x512"
        assert details2.file_size == "1.00 MB"
        assert details2.annotation_data.tags == ["digital art", "anime", "character"]

    def test_batch_operations_simulation(self, integration_service, mock_db_manager_complex):
        """バッチ操作シミュレーションテスト（プレースホルダー実装）"""
        image_ids = [1, 2]

        results = []
        for image_id in image_ids:
            rating = "PG" if image_id == 1 else "G"
            result = integration_service.update_rating(image_id, rating)
            results.append(result)

        # プレースホルダー実装では全て成功
        assert all(results)

    def test_service_state_consistency(self, integration_service):
        """サービス状態の一貫性テスト"""
        # 複数回の呼び出しで状態が一貫していることを確認
        details_first_call = integration_service.get_image_details(1)
        details_second_call = integration_service.get_image_details(1)

        # 同じ結果が返される
        assert details_first_call.image_id == details_second_call.image_id
        assert details_first_call.file_name == details_second_call.file_name
        assert details_first_call.annotation_data.tags == details_second_call.annotation_data.tags

    def test_performance_mock_validation(self, integration_service, mock_db_manager_complex):
        """パフォーマンス考慮のモック検証テスト"""
        # 大量画像IDのシミュレーション（実際にはモックを使用）
        image_ids = list(range(1, 101))  # 100画像

        # 存在しない画像IDに対する応答
        details_list = []
        for image_id in image_ids[:5]:  # 最初の5つのみテスト
            details = integration_service.get_image_details(image_id)
            details_list.append(details)

        # 存在する画像（1, 2）と存在しない画像（3, 4, 5）の混在
        assert details_list[0].image_id == 1  # 存在
        assert details_list[1].image_id == 2  # 存在
        assert details_list[2].image_id is None  # 存在しない
        assert details_list[3].image_id is None  # 存在しない
        assert details_list[4].image_id is None  # 存在しない
