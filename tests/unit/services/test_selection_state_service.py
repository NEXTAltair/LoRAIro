"""SelectionStateServiceの単体テスト

Phase 2.3で作成されたSelectionStateServiceのテスト。
画像選択ロジックのフォールバック戦略を検証。
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from lorairo.services.selection_state_service import SelectionStateService


@pytest.fixture
def mock_dataset_state_manager():
    """DatasetStateManagerのモック"""
    manager = Mock()
    manager.selected_image_ids = []
    manager.filtered_images = []
    manager.all_images = []
    manager.has_filtered_images.return_value = False
    manager.get_image_by_id.return_value = None
    return manager


@pytest.fixture
def mock_db_repository():
    """ImageRepositoryのモック"""
    repo = Mock()
    return repo


@pytest.fixture
def service(mock_dataset_state_manager, mock_db_repository):
    """SelectionStateServiceインスタンス"""
    return SelectionStateService(
        dataset_state_manager=mock_dataset_state_manager,
        db_repository=mock_db_repository,
    )


class TestSelectionStateServiceInit:
    """初期化テスト"""

    def test_init(self, mock_dataset_state_manager, mock_db_repository):
        """正常な初期化"""
        service = SelectionStateService(
            dataset_state_manager=mock_dataset_state_manager,
            db_repository=mock_db_repository,
        )

        assert service.dataset_state_manager is mock_dataset_state_manager
        assert service.db_repository is mock_db_repository

    def test_init_with_none_managers(self):
        """None managers should be accepted"""
        service = SelectionStateService(
            dataset_state_manager=None,
            db_repository=None,
        )

        assert service.dataset_state_manager is None
        assert service.db_repository is None


class TestGetSelectedImagesForAnnotation:
    """get_selected_images_for_annotation()テスト"""

    def test_get_selected_images_success_from_selected_ids(
        self, service, mock_dataset_state_manager
    ):
        """第1優先: selected_image_idsから取得成功"""
        # Setup
        mock_dataset_state_manager.selected_image_ids = [1, 2, 3]
        mock_dataset_state_manager.get_image_by_id.side_effect = [
            {"id": 1, "stored_image_path": "/path/to/image1.jpg"},
            {"id": 2, "stored_image_path": "/path/to/image2.jpg"},
            {"id": 3, "stored_image_path": "/path/to/image3.jpg"},
        ]

        # Execute
        result = service.get_selected_images_for_annotation()

        # Assert
        assert len(result) == 3
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2
        assert result[2]["id"] == 3
        assert mock_dataset_state_manager.get_image_by_id.call_count == 3

    def test_get_selected_images_fallback_to_filtered(
        self, service, mock_dataset_state_manager
    ):
        """第2優先（最終）: filtered_imagesから取得"""
        # Setup - No selected_image_ids
        mock_dataset_state_manager.selected_image_ids = []
        mock_dataset_state_manager.has_filtered_images.return_value = True
        mock_dataset_state_manager.filtered_images = [
            {"id": 10, "stored_image_path": "/path/to/filtered1.jpg"},
            {"id": 11, "stored_image_path": "/path/to/filtered2.jpg"},
        ]

        # Execute
        result = service.get_selected_images_for_annotation()

        # Assert
        assert len(result) == 2
        assert result[0]["id"] == 10
        assert result[1]["id"] == 11

    def test_get_selected_images_no_selection_error(
        self, service, mock_dataset_state_manager
    ):
        """画像未選択エラー"""
        # Setup - No images anywhere
        mock_dataset_state_manager.selected_image_ids = []
        mock_dataset_state_manager.has_filtered_images.return_value = False
        mock_dataset_state_manager.filtered_images = []

        # Execute & Assert
        with pytest.raises(ValueError, match="アノテーション対象の画像が選択されていません"):
            service.get_selected_images_for_annotation()

    def test_get_selected_images_with_missing_image_data(
        self, service, mock_dataset_state_manager
    ):
        """一部の画像データが取得できない場合（スキップして継続）"""
        # Setup
        mock_dataset_state_manager.selected_image_ids = [1, 2, 3]
        mock_dataset_state_manager.get_image_by_id.side_effect = [
            {"id": 1, "stored_image_path": "/path/to/image1.jpg"},
            None,  # Image 2 not found
            {"id": 3, "stored_image_path": "/path/to/image3.jpg"},
        ]

        # Execute
        result = service.get_selected_images_for_annotation()

        # Assert - Should skip None and continue
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 3

    def test_get_selected_images_with_missing_path(
        self, service, mock_dataset_state_manager
    ):
        """stored_image_pathが欠落している画像をスキップ"""
        # Setup
        mock_dataset_state_manager.selected_image_ids = [1, 2]
        mock_dataset_state_manager.get_image_by_id.side_effect = [
            {"id": 1, "stored_image_path": "/path/to/image1.jpg"},
            {"id": 2},  # No stored_image_path
        ]

        # Execute
        result = service.get_selected_images_for_annotation()

        # Assert
        assert len(result) == 1
        assert result[0]["id"] == 1

    def test_get_selected_images_no_dataset_state_manager(self):
        """DatasetStateManagerがNoneの場合"""
        # Setup
        service = SelectionStateService(
            dataset_state_manager=None,
            db_repository=Mock(),
        )

        # Execute & Assert
        with pytest.raises(ValueError, match="DatasetStateManagerが設定されていません"):
            service.get_selected_images_for_annotation()


class TestGetSelectedImagePaths:
    """get_selected_image_paths()テスト（便利メソッド）"""

    def test_get_selected_image_paths_success(self, service, mock_dataset_state_manager):
        """パスリストのみを取得"""
        # Setup
        mock_dataset_state_manager.selected_image_ids = [1, 2]
        mock_dataset_state_manager.get_image_by_id.side_effect = [
            {"id": 1, "stored_image_path": "/path/to/image1.jpg"},
            {"id": 2, "stored_image_path": "/path/to/image2.jpg"},
        ]

        # Execute
        result = service.get_selected_image_paths()

        # Assert
        assert len(result) == 2
        assert result[0] == "/path/to/image1.jpg"
        assert result[1] == "/path/to/image2.jpg"

    def test_get_selected_image_paths_empty(self, service, mock_dataset_state_manager):
        """画像未選択時は空リスト"""
        # Setup
        mock_dataset_state_manager.selected_image_ids = []
        mock_dataset_state_manager.has_filtered_images.return_value = False

        # Execute & Assert
        with pytest.raises(ValueError):
            service.get_selected_image_paths()
