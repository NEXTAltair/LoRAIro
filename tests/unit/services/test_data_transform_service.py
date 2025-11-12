"""DataTransformServiceの単体テスト

Phase 2.4 Stage 1で作成されたDataTransformServiceのテスト。
MainWindow._resolve_optimal_thumbnail_data()から抽出されたデータ変換ロジックを検証。
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from lorairo.services.data_transform_service import DataTransformService


@pytest.fixture
def mock_db_manager():
    """DatabaseManagerのモック"""
    manager = Mock()
    manager.check_processed_image_exists = Mock(return_value=None)
    return manager


@pytest.fixture
def service(mock_db_manager):
    """DataTransformServiceインスタンス"""
    return DataTransformService(db_manager=mock_db_manager)


class TestDataTransformServiceInit:
    """初期化テスト"""

    def test_init_with_db_manager(self, mock_db_manager):
        """正常な初期化（db_manager有り）"""
        service = DataTransformService(db_manager=mock_db_manager)
        assert service.db_manager is mock_db_manager

    def test_init_without_db_manager(self):
        """db_manager無しの初期化"""
        service = DataTransformService(db_manager=None)
        assert service.db_manager is None


class TestResolveOptimalThumbnailPaths:
    """resolve_optimal_thumbnail_paths()テスト"""

    def test_resolve_empty_metadata(self, service):
        """空のメタデータリスト"""
        result = service.resolve_optimal_thumbnail_paths([])
        assert result == []

    def test_resolve_with_original_path_only(self, service):
        """元画像のみ（処理済み画像なし）"""
        # Setup
        metadata = [
            {"id": 1, "stored_image_path": "/path/to/image1.jpg"},
            {"id": 2, "stored_image_path": "/path/to/image2.jpg"},
        ]

        # Execute
        result = service.resolve_optimal_thumbnail_paths(metadata)

        # Assert
        assert len(result) == 2
        assert result[0] == (Path("/path/to/image1.jpg"), 1)
        assert result[1] == (Path("/path/to/image2.jpg"), 2)

    def test_resolve_with_processed_image(self, service, mock_db_manager, tmp_path):
        """処理済み画像が存在する場合"""
        # Setup - 一時ファイル作成
        processed_path = tmp_path / "processed_512.jpg"
        processed_path.write_text("dummy")

        metadata = [{"id": 1, "stored_image_path": "/path/to/original.jpg"}]

        # Mock processed image存在
        mock_db_manager.check_processed_image_exists.return_value = {
            "stored_image_path": str(processed_path)
        }

        # Execute
        result = service.resolve_optimal_thumbnail_paths(metadata)

        # Assert
        assert len(result) == 1
        assert result[0] == (processed_path, 1)
        mock_db_manager.check_processed_image_exists.assert_called_once_with(1, 512)

    def test_resolve_with_nonexistent_processed_image(self, service, mock_db_manager, tmp_path):
        """処理済み画像が存在しない場合（フォールバック）"""
        # Setup
        nonexistent_path = tmp_path / "nonexistent_512.jpg"  # ファイル作成しない

        metadata = [{"id": 1, "stored_image_path": "/path/to/original.jpg"}]

        # Mock processed image情報あり、ファイルなし
        mock_db_manager.check_processed_image_exists.return_value = {
            "stored_image_path": str(nonexistent_path)
        }

        # Execute
        result = service.resolve_optimal_thumbnail_paths(metadata)

        # Assert - 元画像にフォールバック
        assert len(result) == 1
        assert result[0] == (Path("/path/to/original.jpg"), 1)

    def test_resolve_without_db_manager(self):
        """db_manager無しの場合（常に元画像）"""
        # Setup
        service = DataTransformService(db_manager=None)
        metadata = [{"id": 1, "stored_image_path": "/path/to/image1.jpg"}]

        # Execute
        result = service.resolve_optimal_thumbnail_paths(metadata)

        # Assert - 元画像を使用
        assert len(result) == 1
        assert result[0] == (Path("/path/to/image1.jpg"), 1)

    def test_resolve_with_db_manager_error(self, service, mock_db_manager):
        """db_manager.check_processed_image_exists()がエラーの場合"""
        # Setup
        metadata = [{"id": 1, "stored_image_path": "/path/to/original.jpg"}]
        mock_db_manager.check_processed_image_exists.side_effect = RuntimeError("DB error")

        # Execute
        result = service.resolve_optimal_thumbnail_paths(metadata)

        # Assert - 元画像にフォールバック
        assert len(result) == 1
        assert result[0] == (Path("/path/to/original.jpg"), 1)

    def test_resolve_multiple_images_mixed(self, service, mock_db_manager, tmp_path):
        """複数画像で一部処理済み、一部元画像"""
        # Setup
        processed_path = tmp_path / "processed_512.jpg"
        processed_path.write_text("dummy")

        metadata = [
            {"id": 1, "stored_image_path": "/path/to/original1.jpg"},
            {"id": 2, "stored_image_path": "/path/to/original2.jpg"},
        ]

        # Mock: image_id=1は処理済み、image_id=2は処理済みなし
        def mock_check_processed(image_id, size):
            if image_id == 1:
                return {"stored_image_path": str(processed_path)}
            return None

        mock_db_manager.check_processed_image_exists.side_effect = mock_check_processed

        # Execute
        result = service.resolve_optimal_thumbnail_paths(metadata)

        # Assert
        assert len(result) == 2
        assert result[0] == (processed_path, 1)  # 処理済み画像
        assert result[1] == (Path("/path/to/original2.jpg"), 2)  # 元画像

    def test_resolve_with_missing_metadata_fields(self, service):
        """メタデータに必須フィールドが欠けている場合"""
        # Setup - "stored_image_path"が欠けている
        metadata = [{"id": 1}]

        # Execute & Assert - KeyErrorが発生するはず
        with pytest.raises(KeyError):
            service.resolve_optimal_thumbnail_paths(metadata)
