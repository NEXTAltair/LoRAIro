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
import io
import toml
from pathlib import Path
import numpy as np
from PIL import Image, ImageCms
import shutil
from typing import Tuple, List, Optional
from dataclasses import dataclass

@dataclass
class ProcessingConfig:
    dataset_dir: Path
    target_resolution: int
    realesrganer_upscale: bool
    realesrgan_model: str
    image_extensions: List[str]
    text_extensions: List[str]
    preferred_resolutions: List[Tuple[int, int]]

    @classmethod
    def from_toml(cls, file_path: str, image_extensions: List[str], text_extensions: List[str], preferred_resolutions: List[Tuple[int, int]]):
        with open(file_path, 'r', encoding='utf-8') as f:
            config_dict = toml.load(f)
        return cls(
            dataset_dir=Path(config_dict['directories']['dataset_dir']),
            target_resolution=config_dict['resized']['target_resolution'],
            realesrganer_upscale=config_dict['resized']['realesrganer_upscale'],
            realesrgan_model=config_dict['resized']['realesrgan_model'],
            image_extensions=image_extensions,
            text_extensions=text_extensions,
            preferred_resolutions=preferred_resolutions
        )

class ImageProcessor:
    def __init__(self, config: ProcessingConfig):
        self.config = config

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
            return img_converted.convert('RGBA') if has_alpha else img_converted
        else:
            return img.convert('RGBA') if has_alpha else img.convert('RGB')

    def move_low_resolution_images(self, file_path: Path) -> None:
        under_res_folder = Path(f'.\\under-{self.config.target_resolution}') / file_path.parent.name
        under_res_folder.mkdir(parents=True, exist_ok=True)

        under_res_path = under_res_folder / file_path.name
        try:
            file_path.rename(under_res_path)
            print(f'Moved: {file_path.name}')
        except Exception as e:
            print(f'Error: {e} 移動先処理できるディレクトリは同じドライブ内にある必要がある')

        # 同じ名前のテキストファイルとキャプションファイルも移動
        for ext in self.config.text_extensions:
            related_file_path = file_path.with_suffix(ext)
            if related_file_path.exists():
                under_res_related_path = under_res_folder / related_file_path.name
                related_file_path.rename(under_res_related_path)
                print(f'Moved {ext}: {related_file_path.name}')

    def find_matching_resolution(self, original_width: int, original_height: int) -> Optional[Tuple[int, int]]:
        """SDでよく使う解像度と同じアスペクト比の解像度を探す

        Args:
            original_width (int): もとの画像の幅
            original_height (int): もとの画像の高さ

        Returns:
            Optional[Tuple[int, int]]: 同じアスペクト比の解像度のタプル
        """
        if original_width < self.config.target_resolution and original_height < self.config.target_resolution:
            print(f'find_matching_resolution Error: 意図しない小さな画像を受け取った: {original_width}x{original_height}')
            return None

        aspect_ratio = original_width / original_height
        matching_resolutions = [res for res in self.config.preferred_resolutions if res[0] / res[1] == aspect_ratio]

        if matching_resolutions:
            target_area = self.config.target_resolution ** 2
            return min(matching_resolutions, key=lambda res: abs((res[0] * res[1]) - target_area))
        return None

    def resize_image(self, img: Image.Image) -> Image.Image:
        original_width, original_height = img.size
        matching_resolution = self.find_matching_resolution(original_width, original_height)
        
        if matching_resolution:
            new_width, new_height = matching_resolution
        else:
            aspect_ratio = original_width / original_height

            # max_dimensionに基づいて長辺を計算
            if original_width > original_height:
                new_width = self.config.target_resolution
                new_height = int(new_width / aspect_ratio)
            else:
                new_height = self.config.target_resolution
                new_width = int(new_height * aspect_ratio)

            # 両辺を32の倍数に調整
            new_width = round(new_width / 32) * 32
            new_height = round(new_height / 32) * 32

        # アスペクト比を保ちつつ、新しいサイズでリサイズ
        return img.resize((new_width, new_height), Image.Resampling.LANCZOS)

    def get_next_sequence_number(self, output_folder: Path, parent_folder: str) -> str:
        """次の連番を取得"""
        existing_files = list(output_folder.glob(f'{parent_folder}_*.webp'))
        return f'{len(existing_files):05d}'

    def process_image(self, output_folder: Path, file_path: Path, parent_folder: str, img: Image.Image) -> None:
        resized_folder = output_folder / parent_folder
        sequence = self.get_next_sequence_number(resized_folder, parent_folder)

        img = self.convert_to_srgb(img) # 画像の色域変換
        img = self.resize_image(img) # 画像をリサイズ
        output_path = resized_folder / f"{parent_folder}_{sequence}.webp"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path, 'WEBP')
        print(f'Saved webp File: {output_path}')

        for suffix in self.config.text_extensions:
            text_file_path = file_path.with_suffix(suffix)
            if text_file_path.exists():
                output_text_path = resized_folder / f"{parent_folder}_{sequence}{suffix}"
                shutil.copy(text_file_path, output_text_path)
                print(f'Saved {suffix}: {output_text_path}')

    @staticmethod
    def has_letterbox(image: np.ndarray, threshold: int = 10, border_percent: float = 0.03) -> bool:
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

        return (np.all(np.abs(top_color - bottom_color) < threshold) or
                np.all(np.abs(left_color - right_color) < threshold))

    def auto_crop_area(self, image_path: Path) -> Optional[Tuple[int, int, int, int]]:
        try:
            with open(image_path, "rb") as file:
                file_data = file.read()
                image = cv2.imdecode(np.frombuffer(file_data, np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                return None

            if not self.has_letterbox(image):
                return None

            gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
            sharpened_image = cv2.filter2D(gray_image, -1, kernel)

            thresholded_image = cv2.adaptiveThreshold(
                sharpened_image, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 5, 1
            )
            contours, _ = cv2.findContours(thresholded_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if contours:
                largest_contour = max(contours, key=cv2.contourArea)
                return cv2.boundingRect(largest_contour)
            else:
                return None
        except Exception as e:
            print(f"Error processing {image_path}: {e}")
            return None

    def auto_crop_image(self, img: Image.Image) -> Image.Image:
        image_path = Path(img.filename)
        crop_area = self.auto_crop_area(image_path)
        if crop_area:
            x, y, w, h = crop_area
            return img.crop((x, y, x + w, y + h))
        return img

    def process_images(self) -> None:
        output_processed = self.config.dataset_dir.parent / f"{self.config.dataset_dir.name}_Processed"
        for file_path in self.config.dataset_dir.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in self.config.image_extensions:
                parent_folder = file_path.parent.name
                with Image.open(file_path) as image:
                    cropped_image = self.auto_crop_image(image)
                    max_dimension = max(cropped_image.width, cropped_image.height)

                    if max_dimension < self.config.target_resolution:
                        if self.config.realesrganer_upscale:
                            # RealESRGANer implementation goes here
                            pass
                        else:
                            print(f'最大解像度: {max_dimension}')
                            self.move_low_resolution_images(file_path)
                    else:
                        self.process_image(output_processed, file_path, parent_folder, cropped_image)


def main():
    config = ProcessingConfig.from_toml(
        'processing.toml',
        image_extensions=['.jpg', '.png', '.bmp', '.gif', '.tif', '.tiff', '.jpeg', '.webp'],
        text_extensions=['.txt', '.caption'],
        preferred_resolutions=[
            (512, 512), (768, 512), (512, 768),
            (1024, 1024), (1216, 832), (832, 1216)
        ]
    )
    processor = ImageProcessor(config)
    processor.process_images()

if __name__ == "__main__":
    main()