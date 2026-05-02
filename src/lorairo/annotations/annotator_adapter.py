"""image-annotator-lib統合アダプター

Data Access Layer: image-annotator-libとLoRAIroを統合
ConfigurationServiceからAPIキーを取得し、api_keysパラメータとして明示的に渡す
"""

from typing import TYPE_CHECKING, Any, cast

from image_annotator_lib import (
    AnnotatorInfo,
    discover_available_vision_models,
    get_available_models,
    is_model_deprecated,
    list_all_models,
    list_annotator_info,
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

    def get_available_models_with_metadata(self) -> list[dict[str, Any]]:
        """利用可能アノテーターのメタデータ付き一覧を取得 (dict 互換 API)。

        image-annotator-lib の型安全 API ``list_annotator_info()`` を呼び出し、
        上位層 (ModelSyncService 等) が期待する dict 形式に変換する。

        ※ 後続 Issue で Protocol/sync_service を ``list[AnnotatorInfo]`` に揃え、
           ``provider`` 等は config_registry 経由で取得する想定 (Phase 2)。

        Returns:
            list[dict[str, Any]]: モデルメタデータリスト
        """
        try:
            logger.debug("image-annotator-libからモデルメタデータを取得中...")

            infos: list[AnnotatorInfo] = list_annotator_info()
            models: list[dict[str, Any]] = [self._annotator_info_to_dict(info) for info in infos]

            logger.info(f"image-annotator-libからモデルメタデータ取得完了: {len(models)}件")
            return models

        except Exception as e:
            error_msg = f"image-annotator-libモデルメタデータ取得エラー: {e}"
            logger.error(error_msg, exc_info=True)
            raise

    @staticmethod
    def _infer_provider(info: AnnotatorInfo) -> str | None:
        """モデル名からプロバイダーを推論する。

        AnnotatorInfo に provider フィールドが存在しないため、モデル名のキーワードから推論する。
        Phase 2 (Issue #19/#220 follow-up) で config_registry 経由の正式取得に置き換える予定。

        Args:
            info: アノテーター情報

        Returns:
            str | None: プロバイダー名。ローカルモデルまたは推論不能の場合は None。
        """
        if not info.is_api:
            return None
        name_lower = info.name.lower()
        if any(k in name_lower for k in ("claude", "anthropic")):
            return "anthropic"
        if any(k in name_lower for k in ("gpt", "openai", "o1-", "o3-", "o4-")):
            return "openai"
        if any(k in name_lower for k in ("gemini", "google")):
            return "google"
        return None

    @staticmethod
    def _annotator_info_to_dict(info: AnnotatorInfo) -> dict[str, Any]:
        """AnnotatorInfo を上位層の dict 形式に変換する。

        旧 ``list_available_annotators_with_metadata()`` が返していたキーを互換目的で含めつつ、
        新規の型安全フィールド (is_local/is_api/device) も追加する。

        Note:
            ``class`` / ``api_model_id`` / ``estimated_size_gb`` / ``discontinued_at`` /
            ``max_output_tokens`` は AnnotatorInfo に含まれないため None で埋める。
            Phase 2 (Issue #19/#220 follow-up) で ``list[AnnotatorInfo]`` への migration と
            同時に config_registry 経由で取得する。
            ``provider`` はモデル名からの推論で補完する (暫定対処)。
        """
        provider = AnnotatorLibraryAdapter._infer_provider(info)
        return {
            "name": info.name,
            "model_name": info.name,
            "model_type": info.model_type,
            "capabilities": [c.value for c in info.capabilities],
            "is_local": info.is_local,
            "is_api": info.is_api,
            "device": info.device,
            "requires_api_key": info.is_api,
            # 旧 dict 互換キー
            "class": None,
            "provider": provider,
            "api_model_id": None,
            "estimated_size_gb": None,
            "discontinued_at": None,
            "max_output_tokens": None,
        }

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
            return list_all_models()
        return get_available_models()

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
