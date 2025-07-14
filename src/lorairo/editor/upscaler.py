"""
Upscaler module for image upscaling functionality.

This module provides image upscaling capabilities using various models
like RealESRGAN, configured through the ConfigurationService.
The implementation supports model caching and configuration-driven operation.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from PIL import Image

if TYPE_CHECKING:
    from ..services.configuration_service import ConfigurationService

from ..utils.log import logger


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
