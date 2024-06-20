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

#import torch
#venv\Lib\site-packages\basicsr\data\degradations.py
#https://github.com/xinntao/Real-ESRGAN/issues/768
# line 8:
#from torchvision.transforms.functional_tensor import rgb_to_grayscale
#to:
#from torchvision.transforms._functional_tensor import rgb_to_grayscale
#from realesrgan import RealESRGANer


# TODO: 作りかけ
REALESRGANER_UPSCALE = False # TARGET_RESOLUTION以下の画像をRealESRGANerでアップスケールするかどうか
REALESRGAN_MODEL = "RealESRGAN_x4plus_anime_6B.pth" # RealESRGANのモデルパス

img_dir = Path(r'testimg\1') # 変換リサイズ対象のフォルダ
TARGET_RESOLUTION = 512 #512  # 長辺のピクセル数

class ImageProcessor:
    """画像の編集機能を提供するクラス"""

    def __init__(self, img_dir: Path, target_resolution: int,
                 realesrganer_upscale: bool = False, realesrgan_model: str = "RealESRGAN_x4plus_anime_6B.pth",
                 image_extensions: list[str] = ['.jpg', '.png', '.bmp', '.gif', '.tif', '.tiff', '.jpeg', '.webp'],
                 text_extensions: list[str] = ['.txt', '.caption']):
        self.img_dir = img_dir
        self.target_resolution = target_resolution
        self.realesrganer_upscale = realesrganer_upscale
        self.realesrgan_model = realesrgan_model
        self.image_extensions = image_extensions
        self.text_extensions = text_extensions
        self.preferred_resolutions = [
            (512, 512),
            (768, 512),
            (512, 768),
            (1024, 1024),
            (1216, 832),
            (832, 1216)
        ]

    def convert_to_srgb(self, img: Image.Image) -> Image.Image:
        """画像の色域を外部sRGBプロファイルを使用してsRGBに変換"""
        # 画像が透過情報を持っているか確認する
        has_alpha = img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info)

        # ICCプロファイルがある場合は色域変換を行う
        if 'icc_profile' in img.info:
            icc = img.info['icc_profile']
            input_profile = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            img_converted = ImageCms.profileToProfile(
                img, input_profile, ImageCms.createProfile('sRGB'), renderingIntent=0, outputMode='RGB'
                )
            # 透過情報を持っている場合、RGBAに再変換
            if has_alpha:
                img_converted = img_converted.convert('RGBA')
            return img_converted
        else:
            # ICCプロファイルがない場合、透過情報を考慮して変換
            if has_alpha:
                return img.convert('RGBA')
            else:
                return img.convert('RGB')


    def move_low_resolution_images(self, file_path):
        """max_dimensionがTARGET_RESOLUTION未満の画像を移動"""
        # 指定解像度以下移動先 スクリプトと同じ階層にunder_res_folderを作って
        # 画像が入っているフォルダと同じ名前のフォルダを作成
        under_res_folder = Path(f'.\\under-{TARGET_RESOLUTION}') / file_path.parent.name
        # under_res_folderがない場合は作成しないとエラーになる
        if not under_res_folder.exists():
            under_res_folder.mkdir(parents=True)

        print(f'File name: {file_path.name}')
        under_res_path = under_res_folder / file_path.name
        try:
            file_path.rename(under_res_path)
            print(f'Moved: {file_path.name}')
        except Exception as e:
            print(f'Error: {e} 移動先処理できるディレクトリは同じドライブ内にある必要がある')

        # 同じ名前のテキストファイルとキャプションファイルも移動
        for ext in self.text_extensions:
            related_file_path = file_path.with_suffix(ext)
            if related_file_path.exists():
                under_res_related_path = under_res_folder / related_file_path.name
                related_file_path.rename(under_res_related_path)
                print(f'Moved {ext}: {related_file_path.name}')


    def upscale_images_to_webp(self, file_path: Path, scale: int = 4) -> np.array:
        """画像をRealESRGANerでアップスケールして返す関数
        #TODO: 未完成 他のモデルにも対応する
        Args:
            file_path (Path): 画像ファイルのパス
            scale (int): アップスケール倍率
        """
        # モデルの設定
        # TODO: RealESRGANerの導入
        # model = RealESRGANer(scale=scale, model_path=self.realesrgan_model, half=True, device='cuda')
        #画像をアップスケール
        if file_path.stem in self.image_extensions:
            print(f'Processing {file_path.name}...')
            # 画像を読み込んで短辺のサイズをチェック
            with Image.open(file_path) as img:
                img = self.convert_to_srgb(img)
                img = np.array(img)
                # アップスケール処理
                # TODO: RealESRGANerの実装
                # output, _ = model.enhance(img, outscale=scale)
                # 結果の保存 (WebP形式)
                # print(f'Upscaled  {output}')
                return output

    def find_matching_resolution(self, original_width: int, original_height: int, max_dimension: int) -> tuple | None:
        """
        元のサイズのアスペクト比と同じ解像度を、優先解像度のリストから探す

        Args:
            original_width (int): 元の画像の幅
            original_height (int): 元の画像の高さ
            max_dimension (int): 長辺のサイズ

        Returns:
            tuple or None: 元のサイズのアスペクト比の解像度を表すタプル。
                       一致する解像度が見つからない場合は、None
        """
        # 対象としない小さな画像が指定された場合はエラー表示 None
        if original_width < max_dimension and original_height < max_dimension:
            print(f'find_matching_resolution Error: 意図しない小さな画像を受け取った: {original_width}x{original_height}')
            return None
        aspect_ratio = original_width / original_height

        # アスペクト比が一致する解像度を探す
        matching_resolutions = []
        for resolution in self.preferred_resolutions:
            res_width, res_height = resolution
            res_aspect_ratio = res_width / res_height
            if res_aspect_ratio == aspect_ratio:
                matching_resolutions.append(resolution)
        # 一致したアスペクト比の解像度がある場合、max_dimension**2に最も近い解像度を返す
        if matching_resolutions:
            target_area = max_dimension ** 2
            best_resolution = matching_resolutions[0]
            closest_diff = abs((best_resolution[0] * best_resolution[1]) - target_area)
            for resolution in matching_resolutions:
                res_area = resolution[0] * resolution[1]
                diff = abs(res_area - target_area)
                if diff < closest_diff:
                    best_resolution = resolution
                    closest_diff = diff
            return best_resolution

        return None

    def resize_image(self, img: Image.Image, max_dimension: int) -> Image.Image:
        """アスペクト比をできるだけ維持しつつ、両辺をできるだけ32の倍数に近づける

        Args:
            img (Image.Image): PILのイメージオブジェクト
            max_dimension (int): 最大の辺の長さ

        Returns:
            Image.Image: リサイズされたイメージオブジェクト
        """
        original_width, original_height = img.size
        matching_resolution = self.find_matching_resolution(original_width, original_height, max_dimension)
        if matching_resolution:
            new_width, new_height = matching_resolution
        else:
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

    def get_next_sequence_number(self, output_folder: Path, parent_folder: str) -> str:
        """次の連番を取得"""
        existing_files = list(output_folder.glob(f'{parent_folder}_*.webp'))
        next_number = len(existing_files)
        return f'{next_number:05d}'

    def process_image(self, output_folder: Path, file_path: Path, parent_folder: str, img: Image.Image = None):
        """画像を変換して保存
        """
        resized_folder = output_folder / parent_folder
        sequence = self.get_next_sequence_number(resized_folder, parent_folder)

        img = self.convert_to_srgb(img) # 画像の色域変換
        img = self.resize_image(img, self.target_resolution) # 画像をリサイズ
        output_path = resized_folder / f"{parent_folder}_{sequence}.webp"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path, 'WEBP')
        print(f'Saved webp File: {output_path}')

        for suffix in self.text_extensions:
            text_file_path = file_path.with_suffix(suffix)
            if text_file_path.exists():
                output_text_path = resized_folder / f"{parent_folder}_{sequence}{suffix}"
                shutil.copy(text_file_path, output_text_path)
                print(f'Saved {suffix}: {output_text_path}')

    def has_letterbox(self, image: np.ndarray, threshold: int = 10, border_percent: float = 0.03) -> bool:
        """画像にレターボックスがあるか判定
        Args:
            image (np.ndarray): OpenCVの画像オブジェクト
            threshold (int): レターボックスの色の変化を許容するしきい値
            border_percent (float): チェックする端の幅の% (0.0 ~ 1.0)
        Returns:
            bool: レターボックスがあるかどうか
        """
        height, width = image.shape[:2]
        border_size = int(min(height, width) * border_percent)

        # 画像の端の色を取得
        top_border = image[:border_size, :]
        bottom_border = image[-border_size:, :]
        left_border = image[:, :border_size]
        right_border = image[:, -border_size:]

        # 端の色の平均値を計算
        top_color = np.mean(top_border, axis=(0, 1))
        bottom_color = np.mean(bottom_border, axis=(0, 1))
        left_color = np.mean(left_border, axis=(0, 1))
        right_color = np.mean(right_border, axis=(0, 1))

        # 端の色が同じかどうかをチェック
        if (np.all(np.abs(top_color - bottom_color) < threshold) or
            np.all(np.abs(left_color - right_color) < threshold) ):
            return True

        return False

    def auto_crop_area(self, image_path: Path) -> tuple[int, int, int, int] | None:
            """画像の枠を自動検出
            バイナリで読み込んだ画像をグレースケールに変換し、適応的しきい値処理を行って輪郭を検出
            矩形だけを取得して返すのはバイナリで読み込んだ画像を返すと画像のデータが欠落する場合があるため
            Args:
                image_path (Path): 画像ファイルのパス
            Returns:
                tuple[int, int, int, int]: クロッピングする矩形の座標とサイズ (x, y, w, h)
                        クロップできない場合は None
            """
            try:
                # 画像を読み込む日本語パスだとおかしくなるので一度バイナリ形式に変換
                with open(image_path, "rb") as file:
                    file_data = file.read()
                    image = cv2.imdecode(np.frombuffer(file_data, np.uint8), cv2.IMREAD_COLOR)
                if image is None:
                    return None  # 画像が正しく読み込めなかった場合はスキップ

                # レターボックスの有無を判定
                if not self.has_letterbox(image):
                    return None  # レターボックスがない場合はクロップしない

                # 画像をグレースケールに変換
                gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                # シャープニングフィルタ
                kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
                sharpened_image = cv2.filter2D(gray_image, -1, kernel)

                thresholded_image = cv2.adaptiveThreshold(
                    sharpened_image, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 5, 1
                    )# 輪郭を検出
                contours, _ = cv2.findContours(thresholded_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                # 最大の輪郭を見つける
                if contours:
                    # 最大の輪郭を見つける
                    largest_contour = max(contours, key=cv2.contourArea)
                    # 最小外接矩形を取得
                    x, y, w, h = cv2.boundingRect(largest_contour)
                    return (x, y, w, h)  # クロッピングする矩形の座標とサイズを返す
                else:
                    return None
            except Exception as e:
                print(f"Error processing {image_path}: {e}")
                return None

    def auto_crop_image(self, img: Image.Image) -> Image.Image:
        """画像の枠を自動検出してクロップ
        Args:
            img (Image.Image): PILのイメージオブジェクト
        Returns:
            Image.Image: クロップされたイメージオブジェクト
        """
        # imageオブジェクトからパスを取得
        image_path = Path(img.filename)

        # 画像の枠を自動検出
        crop_area = self.auto_crop_area(image_path)
        if crop_area:
            x, y, w, h = crop_area
            img = img.crop((x, y, x + w, y + h))
            return img
        else:
            return img

    def process_images(self):
        """画像をリサイズして保存
        """
        output_processed = self.img_dir.parent / f"{self.img_dir.name}_Processed"  # 出力フォルダ
        for file_path in self.img_dir.rglob('*'):
            if file_path.is_file():
                parent_path = file_path.parent  # 変換前の画像が入っているフォルダのpath
                parent_folder = parent_path.name  # 変換前の画像が入っているフォルダの名前
                ext = file_path.suffix.lower()  # 拡張子
                if ext in self.image_extensions:
                    with Image.open(file_path) as image:
                        croped_image = self.auto_crop_image(image)
                        max_dimension = max(croped_image.width, croped_image.height)

                        if max_dimension < self.target_resolution:
                            if self.realesrganer_upscale: # TODO: 未完成
                                exit()
                                # RealESRGANerでアップスケール
                                # upscale_image = self.upscale_images_to_webp(croped_image)
                                # self.process_image(output_processed, file_path, parent_folder, upscale_image)
                            else:
                                # ちっちゃい画像とそれに付随するテキストファイルを移動
                                print(f'最大解像度: {max_dimension}')
                                self.move_low_resolution_images(file_path)
                        else:
                            self.process_image(output_processed, file_path, parent_folder, croped_image)
                else:
                    continue


if __name__ == "__main__":
    # 設定をインスタンス化
    processor = ImageProcessor(
        img_dir=img_dir,
        target_resolution=TARGET_RESOLUTION,
        realesrganer_upscale=REALESRGANER_UPSCALE,
        realesrgan_model=REALESRGAN_MODEL,
    )

    processor.process_images()