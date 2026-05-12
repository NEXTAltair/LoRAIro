"""image-annotator-lib統合アダプター

Data Access Layer: image-annotator-libとLoRAIroを統合
ConfigurationServiceからAPIキーを取得し、api_keysパラメータとして明示的に渡す
`ModelRegistryServiceProtocol` を実装し、GUI/CLI から統一窓口として使用される。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from image_annotator_lib import (
    AnnotatorInfo,
    discover_available_vision_models,
    get_available_models,
    is_model_deprecated,
    list_all_models,
    list_annotator_info,
)
from image_annotator_lib.core.types import TaskCapability
from PIL import Image

from lorairo.services.configuration_service import ConfigurationService
from lorairo.services.model_registry_protocol import ModelInfo
from lorairo.utils.log import logger

if TYPE_CHECKING:
    from image_annotator_lib import (
        PHashAnnotationResults,
    )


# AnnotatorInfo.capabilities (frozenset[TaskCapability]) → ModelInfo.capabilities (list[str])
# の変換テーブル。TaskCapability.value をそのまま採用する。
_CAPABILITY_VALUES: dict[TaskCapability, str] = {
    TaskCapability.TAGS: "tags",
    TaskCapability.CAPTIONS: "captions",
    TaskCapability.SCORES: "scores",
}

__all__ = ["AnnotatorLibraryAdapter"]


class AnnotatorLibraryAdapter:
    """image-annotator-lib統合アダプター

    LoRAIro側の設計とimage-annotator-libのAPIを橋渡しする。
    ConfigurationService経由でAPIキーを取得し、image-annotator-libに渡す。
    `ModelRegistryServiceProtocol` を実装する (構造的サブタイピング)。
    """

    def __init__(self, config_service: ConfigurationService):
        """AnnotatorLibraryAdapter初期化

        Args:
            config_service: 設定サービス（APIキー取得用）
        """
        self.config_service = config_service
        logger.info("AnnotatorLibraryAdapter初期化完了（実ライブラリ統合モード）")

    def list_annotator_info(self) -> list[AnnotatorInfo]:
        """利用可能アノテーターの型安全メタデータ一覧を取得する。

        image-annotator-lib の ``list_annotator_info()`` 公開 API を委譲呼び出しで返す。
        ローカル ML モデルと WebAPI モデル、PydanticAI 直接モデルを統合した完全リストを
        ``list[AnnotatorInfo]`` で返却する (ソート: name 昇順)。

        Returns:
            list[AnnotatorInfo]: 型安全なアノテーター情報のリスト
        """
        try:
            infos = list_annotator_info()
            logger.debug(f"image-annotator-lib から AnnotatorInfo を {len(infos)} 件取得")
            return infos
        except Exception:
            logger.error("image-annotator-lib AnnotatorInfo 取得エラー", exc_info=True)
            raise

    def get_available_models(self) -> list[ModelInfo]:
        """`ModelRegistryServiceProtocol` 実装: 利用可能モデルを `ModelInfo` で返す。

        Returns:
            list[ModelInfo]: 全 AnnotatorInfo + Extras から組み立てた ModelInfo リスト
        """
        infos = self.list_annotator_info()
        return [self._to_model_info(info) for info in infos]

    def get_available_models_with_metadata(self) -> list[ModelInfo]:
        """`ModelRegistryServiceProtocol` 実装 (互換別名): 同上。"""
        return self.get_available_models()

    def _to_model_info(self, info: AnnotatorInfo) -> ModelInfo:
        """`AnnotatorInfo` から `ModelInfo` を組み立てる。

        provider は `info.provider` を使用し、未設定の場合は
        API モデルなら "unknown"、ローカルモデルなら "local" にフォールバックする。
        """
        capabilities = sorted(_CAPABILITY_VALUES[c] for c in info.capabilities)
        return ModelInfo(
            name=info.name,
            provider=info.provider or ("unknown" if info.is_api else "local"),
            capabilities=capabilities,
            litellm_model_id=info.litellm_model_id,
            requires_api_key=info.is_api,
            estimated_size_gb=info.estimated_size_gb,
        )

    def refresh_available_models(self) -> list[str]:
        """WebAPIモデル一覧を取得し、利用可能なモデルIDを返す。

        ADR 0023 Phase 1 で `force_refresh` 引数は廃止された。LiteLLM 同梱 DB を
        runtime SSoT として直接参照するため、refresh 概念が消失している。
        """
        try:
            logger.info("image-annotator-libモデル一覧の取得を開始")
            result = discover_available_vision_models()
            models = cast(list[str], result.get("models", []))
            logger.info(f"image-annotator-libモデル一覧取得完了: {len(models)}件")
            return models
        except Exception:
            logger.error("image-annotator-libモデル一覧取得エラー", exc_info=True)
            raise

    def list_available_models(self, include_deprecated: bool = False) -> list[str]:
        """利用可能なWebAPIモデル一覧を返す。

        Args:
            include_deprecated: Trueの場合は廃止済みモデルも含める。
        """
        if include_deprecated:
            return list_all_models()
        return get_available_models()

    def is_model_deprecated(self, model_name: str) -> bool:
        """指定モデルが廃止済みかどうかを返す。"""
        return bool(is_model_deprecated(model_name))

    def annotate(
        self,
        images: list[Image.Image],
        litellm_model_ids: list[str],
        phash_list: list[str] | None = None,
    ) -> PHashAnnotationResults:
        """アノテーション実行

        image-annotator-libの`annotate()`を呼び出し、画像にアノテーションを付与する。
        APIキーは引数として明示的に渡す（グローバル環境変数を汚染しない）。

        Issue #245 / ADR 0023 Phase 1.11: 引数の `litellm_model_ids` は LoRAIro 側の
        `Model.litellm_model_id` (registry key SSoT)。ライブラリ側の `model_name_list`
        は `AnnotatorInfo.name` (= WebAPI で LiteLLM 完全 ID、ローカル ML で bare 名)
        を取るが、両者は Phase 1.10 / 1.11 で一致する値域に収束済みのためそのまま
        forward する。

        Args:
            images: アノテーション対象画像リスト
            litellm_model_ids: 使用モデルの `litellm_model_id` リスト
            phash_list: 画像のpHashリスト（省略時は自動計算）

        Returns:
            PHashAnnotationResults: アノテーション結果（pHashをキーとする辞書）

        Raises:
            Exception: アノテーション実行時のエラー
        """
        try:
            logger.debug(
                f"アノテーション実行開始: {len(images)}画像, "
                f"litellm_model_ids={litellm_model_ids}, "
                f"pHash指定={'あり' if phash_list else 'なし'}"
            )

            # APIキー準備（引数として渡す形式）
            api_keys = self._prepare_api_keys()
            logger.debug(f"利用可能プロバイダー: {list(api_keys.keys()) if api_keys else '（なし）'}")

            # image-annotator-lib API呼び出し
            from image_annotator_lib import annotate

            logger.debug(f"image-annotator-lib.annotate() 呼び出し: model_name_list={litellm_model_ids}")

            results = annotate(
                images_list=images,
                model_name_list=litellm_model_ids,
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
