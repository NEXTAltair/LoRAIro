#!/usr/bin/env python3
"""
シンプルな4手法AutoCrop比較テスト
"""

import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import cv2
import time

# プロジェクトルートを追加
project_root = Path(__file__).parent
sys.path.append(str(project_root / "src"))

from lorairo.editor.image_processor import AutoCrop

# rembg依存関係チェック
try:
    from rembg import remove
    REMBG_AVAILABLE = True
    print("✓ rembg available")
except ImportError:
    print("✗ rembg not found")
    REMBG_AVAILABLE = False

# scipy依存関係チェック
try:
    import scipy.ndimage
    SCIPY_AVAILABLE = True
    print("✓ scipy available")
except ImportError:
    print("✗ scipy not found")
    SCIPY_AVAILABLE = False


def apply_autocrop_with_params(img: Image.Image, params: dict) -> tuple[Image.Image, dict]:
    """現在のAutoCropアルゴリズムを適用"""
    start_time = time.time()
    
    # AutoCropインスタンス作成
    autocrop = AutoCrop()
    cropped_img = autocrop._auto_crop_image(img)
    
    # クロップ情報を計算
    crop_ratio = (cropped_img.size[0] * cropped_img.size[1]) / (img.size[0] * img.size[1])
    
    crop_info = {
        "detected": crop_ratio < 1.0,
        "method": "current_autocrop",
        "original_size": img.size,
        "cropped_size": cropped_img.size,
        "crop_ratio": crop_ratio,
        "processing_time": time.time() - start_time,
        "contours_found": 1 if crop_ratio < 1.0 else 0
    }
    
    return cropped_img, crop_info


def apply_rembg_autocrop(img: Image.Image) -> tuple[Image.Image, dict]:
    """rembgベースのAutoCrop"""
    start_time = time.time()
    
    if not REMBG_AVAILABLE:
        crop_info = {
            "detected": False,
            "method": "rembg_background_removal",
            "error": "rembg_not_available",
            "original_size": img.size,
            "cropped_size": img.size,
            "crop_ratio": 1.0,
            "processing_time": time.time() - start_time,
            "contours_found": 0
        }
        return img.copy(), crop_info
    
    try:
        # rembgで背景除去実行
        with_alpha = remove(img)
        
        if with_alpha.mode == 'RGBA':
            # アルファチャンネル取得
            alpha = with_alpha.split()[-1]
            alpha_array = np.array(alpha)
            
            # 非透明領域の境界を検出
            non_transparent = alpha_array > 0
            
            if np.any(non_transparent):
                # 非透明領域の境界ボックスを計算
                coords = np.where(non_transparent)
                y_min, y_max = coords[0].min(), coords[0].max()
                x_min, x_max = coords[1].min(), coords[1].max()
                
                # 少しマージンを追加
                margin = 5
                height, width = alpha_array.shape
                y_min = max(0, y_min - margin)
                y_max = min(height, y_max + margin)
                x_min = max(0, x_min - margin)
                x_max = min(width, x_max + margin)
                
                # 元画像をクロップ
                cropped_img = img.crop((x_min, y_min, x_max, y_max))
                
                crop_info = {
                    "detected": True,
                    "method": "rembg_background_removal",
                    "original_size": img.size,
                    "cropped_size": cropped_img.size,
                    "crop_ratio": ((x_max - x_min) * (y_max - y_min)) / (width * height),
                    "processing_time": time.time() - start_time,
                    "contours_found": 1,
                    "alpha_coverage": np.sum(non_transparent) / (width * height)
                }
                return cropped_img, crop_info
    
    except Exception as e:
        print(f"RembgAutoCrop error: {e}")
    
    # フォールバック
    crop_info = {
        "detected": False,
        "method": "rembg_background_removal",
        "original_size": img.size,
        "cropped_size": img.size,
        "crop_ratio": 1.0,
        "processing_time": time.time() - start_time,
        "contours_found": 0
    }
    return img.copy(), crop_info


def create_comparison_image(original: Image.Image, results: list, test_name: str) -> Image.Image:
    """比較画像を作成"""
    
    # 全画像リスト（オリジナル + 結果）
    all_images = [original] + [result[0] for result in results]
    all_infos = [{"method": "Original", "cropped_size": original.size, "crop_ratio": 1.0, "processing_time": 0}] + [result[1] for result in results]
    
    # 最大サイズ決定
    max_width = max(img.size[0] for img in all_images)
    max_height = max(img.size[1] for img in all_images)
    target_size = (max_width, max_height)
    
    # パディング関数
    def pad_image(img: Image.Image, target_size: tuple[int, int]) -> Image.Image:
        new_img = Image.new("RGB", target_size, (240, 240, 240))
        x_offset = (target_size[0] - img.size[0]) // 2
        y_offset = (target_size[1] - img.size[1]) // 2
        new_img.paste(img, (x_offset, y_offset))
        return new_img
    
    # 画像パディング
    padded_images = [pad_image(img, target_size) for img in all_images]
    
    # 比較画像作成
    text_height = 120
    spacing = 8
    comparison_width = max_width * len(all_images) + spacing * (len(all_images) + 1)
    comparison_height = max_height + text_height
    
    comparison = Image.new("RGB", (comparison_width, comparison_height), (255, 255, 255))
    
    # 画像配置
    for i, padded_img in enumerate(padded_images):
        x_pos = spacing + i * (max_width + spacing)
        comparison.paste(padded_img, (x_pos, text_height))
    
    # テキスト描画
    draw = ImageDraw.Draw(comparison)
    try:
        font = ImageFont.load_default()
    except:
        font = None
    
    # タイトル
    title = f"AutoCrop Methods Comparison: {test_name}"
    draw.text((10, 10), title, fill=(0, 0, 0), font=font)
    
    # 各画像のラベル
    for i, info in enumerate(all_infos):
        x_pos = spacing + i * (max_width + spacing)
        
        if i == 0:  # Original
            label = f"Original\\n{info['cropped_size'][0]}x{info['cropped_size'][1]}"
        else:
            method_name = info.get('method', 'Unknown')
            label = f"{method_name}\\n{info['cropped_size'][0]}x{info['cropped_size'][1]}\\nRatio: {info['crop_ratio']:.3f}\\nTime: {info['processing_time']:.3f}s"
            
            if 'alpha_coverage' in info:
                label += f"\\nAlpha: {info['alpha_coverage']:.3f}"
        
        draw.text((x_pos, 40), label, fill=(0, 0, 0), font=font)
    
    return comparison


def test_single_image(image_path: Path) -> None:
    """単一画像での比較テスト"""
    print(f"\\n=== Testing: {image_path.name} ===")
    
    if not image_path.exists():
        print(f"Image not found: {image_path}")
        return
    
    # 画像読み込み
    test_img = Image.open(image_path)
    print(f"Original size: {test_img.size}")
    
    # テスト実行
    results = []
    
    # 1. Current AutoCrop (Optimized)
    print("Testing Current AutoCrop...")
    opt_result, opt_info = apply_autocrop_with_params(test_img, {})
    opt_info["method"] = "Current AutoCrop"
    results.append((opt_result, opt_info))
    
    # 2. rembg AutoCrop
    print("Testing rembg AutoCrop...")
    rembg_result, rembg_info = apply_rembg_autocrop(test_img)
    results.append((rembg_result, rembg_info))
    
    # 比較画像作成
    comparison_img = create_comparison_image(test_img, results, image_path.stem)
    
    # ファイル保存
    output_dir = Path("simple_test_results")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"{image_path.stem}_comparison.png"
    comparison_img.save(output_path)
    
    # 結果出力
    print(f"\\nResults:")
    for result_img, result_info in results:
        print(f"  {result_info['method']}: ratio={result_info['crop_ratio']:.3f}, time={result_info['processing_time']:.3f}s")
        if 'alpha_coverage' in result_info:
            print(f"    Alpha coverage: {result_info['alpha_coverage']:.3f}")
    
    print(f"Comparison image saved: {output_path}")


def main():
    """メイン処理"""
    print("=== シンプル4手法AutoCrop比較テスト ===")
    
    # テスト画像
    test_images = [
        Path("tests/resources/img/bordercrop/image_0001.png"),
        Path("tests/resources/img/bordercrop/image_0006.png")
    ]
    
    for img_path in test_images:
        test_single_image(img_path)
    
    print("\\n=== テスト完了 ===")


if __name__ == "__main__":
    main()