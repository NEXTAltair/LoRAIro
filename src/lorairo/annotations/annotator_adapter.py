"""image-annotator-lib統合アダプター

Data Access Layer: image-annotator-libとLoRAIroを統合
ConfigurationServiceからAPIキーを取得し、api_keysパラメータとして明示的に渡す
"""

from typing import TYPE_CHECKING, Any, cast

from image_annotator_lib import (
    discover_available_vision_models,
    get_available_models,
    is_model_deprecated,
    list_all_models,
    list_available_annotators_with_metadata,
)
from PIL import Image

from lorairo.services.configuration_service import ConfigurationService
from lorairo.utils.log import logger

if TYPE_CHECKING:
    from image_annotator_lib import (
        PHashAnnotationResults,
    )


class AnnotatorLibraryAdapter:
    """image-annotator-lib統合アダプター

    LoRAIro側の設計とimage-annotator-libのAPIを橋渡しする。
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
            # 外部ライブラリの戻り値型が未定義のためcastで明示
            models = cast(list[dict[str, Any]], list_available_annotators_with_metadata())

            logger.info(f"image-annotator-libからモデルメタデータ取得完了: {len(models)}件")
            return models

        except Exception as e:
            error_msg = f"image-annotator-libモデルメタデータ取得エラー: {e}"
            logger.error(error_msg, exc_info=True)
            raise

    def refresh_available_models(self, force_refresh: bool = True) -> list[str]:
        """WebAPIモデル一覧を強制更新し、利用可能なモデルIDを返す。"""
        try:
            logger.info("image-annotator-libモデル一覧の手動更新を開始")
            result = discover_available_vision_models(force_refresh=force_refresh)
            if "error" in result:
                raise RuntimeError(result["error"])

            models = cast(list[str], result.get("models", []))
            logger.info(f"image-annotator-libモデル一覧更新完了: {len(models)}件")
            return models
        except Exception:
            logger.error("image-annotator-libモデル一覧更新エラー", exc_info=True)
            raise

    def list_available_models(self, include_deprecated: bool = False) -> list[str]:
        """利用可能なWebAPIモデル一覧を返す。

        Args:
            include_deprecated: Trueの場合は廃止済みモデルも含める。
        """
        if include_deprecated:
            return cast(list[str], list_all_models())
        return cast(list[str], get_available_models())

    def is_model_deprecated(self, model_name: str) -> bool:
        """指定モデルが廃止済みかどうかを返す。"""
        return bool(is_model_deprecated(model_name))

    def annotate(
        self,
        images: list[Image.Image],
        model_names: list[str],
        phash_list: list[str] | None = None,
    ) -> "PHashAnnotationResults":
        """アノテーション実行

        image-annotator-libの`annotate()`を呼び出し、画像にアノテーションを付与する。
        APIキーは引数として明示的に渡す（グローバル環境変数を汚染しない）。

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
            logger.debug(
                f"アノテーション実行開始: {len(images)}画像, モデル={model_names}, "
                f"pHash指定={'あり' if phash_list else 'なし'}"
            )

            # APIキー準備（引数として渡す形式）
            api_keys = self._prepare_api_keys()
            logger.debug(f"利用可能プロバイダー: {list(api_keys.keys()) if api_keys else '（なし）'}")

            # image-annotator-lib API呼び出し
            from image_annotator_lib import annotate

            logger.debug(f"image-annotator-lib.annotate() 呼び出し: model_name_list={model_names}")

            results = annotate(
                images_list=images,
                model_name_list=model_names,
                phash_list=phash_list,
                api_keys=api_keys,  # 明示的に引数として渡す
            )

            logger.info(f"アノテーション実行完了: {len(results)}件の結果")
            return results

        except Exception as e:
            error_msg = f"アノテーション実行エラー: {e}"
            logger.error(error_msg, exc_info=True)
            raise

    def _prepare_api_keys(self) -> dict[str, str]:
        """APIキー辞書を準備

        ConfigurationService経由でconfig/lorairo.tomlからAPIキーを取得し、
        image-annotator-libに渡す形式の辞書を構築する。

        Returns:
            dict[str, str]: APIキー辞書
                - キー: プロバイダー名（"openai", "anthropic", "google"）
                - 値: APIキー文字列

        Note:
            空文字列のキーは除外される。
            ログ出力時はマスキングされる。
        """
        # ConfigurationServiceから各プロバイダーのAPIキーを取得
        api_keys = {
            "openai": self.config_service.get_setting("api", "openai_key", ""),
            "anthropic": self.config_service.get_setting("api", "claude_key", ""),
            "google": self.config_service.get_setting("api", "google_key", ""),
        }

        # 空のキーを除外（空文字列や空白のみの文字列を除く）
        api_keys = {k: v for k, v in api_keys.items() if v and v.strip()}

        if api_keys:
            # マスキングしてデバッグログ出力
            masked_keys = {k: self._mask_key(v) for k, v in api_keys.items()}
            logger.debug(f"APIキー準備完了: {list(api_keys.keys())} (masked: {masked_keys})")
        else:
            logger.warning("利用可能なAPIキーがありません")

        return api_keys

    def _mask_key(self, key: str) -> str:
        """APIキーをマスキング（ログ用）

        Args:
            key: APIキー文字列

        Returns:
            str: マスキングされたAPIキー
                - 8文字未満: "***"
                - 8文字以上: "sk-ab***cd" 形式（先頭4文字 + *** + 末尾4文字）
        """
        if not key or len(key) < 8:
            return "***"
        return f"{key[:4]}***{key[-4:]}"

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
