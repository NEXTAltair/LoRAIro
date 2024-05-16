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
import io
import shutil
from PIL import Image, ImageCms
import imageio
import torch

#venv\Lib\site-packages\basicsr\data\degradations.py
#https://github.com/xinntao/Real-ESRGAN/issues/768
# line 8:
#from torchvision.transforms.functional_tensor import rgb_to_grayscale
#to:
#from torchvision.transforms._functional_tensor import rgb_to_grayscale
from realesrgan import RealESRGANer


# 設定
RESIZE = True # リサイズの使用
CROP = False # クロップの使用

#TODO:作りかけ
REALESRGANER_UPSCALE = False # TARGET_RESOLUTION以下の画像をRealESRGANerでアップスケールするかどうか
REALESRGAN_MODEL = "RealESRGAN_x4plus_anime_6B.pth" # RealESRGANのモデルパス

RESIZE_FOLDER = Path(r'H:\lora\Fatima-XL\img\1Fatima_ADD') # 変換リサイズ対象のフォルダ
CROP_FOLDER = Path(r"H:\lora\素材リスト\スクリプト\testimg\bordercrop") # クロップ対象の画像フォルダ
TARGET_RESOLUTION = 1024 #512  # 長辺のピクセル数
IMAGE_EXTENSIONS = ['.jpg', '.png', '.bmp', '.gif', '.tif', '.tiff', '.jpeg', '.webp'] # 処理対象の画像ファイルの拡張子
TEXT_EXTENSIONS = ['.txt', '.caption'] # 処理対象のテキストファイルの拡張子


def convert_to_srgb(img):
    """画像の色域を外部sRGBプロファイルを使用してsRGBに変換"""
    if 'icc_profile' in img.info:
        icc = img.info['icc_profile']
        input_profile = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        img_converted = ImageCms.profileToProfile(img, input_profile, ImageCms.createProfile('sRGB'), renderingIntent=0, outputMode='RGB')
        return img_converted
    else:
        # ICCプロファイルがない場合、RGBに変換
        return img.convert('RGB')


def move_low_resolution_images(file_path):
    """max_dimensionがTARGET_RESOLUTION未満の画像を移動"""
    under_res_folder = Path(f'.\\under-{TARGET_RESOLUTION}') / file_path.parent.name
    if not under_res_folder.exists():
        under_res_folder.mkdir(parents=True)

    print(f'Low resolution: {file_path.name}')
    under_res_path = under_res_folder / file_path.name
    file_path.rename(under_res_path)

    # 同じ名前のテキストファイルとキャプションファイルも移動
    for ext in TEXT_EXTENSIONS:
        related_file_path = file_path.with_suffix(ext)
        if related_file_path.exists():
            under_res_related_path = under_res_folder / related_file_path.name
            related_file_path.rename(under_res_related_path)
            print(f'Moved {ext}: {related_file_path.name}')


def upscale_images_to_webp(file_path, scale=4):
    """画像をRealESRGANerでアップスケールして返す関数
    #TODO: 他のモデルにも対応する
    Args:
        file_path (Path): 画像ファイルのパス
        scale (int): アップスケール倍率
    """
    # モデルの設定
    model = RealESRGANer(scale=scale, model_path=REALESRGAN_MODEL, half=True, device='cuda')
    #画像をアップスケール
    if file_path.stem in IMAGE_EXTENSIONS:
        print(f'Processing {file_path.name}...')
        # 画像を読み込んで短辺のサイズをチェック
        with Image.open(file_path) as img:
                img = convert_to_srgb(img)
                img = np.array(img)
                # アップスケール処理
                output, _ = model.enhance(img, outscale=scale)
                # 結果の保存 (WebP形式)
                print(f'Upscaled  {output}')
                return output


def resize_image(img, max_dimension):
    """アスペクト比をできるだけ維持しつつ、両辺をできるだけ32の倍数に近づける

    Args:
        img (Image.Image): PILのイメージオブジェクト
        max_dimension (int): 最大の辺の長さ

    Returns:
        Image.Image: リサイズされたイメージオブジェクト
    """
    original_width, original_height = img.size
    aspect_ratio = original_width / original_height

    # max_dimensionに基づいて長辺を計算
    if original_width > original_height:
        new_width = max_dimension
        new_height = int(new_width / aspect_ratio)
    else:
        new_height = max_dimension
        new_width = int(new_height * aspect_ratio)

    # 両辺を32の倍数に調整
    new_width = round(new_width / 32) * 32
    new_height = round(new_height / 32) * 32

    # アスペクト比を保ちつつ、新しいサイズでリサイズ
    return img.resize((new_width, new_height), Image.Resampling.LANCZOS)


def get_next_sequence_number(output_folder, parent_folder):
    """次の連番を取得"""
    existing_files = list(output_folder.glob(f'{parent_folder}_*.webp'))
    return len(existing_files) + 1


def process_image(output_folder, file_path, parent_folder, up_img):
    """画像を変換して保存
    """
    resized_folder = output_folder / file_path.parent.stem
    sequence = get_next_sequence_number(resized_folder, parent_folder)

    if up_img is not None:
        img = up_img
    elif file_path.suffix in IMAGE_EXTENSIONS:
        img = Image.open(file_path)
    else:
        return  # 画像ファイルではないため処理をスキップ

    img = convert_to_srgb(img)
    img = resize_image(img, TARGET_RESOLUTION)
    output_path = resized_folder / f"{parent_folder}_{sequence}.webp"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, 'WEBP')
    print(f'Saved webp File: {output_path}')

    for suffix in TEXT_EXTENSIONS:
        text_file_path = file_path.parent / file_path.with_suffix(suffix)
        if text_file_path.exists():
            output_text_path = resized_folder / f"{parent_folder}_{sequence}{suffix}"
            shutil.copy(text_file_path, output_text_path)
            print(f'Saved {suffix}: {output_text_path}')



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


def crop_box(output_Cropped):
    """画像の枠を自動検出して削除して保存する
    Raises:
        Exception: _description_
    """
    for ext in IMAGE_EXTENSIONS:
        for image_path in CROP_FOLDER.rglob(f"*{ext}"):
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
                if not output_Cropped.exists():
                    output_Cropped.mkdir(parents=True)
                output_path = output_Cropped / image_path.name
                with open(output_path, 'wb') as f:
                    f.write(buffer)
                    print(f"Saved cropped image to {output_path}")
            except Exception as e:
                print(f"Error processing {image_path}: {e}")


def image_resize(output_folder):
    for file_path in RESIZE_FOLDER.rglob('*'):
        if file_path.is_file():
            parent_path = file_path.parent #変換前の画像が入っているフォルダのpath
            parent_folder = parent_path.name #変換前の画像が入っているフォルダの名前
            _, ext = file_path.stem, file_path.suffix.lower() #拡張子
            if ext in IMAGE_EXTENSIONS:
                with Image.open(file_path) as img:
                    max_dimension = max(img.width, img.height)
            else:
                continue

            # 解像度が未満の画像を移動
            # 指定解像度以下移動先 スクリプトと同じ階層にunder_res_folderを作って
            # 画像が入っているフォルダと同じ名前のフォルダを作成
            under_res_folder = Path(f'.\\under-{TARGET_RESOLUTION}') / parent_folder
            # under_res_folderがない場合は作成しないとエラーになる
            if not under_res_folder.exists():
                under_res_folder.mkdir(parents=True)

            if max_dimension < TARGET_RESOLUTION:
                if REALESRGANER_UPSCALE:
                    # RealESRGANerでアップスケール
                    up_img = upscale_images_to_webp(file_path)
                    process_image(output_folder, file_path, parent_folder, up_img=None)
                else:
                    #ちっちゃい画像とそれに付随するテキストファイルを移動
                    move_low_resolution_images(file_path)

            else:
                # 画像を変換して保存
                process_image(output_folder, file_path, parent_folder, up_img=None)


if __name__ == "__main__":
    output_Processed = RESIZE_FOLDER.parent / f"{RESIZE_FOLDER.name}_Processed" # 出力フォルダ
    output_Cropped =  CROP_FOLDER.parent / f"{CROP_FOLDER.name}_Cropped" # クロップされた画像を保存
    if RESIZE:
        image_resize(output_Processed)
    if CROP:
        crop_box(output_Cropped)