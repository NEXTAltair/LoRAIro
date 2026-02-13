"""512px サムネイル生成に関するImageDatabaseManagerのユニットテスト"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.db_repository import ImageRepository
from lorairo.services.configuration_service import ConfigurationService
from lorairo.storage.file_system import FileSystemManager


@pytest.fixture
def mock_repository() -> Mock:
    """MockImageRepositoryを作成"""
    return Mock(spec=ImageRepository)


@pytest.fixture
def mock_config_service() -> Mock:
    """MockConfigurationServiceを作成"""
    config_service = Mock(spec=ConfigurationService)
    config_service.get_image_processing_config.return_value = {
        "upscaler": "RealESRGAN_x4plus"
    }
    return config_service


@pytest.fixture
def mock_fsm() -> Mock:
    """MockFileSystemManagerを作成"""
    return Mock(spec=FileSystemManager)


@pytest.fixture
def db_manager(mock_repository: Mock, mock_config_service: Mock) -> ImageDatabaseManager:
    """ImageDatabaseManagerのインスタンスを作成"""
    return ImageDatabaseManager(
        repository=mock_repository,
        config_service=mock_config_service,
        fsm=None,
    )


class TestCreateAndSaveThumbnail:
    """_create_and_save_thumbnail() メソッドのテスト"""

    def test_success_creates_thumbnail_and_returns_path_and_metadata(
        self,
        db_manager: ImageDatabaseManager,
        mock_fsm: Mock,
    ) -> None:
        """正常系: 512px サムネイル作成成功時、パスとメタデータを返す"""
        # アレンジ
        image_id = 1
        original_path = Path("/data/original.jpg")
        original_metadata = {
            "width": 1024,
            "height": 1024,
            "has_alpha": False,
            "mode": "RGB",
        }

        # モック設定
        processed_image_mock = MagicMock()
        processing_metadata = {
            "was_upscaled": True,
            "upscaler_used": "RealESRGAN_x4plus",
            "width": 512,
            "height": 512,
        }

        with patch(
            "lorairo.editor.image_processor.ImageProcessingManager"
        ) as mock_ipm_class:
            mock_ipm = Mock()
            mock_ipm_class.return_value = mock_ipm
            mock_ipm.process_image.return_value = (processed_image_mock, processing_metadata)

            processed_path = Path("/data/processed_512.jpg")
            mock_fsm.save_processed_image.return_value = processed_path

            # アクト
            result = db_manager._create_and_save_thumbnail(
                image_id,
                original_path,
                original_metadata,
                mock_fsm,
            )

            # アサート
            assert result is not None
            assert result[0] == processed_path
            assert result[1] == processing_metadata

    def test_returns_none_when_processing_fails(
        self,
        db_manager: ImageDatabaseManager,
        mock_fsm: Mock,
    ) -> None:
        """画像処理が失敗したときはNoneを返す"""
        # アレンジ
        image_id = 1
        original_path = Path("/data/original.jpg")
        original_metadata = {
            "width": 256,  # 小さすぎるサイズ
            "height": 256,
            "has_alpha": False,
            "mode": "RGB",
        }

        with patch(
            "lorairo.editor.image_processor.ImageProcessingManager"
        ) as mock_ipm_class:
            mock_ipm = Mock()
            mock_ipm_class.return_value = mock_ipm
            # process_image が None を返す（処理できない）
            mock_ipm.process_image.return_value = (None, {})

            # アクト
            result = db_manager._create_and_save_thumbnail(
                image_id,
                original_path,
                original_metadata,
                mock_fsm,
            )

            # アサート
            assert result is None
            mock_fsm.save_processed_image.assert_not_called()

    def test_calls_image_processor_with_correct_parameters(
        self,
        db_manager: ImageDatabaseManager,
        mock_fsm: Mock,
    ) -> None:
        """ImageProcessingManager に正しいパラメータが渡される"""
        # アレンジ
        image_id = 1
        original_path = Path("/data/original.jpg")
        original_metadata = {
            "width": 1024,
            "height": 768,
            "has_alpha": True,
            "mode": "RGBA",
        }

        with patch(
            "lorairo.editor.image_processor.ImageProcessingManager"
        ) as mock_ipm_class:
            mock_ipm = Mock()
            mock_ipm_class.return_value = mock_ipm
            mock_ipm.process_image.return_value = (MagicMock(), {})
            mock_fsm.save_processed_image.return_value = Path("/data/processed.jpg")

            # アクト
            db_manager._create_and_save_thumbnail(
                image_id,
                original_path,
                original_metadata,
                mock_fsm,
            )

            # アサート
            mock_ipm.process_image.assert_called_once()
            call_args = mock_ipm.process_image.call_args
            assert call_args[0][0] == original_path
            assert call_args[0][1] is True  # has_alpha
            assert call_args[0][2] == "RGBA"  # mode
            assert call_args[1]["upscaler"] == "RealESRGAN_x4plus"


class TestRegisterThumbnailInDb:
    """_register_thumbnail_in_db() メソッドのテスト"""

    def test_success_registers_thumbnail_and_returns_id(
        self,
        db_manager: ImageDatabaseManager,
        mock_fsm: Mock,
        mock_repository: Mock,
    ) -> None:
        """正常系: DB登録成功時、処理済み画像IDを返す"""
        # アレンジ
        image_id = 1
        processed_path = Path("/data/processed_512.jpg")
        processing_metadata = {
            "was_upscaled": True,
            "upscaler_used": "RealESRGAN_x4plus",
        }
        original_path = Path("/data/original.jpg")

        processed_metadata = {
            "width": 512,
            "height": 512,
            "has_alpha": False,
        }

        mock_fsm.get_image_info.return_value = processed_metadata
        mock_repository.register_processed_image = Mock(return_value=5)
        db_manager.register_processed_image = Mock(return_value=5)

        # アクト
        result = db_manager._register_thumbnail_in_db(
            image_id,
            processed_path,
            processing_metadata,
            original_path,
            mock_fsm,
        )

        # アサート
        assert result == 5
        mock_fsm.get_image_info.assert_called_once_with(processed_path)

    def test_adds_upscaler_metadata_when_upscaled(
        self,
        db_manager: ImageDatabaseManager,
        mock_fsm: Mock,
    ) -> None:
        """アップスケール情報がメタデータに追加される"""
        # アレンジ
        image_id = 1
        processed_path = Path("/data/processed_512.jpg")
        processing_metadata = {
            "was_upscaled": True,
            "upscaler_used": "RealESRGAN_x4plus",
        }
        original_path = Path("/data/original.jpg")

        processed_metadata = {
            "width": 512,
            "height": 512,
            "has_alpha": False,
        }

        mock_fsm.get_image_info.return_value = processed_metadata

        with patch.object(
            db_manager,
            "register_processed_image",
            return_value=5,
        ) as mock_register:
            # アクト
            db_manager._register_thumbnail_in_db(
                image_id,
                processed_path,
                processing_metadata,
                original_path,
                mock_fsm,
            )

            # アサート
            # register_processed_image が呼ばれたことを確認
            mock_register.assert_called_once()
            call_args = mock_register.call_args[0]
            # メタデータに upscaler_used が追加されているか確認
            passed_metadata = call_args[2]
            assert "upscaler_used" in passed_metadata
            assert passed_metadata["upscaler_used"] == "RealESRGAN_x4plus"

    def test_returns_none_when_registration_fails(
        self,
        db_manager: ImageDatabaseManager,
        mock_fsm: Mock,
    ) -> None:
        """DB登録が失敗したときはNoneを返す"""
        # アレンジ
        image_id = 1
        processed_path = Path("/data/processed_512.jpg")
        processing_metadata = {"was_upscaled": False}
        original_path = Path("/data/original.jpg")

        processed_metadata = {
            "width": 512,
            "height": 512,
            "has_alpha": False,
        }

        mock_fsm.get_image_info.return_value = processed_metadata

        with patch.object(
            db_manager,
            "register_processed_image",
            return_value=None,
        ):
            # アクト
            result = db_manager._register_thumbnail_in_db(
                image_id,
                processed_path,
                processing_metadata,
                original_path,
                mock_fsm,
            )

            # アサート
            assert result is None


class TestGenerateThumbnail512px:
    """_generate_thumbnail_512px() メソッドのテスト"""

    def test_success_orchestrates_thumbnail_generation(
        self,
        db_manager: ImageDatabaseManager,
        mock_fsm: Mock,
    ) -> None:
        """正常系: 2つのステップを順序正しく実行"""
        # アレンジ
        image_id = 1
        original_path = Path("/data/original.jpg")
        original_metadata = {
            "width": 1024,
            "height": 1024,
            "has_alpha": False,
            "mode": "RGB",
        }

        processed_path = Path("/data/processed_512.jpg")
        processing_metadata = {"was_upscaled": True}

        with patch.object(
            db_manager,
            "_create_and_save_thumbnail",
            return_value=(processed_path, processing_metadata),
        ) as mock_create:
            with patch.object(
                db_manager,
                "_register_thumbnail_in_db",
                return_value=5,
            ) as mock_register:
                # アクト
                db_manager._generate_thumbnail_512px(
                    image_id,
                    original_path,
                    original_metadata,
                    mock_fsm,
                )

                # アサート
                mock_create.assert_called_once_with(
                    image_id,
                    original_path,
                    original_metadata,
                    mock_fsm,
                )
                mock_register.assert_called_once()

    def test_stops_when_thumbnail_creation_fails(
        self,
        db_manager: ImageDatabaseManager,
        mock_fsm: Mock,
    ) -> None:
        """スムネイル作成失敗時、DB登録は実行されない"""
        # アレンジ
        image_id = 1
        original_path = Path("/data/original.jpg")
        original_metadata = {
            "width": 256,
            "height": 256,
            "has_alpha": False,
            "mode": "RGB",
        }

        with patch.object(
            db_manager,
            "_create_and_save_thumbnail",
            return_value=None,
        ) as mock_create:
            with patch.object(
                db_manager,
                "_register_thumbnail_in_db",
            ) as mock_register:
                # アクト
                db_manager._generate_thumbnail_512px(
                    image_id,
                    original_path,
                    original_metadata,
                    mock_fsm,
                )

                # アサート
                mock_create.assert_called_once()
                # DB登録は実行されない
                mock_register.assert_not_called()

    def test_handles_exception_and_raises(
        self,
        db_manager: ImageDatabaseManager,
        mock_fsm: Mock,
    ) -> None:
        """例外が発生したときは上位に伝える"""
        # アレンジ
        image_id = 1
        original_path = Path("/data/original.jpg")
        original_metadata = {
            "width": 1024,
            "height": 1024,
            "has_alpha": False,
            "mode": "RGB",
        }

        with patch.object(
            db_manager,
            "_create_and_save_thumbnail",
            side_effect=RuntimeError("Image processing error"),
        ):
            # アクト & アサート
            with pytest.raises(RuntimeError):
                db_manager._generate_thumbnail_512px(
                    image_id,
                    original_path,
                    original_metadata,
                    mock_fsm,
                )
