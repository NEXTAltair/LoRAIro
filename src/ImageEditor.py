"""
画像編集スクリプト
- 画像の保存
- 画像の色域を変換
- 画像をリサイズ
"""
import cv2
import logging
from pathlib import Path
import numpy as np
from PIL import Image, ImageCms
from module.file_sys import FileSystemManager
from typing import Dict, List, Tuple, Optional, Any, Literal, Type
from scipy import ndimage

class ImageProcessingManager:
    def __init__(self, file_system_manager: FileSystemManager):
        self.file_system_manager = file_system_manager
        self.logger = logging.getLogger(__name__)
        self.config = None
        self.image_processor = None
        self.processing_date = None
        self.original_images_dir = None
        self.resized_images_dir = None

    def initialize(self, target_resolution: int, preferred_resolutions: List[Tuple[int, int]]) -> None:
        """
        提供された設定でImageProcessingManagerを初期化
        デフォルト値はmodule/config.pyに定義されている。

        Args:
            config (Dict[str, Any]): 画像処理設定を含む設定辞書。
        """
        self.target_resolution = target_resolution
        self.preferred_resolutions = preferred_resolutions


        try:
            # 画像処理の設定をセットアップ
            self.original_images_dir = self.file_system_manager.original_images_dir
            self.resized_images_dir = self.file_system_manager.resized_images_dir

            # ImageProcessorの初期化
            self.image_processor = ImageProcessor(self.file_system_manager, self.target_resolution, self.preferred_resolutions)

            self.logger.info("ImageProcessingManagerが正常に初期化。")
        except Exception as e:
            message = f"ImageProcessingManagerの初期化中エラー: {e}"
            self.logger.error(message)
            raise ValueError(message)

    def process_image(self, db_stored_original_path: Path, original_has_alpha: bool, original_mode: str) -> Optional[Image.Image]:
        """
        画像を処理し、処理後の画像オブジェクトを返す

        Args:
            db_stored_original_path (Path): 処理する画像ファイルのパス
            original_has_alpha (bool): 元画像がアルファチャンネルを持つかどうか
            original_mode (str): 元画像のモード (例: 'RGB', 'CMYK', 'P')

        Returns:
            Optional[Image.Image]: 処理済み画像オブジェクト。処理不要の場合はNone

        Ret            Optional[Image.Image]: 処理済み画像オブジェクト。処理不要の場合はNone
        """
        try:
            # . 元画像を受け取る
            with Image.open(db_stored_original_path) as img:
                # 1. 画像の枠を自動でクロップ
                cropped_img = AutoCrop.auto_crop_image(img)

                # 3. クロップ後長辺が設定値以下の場合処理をしない
                if max(cropped_img.width, cropped_img.height) < self.target_resolution:
                    self.logger.info("画像サイズが小さすぎるため処理をスキップ: %s", db_stored_original_path)
                    return None

                # 4. 画像色域を変換
                converted_img = self.image_processor.normalize_color_profile(cropped_img, original_has_alpha, original_mode)

                # 5. リサイズ
                resized_img = self.image_processor.resize_image(converted_img)

                # 6. 画像オブジェクトを返す
                return resized_img

        except Exception as e:
            self.logger.error(f"画像処理中にエラーが発生しました: {e}")

class ImageProcessor:
    def __init__(self, file_system_manager: FileSystemManager, target_resolution: int, preferred_resolutions: List[Tuple[int, int]]) -> None:
        self.logger = logging.getLogger(__name__)
        self.file_system_manager = file_system_manager
        self.target_resolution = target_resolution
        self.preferred_resolutions = preferred_resolutions

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

    def _find_matching_resolution(self, original_width: int, original_height: int) -> Optional[Tuple[int, int]]:
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

        matching_resolutions = []
        for res in self.preferred_resolutions:
            if res[0] / res[1] == aspect_ratio:
                matching_resolutions.append(res)

        if matching_resolutions:
            target_area = self.target_resolution ** 2
            return min(matching_resolutions, key=lambda res: abs((res[0] * res[1]) - target_area))
        return None

    def resize_image(self, img: Image.Image) -> Image.Image:
        original_width, original_height = img.size
        matching_resolution = self._find_matching_resolution(original_width, original_height)

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

class AutoCrop:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AutoCrop, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        self.logger = logging.getLogger(__name__)

    @classmethod
    def auto_crop_image(cls, pil_image: Image.Image) -> Image.Image:
        instance = cls()
        return instance._auto_crop_image(pil_image)

    @staticmethod #TODO: 使えるが調整不足
    def has_letterbox(image: np.ndarray, color_threshold: float = 0.15, std_threshold: float = 0.05,
                    edge_threshold: float = 0.1, gradient_threshold: float = 0.5) -> bool:
        height, width = image.shape[:2]

        # グレースケールに変換
        if image.ndim == 3:
            if image.shape[2] == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            elif image.shape[2] == 4:
                rgb = cv2.cvtColor(image, cv2.COLOR_RGBA2RGB)
                gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
            else:
                raise ValueError(f"サポートされていない画像形式です。形状: {image.shape}")
        else:
            gray = image
        # エッジ検出
        edges = ndimage.sobel(gray)

        # 領域のスライスを定義
        slices = [
            (slice(0, height//20), slice(None)),  # top
            (slice(-height//20, None), slice(None)),  # bottom
            (slice(None), slice(0, width//20)),  # left
            (slice(None), slice(-width//20, None)),  # right
            (slice(height//5, 4*height//5), slice(width//5, 4*width//5))  # center
        ]

        # 各領域の平均値と標準偏差を計算
        means = [np.mean(gray[s]) for s in slices]
        stds = [np.std(gray[s]) for s in slices]

        # エッジの強さを計算
        edge_strengths = [np.mean(edges[s]) for s in slices]

        # 各辺の評価
        def evaluate_edge(edge_index, center_index):
            color_diff = abs(means[edge_index] - means[center_index]) / 255
            is_uniform = stds[edge_index] < std_threshold * 255
            has_strong_edge = edge_strengths[edge_index] > edge_threshold * 255
            return color_diff > color_threshold and (is_uniform or has_strong_edge)

        is_letterbox_top = evaluate_edge(0, 4)
        is_letterbox_bottom = evaluate_edge(1, 4)
        is_pillarbox_left = evaluate_edge(2, 4)
        is_pillarbox_right = evaluate_edge(3, 4)

        # グラデーションの検出
        vertical_gradient = abs(means[0] - means[1]) / 255
        horizontal_gradient = abs(means[2] - means[3]) / 255
        is_gradient = vertical_gradient > gradient_threshold or horizontal_gradient > gradient_threshold

        # 最終判定（上下両方、または左右両方にレターボックス/ピラーボックスがある場合のみ真）
        has_letterbox = (is_letterbox_top and is_letterbox_bottom) or (is_pillarbox_left and is_pillarbox_right)
        return has_letterbox and not is_gradient

    def _get_crop_area(self, np_image: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        try:
            # レターボックス/ピラーボックスのチェックを維持
            if not self.has_letterbox(np_image):
                return None

            # カラースペース変換の改善
            if len(np_image.shape) == 3:
                if np_image.shape[2] == 3:
                    gray_image = cv2.cvtColor(np_image, cv2.COLOR_RGB2GRAY)
                elif np_image.shape[2] == 4:
                    # RGBA画像の場合、アルファチャンネルを無視してRGBに変換
                    rgb_image = cv2.cvtColor(np_image, cv2.COLOR_RGBA2RGB)
                    gray_image = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2GRAY)
                else:
                    self.logger.error(f"サポートされていない画像形式です。形状: {np_image.shape}")
                    return None
            elif len(np_image.shape) == 2:
                gray_image = np_image
            else:
                self.logger.error(f"サポートされていない画像形式です。形状: {np_image.shape}")
                return None

            # ノイズ除去のためのブラー処理
            blurred = cv2.GaussianBlur(gray_image, (5, 5), 0)

            # 適応的閾値処理
            thresh = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                        cv2.THRESH_BINARY, 11, 2)

            # 輪郭検出
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if contours:
                # 最大の輪郭を選択
                largest_contour = max(contours, key=cv2.contourArea)
                x, y, w, h = cv2.boundingRect(largest_contour)

                # レターボックス/ピラーボックスの特性を考慮したクロップ領域の検証
                image_height, image_width = np_image.shape[:2]
                if (w > 0.5 * image_width and h > 0.5 * image_height and
                    (w < 0.98 * image_width or h < 0.98 * image_height)):
                    return x, y, w, h

            return None
        except Exception as e:
            self.logger.error(f"クロップ領域の特定中にエラーが発生しました: {e}")
            return None

    def _auto_crop_image(self, pil_image: Image.Image) -> Image.Image:
        """
        PIL.Image オブジェクトを受け取り、必要に応じて自動クロップを行います。

        PILでのクロップのほうが画質絵の影響が少ないらしい

        Args:
            pil_image (Image.Image): 処理する PIL.Image オブジェクト

        Returns:
            Image.Image: クロップされた（または元の）PIL.Image オブジェクト
        """
        try:
            # PIL.Image を NumPy 配列に変換
            np_image = np.array(pil_image)

            # RGB to BGR (OpenCV uses BGR)
            if len(np_image.shape) == 3 and np_image.shape[2] == 3:
                np_image = cv2.cvtColor(np_image, cv2.COLOR_RGB2BGR)
            crop_area = self._get_crop_area(np_image)

            if crop_area:
                x, y, w, h = crop_area
                return pil_image.crop((x, y, w, h))
            else:
                return pil_image
        except Exception as e:
            self.logger.error(f"自動クロップ処理中にエラーが発生しました: {e}")
            return pil_image  # エラーが発生した場合は元の画像を返す