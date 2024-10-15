"""
画像編集スクリプト
- 画像の保存
- 画像の色域を変換
- 画像をリサイズ
"""
import cv2
from pathlib import Path
from spandrel import ModelLoader, ImageModelDescriptor
import torch
import numpy as np
from PIL import Image
from module.file_sys import FileSystemManager
from module.log import get_logger
from typing import Optional
from scipy import ndimage

class ImageProcessingManager:
    def __init__(self, file_system_manager: FileSystemManager, target_resolution: int,
                 preferred_resolutions: list[tuple[int, int]]):
        """
        ImageProcessingManagerを初期化
        デフォルト値はmodule/config.pyに定義

        Args:
            file_system_manager (FileSystemManager): ファイルシステムマネージャ
            target_resolution (int): 目標解像度
            preferred_resolutions (list[tuple[int, int]]): 優先解像度リスト #TODO: 解像度じゃなくてアスペクト比表記のほうがいいかも
        """
        self.logger = get_logger(__name__)
        self.file_system_manager = file_system_manager
        self.target_resolution = target_resolution

        try:
            # ImageProcessorの初期化
            self.image_processor = ImageProcessor(self.file_system_manager, target_resolution, preferred_resolutions)
            self.logger.info("ImageProcessingManagerが正常に初期化。")

        except Exception as e:
            message = f"ImageProcessingManagerの初期化中エラー: {e}"
            self.logger.error(message)
            raise ValueError(message) from e

    def process_image(self, db_stored_original_path: Path, original_has_alpha: bool, original_mode: str, upscaler: str = None) -> Optional[Image.Image]:
        """
        画像を処理し、処理後の画像オブジェクトを返す

        Args:
            db_stored_original_path (Path): 処理する画像ファイルのパス
            original_has_alpha (bool): 元画像がアルファチャンネルを持つかどうか
            original_mode (str): 元画像のモード (例: 'RGB', 'CMYK', 'P')
            upscaler (str): アップスケーラーの名前

        Returns:
            Optional[Image.Image]: 処理済み画像オブジェクト。処理不要の場合はNone

        """
        try:
            with Image.open(db_stored_original_path) as img:
                cropped_img = AutoCrop.auto_crop_image(img)

                converted_img = self.image_processor.normalize_color_profile(cropped_img, original_has_alpha, original_mode)

                if max(cropped_img.width, cropped_img.height) < self.target_resolution:
                    if upscaler: #TODO: アップスケールした画像はそれを示すデータも保存すべきか？
                        if converted_img.mode == 'RGBA':
                            self.logger.info(f"RGBA 画像のためアップスケールをスキップ: {db_stored_original_path}")
                        else:
                            self.logger.debug(f"長編が指定解像度未満のため{db_stored_original_path}をアップスケールします: {upscaler}")
                            converted_img = Upscaler.upscale_image(converted_img, upscaler)
                            if max(converted_img.width, converted_img.height) < self.target_resolution:
                                self.logger.info(f"画像サイズが小さすぎるため処理をスキップ: {db_stored_original_path}")
                                return None
                resized_img = self.image_processor.resize_image(converted_img)

                return resized_img

        except Exception as e:
            self.logger.error("画像処理中にエラーが発生しました: %s", e)

class ImageProcessor:
    logger = get_logger("ImageProcessor")
    def __init__(self, file_system_manager: FileSystemManager, target_resolution: int, preferred_resolutions: list[tuple[int, int]]) -> None:
        self.logger = ImageProcessor.logger
        self.file_system_manager = file_system_manager
        self.target_resolution = target_resolution
        self.preferred_resolutions = preferred_resolutions

    @staticmethod
    def normalize_color_profile(img: Image.Image, has_alpha: bool, mode: str = 'RGB') -> Image.Image:
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
                return ImageProcessor.normalize_color_profile(img.convert('RGB'), has_alpha, 'RGB')
            else:
                # サポートされていないモード
                ImageProcessor.logger.warning("ImageProcessor.normalize_color_profile サポートされていないモード: %s", mode)
                return img.convert('RGBA') if has_alpha else img.convert('RGB')

        except Exception as e:
            ImageProcessor.logger.error(f"ImageProcessor.normalize_color_profile :{e}")
            raise

    def _find_matching_resolution(self, original_width: int, original_height: int) -> Optional[tuple[int, int]]:
        """SDでよく使う解像度と同じアスペクト比の解像度を探す

        Args:
            original_width (int): もとの画像の幅
            original_height (int): もとの画像の高さ

        Returns:
            Optional[tuple[int, int]]: 同じアスペクト比の解像度のタプル
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
        self.logger = get_logger(__name__)

    @classmethod
    def auto_crop_image(cls, pil_image: Image.Image) -> Image.Image:
        instance = cls()
        return instance._auto_crop_image(pil_image)

    @staticmethod
    def _convert_to_gray(image: np.ndarray) -> np.ndarray:
        """RGBまたはRGBA画像をグレースケールに変換する"""
        if image.ndim == 2:
            return image
        if image.shape[2] == 3:
            return cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        if image.shape[2] == 4:
            return cv2.cvtColor(cv2.cvtColor(image, cv2.COLOR_RGBA2RGB), cv2.COLOR_RGB2GRAY)
        raise ValueError(f"サポートされていない画像形式です。形状: {image.shape}")

    @staticmethod
    def _calculate_edge_strength(gray_image: np.ndarray) -> np.ndarray:
        """グレースケール画像でエッジの強さを計算する"""
        return ndimage.sobel(gray_image)

    @staticmethod
    def _get_slices(height: int, width: int) -> list[tuple[slice, slice]]:
        """画像の特定の領域（上下左右および中央）をスライスで定義する"""
        return [
            (slice(0, height // 20), slice(None)),  # top
            (slice(-height // 20, None), slice(None)),  # bottom
            (slice(None), slice(0, width // 20)),  # left
            (slice(None), slice(-width // 20, None)),  # right
            (slice(height // 5, 4 * height // 5), slice(width // 5, 4 * width // 5))  # center
        ]

    @staticmethod
    def _calculate_region_statistics(gray_image: np.ndarray, edges: np.ndarray, slices: list[tuple[slice, slice]]) -> tuple[list[float], list[float], list[float]]:
        """各領域の平均値、標準偏差、およびエッジ強度を計算する"""
        means = [np.mean(gray_image[s]) for s in slices]
        stds = [np.std(gray_image[s]) for s in slices]
        edge_strengths = [np.mean(edges[s]) for s in slices]
        return means, stds, edge_strengths

    @staticmethod
    def _evaluate_edge(means: list[float], stds: list[float], edge_strengths: list[float],
                       edge_index: int, center_index: int,
                       color_threshold: float, std_threshold: float, edge_threshold: float) -> bool:
        """各辺の評価を行う"""
        color_diff = abs(means[edge_index] - means[center_index]) / 255
        is_uniform = stds[edge_index] < std_threshold * 255
        has_strong_edge = edge_strengths[edge_index] > edge_threshold * 255
        return color_diff > color_threshold and (is_uniform or has_strong_edge)

    @staticmethod
    def _detect_gradient(means: list[float], gradient_threshold: float) -> bool:
        """グラデーションを検出する"""
        vertical_gradient = abs(means[0] - means[1]) / 255
        horizontal_gradient = abs(means[2] - means[3]) / 255
        return vertical_gradient > gradient_threshold or horizontal_gradient > gradient_threshold

    @staticmethod
    def _detect_border_shape(image: np.ndarray, color_threshold: float = 0.15, std_threshold: float = 0.05,
                             edge_threshold: float = 0.1, gradient_threshold: float = 0.5) -> list[str]:
        height, width = image.shape[:2]
        gray_image = AutoCrop._convert_to_gray(image)
        edges = AutoCrop._calculate_edge_strength(gray_image)
        slices = AutoCrop._get_slices(height, width)
        means, stds, edge_strengths = AutoCrop._calculate_region_statistics(gray_image, edges, slices)

        detected_borders = []
        if AutoCrop._evaluate_edge(means, stds, edge_strengths, 0, 4, color_threshold, std_threshold, edge_threshold):
            detected_borders.append("TOP")
        if AutoCrop._evaluate_edge(means, stds, edge_strengths, 1, 4, color_threshold, std_threshold, edge_threshold):
            detected_borders.append("BOTTOM")
        if AutoCrop._evaluate_edge(means, stds, edge_strengths, 2, 4, color_threshold, std_threshold, edge_threshold):
            detected_borders.append("LEFT")
        if AutoCrop._evaluate_edge(means, stds, edge_strengths, 3, 4, color_threshold, std_threshold, edge_threshold):
            detected_borders.append("RIGHT")

        if AutoCrop._detect_gradient(means, gradient_threshold):
            return []  # グラデーションが検出された場合は境界なしとする

        return detected_borders

    def _get_crop_area(self, np_image: np.ndarray) -> Optional[tuple[int, int, int, int]]:
        """
        クロップ領域を検出するためのメソッド。OpenCV を使ったエリア検出。
        """
        try:
            # 差分によるクロップ領域検出を追加
            complementary_color = [255 - np.mean(np_image[..., i]) for i in range(3)]
            background = np.full(np_image.shape, complementary_color, dtype=np.uint8)
            diff = cv2.absdiff(np_image, background)

            # 差分をグレースケール変換
            gray_diff = self._convert_to_gray(diff)

            # ブラー処理を適用してノイズ除去
            blurred_diff = cv2.GaussianBlur(gray_diff, (5, 5), 0)

            # しきい値処理
            thresh = cv2.adaptiveThreshold(
                blurred_diff,  # グレースケール化された差分画像を使う
                255,  # 最大値（白）
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,  # 適応的しきい値の種類（ガウス法）
                cv2.THRESH_BINARY,  # 2値化（白か黒）
                11,  # ピクセル近傍のサイズ (奇数で指定)
                2   # 平均値または加重平均から減算する定数
            )
            # エッジ検出
            edges = cv2.Canny(thresh, threshold1=30, threshold2=100)
            # 輪郭検出
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if contours:
                x_min, y_min, x_max, y_max = np_image.shape[1], np_image.shape[0], 0, 0
                for contour in contours:
                    x, y, w, h = cv2.boundingRect(contour)
                    x_min, y_min = min(x_min, x), min(y_min, y)
                    x_max, y_max = max(x_max, x + w), max(y_max, y + h)

                # マスク処理によってクロップ領域を決定する
                mask = np.zeros(np_image.shape[:2], dtype=np.uint8)
                for contour in contours:
                    cv2.drawContours(mask, [contour], -1, 255, thickness=cv2.FILLED)

                # マスクの白い領域の座標を取得
                y_coords, x_coords = np.where(mask == 255)
                if len(x_coords) > 0 and len(y_coords) > 0:
                    x_min, y_min = np.min(x_coords), np.min(y_coords)
                    x_max, y_max = np.max(x_coords), np.max(y_coords)

                    # エリアを検証する必要がなくなり、ここで余分な領域を削るロジックを追加する
                    # TODO: このロジックは適切かどうかを検討する
                    margin = 5  # 余分に削るピクセル数
                    x_min = max(0, x_min + margin)
                    y_min = max(0, y_min + margin)
                    x_max = min(np_image.shape[1], x_max - margin)
                    y_max = min(np_image.shape[0], y_max - margin)

                    return x_min, y_min, x_max - x_min, y_max - y_min
            return None
        except Exception as e:
            self.logger.error(f"AutoCrop._get_crop_area: クロップ領域の検出中にエラーが発生しました: {e}")
            return None

    def _auto_crop_image(self, pil_image: Image.Image) -> Image.Image:
        """
        PIL.Image オブジェクトを受け取り、必要に応じて自動クロップを行います。

        Args:
            pil_image (Image.Image): 処理する PIL.Image オブジェクト

        Returns:
            Image.Image: クロップされた（または元の）PIL.Image オブジェクト
        """
        try:
            np_image = np.array(pil_image)
            crop_area = self._get_crop_area(np_image)

            # デバッグ情報の出力
            self.logger.debug(f"Crop area: {crop_area}")
            self.logger.debug(f"Original image size: {pil_image.size}")

            if crop_area:
                x, y, w, h = crop_area
                right, bottom = x + w, y + h
                cropped_image = pil_image.crop((x, y, right, bottom))
                self.logger.debug(f"Cropped image size: {cropped_image.size}")
                return cropped_image
            else:
                self.logger.debug("No crop area detected, returning original image")
                return pil_image
        except Exception as e:
            self.logger.error(f"自動クロップ処理中にエラーが発生しました: {e}")
            return pil_image

class Upscaler:
    # TODO: 暫定的なモデルパスとスケール値､もっと追加がしやすいようにする
    MODEL_PATHS: dict[str, tuple[Path, float]] = {
        "RealESRGAN_x4plus": (Path(r"H:\StabilityMatrix-win-x64\Data\Models\RealESRGAN\RealESRGAN_x4plus.pth"), 4.0),
    }
    def __init__(self, model_name: str):
        self.logger = get_logger(__name__)
        self.model_path, self.recommended_scale = self.MODEL_PATHS[model_name]
        self.model = self._load_model(self.model_path)
        self.model.cuda().eval()

    @classmethod
    def get_available_models(cls) -> list[str]:
        return list(cls.MODEL_PATHS.keys())

    @classmethod
    def upscale_image(cls, img: Image.Image, model_name: str, scale: float = None) -> Image.Image:
        upscaler = cls(model_name)
        scale = scale or upscaler.recommended_scale
        return upscaler._upscale(img, scale)

    def _load_model(self, model_path: Path) -> ImageModelDescriptor:
        model = ModelLoader().load_from_file(model_path)
        if not isinstance(model, ImageModelDescriptor):
            self.logger.error("読み込まれたモデルは ImageModelDescriptor のインスタンスではありません")
        return model

    def _upscale(self, img: Image.Image, scale: float) -> Image.Image:
        """
        画像をアップスケールする
        Args:
            img (Image.Image): アップスケールする画像
            scale (float): スケール倍率
        Returns:
            Image.Image: アップスケールされた画像
        """
        try:
            img_tensor = self._convert_image_to_tensor(img)
            with torch.no_grad():
                output = self.model(img_tensor)
            return self._convert_tensor_to_image(output, scale, img.size)
        except Exception as e:
            self.logger.error(f"アップスケーリング中のエラー: {e}")
            return img

    def _convert_image_to_tensor(self, image: Image.Image) -> torch.Tensor:
        img_np = np.array(image).astype(np.float32) / 255.0
        img_tensor = torch.from_numpy(img_np).permute(2, 0, 1).unsqueeze(0).cuda()
        return img_tensor

    def _convert_tensor_to_image(self, tensor: torch.Tensor, scale: float, original_size: tuple) -> Image.Image:
        output_np = tensor.squeeze().cpu().numpy().transpose(1, 2, 0)
        output_np = (output_np * 255).clip(0, 255).astype(np.uint8)
        output_image = Image.fromarray(output_np)
        expected_size = (int(original_size[0] * scale), int(original_size[1] * scale))
        if output_image.size != expected_size:
            output_image = output_image.resize(expected_size, Image.LANCZOS)
        return output_image

if __name__ == '__main__':
    ##自動クロップのテスト
    import matplotlib.pyplot as plt
    from PIL import Image

    img_path = Path(r'testimg\bordercrop\image_0001.png')
    img = Image.open(img_path)

    cropped_img = AutoCrop.auto_crop_image(img)
    plt.imshow(cropped_img)
    plt.show()
    print(cropped_img.size)