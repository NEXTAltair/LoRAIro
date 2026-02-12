# tests/unit/conftest.py
"""
ユニットテスト層の共有フィクスチャ

責務:
- 外部API モック実装（OpenAI, Google等）
- ダミーデータ生成
- サービス/マネージャー用モック

このファイルは tests/conftest.py (ルート) に依存します。
ルート conftest では genai-tag-db-tools モックと Qt 設定が済みです。
"""

from unittest.mock import MagicMock, Mock, patch

import numpy as np
import pytest
from PIL import Image

# ===== External API Mocks =====


@pytest.fixture
def mock_openai():
    """OpenAI API モック"""
    with patch("openai.ChatCompletion.create") as mock:
        mock.return_value = Mock(choices=[Mock(message=Mock(content="test response"))])
        yield mock


@pytest.fixture
def mock_google_vision():
    """Google Vision API モック"""
    with patch("google.cloud.vision.ImageAnnotatorClient") as mock:
        yield mock


@pytest.fixture
def mock_anthropic():
    """Anthropic Claude API モック"""
    with patch("anthropic.Anthropic") as mock:
        yield mock


# ===== Dummy Data Fixtures =====


@pytest.fixture
def dummy_pil_image() -> Image.Image:
    """ダミー PIL Image（100x100 RGB）"""
    return Image.new("RGB", (100, 100), color="red")


@pytest.fixture
def dummy_image_array() -> np.ndarray:
    """ダミー numpy 配列（100x100x3）"""
    return np.zeros((100, 100, 3), dtype=np.uint8)


@pytest.fixture
def dummy_image_path(tmp_path):
    """ダミー画像ファイルパス"""
    img = Image.new("RGB", (100, 100), color="blue")
    img_path = tmp_path / "test_image.png"
    img.save(img_path)
    return img_path


# ===== Service Mocks =====


@pytest.fixture
def mock_config_service():
    """ConfigService モック"""
    mock = Mock()
    mock.get_setting.return_value = None
    mock.get_all_settings.return_value = {}
    return mock


@pytest.fixture
def mock_db_manager():
    """ImageDatabaseManager モック"""
    mock = Mock()
    mock.get_all_images.return_value = []
    mock.save_image.return_value = None
    return mock


@pytest.fixture
def mock_file_system_manager():
    """FileSystemManager モック"""
    mock = Mock()
    mock.get_image_files.return_value = []
    mock.create_directory.return_value = None
    return mock


@pytest.fixture
def mock_image_processor():
    """ImageProcessor モック"""
    mock = Mock()
    mock.process.return_value = np.zeros((256, 256, 3))
    return mock


# ===== Batch Processing Mocks =====


@pytest.fixture
def mock_batch_processor():
    """BatchProcessor モック"""
    mock = Mock()
    mock.process_batch.return_value = {"success": 0, "failed": 0}
    return mock


@pytest.fixture
def mock_worker_service():
    """WorkerService モック"""
    mock = Mock()
    mock.get_active_worker_count.return_value = 0
    mock.cancel_all_workers.return_value = True
    return mock


# ===== Test Data Factories =====


@pytest.fixture
def sample_image_metadata():
    """サンプル画像メタデータ"""
    return {
        "id": 1,
        "filename": "test.png",
        "original_path": "/tmp/test.png",
        "phash": "abc123",
        "width": 512,
        "height": 512,
    }


@pytest.fixture
def sample_annotation():
    """サンプルアノテーション"""
    return {
        "text": "a dog running in a field",
        "tags": ["dog", "running", "field"],
        "model": "gpt-4",
    }


# ===== Scope Helpers =====


@pytest.fixture
def isolated_temp_dir(tmp_path):
    """隔離された一時ディレクトリ"""
    return tmp_path


# ===== Automatic Marker Application =====


def pytest_collection_modifyitems(config, items):
    """tests/unit 配下のテストに @pytest.mark.unit を自動付与"""
    for item in items:
        if "tests/unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
