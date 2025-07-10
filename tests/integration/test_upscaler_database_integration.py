"""アップスケーラー情報記録のデータベース統合テスト"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from lorairo.database.db_core import create_db_engine
from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.db_repository import ImageRepository
from lorairo.services.configuration_service import ConfigurationService
from lorairo.services.image_processing_service import ImageProcessingService
from lorairo.storage.file_system import FileSystemManager


@pytest.fixture
def temp_db_path():
    """テスト用の一時データベースパス"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)
    yield db_path
    # クリーンアップ
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def test_database(temp_db_path):
    """テスト用データベースの初期化"""
    from lorairo.database.schema import Base
    
    database_url = f"sqlite:///{temp_db_path.resolve()}?check_same_thread=False"
    engine = create_db_engine(database_url)
    Base.metadata.create_all(engine)
    return temp_db_path


@pytest.fixture
def image_repository(test_database):
    """ImageRepositoryのインスタンス"""
    from lorairo.database.db_core import create_session_factory
    
    database_url = f"sqlite:///{test_database.resolve()}?check_same_thread=False"
    engine = create_db_engine(database_url)
    session_factory = create_session_factory(engine)
    return ImageRepository(session_factory)


@pytest.fixture
def image_db_manager(image_repository):
    """ImageDatabaseManagerのインスタンス"""
    from lorairo.services.configuration_service import ConfigurationService
    config_service = ConfigurationService()
    return ImageDatabaseManager(image_repository, config_service)


@pytest.fixture
def test_image():
    """テスト用の小さな画像を作成"""
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        # 256x256の小さな画像を作成（アップスケール対象）
        img = Image.new('RGB', (256, 256), color='red')
        img.save(tmp.name, 'JPEG')
        yield Path(tmp.name)
    # クリーンアップ
    Path(tmp.name).unlink(missing_ok=True)


class TestUpscalerDatabaseIntegration:
    """アップスケーラー情報のデータベース統合テスト"""

    def test_processed_image_schema_has_upscaler_used_column(self, test_database):
        """ProcessedImageテーブルにupscaler_usedカラムが存在することをテスト"""
        import sqlite3
        
        conn = sqlite3.connect(test_database)
        cursor = conn.execute("PRAGMA table_info(processed_images)")
        columns = [row[1] for row in cursor.fetchall()]
        conn.close()
        
        assert "upscaler_used" in columns

    def test_processed_image_with_upscaler_info_insertion(self, image_db_manager):
        """アップスケーラー情報付きでProcessedImageレコードが挿入できることをテスト"""
        # まずオリジナル画像を登録
        original_metadata = {
            "uuid": "test-uuid-123",
            "phash": "test-phash-123",
            "original_image_path": "/test/original.jpg",
            "stored_image_path": "/test/stored.jpg",
            "width": 256,
            "height": 256,
            "format": "JPEG",
            "mode": "RGB",
            "has_alpha": False,
            "filename": "test.jpg",
            "extension": ".jpg"
        }
        
        image_id = image_db_manager.repository.add_original_image(original_metadata)
        assert image_id is not None
        
        # アップスケーラー情報付きでProcessedImageを登録
        processed_metadata = {
            "image_id": image_id,
            "stored_image_path": "/test/processed_1024.webp",
            "width": 1024,
            "height": 1024,
            "mode": "RGB",
            "has_alpha": False,
            "filename": "processed_1024.webp",
            "upscaler_used": "RealESRGAN_x4plus"
        }
        
        processed_id = image_db_manager.register_processed_image(
            image_id, Path(processed_metadata["stored_image_path"]), processed_metadata
        )
        assert processed_id is not None
        
        # データベースから取得して確認
        result = image_db_manager.repository.get_processed_image(image_id, all_data=True)
        assert isinstance(result, list)
        assert len(result) == 1
        
        processed_image = result[0]
        assert processed_image["upscaler_used"] == "RealESRGAN_x4plus"

    def test_processed_image_without_upscaler_info_insertion(self, image_db_manager):
        """アップスケーラー情報なしでProcessedImageレコードが挿入できることをテスト"""
        # まずオリジナル画像を登録
        original_metadata = {
            "uuid": "test-uuid-456",
            "phash": "test-phash-456",
            "original_image_path": "/test/original2.jpg",
            "stored_image_path": "/test/stored2.jpg",
            "width": 1024,
            "height": 1024,
            "format": "JPEG",
            "mode": "RGB",
            "has_alpha": False,
            "filename": "test2.jpg",
            "extension": ".jpg"
        }
        
        image_id = image_db_manager.repository.add_original_image(original_metadata)
        assert image_id is not None
        
        # アップスケーラー情報なしでProcessedImageを登録
        processed_metadata = {
            "image_id": image_id,
            "stored_image_path": "/test/processed_512.webp",
            "width": 512,
            "height": 512,
            "mode": "RGB",
            "has_alpha": False,
            "filename": "processed_512.webp"
            # upscaler_used は意図的に含めない
        }
        
        processed_id = image_db_manager.register_processed_image(
            image_id, Path(processed_metadata["stored_image_path"]), processed_metadata
        )
        assert processed_id is not None
        
        # データベースから取得して確認
        result = image_db_manager.repository.get_processed_image(image_id, all_data=True)
        assert isinstance(result, list)
        assert len(result) == 1
        
        processed_image = result[0]
        assert processed_image["upscaler_used"] is None

    def test_upscaled_tag_integration(self, image_db_manager):
        """upscaledタグの統合テスト"""
        # オリジナル画像を登録
        original_metadata = {
            "uuid": "test-uuid-789",
            "phash": "test-phash-789",
            "original_image_path": "/test/original3.jpg",
            "stored_image_path": "/test/stored3.jpg",
            "width": 256,
            "height": 256,
            "format": "JPEG",
            "mode": "RGB",
            "has_alpha": False,
            "filename": "test3.jpg",
            "extension": ".jpg"
        }
        
        image_id = image_db_manager.repository.add_original_image(original_metadata)
        assert image_id is not None
        
        # ConfigurationServiceとFileSystemManagerをモック
        mock_config_service = MagicMock(spec=ConfigurationService)
        mock_fsm = MagicMock(spec=FileSystemManager)
        
        # ImageProcessingServiceを作成
        service = ImageProcessingService(mock_config_service, mock_fsm, image_db_manager)
        
        # upscaledタグを追加
        service._add_upscaled_tag(image_id, "RealESRGAN_x4plus")
        
        # データベースからタグを取得して確認
        annotations = image_db_manager.get_image_annotations(image_id)
        
        assert "tags" in annotations
        tags = annotations["tags"]
        assert len(tags) > 0
        
        # upscaledタグが存在することを確認
        upscaled_tags = [tag for tag in tags if tag["tag"] == "upscaled"]
        assert len(upscaled_tags) == 1
        
        upscaled_tag = upscaled_tags[0]
        assert upscaled_tag["tag_id"] == 33138
        assert upscaled_tag["existing"] is False
        assert upscaled_tag["is_edited_manually"] is False

    @patch('lorairo.editor.image_processor.ImageProcessingManager')
    def test_512px_generation_with_upscaler_info(self, mock_ipm_class, image_db_manager):
        """512px生成時のアップスケーラー情報記録の統合テスト"""
        # オリジナル画像を登録
        original_metadata = {
            "uuid": "test-uuid-512",
            "phash": "test-phash-512",
            "original_image_path": "/test/small.jpg",
            "stored_image_path": "/test/stored_small.jpg",
            "width": 200,
            "height": 200,
            "format": "JPEG",
            "mode": "RGB",
            "has_alpha": False,
            "filename": "small.jpg",
            "extension": ".jpg"
        }
        
        image_id = image_db_manager.repository.add_original_image(original_metadata)
        assert image_id is not None
        
        # ImageProcessingManagerのモック設定
        mock_ipm = MagicMock()
        mock_ipm_class.return_value = mock_ipm
        
        mock_processed_image = MagicMock()
        processing_metadata = {
            "was_upscaled": True,
            "upscaler_used": "RealESRGAN_x4plus"
        }
        mock_ipm.process_image.return_value = (mock_processed_image, processing_metadata)
        
        # FileSystemManagerのモック
        mock_fsm = MagicMock(spec=FileSystemManager)
        mock_fsm.save_processed_image.return_value = Path("/test/512px.webp")
        mock_fsm.get_image_info.return_value = {
            "width": 512,
            "height": 512,
            "mode": "RGB",
            "has_alpha": False,
            "filename": "512px.webp"
        }
        
        # 512px生成を実行
        original_path = Path("/test/stored_small.jpg")
        image_db_manager._generate_thumbnail_512px(image_id, original_path, original_metadata, mock_fsm)
        
        # データベースから結果を確認
        processed_images = image_db_manager.repository.get_processed_image(image_id, all_data=True)
        assert isinstance(processed_images, list)
        assert len(processed_images) == 1
        
        processed_image = processed_images[0]
        assert processed_image["width"] == 512
        assert processed_image["height"] == 512
        assert processed_image["upscaler_used"] == "RealESRGAN_x4plus"

    def test_query_by_upscaler_used(self, image_db_manager):
        """upscaler_usedカラムでクエリできることをテスト"""
        # 複数の処理済み画像を登録（異なるアップスケーラー情報で）
        original_metadata = {
            "uuid": "test-uuid-query",
            "phash": "test-phash-query",
            "original_image_path": "/test/query.jpg",
            "stored_image_path": "/test/stored_query.jpg",
            "width": 512,
            "height": 512,
            "format": "JPEG",
            "mode": "RGB",
            "has_alpha": False,
            "filename": "query.jpg",
            "extension": ".jpg"
        }
        
        image_id = image_db_manager.repository.add_original_image(original_metadata)
        
        # RealESRGAN_x4plusで処理された画像
        processed_metadata_1 = {
            "image_id": image_id,
            "stored_image_path": "/test/proc1.webp",
            "width": 1024,
            "height": 1024,
            "mode": "RGB",
            "has_alpha": False,
            "filename": "proc1.webp",
            "upscaler_used": "RealESRGAN_x4plus"
        }
        
        # アップスケールなしの画像
        processed_metadata_2 = {
            "image_id": image_id,
            "stored_image_path": "/test/proc2.webp",
            "width": 768,
            "height": 768,
            "mode": "RGB",
            "has_alpha": False,
            "filename": "proc2.webp"
            # upscaler_used なし
        }
        
        image_db_manager.register_processed_image(
            image_id, Path(processed_metadata_1["stored_image_path"]), processed_metadata_1
        )
        image_db_manager.register_processed_image(
            image_id, Path(processed_metadata_2["stored_image_path"]), processed_metadata_2
        )
        
        # SQLクエリでアップスケーラー別に検索
        import sqlite3
        conn = sqlite3.connect(image_db_manager.repository.engine.url.database)
        
        # RealESRGAN_x4plusで処理された画像を検索
        cursor = conn.execute(
            "SELECT COUNT(*) FROM processed_images WHERE upscaler_used = ?",
            ("RealESRGAN_x4plus",)
        )
        count_with_upscaler = cursor.fetchone()[0]
        
        # アップスケーラー情報がない画像を検索
        cursor = conn.execute(
            "SELECT COUNT(*) FROM processed_images WHERE upscaler_used IS NULL"
        )
        count_without_upscaler = cursor.fetchone()[0]
        
        conn.close()
        
        assert count_with_upscaler >= 1  # 少なくとも1つはRealESRGAN_x4plusで処理
        assert count_without_upscaler >= 1  # 少なくとも1つはアップスケーラーなし