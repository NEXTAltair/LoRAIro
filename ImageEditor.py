"""
画像編集スクリプト
- 画像の保存
- 画像の色域を変換
- 画像をリサイズ
"""
import cv2
import io
from pathlib import Path
import logging
import numpy as np
from PIL import Image, ImageCms
import shutil
from typing import Dict, Tuple, Optional, Any, Literal, Type
from datetime import datetime


def get_image_info(image_path: Path) -> Dict[str, Any]:
    """
    画像ファイルから基本的な情報を取得する

    Args:
        image_path (Path): 画像ファイルのパス

    Returns:
        Dict[str, Any]: 画像の基本情報（UUID､幅、高さ、フォーマット､ モード､ カラープロファイル､ アルファチャンネル情報､元ファイル名､元ファイルの拡張子､元ファイルのパス）
    """
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            format = img.format.lower() if img.format else 'unknown'
            mode = img.mode

            # ファイル名と拡張子の取得
            original_filename = Path(image_path).name
            original_extension = Path(image_path).suffix

            # カラープロファイル情報の取得
            if 'icc_profile' in img.info:
                icc_profile = img.info['icc_profile']
                try:
                    profile = ImageCms.ImageCmsProfile(io.BytesIO(icc_profile))
                    color_profile = {
                        'name': profile.profile.profile_description,
                        'color_space': profile.profile.color_space,
                    }
                except:
                    color_profile = 'Invalid ICC Profile'
            else:
                color_profile = 'No ICC Profile'
            # アルファチャンネル画像情報 BOOL
            has_alpha = img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info)

            return {
                'width': width,
                'height': height,
                'format': format,
                'mode': mode,
                'color_profile': str(color_profile),
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
            image_path (Path): 保存する画像のパス
            image_type (Literal['original', 'processed']): 画像のタイプ（'original' または 'processed'）

        Returns:
            str: 保存された画像のパス
        """
        try:
            file_name = image_path.name

            if image_type == 'original':
                base_dir = self.original_dir
            elif image_type == 'processed':
                base_dir = self.resolution_dir
            else:
                raise ValueError(f"画像のタイプが不正: {image_type}. 'original' か'processed'しか受け付けない。6")

            new_path = base_dir / self.date_str / image_path.parent.name / file_name
            new_path.parent.mkdir(parents=True, exist_ok=True)

            # ファイルが既に存在する場合、ユニークな名前を生成（元画像の場合のみ）
            if image_type == 'original':
                counter = 1
                while new_path.exists():
                    new_path = new_path.with_name(f"{new_path.stem}_{counter}{new_path.suffix}")
                    counter += 1

            # ファイルをコピー
            shutil.copy2(image_path, new_path)

            self.logger.info(f"{image_type.capitalize()} 画像が保存完了: {new_path}")
            return str(new_path)

        except Exception as e:
            self.logger.error(f"{image_type.capitalize()} 画像の保存中にエラー {image_path}: {str(e)}")
            raise


    def normalize_color_profile(self, img: Image.Image) -> Image.Image:
        """
        画像の色プロファイルを正規化し、必要に応じて色域変換する

        この関数は以下の処理：
        1. 画像にICCプロファイルがある場合、そのプロファイルからsRGBに変換
        2. ICCプロファイルがない場合、画像のモードに応じてRGBまたはRGBAに変換
        3. 透過情報（アルファチャンネル）がある場合、それを保持
        Args:
            img (Image.Image): 処理する画像

        Returns:
            Image.Image: 色プロファイルが正規化された画像
        """
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
            # ICCプロファイルがない場合、単純にRGBまたはRGBAに変換
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

    def save_original_and_return_metadata(self, file_path: Path) -> Tuple[str, Dict[str, Any]]:
        """編集前画像をDBディレクトリへ保存してmainにDB登録用Dictを返す

        Args:
            file_path (Path): 編集前画像ファイルのパス

        Returns:
            Path (str): DB用ディレクトリ移動後ファイルパス
            Dict[str, Any]: 画像の基本情報（UUID､幅、高さ、フォーマット､ モード､ カラープロファイル､ アルファチャンネル情報､元ファイル名､元ファイルの拡張子､元ファイルのパス）
        """
        # 画像の保存
        path = self.save_image(file_path, 'original')
        # 画像情報の取得
        info = get_image_info(file_path)
        return path, info

    def process_and_save_image(self, file_path: Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
            # 画像処理
            processed_img = self.normalize_color_profile(img)  # 色域変換
            processed_img = self.resize_image(processed_img)  # リサイズ
            processed_img = self.resize_image(img, base_model['target_resolution'])
    #             if remove_alpha and original_info['has_alpha']:
    #                 processed_img = processed_img.convert('RGB')

    #             # 処理済み画像の保存パスを構築
    #             original_path = Path(original_path)
    #             relative_path = original_path.relative_to(self.original_dir)
    #             date_str = datetime.now().strftime("%Y/%m/%d")
    #             processed_filename = f"{original_path.stem}_processed_{base_model['name']}.webp"
    #             processed_path = self.processed_dir / date_str / relative_path.parent / processed_filename
    #             processed_path.parent.mkdir(parents=True, exist_ok=True)

    #             processed_img.save(processed_path, 'WEBP')

    #             processed_info = {
    #                 'image_id': image_id,
    #                 'base_model_id': base_model['id'],
    #                 'processed_path': str(processed_path),
    #                 'processed_width': processed_img.width,
    #                 'processed_height': processed_img.height,
    #                 'processed_format': 'WEBP',
    #                 'alpha_removed': remove_alpha and original_info['has_alpha']
    #             }
    #             return original_info, processed_info

    # def process_image(self, img: Image.Image) -> None:
    #     sequence = self.get_next_sequence_number(resized_folder, parent_folder)

    #     img = self.convert_to_srgb(img) # 画像の色域変換
    #     img = self.resize_image(img) # 画像をリサイズ
    #     output_path = resized_folder / f"{parent_folder}_{sequence}.webp"

    #     output_path.parent.mkdir(parents=True, exist_ok=True)
    #     img.save(output_path, 'WEBP')
    #     print(f'Saved webp File: {output_path}')

    #     for suffix in self.config.text_extensions:
    #         text_file_path = file_path.with_suffix(suffix)
    #         if text_file_path.exists():
    #             output_text_path = resized_folder / f"{parent_folder}_{sequence}{suffix}"
    #             shutil.copy(text_file_path, output_text_path)
    #             print(f'Saved {suffix}: {output_text_path}')



    def process_and_save_image(self, file_path: Path, remove_alpha: bool = False) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        with Image.open(file_path) as img:
            # 元画像の情報を取得
            original_info = self.get_image_info(file_path)
            
            # 元画像を保存
            original_saved_path = self.save_image(file_path, 'original')
            original_info['saved_path'] = str(original_saved_path)


            # ---------ここまでDBに依存しない処理--------->

            # 画像処理
            processed_img = self.convert_to_srgb(img)  # 色域変換 #img カラープロファイルはDB参照
            processed_img = self.resize_image(processed_img)  # img データベース参照
            
            if remove_alpha and original_info['has_alpha']: #不要
                processed_img = processed_img.convert('RGB') #不要

            # 処理済み画像の保存パスを構築 #不要 save_imageで処理
            date_str = datetime.now().strftime("%Y/%m/%d")
            parent_folder = file_path.parent.name
            sequence = self.get_next_sequence_number(self.resolution_dir / date_str / parent_folder, parent_folder)
            processed_filename = f"{parent_folder}_{sequence}.webp"
            processed_path = self.resolution_dir / date_str / parent_folder / processed_filename
            processed_path.parent.mkdir(parents=True, exist_ok=True)

            # 処理済み画像を保存
            processed_img.save(processed_path, 'WEBP')
            self.logger.info(f'Saved webp File: {processed_path}')

            # 関連するテキストファイルの処理 
            for suffix in self.config['text_extensions']:
                text_file_path = file_path.with_suffix(suffix)
                if text_file_path.exists():
                    output_text_path = processed_path.with_suffix(suffix)
                    shutil.copy(text_file_path, output_text_path)
                    self.logger.info(f'Saved {suffix}: {output_text_path}')
            # DBに登録する情報を返す
            processed_info = {
                'processed_path': str(processed_path),
                'processed_width': processed_img.width,
                'processed_height': processed_img.height,
                'processed_format': 'WEBP',
                'alpha_removed': remove_alpha and original_info['has_alpha']
            }

            return original_info, processed_info