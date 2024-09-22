import pytest
from unittest.mock import MagicMock
from pathlib import Path
import sys
# プロジェクトルートの src ディレクトリを追加
sys.path.append(str(Path(__file__).resolve().parent.parent / 'src'))

from module.file_sys import FileSystemManager
from module.db import SQLiteManager, ImageRepository, ImageDatabaseManager
from src.module.config import get_config

# 一時ディレクトリのパスをここで指定しないと、パーミッションエラーが出る
@pytest.fixture(scope="session")
def tmp_path_factory(request):
    return request.config.rootpath / "TEST" / "pytest_temp"

@pytest.fixture(scope="session")
def tmp_path(tmp_path_factory):
    return tmp_path_factory

@pytest.fixture(scope="session")
def test_db_paths(tmp_path):
    img_db = tmp_path / "db" / "test_image_database.db"
    tag_db = tmp_path / "db" / "test_tag_database.db"
    img_db.parent.mkdir(parents=True, exist_ok=True)
    tag_db.parent.mkdir(parents=True, exist_ok=True)
    return img_db, tag_db

@pytest.fixture(scope="module")
def sqlite_manager(test_db_paths):
    img_db, tag_db = test_db_paths
    manager = SQLiteManager(img_db, tag_db)
    manager.create_tables()
    manager.insert_models()
    yield manager
    manager.close()
    img_db.unlink(missing_ok=True)
    tag_db.unlink(missing_ok=True)

@pytest.fixture
def sqlite_manager_function(tmp_path):
    img_db, tag_db = tmp_path / "test_image.db", tmp_path / "test_tag.db"
    manager = SQLiteManager(img_db, tag_db)
    manager.create_tables()
    manager.insert_models()
    yield manager
    manager.close()
    img_db.unlink(missing_ok=True)
    tag_db.unlink(missing_ok=True)

@pytest.fixture
def mock_file_system_manager(tmp_path):
    """
    FileSystemManager のモックを提供します。
    テスト用の一時ディレクトリを使用します。
    """
    mock_fs = MagicMock(spec=FileSystemManager)
    mock_fs.original_images_dir = tmp_path / "original_images"
    mock_fs.resized_images_dir = tmp_path / "resized_images"
    mock_fs.batch_request_dir = tmp_path / 'batch_request_jsonl'
    mock_fs.original_images_dir.mkdir(parents=True, exist_ok=True)
    mock_fs.resized_images_dir.mkdir(parents=True, exist_ok=True)
    mock_fs.batch_request_dir.mkdir(parents=True, exist_ok=True)
    return mock_fs

@pytest.fixture(scope="session")
def preferred_resolutions():
    config = get_config()
    return config['preferred_resolutions']

@pytest.fixture
def sample_images(tmp_path):
    """
    テスト用のサンプル画像を作成し、そのパスを提供します。
    """
    from PIL import Image

    # RGB512 画像
    rgb512_image = Image.new('RGB', (512, 512), color='red')
    rgb512_path = tmp_path / "rgb512_image.jpg"
    rgb512_image.save(rgb512_path)

    # RGB 画像
    rgb_image = Image.new('RGB', (800, 600), color='red')
    rgb_path = tmp_path / "rgb_image.jpg"
    rgb_image.save(rgb_path)

    # RGBA 画像
    rgba_image = Image.new('RGBA', (800, 600), color=(0, 255, 0, 128))
    rgba_path = tmp_path / "rgba_image.png"
    rgba_image.save(rgba_path)

    # CMYK 画像
    cmyk_image = Image.new('CMYK', (800, 600), color='blue')
    cmyk_path = tmp_path / "cmyk_image.tiff"
    cmyk_image.save(cmyk_path)

    # パレットモード画像
    p_image = Image.new('P', (800, 600))
    p_image.putpalette([
        0, 0, 0,   # 黒
        255, 0, 0, # 赤
        0, 255, 0, # 緑
        0, 0, 255  # 青
    ] * 64)  # パレットを256色分埋める
    p_image.paste(1, (0, 0, p_image.width, p_image.height))  # 画像全体を赤で塗りつぶす
    p_path = tmp_path / "p_image.png"
    p_image.save(p_path)

    return {
        "rgb": rgb_path,
        "rgb512": rgb512_path,
        "rgba": rgba_path,
        "cmyk": cmyk_path,
        "p": p_path
    }

import shutil
import uuid

@pytest.fixture(scope="session")
def test_image_path(tmp_path):
    source_image = Path("testimg/1_img/file01.webp")  # プロジェクトルートからの相対パス
    temp_dir = tmp_path / "images"
    temp_dir.mkdir(exist_ok=True)
    dest_image = temp_dir / "test_image.webp"
    shutil.copy(source_image, dest_image)
    return dest_image

@pytest.fixture
def test_image_info(test_image_path):
    return {
        'uuid': str(uuid.uuid4()),
        'stored_image_path': str(test_image_path),
        'width': 512,
        'height': 512,
        'format': 'WEBP',
        'mode': 'RGB',
        'has_alpha': False,
        'filename': test_image_path.name,
        'extension': 'webp',
        'color_space': 'sRGB',
        'icc_profile': None
    }

@pytest.fixture
def sample_image_info():
    return {
        'uuid': str(uuid.uuid4()),
        'stored_image_path': 'testimg/1_img/file01.webp',
        'width': 512,
        'height': 512,
        'format': 'WEBP',
        'mode': 'RGB',
        'has_alpha': False,
        'filename': 'file01.webp',
        'extension': 'webp',
        'color_space': 'sRGB',
        'icc_profile': None
    }
