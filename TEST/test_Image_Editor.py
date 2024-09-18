# TEST/test_Image_Editor.py

import pytest
from pathlib import Path
from PIL import Image, ImageDraw
from ImageEditor import ImageProcessingManager, ImageProcessor, AutoCrop, Upscaler
from unittest.mock import MagicMock

@pytest.mark.parametrize("image_type, has_alpha, mode", [
    ("rgb", False, 'RGB'),
    ("rgba", True, 'RGBA'),
    ("cmyk", False, 'CMYK'),
    ("p", False, 'P')
])
def test_normalize_color_profile(mock_file_system_manager, sample_images, preferred_resolutions, image_type, has_alpha, mode):
    processor = ImageProcessor(mock_file_system_manager, target_resolution=1024, preferred_resolutions=preferred_resolutions)
    image = Image.open(sample_images[image_type])
    normalized = processor.normalize_color_profile(image, has_alpha=has_alpha, mode=mode)
    assert normalized.mode == 'RGB' if mode != 'RGBA' else 'RGBA'

def test_resize_image_with_matching_resolution(mock_file_system_manager, sample_images, preferred_resolutions):
    processor = ImageProcessor(mock_file_system_manager, target_resolution=512, preferred_resolutions=preferred_resolutions)
    img = Image.open(sample_images["rgb512"])
    resized = processor.resize_image(img)
    assert resized.size == (512, 512)

def test_resize_image_without_matching_resolution(mock_file_system_manager, sample_images, preferred_resolutions):
    processor = ImageProcessor(mock_file_system_manager, target_resolution=512, preferred_resolutions=preferred_resolutions)
    img = Image.open(sample_images["rgb"])
    resized = processor.resize_image(img)
    # 目標解像度に基づきアスペクト比を維持してリサイズ
    expected_size = (512, 384)  # 800x600 のアスペクト比を維持しつつ、500に近いサイズに調整（32の倍数）
    assert resized.size == expected_size

def test_auto_crop_image_with_letterbox(sample_images, preferred_resolutions):
    # レターボックスがある画像を作成
    img = Image.new('RGB', (800, 600), color='black')
    draw = ImageDraw.Draw(img)  # ImageDraw を使用
    draw.rectangle([100, 100, 700, 500], fill='white')
    cropped = AutoCrop.auto_crop_image(img)
    assert cropped.size == (600, 400)

def test_auto_crop_image_without_letterbox(sample_images, preferred_resolutions):
    # レターボックスがない画像
    img = Image.new('RGB', (800, 600), color='white')
    cropped = AutoCrop.auto_crop_image(img)
    assert cropped.size == (800, 600)

def test_process_image_rgb_no_alpha(mock_file_system_manager, sample_images, preferred_resolutions):
    manager = ImageProcessingManager(
        file_system_manager=mock_file_system_manager,
        target_resolution=512,
        preferred_resolutions=preferred_resolutions
    )
    # モックファイルシステムに画像を配置
    original_path = sample_images["rgb"]
    resized_path = mock_file_system_manager.resized_images_dir / "rgb_resized.jpg"

    # モックの挙動を定義
    mock_file_system_manager.original_images_dir = Path(original_path).parent
    mock_file_system_manager.resized_images_dir = Path(resized_path).parent

    resized_image = manager.process_image(
        db_stored_original_path=original_path,
        original_has_alpha=False,
        original_mode='RGB',
        upscaler=None
    )

    assert resized_image is not None
    assert resized_image.size == (512, 384)

def test_process_image_rgba_with_alpha(mock_file_system_manager, sample_images, preferred_resolutions):
    manager = ImageProcessingManager(
        file_system_manager=mock_file_system_manager,
        target_resolution=512,
        preferred_resolutions=preferred_resolutions
    )
    original_path = sample_images["rgba"]

    resized_image = manager.process_image(
        db_stored_original_path=original_path,
        original_has_alpha=True,
        original_mode='RGBA',
        upscaler=None
    )

    assert resized_image is not None
    assert resized_image.mode == 'RGBA'
    # サイズはレターボックスの有無により異なる場合があります

def test_upscale_image_with_model(sample_images):
    #TODO: RealESRGAN_x4plus のみ対応から対応モデルを増やす
    img = Image.open(sample_images["rgb512"])
    upscaled = Upscaler.upscale_image(img, "RealESRGAN_x4plus")
    assert upscaled.size == (2048, 2048)
