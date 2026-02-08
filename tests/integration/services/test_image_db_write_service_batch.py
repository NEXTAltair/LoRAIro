"""ImageDBWriteService バッチRating/Score更新の統合テスト

Service層 → Repository層の連携を確認する。
"""

from unittest.mock import Mock

import pytest

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.gui.services.image_db_write_service import ImageDBWriteService


class TestImageDBWriteServiceBatchRatingScore:
    """ImageDBWriteService のバッチ更新統合テスト"""

    @pytest.fixture
    def mock_repository(self):
        """モックRepository"""
        repo = Mock()
        # デフォルトの戻り値設定
        repo.update_rating_batch.return_value = (True, 3)
        repo.update_score_batch.return_value = (True, 3)
        return repo

    @pytest.fixture
    def mock_db_manager(self, mock_repository):
        """モックImageDatabaseManager"""
        manager = Mock(spec=ImageDatabaseManager)
        manager.repository = mock_repository
        manager.get_manual_edit_model_id.return_value = 999
        return manager

    @pytest.fixture
    def service(self, mock_db_manager):
        """ImageDBWriteService インスタンス"""
        return ImageDBWriteService(db_manager=mock_db_manager)

    def test_update_rating_batch_success(self, service, mock_repository):
        """update_rating_batch が正しく Repository を呼び出す"""
        image_ids = [1, 2, 3]
        rating = "PG-13"

        success = service.update_rating_batch(image_ids, rating)

        assert success is True
        mock_repository.update_rating_batch.assert_called_once_with(
            image_ids=image_ids,
            rating=rating,
            model_id=999,  # get_manual_edit_model_id() の戻り値
        )

    def test_update_rating_batch_validates_rating(self, service, mock_repository):
        """不正な Rating 値を拒否する"""
        image_ids = [1, 2, 3]
        invalid_rating = "INVALID"

        success = service.update_rating_batch(image_ids, invalid_rating)

        assert success is False
        mock_repository.update_rating_batch.assert_not_called()

    def test_update_rating_batch_empty_list(self, service, mock_repository):
        """空の image_ids リストを拒否する"""
        success = service.update_rating_batch([], "PG-13")

        assert success is False
        mock_repository.update_rating_batch.assert_not_called()

    def test_update_rating_batch_handles_repository_failure(self, service, mock_repository):
        """Repository が失敗を返した場合、False を返す"""
        mock_repository.update_rating_batch.return_value = (False, 0)

        success = service.update_rating_batch([1, 2, 3], "R")

        assert success is False

    def test_update_score_batch_success(self, service, mock_repository):
        """update_score_batch が正しく Repository を呼び出す"""
        image_ids = [1, 2, 3]
        score_ui = 850  # UI値 (0-1000)

        success = service.update_score_batch(image_ids, score_ui)

        assert success is True
        # UI値 → DB値の変換: 850 → 8.5
        mock_repository.update_score_batch.assert_called_once_with(
            image_ids=image_ids,
            score=8.5,  # DB値 (0.0-10.0)
            model_id=999,
        )

    def test_update_score_batch_validates_score(self, service, mock_repository):
        """不正な Score 値を拒否する（範囲外）"""
        image_ids = [1, 2, 3]

        # スコア < 0
        success = service.update_score_batch(image_ids, -100)
        assert success is False
        mock_repository.update_score_batch.assert_not_called()

        # スコア > 1000
        success = service.update_score_batch(image_ids, 1100)
        assert success is False

    def test_update_score_batch_empty_list(self, service, mock_repository):
        """空の image_ids リストを拒否する"""
        success = service.update_score_batch([], 500)

        assert success is False
        mock_repository.update_score_batch.assert_not_called()

    def test_update_score_batch_handles_repository_failure(self, service, mock_repository):
        """Repository が失敗を返した場合、False を返す"""
        mock_repository.update_score_batch.return_value = (False, 0)

        success = service.update_score_batch([1, 2, 3], 600)

        assert success is False

    def test_update_score_batch_ui_db_conversion(self, service, mock_repository):
        """UI値とDB値の変換が正しい"""
        test_cases = [
            (0, 0.0),  # 最小値
            (500, 5.0),  # 中間値
            (1000, 10.0),  # 最大値
            (750, 7.5),  # 小数点
        ]

        for ui_value, expected_db_value in test_cases:
            mock_repository.update_score_batch.reset_mock()

            service.update_score_batch([1], ui_value)

            mock_repository.update_score_batch.assert_called_once_with(
                image_ids=[1],
                score=expected_db_value,
                model_id=999,
            )
