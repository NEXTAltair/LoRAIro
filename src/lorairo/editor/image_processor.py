"""
画像編集スクリプト
- 画像の保存
- 画像の色域を変換
- 画像をリサイズ
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Optional

import numpy as np
from PIL import Image

if TYPE_CHECKING:
    from ..services.configuration_service import ConfigurationService

from ..storage.file_system import FileSystemManager
from ..utils.log import logger
from .autocrop import AutoCrop


class ImageProcessingManager:
    def __init__(
        self,
        file_system_manager: FileSystemManager,
        target_resolution: int,
        preferred_resolutions: list[tuple[int, int]],
        config_service: "ConfigurationService",
    ):
        """
        ImageProcessingManagerを初期化
        一時的なインスタンスとして使用し、処理完了後は破棄される

        Args:
            file_system_manager (FileSystemManager): ファイルシステムマネージャ
            target_resolution (int): 目標解像度（GUI で指定された現在の値）
            preferred_resolutions (list[tuple[int, int]]): 優先解像度リスト
            config_service (ConfigurationService): 設定サービス
        """
        self.file_system_manager = file_system_manager
        self.target_resolution = target_resolution
        self.config_service = config_service

        try:
            # ImageProcessorの初期化
            self.image_processor = ImageProcessor(
                self.file_system_manager, target_resolution, preferred_resolutions
            )

            # Upscaler インスタンス作成（設定駆動型）
            self.upscaler = Upscaler(config_service)

            logger.info(f"ImageProcessingManagerが正常に初期化。target_resolution={target_resolution}")

        except Exception as e:
            message = f"ImageProcessingManagerの初期化中エラー: {e}"
            logger.error(message)
            raise ValueError(message) from e

    @classmethod
    def create_default(
        cls,
        file_system_manager: FileSystemManager,
        target_resolution: int,
        preferred_resolutions: list[tuple[int, int]],
    ) -> "ImageProcessingManager":
        """デフォルト設定でインスタンスを作成するファクトリメソッド（後方互換性用）"""
        from ..services.configuration_service import ConfigurationService

        config_service = ConfigurationService()
        return cls(file_system_manager, target_resolution, preferred_resolutions, config_service)

    def process_image(
        self,
        db_stored_original_path: Path,
        original_has_alpha: bool,
        original_mode: str,
        upscaler: str | None = None,
    ) -> tuple[Image.Image | None, dict[str, Any]]:
        """
        画像を処理し、処理後の画像オブジェクトと処理メタデータを返す

        Args:
            db_stored_original_path (Path): 処理する画像ファイルのパス
            original_has_alpha (bool): 元画像がアルファチャンネルを持つかどうか
            original_mode (str): 元画像のモード (例: 'RGB', 'CMYK', 'P')
            upscaler (str): アップスケーラーの名前

        Returns:
            tuple[Image.Image | None, dict[str, Any]]: (処理済み画像オブジェクト, 処理メタデータ)
                処理メタデータには以下が含まれる:
                - was_upscaled (bool): アップスケールが実行されたかどうか
                - upscaler_used (str | None): 使用されたアップスケーラー名

        """
        # 処理メタデータを初期化
        processing_metadata: dict[str, Any] = {"was_upscaled": False, "upscaler_used": None}

        try:
            with Image.open(db_stored_original_path) as img:
                cropped_img = AutoCrop.auto_crop_image(img)

                converted_img = self.image_processor.normalize_color_profile(
                    cropped_img, original_has_alpha, original_mode
                )

                if max(cropped_img.width, cropped_img.height) < self.target_resolution:
                    if upscaler:
                        if converted_img.mode == "RGBA":
                            logger.info(
                                f"RGBA 画像のためアップスケールをスキップ: {db_stored_original_path}"
                            )
                        else:
                            logger.debug(
                                f"長編が指定解像度未満のため{db_stored_original_path}をアップスケールします: {upscaler}"
                            )
                            converted_img = self.upscaler.upscale_image(converted_img, upscaler)

                            # アップスケール実行をメタデータに記録
                            processing_metadata["was_upscaled"] = True
                            processing_metadata["upscaler_used"] = upscaler

                            if max(converted_img.width, converted_img.height) < self.target_resolution:
                                logger.info(
                                    f"画像サイズが小さすぎるため処理をスキップ: {db_stored_original_path}"
                                )
                                return None, processing_metadata
                resized_img = self.image_processor.resize_image(converted_img)

                return resized_img, processing_metadata

        except Exception as e:
            logger.error(f"画像処理中にエラーが発生しました: {e}")
            logger.error(f"エラー詳細 - ファイル: {db_stored_original_path}, タイプ: {type(e).__name__}")
            import traceback

            logger.error(f"スタックトレース: {traceback.format_exc()}")
            return None, processing_metadata


class ImageProcessor:
    def __init__(
        self,
        file_system_manager: FileSystemManager,
        target_resolution: int,
        preferred_resolutions: list[tuple[int, int]],
    ) -> None:
        self.file_system_manager = file_system_manager
        self.target_resolution = target_resolution
        self.preferred_resolutions = preferred_resolutions

    @staticmethod
    def normalize_color_profile(img: Image.Image, has_alpha: bool, mode: str = "RGB") -> Image.Image:
        """
        画像の色プロファイルを正規化し、必要に応じて色空間変換を行う。

        Args:
            img (Image.Image): 処理する画像
            has_alpha (bool): 透過情報(アルファチャンネル)の有無
            mode (str): 画像のモード (例: 'RGB', 'CMYK', 'P')

        Returns:
            Image.Image: 色空間が正規化された画像
        """
        try:
            if mode in ["RGB", "RGBA"]:
                return img.convert("RGBA") if has_alpha else img.convert("RGB")
            elif mode == "CMYK":
                # CMYKからRGBに変換
                return img.convert("RGB")
            elif mode == "P":
                # パレットモードはRGBに変換してから処理
                return ImageProcessor.normalize_color_profile(img.convert("RGB"), has_alpha, "RGB")
            else:
                # サポートされていないモード
                logger.warning(
                    "ImageProcessor.normalize_color_profile サポートされていないモード: %s", mode
                )
                return img.convert("RGBA") if has_alpha else img.convert("RGB")

        except Exception as e:
            logger.error(f"ImageProcessor.normalize_color_profile :{e}")
            raise

    def _find_matching_resolution(
        self, original_width: int, original_height: int
    ) -> tuple[int, int] | None:
        """SDでよく使う解像度と同じアスペクト比の解像度を探す

        Args:
            original_width (int): もとの画像の幅
            original_height (int): もとの画像の高さ

        Returns:
            Optional[tuple[int, int]]: 同じアスペクト比の解像度のタプル
        """
        if original_width < self.target_resolution and original_height < self.target_resolution:
            print(
                f"find_matching_resolution Error: 意図しない小さな画像を受け取った: {original_width}x{original_height}"
            )
            return None

        aspect_ratio = original_width / original_height

        matching_resolutions = []
        for res in self.preferred_resolutions:
            if res[0] / res[1] == aspect_ratio:
                matching_resolutions.append(res)

        if matching_resolutions:
            target_area = self.target_resolution**2
            return min(matching_resolutions, key=lambda res: abs((res[0] * res[1]) - target_area))
        return None

    def resize_image(self, img: Image.Image) -> Image.Image:
        """
        画像をリサイズします。

        Args:
            img (Image.Image): リサイズする画像

        Returns:
            Image.Image: リサイズされた画像

        Raises:
            ValueError: 無効な画像サイズまたは計算結果の場合
        """
        if img is None:
            raise ValueError("入力画像がNoneです")

        original_width, original_height = img.size

        if original_width <= 0 or original_height <= 0:
            raise ValueError(f"無効な画像サイズです: {original_width}x{original_height}")

        matching_resolution = self._find_matching_resolution(original_width, original_height)

        if matching_resolution:
            new_width, new_height = matching_resolution
        else:
            aspect_ratio = original_width / original_height

            if aspect_ratio <= 0:
                raise ValueError(f"無効なアスペクト比です: {aspect_ratio}")

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

        # サイズの妥当性チェック
        if new_width <= 0 or new_height <= 0:
            raise ValueError(f"計算されたサイズが無効です: {new_width}x{new_height}")

        if new_width > 8192 or new_height > 8192:
            raise ValueError(f"計算されたサイズが大きすぎます: {new_width}x{new_height}")

        # アスペクト比を保ちつつ、新しいサイズでリサイズ
        return img.resize((new_width, new_height), Image.Resampling.LANCZOS)


class Upscaler:
    """設定駆動型アップスケーラークラス（依存注入対応）"""

    def __init__(self, config_service: "ConfigurationService"):
        """
        Upscaler を初期化します。

        Args:
            config_service (ConfigurationService): 設定サービス
        """
        self.config_service = config_service
        self._loaded_models: dict[str, Any] = {}

        # 設定の妥当性チェック
        if not self.config_service.validate_upscaler_config():
            logger.warning("アップスケーラー設定に問題があります。デフォルト設定を使用します。")

    @classmethod
    def create_default(cls) -> "Upscaler":
        """デフォルト設定でインスタンスを作成するファクトリメソッド（後方互換性用）"""
        from ..services.configuration_service import ConfigurationService

        config_service = ConfigurationService()
        return cls(config_service)

    def get_available_models(self) -> list[str]:
        """利用可能なモデル名のリストを取得します。"""
        return self.config_service.get_available_upscaler_names()

    def upscale_image(self, img: Image.Image, model_name: str, scale: float | None = None) -> Image.Image:
        """
        画像をアップスケールします。

        Args:
            img (Image.Image): アップスケールする画像
            model_name (str): 使用するモデル名
            scale (float, optional): スケール倍率。Noneの場合は設定から取得

        Returns:
            Image.Image: アップスケールされた画像
        """
        try:
            # モデル設定取得
            model_config = self.config_service.get_upscaler_model_by_name(model_name)
            if not model_config:
                logger.error(f"アップスケーラーモデル '{model_name}' が見つかりません")
                return img

            # スケール決定
            scale = scale or model_config.get("scale", 4.0)

            # モデル読み込み（キャッシュ使用）
            model = self._get_or_load_model(model_name, model_config)
            if model is None:
                logger.error(f"モデル '{model_name}' の読み込みに失敗しました")
                return img

            return self._upscale(img, model, scale)

        except Exception as e:
            logger.error(f"アップスケーリング中のエラー: {e}")
            return img

    def _get_or_load_model(self, model_name: str, model_config: dict[str, Any]) -> Any:
        """モデルを取得または読み込みします（キャッシュ機能付き）"""
        if model_name in self._loaded_models:
            return self._loaded_models[model_name]

        model_path = Path(model_config["path"])
        if not model_path.is_absolute():
            # 相対パスの場合はプロジェクトルートからの相対パスとして解決
            project_root = Path.cwd()
            model_path = project_root / model_path

        if not model_path.exists():
            logger.error(f"モデルファイルが見つかりません: {model_path}")
            return None

        try:
            model = self._load_model(model_path)
            self._loaded_models[model_name] = model
            return model
        except Exception as e:
            logger.error(f"モデル読み込み中のエラー: {e}")
            return None

    def _load_model(self, model_path: Path) -> Any:
        """モデルファイルを読み込みます。"""
        # Lazy import to avoid slow startup
        from spandrel import ImageModelDescriptor, ModelLoader

        model = ModelLoader().load_from_file(model_path)
        if not isinstance(model, ImageModelDescriptor):
            logger.error("読み込まれたモデルは ImageModelDescriptor のインスタンスではありません")

        # CPU固定で評価モード設定
        model.cpu().eval()
        return model

    def _upscale(self, img: Image.Image, model: Any, scale: float) -> Image.Image:
        """
        画像をアップスケールします。

        Args:
            img (Image.Image): アップスケールする画像
            model: 読み込み済みモデル
            scale (float): スケール倍率

        Returns:
            Image.Image: アップスケールされた画像
        """
        # Lazy import to avoid slow startup
        import torch

        try:
            img_tensor = self._convert_image_to_tensor(img)
            with torch.no_grad():
                output = model(img_tensor)
            return self._convert_tensor_to_image(output, scale, img.size)
        except Exception as e:
            logger.error(f"アップスケーリング中のエラー: {e}")
            return img

    def _convert_image_to_tensor(self, image: Image.Image):
        """PIL画像をPyTorchテンソルに変換します（CPU使用）"""
        # Lazy import to avoid slow startup
        import torch

        img_np = np.array(image).astype(np.float32) / 255.0
        img_tensor = torch.from_numpy(img_np).permute(2, 0, 1).unsqueeze(0)
        # CPU固定（.cuda() 削除）
        return img_tensor

    def _convert_tensor_to_image(self, tensor, scale: float, original_size: tuple) -> Image.Image:
        """PyTorchテンソルをPIL画像に変換します。"""
        # Lazy import to avoid slow startup
        import torch

        output_np = tensor.squeeze().numpy().transpose(1, 2, 0)
        output_np = (output_np * 255).clip(0, 255).astype(np.uint8)
        output_image = Image.fromarray(output_np)
        expected_size = (int(original_size[0] * scale), int(original_size[1] * scale))
        if output_image.size != expected_size:
            output_image = output_image.resize(expected_size, Image.LANCZOS)
        return output_image
