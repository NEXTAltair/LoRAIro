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
            # 画像処理の設定をセットアップ
            self.original_images_dir = self.file_system_manager.original_images_dir
            self.resized_images_dir = self.file_system_manager.resized_images_dir

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
    def __init__(self, file_system_manager: FileSystemManager, target_resolution: int, preferred_resolutions: list[tuple[int, int]]) -> None:
        self.logger = get_logger(__name__)
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
                self.logger.warning("ImageProcessor.normalize_color_profile サポートされていないモード: %s", mode)
                return img.convert('RGBA') if has_alpha else img.convert('RGB')

        except Exception as e:
            self.logger.error("ImageProcessor.normalize_color_profile :%s", e)
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
        has_letterbox = bool(has_letterbox)
        is_gradient = bool(is_gradient)
        return has_letterbox and not is_gradient

    def _get_crop_area(self, np_image: np.ndarray) -> Optional[tuple[int, int, int, int]]:
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
                    self.logger.error("AutoCrop._get_crop_area: サポートされていない画像形式: %s", np_image.shape)
                    return None
            elif len(np_image.shape) == 2:
                gray_image = np_image
            else:
                self.logger.error("AutoCrop._get_crop_area: サポートされていない画像形式: %s", np_image.shape)
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
            self.logger.error("AutoCrop._get_crop_area: クロップ領域の特定中: %s", e)
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
            self.logger.error("自動クロップ処理中にエラーが発生しました: %s", e)
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
            self.logger.error("アップスケーリング中のエラー: %s", e, exc_info=True)
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