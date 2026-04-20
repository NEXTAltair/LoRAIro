"""ImageProcessingService のユニットテスト"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.services.configuration_service import ConfigurationService
from lorairo.services.image_processing_service import ImageProcessingService
from lorairo.storage.file_system import FileSystemManager


@pytest.fixture
def mock_config_service():
    svc = MagicMock(spec=ConfigurationService)
    svc.get_preferred_resolutions.return_value = [(512, 512), (768, 768)]
    svc.get_image_processing_config.return_value = {"target_resolution": 512, "upscaler": "ESRGAN"}
    return svc


@pytest.fixture
def mock_fsm():
    fsm = MagicMock(spec=FileSystemManager)
    fsm.save_processed_image.return_value = Path("/processed/image_512.png")
    fsm.get_image_info.return_value = {"width": 512, "height": 512, "mode": "RGB"}
    return fsm


@pytest.fixture
def mock_idm():
    idm = MagicMock(spec=ImageDatabaseManager)
    idm.detect_duplicate_image.return_value = None
    idm.register_original_image.return_value = (
        1,
        {"stored_image_path": "original/image.png", "has_alpha": False, "mode": "RGB"},
    )
    idm.get_image_metadata.return_value = {
        "stored_image_path": "original/image.png",
        "has_alpha": False,
        "mode": "RGB",
    }
    idm.check_processed_image_exists.return_value = None
    return idm


@pytest.fixture
def service(mock_config_service, mock_fsm, mock_idm):
    return ImageProcessingService(mock_config_service, mock_fsm, mock_idm)


@pytest.fixture
def image_file():
    return Path("/test/images/sample.png")


@pytest.fixture
def mock_image_processor_module():
    """lorairo.editor.image_processor のモジュールモック（torch 循環 import 回避）"""
    mock_module = MagicMock()
    mock_ipm = MagicMock()
    mock_module.ImageProcessingManager = MagicMock(return_value=mock_ipm)
    with patch.dict("sys.modules", {"lorairo.editor.image_processor": mock_module}):
        yield mock_module


class TestCreateProcessingManager:
    """create_processing_manager のテスト"""

    def test_success(self, service, mock_config_service, mock_image_processor_module):
        """正常系: ImageProcessingManager が返される"""
        result = service.create_processing_manager(512)

        mock_config_service.get_preferred_resolutions.assert_called_once()
        mock_image_processor_module.ImageProcessingManager.assert_called_once()
        assert result is mock_image_processor_module.ImageProcessingManager.return_value

    def test_raises_value_error_on_failure(self, service, mock_config_service, mock_image_processor_module):
        """異常系: 初期化例外 → ValueError に変換"""
        mock_config_service.get_preferred_resolutions.side_effect = Exception("config error")

        with pytest.raises(ValueError, match="ImageProcessingManager の作成に失敗しました"):
            service.create_processing_manager(512)


class TestResolveUpscaler:
    """_resolve_upscaler のテスト"""

    def test_with_override(self, service, mock_config_service, image_file):
        """override が指定された場合はそのまま返す"""
        result = service._resolve_upscaler(image_file, "RealESRGAN")

        assert result == "RealESRGAN"
        mock_config_service.get_image_processing_config.assert_not_called()

    def test_from_config(self, service, mock_config_service, image_file):
        """override が None の場合は config から取得する"""
        mock_config_service.get_image_processing_config.return_value = {"upscaler": "ESRGAN"}

        result = service._resolve_upscaler(image_file, None)

        assert result == "ESRGAN"

    def test_no_upscaler_in_config(self, service, mock_config_service, image_file):
        """override も config にも upscaler がない場合は None"""
        mock_config_service.get_image_processing_config.return_value = {}

        result = service._resolve_upscaler(image_file, None)

        assert result is None


class TestResolveOriginalMetadata:
    """_resolve_original_metadata のテスト"""

    def test_new_image_registration(self, service, mock_idm, image_file):
        """DB 未登録画像 → 新規登録して (id, metadata) を返す"""
        mock_idm.detect_duplicate_image.return_value = None
        mock_idm.register_original_image.return_value = (1, {"stored_image_path": "path.png"})

        image_id, metadata = service._resolve_original_metadata(image_file)

        assert image_id == 1
        assert metadata == {"stored_image_path": "path.png"}
        mock_idm.register_original_image.assert_called_once_with(image_file, service.fsm)

    def test_existing_image(self, service, mock_idm, image_file):
        """DB 登録済み画像 → get_image_metadata を呼び出して返す"""
        mock_idm.detect_duplicate_image.return_value = 42
        mock_idm.get_image_metadata.return_value = {"stored_image_path": "path.png"}

        image_id, metadata = service._resolve_original_metadata(image_file)

        assert image_id == 42
        assert metadata == {"stored_image_path": "path.png"}
        mock_idm.get_image_metadata.assert_called_once_with(42)

    def test_registration_returns_none(self, service, mock_idm, image_file):
        """register_original_image が None → RuntimeError"""
        mock_idm.detect_duplicate_image.return_value = None
        mock_idm.register_original_image.return_value = None

        with pytest.raises(RuntimeError, match="Failed to register"):
            service._resolve_original_metadata(image_file)

    def test_registration_returns_none_id(self, service, mock_idm, image_file):
        """登録後に id が None → RuntimeError"""
        mock_idm.detect_duplicate_image.return_value = None
        mock_idm.register_original_image.return_value = (None, {"stored_image_path": "path.png"})

        with pytest.raises(RuntimeError, match="Failed to get valid data"):
            service._resolve_original_metadata(image_file)

    def test_metadata_retrieval_fails(self, service, mock_idm, image_file):
        """get_image_metadata が None → RuntimeError"""
        mock_idm.detect_duplicate_image.return_value = 42
        mock_idm.get_image_metadata.return_value = None

        with pytest.raises(RuntimeError, match="Failed to get metadata"):
            service._resolve_original_metadata(image_file)


class TestProcessSingleImage:
    """_process_single_image のテスト"""

    def test_no_ipm_raises_runtime_error(self, service, image_file):
        """ipm が None → RuntimeError"""
        with pytest.raises(RuntimeError, match="ImageProcessingManager is not provided"):
            service._process_single_image(image_file, ipm=None)

    def test_skip_existing_processed_image(self, service, mock_idm, mock_config_service, image_file):
        """処理済み画像が既に存在する場合はスキップ"""
        mock_ipm = MagicMock()
        mock_idm.detect_duplicate_image.return_value = 1
        mock_idm.get_image_metadata.return_value = {"stored_image_path": "path.png"}
        mock_idm.check_processed_image_exists.return_value = {"stored_image_path": "processed.png"}
        mock_config_service.get_image_processing_config.return_value = {"target_resolution": 512}

        service._process_single_image(image_file, upscaler="ESRGAN", ipm=mock_ipm)

        mock_ipm.process_image.assert_not_called()

    def test_skip_when_upscaler_is_none(self, service, mock_idm, mock_config_service, image_file):
        """upscaler が解決できない場合はスキップ"""
        mock_ipm = MagicMock()
        mock_idm.detect_duplicate_image.return_value = 1
        mock_idm.get_image_metadata.return_value = {"stored_image_path": "path.png"}
        mock_idm.check_processed_image_exists.return_value = None
        mock_config_service.get_image_processing_config.return_value = {"target_resolution": 512}

        service._process_single_image(image_file, upscaler=None, ipm=mock_ipm)

        mock_ipm.process_image.assert_not_called()

    def test_successful_processing_with_upscale(self, service, mock_idm, mock_config_service, image_file):
        """アップスケール実行時: タグ追加と processed 画像登録が行われる"""
        mock_ipm = MagicMock()
        mock_image = MagicMock()
        mock_ipm.process_image.return_value = (
            mock_image,
            {"was_upscaled": True, "upscaler_used": "ESRGAN"},
        )
        mock_idm.detect_duplicate_image.return_value = 1
        mock_idm.get_image_metadata.return_value = {
            "stored_image_path": "original.png",
            "has_alpha": False,
            "mode": "RGB",
        }
        mock_idm.check_processed_image_exists.return_value = None
        mock_config_service.get_image_processing_config.return_value = {
            "target_resolution": 512,
            "upscaler": "ESRGAN",
        }

        with patch("lorairo.database.db_core.resolve_stored_path", return_value=Path("/resolved/path.png")):
            service._process_single_image(image_file, upscaler="ESRGAN", ipm=mock_ipm)

        mock_idm.save_tags.assert_called_once()
        mock_idm.register_processed_image.assert_called_once()

    def test_successful_processing_without_upscale(
        self, service, mock_idm, mock_config_service, image_file
    ):
        """アップスケールなし: タグ追加なしで processed 画像登録が行われる"""
        mock_ipm = MagicMock()
        mock_image = MagicMock()
        mock_ipm.process_image.return_value = (mock_image, {"was_upscaled": False})
        mock_idm.detect_duplicate_image.return_value = 1
        mock_idm.get_image_metadata.return_value = {
            "stored_image_path": "original.png",
            "has_alpha": False,
            "mode": "RGB",
        }
        mock_idm.check_processed_image_exists.return_value = None
        mock_config_service.get_image_processing_config.return_value = {
            "target_resolution": 512,
            "upscaler": "ESRGAN",
        }

        with patch("lorairo.database.db_core.resolve_stored_path", return_value=Path("/resolved/path.png")):
            service._process_single_image(image_file, upscaler="ESRGAN", ipm=mock_ipm)

        mock_idm.save_tags.assert_not_called()
        mock_idm.register_processed_image.assert_called_once()

    def test_processed_image_is_none(self, service, mock_idm, mock_config_service, image_file):
        """process_image が None を返した場合は register_processed_image を呼ばない"""
        mock_ipm = MagicMock()
        mock_ipm.process_image.return_value = (None, {})
        mock_idm.detect_duplicate_image.return_value = 1
        mock_idm.get_image_metadata.return_value = {
            "stored_image_path": "original.png",
            "has_alpha": False,
            "mode": "RGB",
        }
        mock_idm.check_processed_image_exists.return_value = None
        mock_config_service.get_image_processing_config.return_value = {
            "target_resolution": 512,
            "upscaler": "ESRGAN",
        }

        with patch("lorairo.database.db_core.resolve_stored_path", return_value=Path("/resolved/path.png")):
            service._process_single_image(image_file, upscaler="ESRGAN", ipm=mock_ipm)

        mock_idm.register_processed_image.assert_not_called()


class TestEnsure512pxImage:
    """ensure_512px_image のテスト"""

    def test_existing_512px_path_exists(self, service, mock_idm, tmp_path):
        """512px 画像が DB とファイルシステムに存在する場合はそのパスを返す"""
        img_path = tmp_path / "image_512.png"
        img_path.touch()
        mock_idm.check_processed_image_exists.return_value = {"stored_image_path": "image_512.png"}

        with patch("lorairo.database.db_core.resolve_stored_path", return_value=img_path):
            result = service.ensure_512px_image(1)

        assert result == img_path
        mock_idm.get_image_metadata.assert_not_called()

    def test_existing_512px_file_missing_then_creates(self, service, mock_idm, tmp_path):
        """512px 画像が DB にあるがファイル不在 → 新規作成フロー"""
        missing_path = tmp_path / "nonexistent.png"
        new_path = tmp_path / "new_512.png"
        new_path.touch()

        mock_idm.check_processed_image_exists.side_effect = [
            {"stored_image_path": "nonexistent.png"},
            {"stored_image_path": "new_512.png"},
        ]
        mock_idm.get_image_metadata.return_value = {"stored_image_path": "original.png"}

        with (
            patch("lorairo.database.db_core.resolve_stored_path") as mock_resolve,
            patch.object(service, "_process_single_image_for_resolution"),
        ):
            mock_resolve.side_effect = [missing_path, Path("/original/path.png"), new_path]
            result = service.ensure_512px_image(1)

        assert result == new_path

    def test_creates_512px_successfully(self, service, mock_idm, tmp_path):
        """512px 画像が未存在 → 作成後にパスを返す"""
        new_path = tmp_path / "new_512.png"
        new_path.touch()

        mock_idm.check_processed_image_exists.side_effect = [
            None,
            {"stored_image_path": "new_512.png"},
        ]
        mock_idm.get_image_metadata.return_value = {"stored_image_path": "original.png"}

        with (
            patch("lorairo.database.db_core.resolve_stored_path") as mock_resolve,
            patch.object(service, "_process_single_image_for_resolution"),
        ):
            mock_resolve.side_effect = [Path("/original/path.png"), new_path]
            result = service.ensure_512px_image(1)

        assert result == new_path

    def test_no_metadata_returns_none(self, service, mock_idm):
        """元画像のメタデータが取得できない場合は None を返す"""
        mock_idm.check_processed_image_exists.return_value = None
        mock_idm.get_image_metadata.return_value = None

        result = service.ensure_512px_image(1)

        assert result is None

    def test_exception_returns_none(self, service, mock_idm):
        """例外発生時は None を返す（例外は伝播しない）"""
        mock_idm.check_processed_image_exists.return_value = None
        mock_idm.get_image_metadata.return_value = {"stored_image_path": "original.png"}

        with (
            patch("lorairo.database.db_core.resolve_stored_path", return_value=Path("/original/path.png")),
            patch.object(
                service, "_process_single_image_for_resolution", side_effect=Exception("処理失敗")
            ),
        ):
            result = service.ensure_512px_image(1)

        assert result is None


class TestAddUpscaledTag:
    """_add_upscaled_tag のテスト"""

    def test_successful_tag_addition(self, service, mock_idm):
        """upscaled タグが正しい内容で save_tags に渡される"""
        service._add_upscaled_tag(1, "ESRGAN")

        mock_idm.save_tags.assert_called_once()
        call_args = mock_idm.save_tags.call_args
        image_id_arg, tags_arg = call_args[0]
        assert image_id_arg == 1
        assert len(tags_arg) == 1
        tag = tags_arg[0]
        assert tag["tag"] == "upscaled"
        assert tag["tag_id"] == 33138
        assert tag["model_id"] is None

    def test_exception_does_not_propagate(self, service, mock_idm):
        """save_tags が例外を投げても RuntimeError を伝播させない"""
        mock_idm.save_tags.side_effect = Exception("DB error")

        service._add_upscaled_tag(1, "ESRGAN")  # 例外が発生しないこと


class TestProcessSingleImageForResolution:
    """_process_single_image_for_resolution のテスト"""

    def test_skip_existing(self, service, mock_idm, image_file):
        """処理済み画像が既に存在する場合はスキップ"""
        mock_idm.check_processed_image_exists.return_value = {"stored_image_path": "processed.png"}

        service._process_single_image_for_resolution(image_file, 1, 512)

        mock_idm.get_image_metadata.assert_not_called()

    def test_no_metadata_raises_runtime_error(self, service, mock_idm, image_file):
        """get_image_metadata が None → RuntimeError"""
        mock_idm.check_processed_image_exists.return_value = None
        mock_idm.get_image_metadata.return_value = None

        with pytest.raises(RuntimeError, match="Failed to get metadata"):
            service._process_single_image_for_resolution(image_file, 1, 512)

    def test_successful_processing(
        self, service, mock_idm, mock_config_service, image_file, mock_image_processor_module
    ):
        """正常系: 画像処理成功 → register_processed_image が呼ばれる"""
        mock_idm.check_processed_image_exists.return_value = None
        mock_idm.get_image_metadata.return_value = {
            "stored_image_path": "original.png",
            "has_alpha": False,
            "mode": "RGB",
        }
        mock_config_service.get_image_processing_config.return_value = {
            "target_resolution": 512,
            "upscaler": "ESRGAN",
        }
        mock_image = MagicMock()
        mock_ipm_instance = mock_image_processor_module.ImageProcessingManager.return_value
        mock_ipm_instance.process_image.return_value = (mock_image, {"was_upscaled": False})

        with patch("lorairo.database.db_core.resolve_stored_path", return_value=Path("/resolved/path.png")):
            service._process_single_image_for_resolution(image_file, 1, 512)

        mock_idm.register_processed_image.assert_called_once()

    def test_none_result_raises_runtime_error(
        self, service, mock_idm, mock_config_service, image_file, mock_image_processor_module
    ):
        """process_image が None を返した場合は RuntimeError"""
        mock_idm.check_processed_image_exists.return_value = None
        mock_idm.get_image_metadata.return_value = {
            "stored_image_path": "original.png",
            "has_alpha": False,
            "mode": "RGB",
        }
        mock_config_service.get_image_processing_config.return_value = {
            "target_resolution": 512,
            "upscaler": "ESRGAN",
        }
        mock_ipm_instance = mock_image_processor_module.ImageProcessingManager.return_value
        mock_ipm_instance.process_image.return_value = (None, {})

        with patch("lorairo.database.db_core.resolve_stored_path", return_value=Path("/resolved/path.png")):
            with pytest.raises(RuntimeError, match="Image processing returned None"):
                service._process_single_image_for_resolution(image_file, 1, 512)


class TestProcessImagesInList:
    """process_images_in_list のテスト"""

    def test_empty_list(self, service, mock_image_processor_module):
        """空リスト → 処理なし、完了メッセージのみ"""
        status_callback = MagicMock()

        service.process_images_in_list([], 512, status_callback=status_callback)

        status_callback.assert_called_with("画像処理が完了しました。")

    def test_cancellation_mid_process(self, service, mock_image_processor_module, tmp_path):
        """2枚目でキャンセル → 残り処理しない"""
        files = [tmp_path / "a.png", tmp_path / "b.png", tmp_path / "c.png"]
        cancel_count = {"n": 0}

        def is_canceled():
            cancel_count["n"] += 1
            return cancel_count["n"] >= 2

        with patch.object(service, "_process_single_image") as mock_process:
            service.process_images_in_list(files, 512, is_canceled=is_canceled)

        assert mock_process.call_count == 1

    def test_progress_callback(self, service, mock_image_processor_module, tmp_path):
        """3枚処理 → progress_callback に 33, 66, 100 が渡される"""
        files = [tmp_path / "a.png", tmp_path / "b.png", tmp_path / "c.png"]
        progress_callback = MagicMock()

        with patch.object(service, "_process_single_image"):
            service.process_images_in_list(files, 512, progress_callback=progress_callback)

        calls = [c[0][0] for c in progress_callback.call_args_list]
        assert calls == [33, 66, 100]

    def test_status_callback(self, service, mock_image_processor_module, tmp_path):
        """各画像で status_callback が呼ばれる"""
        files = [tmp_path / "a.png", tmp_path / "b.png"]
        status_callback = MagicMock()

        with patch.object(service, "_process_single_image"):
            service.process_images_in_list(files, 512, status_callback=status_callback)

        assert status_callback.call_count >= 3  # 各画像分 + 完了メッセージ

    def test_error_continues_processing(self, service, mock_image_processor_module, tmp_path):
        """1枚目が例外 → エラーをログに記録して2枚目も処理する"""
        files = [tmp_path / "a.png", tmp_path / "b.png"]
        call_count = {"n": 0}

        def mock_process(image_file, upscaler, ipm):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("処理失敗")

        with patch.object(service, "_process_single_image", side_effect=mock_process):
            service.process_images_in_list(files, 512)

        assert call_count["n"] == 2
