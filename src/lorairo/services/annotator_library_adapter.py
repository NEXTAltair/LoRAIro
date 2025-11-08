"""image-annotator-lib統合アダプター

Phase 4-1: 実ライブラリ統合実装
AnnotatorLibraryProtocolを実装し、image-annotator-libとLoRAIroを統合
"""

import os
from typing import TYPE_CHECKING, Any

from image_annotator_lib import list_available_annotators_with_metadata
from PIL import Image

from ..utils.log import logger
from .configuration_service import ConfigurationService

if TYPE_CHECKING:
    from image_annotator_lib import PHashAnnotationResults  # type: ignore[attr-defined]


class AnnotatorLibraryAdapter:
    """image-annotator-lib統合アダプター

    LoRAIro側のProtocol-based設計とimage-annotator-libのAPIを橋渡しする。
    ConfigurationService経由でAPIキーを取得し、image-annotator-libに渡す。
    """

    def __init__(self, config_service: ConfigurationService):
        """AnnotatorLibraryAdapter初期化

        Args:
            config_service: 設定サービス（APIキー取得用）
        """
        self.config_service = config_service
        logger.info("AnnotatorLibraryAdapter初期化完了（実ライブラリ統合モード）")

    def get_available_models_with_metadata(self) -> list[dict[str, Any]]:
        """利用可能アノテーターのメタデータ付き一覧を取得

        image-annotator-libの`list_available_annotators_with_metadata()`を呼び出し、
        モデルメタデータを取得する。

        Returns:
            list[dict[str, Any]]: モデルメタデータリスト

        Raises:
            Exception: image-annotator-lib呼び出し時のエラー
        """
        try:
            logger.debug("image-annotator-libからモデルメタデータを取得中...")

            # image-annotator-lib API呼び出し
            models: list[dict[str, Any]] = list_available_annotators_with_metadata()  # type: ignore[assignment]

            logger.info(f"image-annotator-libからモデルメタデータ取得完了: {len(models)}件")
            return models

        except Exception as e:
            error_msg = f"image-annotator-libモデルメタデータ取得エラー: {e}"
            logger.error(error_msg, exc_info=True)
            raise

    def annotate(
        self,
        images: list[Image.Image],
        model_names: list[str],
        phash_list: list[str] | None = None,
    ) -> "PHashAnnotationResults":
        """アノテーション実行

        image-annotator-libの`annotate()`を呼び出し、画像にアノテーションを付与する。
        実行前にAPIキーを環境変数に設定する。

        Args:
            images: アノテーション対象画像リスト
            model_names: 使用モデル名リスト
            phash_list: 画像のpHashリスト（省略時は自動計算）

        Returns:
            PHashAnnotationResults: アノテーション結果（pHashをキーとする辞書）

        Raises:
            Exception: アノテーション実行時のエラー
        """
        try:
            logger.debug(f"アノテーション実行開始: {len(images)}画像, {len(model_names)}モデル")

            # APIキー設定（環境変数に設定）
            self._set_api_keys_to_env()

            # image-annotator-lib API呼び出し
            # NOTE: image-annotator-libは内部で環境変数からAPIキーを読み取る
            from image_annotator_lib import annotate

            results = annotate(
                images_list=images,
                model_name_list=model_names,
                phash_list=phash_list,
            )

            logger.info(f"アノテーション実行完了: {len(results)}件の結果")
            return results

        except Exception as e:
            error_msg = f"アノテーション実行エラー: {e}"
            logger.error(error_msg, exc_info=True)
            raise

    def _set_api_keys_to_env(self) -> None:
        """APIキーを環境変数に設定

        ConfigurationService経由でconfig/lorairo.tomlからAPIキーを取得し、
        image-annotator-libが参照する環境変数に設定する。

        image-annotator-libが参照する環境変数:
        - OPENAI_API_KEY: OpenAI APIキー
        - ANTHROPIC_API_KEY: Anthropic APIキー
        - GOOGLE_API_KEY: Google APIキー
        """
        # OpenAI APIキー
        openai_key = self.config_service.get_setting("api", "openai_key", "")
        if openai_key:
            os.environ["OPENAI_API_KEY"] = openai_key
            logger.debug("OPENAI_API_KEY を環境変数に設定")
        else:
            logger.debug("OPENAI_API_KEY は未設定")

        # Anthropic APIキー
        claude_key = self.config_service.get_setting("api", "claude_key", "")
        if claude_key:
            os.environ["ANTHROPIC_API_KEY"] = claude_key
            logger.debug("ANTHROPIC_API_KEY を環境変数に設定")
        else:
            logger.debug("ANTHROPIC_API_KEY は未設定")

        # Google APIキー
        google_key = self.config_service.get_setting("api", "google_key", "")
        if google_key:
            os.environ["GOOGLE_API_KEY"] = google_key
            logger.debug("GOOGLE_API_KEY を環境変数に設定")
        else:
            logger.debug("GOOGLE_API_KEY は未設定")

    def get_adapter_info(self) -> dict[str, Any]:
        """アダプター情報取得

        Returns:
            dict[str, Any]: アダプター情報
        """
        return {
            "adapter_type": "AnnotatorLibraryAdapter",
            "library": "image-annotator-lib",
            "mode": "production",
            "config_service": type(self.config_service).__name__,
        }
