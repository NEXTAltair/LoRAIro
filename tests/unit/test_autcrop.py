import pytest
import numpy as np
from PIL import Image, ImageDraw, ImageOps
from pathlib import Path

from editor.image_processor import AutoCrop


@pytest.fixture(scope="module")
def crop_test_images():
    """
    テスト用の画像を作成するフィクスチャ。
    各画像は仕様に基づいた枠パターンを持つ。
    """
    images = {}
    size = (256, 256)  # 基本のサイズ

    # 1. 枠のない画像
    no_borders_img = Image.new("RGB", size, (255, 0, 0))  # 赤色の単色画像
    images["no_borders"] = no_borders_img

    # 2. レターボックス画像（上下に黒い帯）
    letterbox_img = no_borders_img.copy()
    draw = ImageDraw.Draw(letterbox_img)
    border_thickness = 20
    draw.rectangle([0, 0, size[0], border_thickness], fill=(0, 0, 0))  # 上部
    draw.rectangle([0, size[1] - border_thickness, size[0], size[1]], fill=(0, 0, 0))  # 下部
    images["letterbox"] = letterbox_img

    # 3. ピラーボックス画像（左右に黒い帯）
    pillarbox_img = no_borders_img.copy()
    draw = ImageDraw.Draw(pillarbox_img)
    draw.rectangle([0, 0, border_thickness, size[1]], fill=(0, 0, 0))  # 左側
    draw.rectangle([size[0] - border_thickness, 0, size[0], size[1]], fill=(0, 0, 0))  # 右側
    images["pillarbox"] = pillarbox_img

    # 4. 両方の枠（四方に黒い帯）
    four_sides_img = no_borders_img.copy()
    draw = ImageDraw.Draw(four_sides_img)
    draw.rectangle([0, 0, size[0], border_thickness], fill=(0, 0, 0))  # 上部
    draw.rectangle([0, size[1] - border_thickness, size[0], size[1]], fill=(0, 0, 0))  # 下部
    draw.rectangle([0, 0, border_thickness, size[1]], fill=(0, 0, 0))  # 左側
    draw.rectangle([size[0] - border_thickness, 0, size[0], size[1]], fill=(0, 0, 0))  # 右側
    images["four_sides"] = four_sides_img

    # 5. グラデーションの枠付き画像
    gradient_img = Image.new("RGB", size, (255, 255, 255))
    draw = ImageDraw.Draw(gradient_img)
    for i in range(border_thickness, size[1] - border_thickness):
        gradient_color = int(255 * (i - border_thickness) / (size[1] - 2 * border_thickness))
        draw.line(
            [(border_thickness, i), (size[0] - border_thickness, i)],
            fill=(gradient_color, gradient_color, gradient_color),
        )
    draw.rectangle([0, 0, size[0], border_thickness], fill=(0, 0, 0))  # 上部
    draw.rectangle([0, size[1] - border_thickness, size[0], size[1]], fill=(0, 0, 0))  # 下部
    draw.rectangle([0, 0, border_thickness, size[1]], fill=(0, 0, 0))  # 左側
    draw.rectangle([size[0] - border_thickness, 0, size[0], size[1]], fill=(0, 0, 0))  # 右側
    images["gradient_with_borders"] = gradient_img

    # 6. グラデーションのみの画像
    pure_gradient_img = Image.new("RGB", size, (0, 0, 0))
    draw = ImageDraw.Draw(pure_gradient_img)
    for i in range(size[1]):
        gradient_color = int(255 * i / size[1])
        draw.line([(0, i), (size[0], i)], fill=(gradient_color, gradient_color, gradient_color))
    images["gradient_only"] = pure_gradient_img

    # 7. アルファチャンネル付きの画像（透明な枠付き）
    rgba_img = Image.new("RGBA", size, (255, 0, 0, 255))  # 赤色の画像
    draw = ImageDraw.Draw(rgba_img)
    draw.rectangle([0, 0, size[0], border_thickness], fill=(0, 0, 0, 0))  # 上部の透明な枠
    draw.rectangle([0, size[1] - border_thickness, size[0], size[1]], fill=(0, 0, 0, 0))  # 下部の透明な枠
    images["alpha_with_borders"] = rgba_img

    # 8. グレースケール画像
    grayscale_img = Image.new("L", size, 255)  # 白色のグレースケール画像
    draw = ImageDraw.Draw(grayscale_img)
    draw.rectangle([0, 0, size[0], border_thickness], fill=0)  # 上部の黒い枠
    draw.rectangle([0, size[1] - border_thickness, size[0], size[1]], fill=0)  # 下部の黒い枠
    images["grayscale_with_borders"] = grayscale_img

    # 9. 非標準のアスペクト比画像
    non_standard_aspect_img = Image.new("RGB", (128, 256), (255, 255, 0))  # 黄色の画像
    draw = ImageDraw.Draw(non_standard_aspect_img)
    draw.rectangle([0, 0, 128, border_thickness], fill=(0, 0, 0))  # 上部
    draw.rectangle([0, 256 - border_thickness, 128, 256], fill=(0, 0, 0))  # 下部
    images["non_standard_aspect"] = non_standard_aspect_img

    # 10. 小さい画像
    small_img = Image.new("RGB", (32, 32), (255, 0, 0))  # 小さい赤色の画像
    images["small"] = small_img

    ##11. testimg内部の画像にレターボックスを追加
    IMAGE_DIR = Path(r"testimg\1_img")
    for img_path in IMAGE_DIR.glob("*.*"):
        if img_path.suffix.lower() not in [".jpg", ".jpeg", ".png", ".webp"]:
            continue
        img = Image.open(img_path).convert("RGB")
        # 画像の高さに基づいて20%のレターボックスを計算
        width, height = img.size
        border_height = int(height * 0.2)  # 上下に20%ずつ
        # 上下に黒い帯を追加（レターボックス）
        bordered_img = ImageOps.expand(img, (0, border_height), fill=(0, 0, 0))
        # 画像のファイル名をキーとして辞書に追加
        images[img_path.stem + "_letterbox"] = bordered_img

    # 12. testimg内部の画像
    IMAGE_DIR01 = Path(r"tests\resources\img\1_img\file10.webp")
    for img_path in IMAGE_DIR01.glob("*.*"):
        if img_path.suffix.lower() not in [".jpg", ".jpeg", ".png", ".webp"]:
            continue
        img = Image.open(img_path).convert("RGB")
        images[img_path.stem] = img

    return images


@pytest.fixture(scope="module")
def autocrop_instance():
    """
    AutoCropクラスのインスタンスを返すフィクスチャ。
    """
    return AutoCrop()


def test_detect_border_shape(crop_test_images):
    """
    _detect_border_shapeメソッドのテスト。枠が検出されるか確認する。
    """
    # レターボックスのある画像
    letterbox_img = crop_test_images["letterbox"]
    letterbox_np = np.array(letterbox_img)
    # 検出結果を取得
    detected_borders = AutoCrop._detect_border_shape(letterbox_np)
    # クラスメソッドから直接呼び出し
    assert set(detected_borders) == {"TOP", "BOTTOM"}, "レターボックスが検出されませんでした。"

    # 枠のない画像
    no_borders_img = crop_test_images["no_borders"]
    no_borders_np = np.array(no_borders_img)
    detected_borders = AutoCrop._detect_border_shape(no_borders_np)
    # クラスメソッドから直接呼び出し
    assert detected_borders == [], "枠がないのに検出されました。"


def test_get_crop_area(crop_test_images):
    """
    _get_crop_areaメソッドのテスト。クロップ領域が正しく計算されるか確認する。
    """
    # インスタンスの生成
    autocrop_instance = AutoCrop()

    # レターボックスのある画像
    letterbox_img = crop_test_images["letterbox"]
    letterbox_np = np.array(letterbox_img)

    # インスタンスメソッドから呼び出し
    crop_area = autocrop_instance._get_crop_area(letterbox_np)
    assert crop_area is not None, "クロップ領域が取得できませんでした。"
    x, y, w, h = crop_area
    # 上下の枠をクロップするので、高さが変わっているはず
    assert h < letterbox_np.shape[0], "高さが変更されていません。"


def test_auto_crop_image(crop_test_images):
    """
    _auto_crop_imageメソッドのテスト。画像が正しくクロップされるか確認する。
    """
    # インスタンスメソッドなのでインスタンス生成が必要
    autocrop_instance = AutoCrop()

    # レターボックスのある画像
    letterbox_img = crop_test_images["letterbox"]

    # 自動クロップを実行
    cropped_img = autocrop_instance._auto_crop_image(letterbox_img)

    # クロップ後のサイズが変わっているか確認
    assert cropped_img.size[1] < letterbox_img.size[1], "画像の高さが変更されていません。"
