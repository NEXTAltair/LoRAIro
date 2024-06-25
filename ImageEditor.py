"""
画像編集スクリプト
- 画像の保存
- 画像の色域を変換
- 画像をリサイズ
"""
import cv2
import io
import json
from pathlib import Path
import logging
import numpy as np
from PIL import Image, ImageCms
import shutil
from typing import Dict, Tuple, Optional, Any, Literal, Type, Union
from datetime import datetime


def get_image_info(image_path: Path) -> Dict[str, Any]:
    """
    画像ファイルから基本的な情報を取得する

    Args:
        image_path (Path): 画像ファイルのパス

    Returns:
        Dict[str, Any]: 画像の基本情報（UUID､幅、高さ、フォーマット､ モード､ アルファチャンネル情報､元ファイル名､元ファイルの拡張子､元ファイルのパス）
    """
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            format = img.format.lower() if img.format else 'unknown'
            mode = img.mode

            # ファイル名と拡張子の取得
            original_filename = Path(image_path).name
            original_extension = Path(image_path).suffix

            # アルファチャンネル画像情報 BOOL
            has_alpha = img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info)

            return {
                'width': width,
                'height': height,
                'format': format,
                'mode': mode,
                'has_alpha': has_alpha,
                'filename': original_filename,
                'extension': original_extension,
            }
    except Exception as e:
        raise ValueError(f"画像情報の取得失敗: {image_path}. エラー: {str(e)}")

class ImageProcessor:
    def __init__(self, config: Dict, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger
        self.target_resolution = self.config['image_processing']['target_resolution']
        self.output_dir = Path(config['directories']['output']) / 'image_dataset'
        self.original_dir = self.output_dir / 'original_images'
        self.resolution_dir = self.output_dir / str(self.config['image_processing']['target_resolution'])
        for dir in [self.original_dir,self.resolution_dir]:
            dir.mkdir(parents=True, exist_ok=True)
        self.date_str = datetime.now().strftime("%Y/%m/%d")

    def save_image(self, image_path: Path, image_type: Literal['original', 'processed']) -> str:
        """
        画像を保存する。元画像と処理済み画像の両方に対応。

        Args:
            image_path (Path): 保存する画像のパスまたは画像オブジェクト
            image_type (Literal['original', 'processed']): 画像のタイプ（'original' または 'processed'）

        Returns:
            str: 保存された画像のパス
        """
        try:
            file_name = image_path.name
            parent_name = image_path.parent.name

            if image_type == 'original':
                base_dir = self.original_dir
                new_path = base_dir / self.date_str / parent_name / file_name
            elif image_type == 'processed':
                base_dir = self.resolution_dir
                new_parent = self.date_str / parent_name
                sequence = self.get_next_sequence_number(new_parent)
                new_filename = f"{parent_name}_{sequence}.webp"
                new_path = base_dir / self.date_str / parent_name / new_filename
            else:
                raise ValueError(f"画像のタイプが不正: {image_type}. 'original' か 'processed' しか受け付けない。")

            new_path.parent.mkdir(parents=True, exist_ok=True)

            if image_type == 'original':
                existing_files = [f.name for f in new_path.parent.iterdir()]
                counter = 1
                while new_path.name in existing_files:
                    new_path = new_path.with_name(f"{new_path.stem}_{counter}{new_path.suffix}")
                    counter += 1

                with Image.open(image_path) as img:
                    img.save(new_path, format=new_path.suffix[1:].lower())
            else:
                with Image.open(image_path) as img:
                    img.save(new_path, format='webp')

            self.logger.info(f"{image_type.capitalize()} 画像が保存完了: {new_path}")
            return str(new_path)

        except Exception as e:
            self.logger.error(f"{image_type.capitalize()} 画像の保存中にエラー: {str(e)}")
            raise

    def save_image_object(self, img: Image.Image, image_type: Literal['original', 'processed'], db_path: str) -> str:
        """
        画像オブジェクトを保存する。

        Args:
            img (Image.Image): 保存する画像オブジェクト
            image_type (Literal['original', 'processed']): 画像のタイプ（'original' または 'processed'）
            db_path (str): DB用のファイルパス

        Returns:
            str: 保存された画像のパス
        """
        try:
            file_name = Path(db_path).name
            parent_name = Path(db_path).parent.name

            if image_type == 'original':
                base_dir = self.original_dir
                new_path = base_dir / self.date_str / parent_name / file_name
            elif image_type == 'processed':
                base_dir = self.resolution_dir
                new_parent = base_dir / self.date_str / parent_name
                sequence = self.get_next_sequence_number(new_parent)
                new_filename = f"{parent_name}_{sequence}.webp"
                new_path = base_dir / self.date_str / parent_name / new_filename
            else:
                raise ValueError(f"画像のタイプが不正: {image_type}. 'original' か 'processed' しか受け付けない。")

            new_path.parent.mkdir(parents=True, exist_ok=True)

            if image_type == 'original':
                existing_files = [f.name for f in new_path.parent.iterdir()]
                counter = 1
                while new_path.name in existing_files:
                    new_path = new_path.with_name(f"{new_path.stem}_{counter}{new_path.suffix}")
                    counter += 1

                img.save(new_path, format=new_path.suffix[1:].lower())
            else:
                img.save(new_path, format='webp')

            self.logger.info(f"{image_type.capitalize()} 画像が保存完了: {new_path}")
            return str(new_path)

        except Exception as e:
            self.logger.error(f"{image_type.capitalize()} 画像の保存中にエラー: {str(e)}")
            raise

    def get_next_sequence_number(self, parent_dir: Path) -> str:
        """次の連番を取得"""
        existing_files = list(parent_dir.glob(f'{parent_dir.name}_*.webp'))
        return f'{len(existing_files):05d}'

    def normalize_color_profile(self, img: Image.Image, has_alpha: bool, mode: str = 'RGB') -> Image.Image:
        """
        画像の色プロファイルを正規化し、必要に応じて色空間変換を行う。

        Args:
            img (Image.Image): 処理する画像
            has_alpha (bool): 透過情報（アルファチャンネル）の有無
            mode (str): 画像のモード (例: 'RGB', 'CMYK', 'P')

        Returns:
            Image.Image: 色空間が正規化された画像
        """
        try:
            if mode in ['RGB', 'RGBA']:
                return img.convert('RGBA') if has_alpha else img.convert('RGB')
            elif mode == 'CMYK':
                # CMYKからRGBに変換
                return img.convert('RGB')
            elif mode == 'P':
                # パレットモードはRGBに変換してから処理
                return self.normalize_color_profile(img.convert('RGB'), has_alpha, 'RGB')
            else:
                # サポートされていないモード
                self.logger.warning(f"サポートされていないモード: {mode}")
                return img.convert('RGBA') if has_alpha else img.convert('RGB')

        except Exception as e:
            self.logger.error(f"カラープロファイルの正規化中にエラー: {e}")
            raise

    def find_matching_resolution(self, original_width: int, original_height: int) -> Optional[Tuple[int, int]]:
        """SDでよく使う解像度と同じアスペクト比の解像度を探す

        Args:
            original_width (int): もとの画像の幅
            original_height (int): もとの画像の高さ

        Returns:
            Optional[Tuple[int, int]]: 同じアスペクト比の解像度のタプル
        """
        if original_width < self.target_resolution and original_height < self.target_resolution:
            print(f'find_matching_resolution Error: 意図しない小さな画像を受け取った: {original_width}x{original_height}')
            return None

        aspect_ratio = original_width / original_height
        preferred_resolutions = self.config['preferred_resolutions']

        matching_resolutions = []
        for res in preferred_resolutions:
            if res[0] / res[1] == aspect_ratio:
                matching_resolutions.append(res)

        if matching_resolutions:
            target_area = self.target_resolution ** 2
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
                new_width = self.target_resolution
                new_height = int(new_width / aspect_ratio)
            else:
                new_height = self.target_resolution
                new_width = int(new_height * aspect_ratio)

            # 両辺を32の倍数に調整
            new_width = round(new_width / 32) * 32
            new_height = round(new_height / 32) * 32

        # アスペクト比を保ちつつ、新しいサイズでリサイズ
        return img.resize((new_width, new_height), Image.Resampling.LANCZOS)

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

    def auto_crop_area(self, image_path: str) -> Optional[Tuple[int, int, int, int]]:
        try:
            with open(image_path, "rb") as file:
                file_data = file.read()
                image = cv2.imdecode(np.frombuffer(file_data, np.uint8), cv2.IMREAD_COLOR)

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

    def auto_crop_image(self, image_path: str) -> Image.Image:
        crop_area = self.auto_crop_area(image_path)
        with Image.open(image_path) as img:
            if crop_area:
                x, y, w, h = crop_area
                return img.crop((x, y, x + w, y + h))
            return img

    def save_original_and_return_metadata(self, file_path: Path) -> Tuple[str, Dict[str, Any]]:
        """編集前画像をDBディレクトリへ保存してmainにDB登録用Dictを返す

        Args:
            file_path (Path): 編集前画像ファイルのパス

        Returns:
            Path (str): DB用ディレクトリ移動後ファイルパス
            Dict[str, Any]: 画像の基本情報（UUID､幅、高さ、フォーマット､ モード､ カラープロファイル､ アルファチャンネル情報､元ファイル名､元ファイルの拡張子､元ファイルのパス）
        """
        try:
            # 画像の保存
            path = self.save_image(file_path, 'original')
            # 画像情報の取得
            info = get_image_info(file_path)
            return path, info
        except Exception as e:
            self.logger.error(f"編集前画像の保存とメタデータ取得中にエラー: {e}")
            raise

    def save_processed_and_return_metadata(self, processed_img: Image.Image, db_original_image_path: str) -> Dict[str, Any]:
        """処理済み画像をDBディレクトリへ保存してmainにDB登録用Dictを返す

        Args:
            processed_img (Image.Image): 処理済み画像オブジェクト
            db_original_image_path (Path): 元の画像ファイルのパス

        Returns:
            Tuple[str, Dict[str, Any]]:
                str: DB用ディレクトリ保存後のファイルパス
                Dict[str, Any]: 画像の基本情報（幅、高さ、フォーマット、モード、アルファチャンネル情報、元ファイル名、保存されたファイル名）
        """
        try:
            # 処理済み画像の保存
            processed_path = self.save_image_object(processed_img, 'processed', db_original_image_path)
            # 画像情報の取得
            processed_info = {
                'path' : processed_path,
                'width': processed_img.width,
                'height': processed_img.height,
                'format': 'WEBP',  # 処理済み画像は常にWEBP形式
                'mode': processed_img.mode,
                'has_alpha': processed_img.mode == 'RGBA',
                'saved_filename': Path(processed_path).name
            }
            self.logger.info(f"処理済み画像を保存し、メタデータを取得しました: {processed_path}")
            return processed_info
        except Exception as e:
            self.logger.error(f"処理済み画像の保存とメタデータ取得中にエラー: {e}")
            raise

    def process_image(self, img: Image.Image, has_alpha: bool, mode: str) -> Tuple[Image.Image, str]:
        """
        画像の色域を正規化してリサイズする

        Args:
            img (Image.Image): 処理する画像オブジェクト
            db_path (str): dbファイルのパス
            has_alpha (bool): アルファチャンネルの有無
            mode (str): 画像のカラーモード（例：'RGB', 'RGBA'）

        Returns:
            Image.Image: 処理済み画像オブジェクト
            mode (str): コンバート後の画像のカラーモード（例：'RGB', 'RGBA'）
        """
        try:
            normalized_img = self.normalize_color_profile(img, has_alpha, mode)
            self.resize_image(normalized_img)
            return self.resize_image(normalized_img)
        except Exception as e:
            self.logger.error(f"画像処理中にエラーが発生しました: {e}")
            raise