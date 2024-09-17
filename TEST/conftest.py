# TEST/conftest.py

import pytest
from unittest.mock import MagicMock
from pathlib import Path
import sys
# プロジェクトルートの src ディレクトリを追加
sys.path.append(str(Path(__file__).resolve().parent.parent / 'src'))

from module.file_sys import FileSystemManager
from src.module.config import get_config

# 一時ディレクトリのパスをここで指定しないと、パーミッションエラーが出る
@pytest.fixture(scope="session")
def tmp_path_factory(request):
    return request.config.rootpath / "TEST" / "pytest_temp"

@pytest.fixture
def tmp_path(tmp_path_factory):
    return tmp_path_factory

@pytest.fixture
def mock_file_system_manager(tmp_path):
    """
    FileSystemManager のモックを提供します。
    テスト用の一時ディレクトリを使用します。
    """
    mock_fs = MagicMock(spec=FileSystemManager)
    mock_fs.original_images_dir = tmp_path / "original_images"
    mock_fs.resized_images_dir = tmp_path / "resized_images"
    mock_fs.original_images_dir.mkdir(parents=True, exist_ok=True)
    mock_fs.resized_images_dir.mkdir(parents=True, exist_ok=True)
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
    ])
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
