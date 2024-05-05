#長辺が指定解像度未満の画像をカレントディレクトリ｢under-指定解像度｣移動
#それ以外の画像を色空間をsRGBに変換
#長辺を指定解像度にリサイズ
#アスペクト比を維持したまま短辺を32の倍数に調整
#入力ディレクトリと同じ場所に｢入力ディレクトリ名_Webp｣にWebP形式で｢入力ディレクトリ名+連番｣の名前で保存
import os
import io
import shutil
from pathlib import Path
from PIL import Image, ImageCms

# 設定
TARGET_FOLDER = Path(r'H:\lora\samulora-xl_v001\10_samurahiroaki_v002_')
TARGET_RESOLUTION = 1024  # 長辺のピクセル数


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


def resize_image(img, max_dimension):
    """
    長辺をmax_dimension以下の32の倍数に、短辺を32の倍数にリサイズ
    アスペクト比を維持したままリサイズ
    """
    width, height = img.size
    aspect_ratio = width / height

    # 長辺をmax_dimensionに合わせてリサイズ
    if width > height:
        new_width = max_dimension
        new_height = int(new_width / aspect_ratio)
    else:
        new_height = max_dimension
        new_width = int(new_height * aspect_ratio)

    # 短辺を32の倍数に調整
    if width > height:
        new_height = round(new_height / 32) * 32
        new_width = round(new_height * aspect_ratio / 32) * 32
    else:
        new_width = round(new_width / 32) * 32
        new_height = round(new_width / aspect_ratio / 32) * 32

    # 長辺がmax_dimensionを超えないように確認
    new_width = min(new_width, max_dimension)
    new_height = min(new_height, max_dimension)

    return img.resize((new_width, new_height), Image.Resampling.LANCZOS)


def main():
    """メインの処理を行う"""
    under_res = Path(f'.\\under-{TARGET_RESOLUTION}') / TARGET_FOLDER.name # 指定解像度以下移動先フォルダ
    output_folder = TARGET_FOLDER.parent / f"{TARGET_FOLDER.name}_Processed"  # 出力ディレクトリ
    sequence = 1
    if not output_folder.exists():
        output_folder.mkdir(parents=True)

    for root, dirs, files in os.walk(TARGET_FOLDER):
        root_path = Path(root)
        relative_path = root_path.relative_to(TARGET_FOLDER)
        for file_name in files:
            file_path = root_path / file_name
            base_name, ext = os.path.splitext(file_name)
            if file_path.suffix.lower() in ['.jpg', '.png', '.bmp', '.gif', '.tif', '.tiff', '.jpeg', '.webp']:
                with Image.open(file_path) as img:
                    max_dimension = max(img.width, img.height)

                # 解像度が未満の画像を移動
                if max_dimension < TARGET_RESOLUTION:
                    under_res_path = under_res / root_path.relative_to(TARGET_FOLDER) / file_name
                    under_res_path.parent.mkdir(parents=True, exist_ok=True)  # 必要なサブディレクトリを確実に作成
                    file_path.rename(under_res_path)
                    # 関連するテキストファイルも移動
                    for suffix in ['.txt', '.caption']:
                        text_file_path = root_path / (base_name + suffix)
                        if text_file_path.exists():
                            text_dest_path = under_res / root_path.relative_to(TARGET_FOLDER) / (base_name + suffix)
                            text_file_path.rename(text_dest_path)
                else:
                    # 画像を変換して保存
                    with Image.open(file_path) as img:
                        img = convert_to_srgb(img)
                        img = resize_image(img, TARGET_RESOLUTION)
                        output_path = output_folder / relative_path / f"{base_name}_{sequence}.webp"
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        img.save(output_path, 'WEBP')
                        print(f'Saved:{output_path}')

                        for suffix in ['.txt', '.caption']:
                            text_file_path = root_path / (base_name + suffix)
                            if text_file_path.exists():
                                output_text_path = output_folder / relative_path / f"{base_name}_{sequence}{suffix}"
                                shutil.copy(text_file_path, output_text_path)
                                print(f'Saved:{output_text_path}')
                        sequence += 1


if __name__ == "__main__":
    main()