"""
画像編集スクリプト
- 画像の保存
- 画像の色域を変換
- 画像をリサイズ
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image

if TYPE_CHECKING:
    from ..services.configuration_service import ConfigurationService

from ..storage.file_system import FileSystemManager
from ..utils.log import logger
from .autocrop import AutoCrop
from .upscaler import Upscaler


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
