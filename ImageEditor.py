"""
画像の編集を行う機能を提供するモジュール
リサイズ
- 長編を基準にアスペクト比を維持したまま指定サイズに近似した値になる32の倍数にリサイズする
プロファイル変換
- 画像の色域をsRGBに変換する､プロファイルがない場合はRGBに変換する
クロップ
- 黒枠､白枠を検出して除去する
"""
import cv2
from pathlib import Path
import numpy as np
import subprocess
# 設定
image_dir = Path(r"H:\lora\素材リスト\スクリプト\testimg\bordercrop")

# クロップされた画像を保存するディレクトリ
output_dir =  image_dir.parent / (image_dir.name + "_Cropped")


def auto_crop_image(image):
    """画像の枠を自動検出して削除
    日本語を含むパスはcv2が扱えないのでバイナリ形式に変換してimageとして渡す必要がある
    Args:
        image (np.array): 入力画像
    Returns:
        np.array: 枠が削除された画像
    """
    # 画像をグレースケールに変換
    gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # 画像を2値化
    #_, thresholded_image = cv2.threshold(gray_image, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, thresholded_image = cv2.threshold(gray_image, 5, 255, cv2.THRESH_BINARY)
    # 輪郭を検出
    contours, _ = cv2.findContours(thresholded_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # 最大の輪郭を見つける
    if contours:
        # 最大の輪郭を見つける
        largest_contour = max(contours, key=cv2.contourArea)
        # 最小外接矩形を取得
        x, y, w, h = cv2.boundingRect(largest_contour)
        # 最小外接矩形で画像をクロップ
        cropped_image = image[y:y+h, x:x+w]
        return cropped_image
    else:
        return None

EXTENSIONS = ["*.jpg", "*.png", "*.jpeg", "*.webp", "*.bmp"]
for ext in EXTENSIONS:
    for image_path in image_dir.glob(ext):
        try:
            # 画像を読み込む日本語パスだとおかしくなるので一度バイナリ形式に変換
            with open(image_path, "rb") as file:
                file_data = file.read()
                image = cv2.imdecode(np.frombuffer(file_data, np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                continue  # 画像が正しく読み込めなかった場合はスキップ

            # 画像をクロップする
            cropped_image = auto_crop_image(image)  # クロップ関数を呼び出し
            if cropped_image is None:
                    print(f"Error reading image: {image_path}")
                    continue

            # cv2.imwriteは日本語パスに対応していないので使わない
            # 日本語パス対応のため画像データを一時的にメモリ上に保存
            is_success, buffer = cv2.imencode(".png", cropped_image)
            if not is_success:
                raise Exception("Could not encode image")

            # クロップされた画像を保存する
            if not output_dir.exists():
                output_dir.mkdir(parents=True)
            output_path = output_dir / image_path.name
            with open(output_path, 'wb') as f:
                f.write(buffer)
                print(f"Saved cropped image to {output_path}")
        except Exception as e:
            print(f"Error processing {image_path}: {e}")
