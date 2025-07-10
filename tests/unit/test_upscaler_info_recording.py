"""アップスケーラー情報記録機能の単体テスト"""

import unittest.mock
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.services.configuration_service import ConfigurationService
from lorairo.services.image_processing_service import ImageProcessingService
from lorairo.storage.file_system import FileSystemManager


class TestUpscalerInfoRecording:
    """アップスケーラー情報記録機能のテスト"""

    @pytest.fixture
    def mock_config_service(self):
        """ConfigurationServiceのモック"""
        config_service = MagicMock(spec=ConfigurationService)
        config_service.get_image_processing_config.return_value = {
            "target_resolution": 1024,
            "upscaler": "RealESRGAN_x4plus"
        }
        config_service.get_preferred_resolutions.return_value = [512, 768, 1024]
        return config_service

    @pytest.fixture
    def mock_fsm(self):
        """FileSystemManagerのモック"""
        fsm = MagicMock(spec=FileSystemManager)
        fsm.save_processed_image.return_value = Path("/test/processed/image.webp")
        fsm.get_image_info.return_value = {
            "width": 1024,
            "height": 1024,
            "has_alpha": False,
            "mode": "RGB",
            "filename": "image.webp"
        }
        return fsm

    @pytest.fixture
    def mock_idm(self):
        """ImageDatabaseManagerのモック"""
        idm = MagicMock(spec=ImageDatabaseManager)
        idm.detect_duplicate_image.return_value = None
        idm.register_original_image.return_value = (1, {"width": 512, "height": 512})
        idm.get_image_metadata.return_value = {
            "has_alpha": False,
            "mode": "RGB",
            "stored_image_path": "/test/original/image.jpg"
        }
        idm.check_processed_image_exists.return_value = None
        idm.register_processed_image.return_value = 1
        return idm

    @pytest.fixture
    def image_processing_service(self, mock_config_service, mock_fsm, mock_idm):
        """ImageProcessingServiceのインスタンス"""
        return ImageProcessingService(mock_config_service, mock_fsm, mock_idm)

    def test_upscaler_metadata_recorded_when_upscaled(self, image_processing_service, mock_fsm, mock_idm):
        """アップスケール実行時にメタデータが記録されることをテスト"""
        # モックの設定
        test_image_path = Path("/test/image.jpg")
        mock_processed_image = MagicMock()
        
        # ImageProcessingManagerのモック
        with patch('lorairo.services.image_processing_service.ImageProcessingManager') as mock_ipm_class:
            mock_ipm = MagicMock()
            mock_ipm_class.return_value = mock_ipm
            
            # アップスケールが実行された場合のメタデータを返す
            processing_metadata = {
                "was_upscaled": True,
                "upscaler_used": "RealESRGAN_x4plus"
            }
            mock_ipm.process_image.return_value = (mock_processed_image, processing_metadata)
            
            # テスト実行
            image_processing_service._process_single_image(test_image_path, "RealESRGAN_x4plus", mock_ipm)
            
            # アップスケール情報がメタデータに追加されたことを確認
            mock_fsm.get_image_info.assert_called_once()
            mock_idm.register_processed_image.assert_called_once()
            
            # register_processed_imageの呼び出し引数を確認
            call_args = mock_idm.register_processed_image.call_args
            processed_metadata = call_args[0][2]  # 第3引数がprocessed_metadata
            
            assert "upscaler_used" in processed_metadata
            assert processed_metadata["upscaler_used"] == "RealESRGAN_x4plus"

    def test_no_upscaler_metadata_when_not_upscaled(self, image_processing_service, mock_fsm, mock_idm):
        """アップスケール未実行時にメタデータが記録されないことをテスト"""
        # モックの設定
        test_image_path = Path("/test/image.jpg")
        mock_processed_image = MagicMock()
        
        # ImageProcessingManagerのモック
        with patch('lorairo.services.image_processing_service.ImageProcessingManager') as mock_ipm_class:
            mock_ipm = MagicMock()
            mock_ipm_class.return_value = mock_ipm
            
            # アップスケールが実行されなかった場合のメタデータを返す
            processing_metadata = {
                "was_upscaled": False,
                "upscaler_used": None
            }
            mock_ipm.process_image.return_value = (mock_processed_image, processing_metadata)
            
            # テスト実行
            image_processing_service._process_single_image(test_image_path, "RealESRGAN_x4plus", mock_ipm)
            
            # register_processed_imageの呼び出し引数を確認
            call_args = mock_idm.register_processed_image.call_args
            processed_metadata = call_args[0][2]  # 第3引数がprocessed_metadata
            
            # アップスケール情報が追加されていないことを確認
            assert "upscaler_used" not in processed_metadata

    def test_upscaled_tag_added_when_upscaled(self, image_processing_service):
        """アップスケール実行時にupscaledタグが追加されることをテスト"""
        # モックの設定
        test_image_path = Path("/test/image.jpg")
        mock_processed_image = MagicMock()
        
        # ImageProcessingManagerのモック
        with patch('lorairo.services.image_processing_service.ImageProcessingManager') as mock_ipm_class:
            mock_ipm = MagicMock()
            mock_ipm_class.return_value = mock_ipm
            
            # アップスケールが実行された場合のメタデータを返す
            processing_metadata = {
                "was_upscaled": True,
                "upscaler_used": "RealESRGAN_x4plus"
            }
            mock_ipm.process_image.return_value = (mock_processed_image, processing_metadata)
            
            # _add_upscaled_tagメソッドをモック
            with patch.object(image_processing_service, '_add_upscaled_tag') as mock_add_tag:
                # テスト実行
                image_processing_service._process_single_image(test_image_path, "RealESRGAN_x4plus", mock_ipm)
                
                # upscaledタグが追加されたことを確認
                mock_add_tag.assert_called_once_with(1, "RealESRGAN_x4plus")

    def test_add_upscaled_tag_creates_correct_tag(self, image_processing_service, mock_idm):
        """_add_upscaled_tagメソッドが正しいタグを作成することをテスト"""
        # テスト実行
        image_processing_service._add_upscaled_tag(123, "RealESRGAN_x4plus")
        
        # save_tagsが正しい引数で呼び出されたことを確認
        mock_idm.save_tags.assert_called_once()
        call_args = mock_idm.save_tags.call_args
        image_id = call_args[0][0]
        tags_data = call_args[0][1]
        
        assert image_id == 123
        assert len(tags_data) == 1
        
        tag_data = tags_data[0]
        assert tag_data["tag"] == "upscaled"
        assert tag_data["tag_id"] == 33138
        assert tag_data["model_id"] is None
        assert tag_data["existing"] is False
        assert tag_data["is_edited_manually"] is False

    def test_512px_generation_uses_image_processing_manager(self, mock_idm):
        """512px生成がImageProcessingManagerを使用することをテスト"""
        # モックの設定
        test_image_path = Path("/test/original.jpg")
        original_metadata = {
            "width": 256,
            "height": 256,
            "has_alpha": False,
            "mode": "RGB"
        }
        mock_fsm = MagicMock(spec=FileSystemManager)
        mock_processed_image = MagicMock()
        
        # ImageProcessingManagerのモック
        with patch('lorairo.editor.image_processor.ImageProcessingManager') as mock_ipm_class:
            mock_ipm = MagicMock()
            mock_ipm_class.return_value = mock_ipm
            
            # アップスケールが実行された場合のメタデータを返す
            processing_metadata = {
                "was_upscaled": True,
                "upscaler_used": "RealESRGAN_x4plus"
            }
            mock_ipm.process_image.return_value = (mock_processed_image, processing_metadata)
            
            # save_processed_imageとget_image_infoのモック
            mock_fsm.save_processed_image.return_value = Path("/test/512px.webp")
            mock_fsm.get_image_info.return_value = {
                "width": 512,
                "height": 512,
                "has_alpha": False,
                "mode": "RGB",
                "filename": "512px.webp"
            }
            mock_idm.register_processed_image.return_value = 1
            
            # テスト実行
            mock_idm._generate_thumbnail_512px(123, test_image_path, original_metadata, mock_fsm)
            
            # ImageProcessingManagerが使用されたことを確認
            mock_ipm_class.assert_called_once()
            mock_ipm.process_image.assert_called_once()
            
            # register_processed_imageが正しいメタデータで呼び出されたことを確認
            call_args = mock_idm.register_processed_image.call_args
            processed_metadata_arg = call_args[0][2]
            assert "upscaler_used" in processed_metadata_arg
            assert processed_metadata_arg["upscaler_used"] == "RealESRGAN_x4plus"