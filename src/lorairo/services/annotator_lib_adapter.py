"""ライブラリ統合アダプター

Phase 1-2: モック実装による独立開発
Phase 4: 実ライブラリ統合実装（外部注入方式）
"""

from typing import Any, Protocol

from PIL import Image

from ..services.configuration_service import ConfigurationService
from ..utils.log import logger


class ProviderManagerProtocol(Protocol):
    """ProviderManagerのプロトコル定義（DI用）"""

    @staticmethod
    def run_inference_with_model(
        model_name: str,
        images_list: list[Image.Image],
        api_model_id: str,
        api_keys: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """外部注入方式でのモデル推論実行"""
        ...


class MockProviderManager:
    """Phase 1-2用のモックProviderManager"""

    @staticmethod
    def run_inference_with_model(
        model_name: str,
        images_list: list[Image.Image],
        api_model_id: str,
        api_keys: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """モック推論実行"""
        logger.debug(f"[モック] ProviderManager推論実行: model={model_name}, api_model_id={api_model_id}")
        logger.debug(f"[モック] APIキー注入: {list(api_keys.keys()) if api_keys else 'なし'}")
        logger.debug(f"[モック] 画像数: {len(images_list)}")

        # モック結果生成
        mock_results = {}
        for i, image in enumerate(images_list):
            # phash計算をモック
            mock_phash = f"mock_phash_{i}_{hash(str(image.size)) % 10000}"

            mock_results[mock_phash] = {
                "tags": [f"mock_tag_{i}_1", f"mock_tag_{i}_2", f"{model_name}_generated"],
                "formatted_output": {
                    "tags": [f"mock_tag_{i}_1", f"mock_tag_{i}_2"],
                    "captions": [f"Mock caption for image {i} using {model_name}"],
                    "score": 0.85 + (i * 0.02),  # 可変スコア
                },
                "error": None,
            }

        return mock_results


class MockAnnotatorLibAdapter:
    """Phase 1-2用モック実装 - LoRAIro独立開発"""

    def __init__(self, config_service: ConfigurationService):
        """MockAnnotatorLibAdapterを初期化

        Args:
            config_service: 設定サービス
        """
        self.config_service = config_service
        self.provider_manager = MockProviderManager()
        logger.info("MockAnnotatorLibAdapterを初期化しました")

    def get_unified_api_keys(self) -> dict[str, str]:
        """LoRAIro設定からAPIキー取得（実装）"""
        api_keys = {}

        # LoRAIro設定から各プロバイダーのAPIキーを取得
        openai_key = self.config_service.get_setting("api", "openai_key", "")
        if openai_key:
            api_keys["openai"] = openai_key

        claude_key = self.config_service.get_setting("api", "claude_key", "")
        if claude_key:
            api_keys["anthropic"] = claude_key

        google_key = self.config_service.get_setting("api", "google_key", "")
        if google_key:
            api_keys["google"] = google_key

        logger.debug(f"統合APIキー取得: {list(api_keys.keys())}")
        return api_keys

    def call_annotate(
        self,
        images: list[Image.Image],
        models: list[str],
        phash_list: list[str] | None = None,
        api_keys: dict[str, str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """モックアノテーション処理

        Args:
            images: 画像リスト
            models: モデル名リスト
            phash_list: pHashリスト（オプション）
            api_keys: 外部注入APIキー（オプション）

        Returns:
            dict[str, dict[str, Any]]: phash -> model -> result の形式
        """
        logger.info(f"[モック] アノテーション処理開始: {len(images)}画像, {len(models)}モデル")

        # APIキー取得（外部注入優先）
        unified_keys = api_keys or self.get_unified_api_keys()

        # 全結果格納用
        all_results: dict[str, dict[str, Any]] = {}

        # 各モデルで推論実行
        for model_name in models:
            try:
                # モックProvider経由で推論実行
                model_results = self.provider_manager.run_inference_with_model(
                    model_name=model_name,
                    images_list=images,
                    api_model_id=model_name,  # Phase 1ではmodel_name = api_model_id
                    api_keys=unified_keys,
                )

                # 結果をphash -> model -> result 形式に変換
                for phash, result in model_results.items():
                    if phash not in all_results:
                        all_results[phash] = {}
                    all_results[phash][model_name] = result

            except Exception as e:
                logger.error(f"[モック] モデル {model_name} でエラー: {e}")
                # エラー結果を格納
                for i in range(len(images)):
                    mock_phash = f"error_phash_{i}"
                    if mock_phash not in all_results:
                        all_results[mock_phash] = {}
                    all_results[mock_phash][model_name] = {
                        "tags": [],
                        "formatted_output": None,
                        "error": str(e),
                    }

        logger.info(f"[モック] アノテーション処理完了: {len(all_results)}件の結果")
        return all_results

    def get_available_models_with_metadata(self) -> list[dict[str, Any]]:
        """モックモデルメタデータ"""
        logger.debug("[モック] 利用可能モデルメタデータ取得")

        return [
            {
                "name": "gpt-4o",
                "provider": "openai",
                "model_type": "vision",
                "api_model_id": "gpt-4o",
                "requires_api_key": True,
                "estimated_size_gb": None,
            },
            {
                "name": "claude-3-5-sonnet",
                "provider": "anthropic",
                "model_type": "vision",
                "api_model_id": "claude-3-5-sonnet-20241022",
                "requires_api_key": True,
                "estimated_size_gb": None,
            },
            {
                "name": "wd-v1-4-swinv2-tagger",
                "provider": None,
                "model_type": "tagger",
                "api_model_id": None,
                "requires_api_key": False,
                "estimated_size_gb": 1.2,
            },
        ]


class AnnotatorLibAdapter:
    """PydanticAI外部注入方式による設定統合アダプター

    Phase 4: 実ライブラリ統合実装
    """

    def __init__(
        self, config_service: ConfigurationService, provider_manager: ProviderManagerProtocol | None = None
    ):
        """AnnotatorLibAdapterを初期化

        Args:
            config_service: 設定サービス
            provider_manager: ProviderManager（None時はモック使用）
        """
        self.config_service = config_service

        # Phase 4: 実ProviderManager注入、Phase 1-2: モック使用
        self.provider_manager = provider_manager or MockProviderManager()

        logger.info("AnnotatorLibAdapterを初期化しました")

    def get_unified_api_keys(self) -> dict[str, str]:
        """LoRAIro設定を単一情報源とするAPIキー取得"""
        api_keys = {}

        # プロバイダー設定マッピング
        provider_mappings = [
            ("openai", "openai_key"),
            ("anthropic", "claude_key"),
            ("google", "google_key"),
        ]

        for provider, key in provider_mappings:
            api_key = self.config_service.get_setting("api", key, "")
            if api_key:
                api_keys[provider] = api_key

        logger.debug(f"統合APIキー取得: {list(api_keys.keys())}")
        return api_keys

    def call_annotate(
        self,
        images: list[Image.Image],
        models: list[str],
        phash_list: list[str] | None = None,
        api_keys: dict[str, str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """PydanticAI Provider-level外部注入による統合実行

        既存 ProviderManager.run_inference_with_model(..., api_keys=dict) 100%活用
        ライブラリ設定をLoRAIro設定で完全オーバーライド

        Args:
            images: 画像リスト
            models: モデル名リスト
            phash_list: pHashリスト（オプション）
            api_keys: 外部注入APIキー（オプション）

        Returns:
            dict[str, dict[str, Any]]: phash -> model -> result の形式
        """
        logger.info(f"アノテーション処理開始: {len(images)}画像, {len(models)}モデル")

        # LoRAIro設定で統一（外部注入方式）
        unified_keys = api_keys or self.get_unified_api_keys()

        # 全結果格納用
        all_results: dict[str, dict[str, Any]] = {}

        # 各モデルで推論実行
        for model_name in models:
            try:
                # PydanticAI Provider-level共有を最大活用
                model_results = self.provider_manager.run_inference_with_model(
                    model_name=model_name,
                    images_list=images,
                    api_model_id=model_name,  # Phase 4: 実際のapi_model_id解決実装
                    api_keys=unified_keys,  # 外部注入でライブラリ設定バイパス
                )

                # 結果をphash -> model -> result 形式に変換
                for phash, result in model_results.items():
                    if phash not in all_results:
                        all_results[phash] = {}
                    all_results[phash][model_name] = result

            except Exception as e:
                logger.error(f"モデル {model_name} でエラー: {e}")
                # エラー処理は実装時に詳細化
                continue

        logger.info(f"アノテーション処理完了: {len(all_results)}件の結果")
        return all_results

    def get_available_models_with_metadata(self) -> list[dict[str, Any]]:
        """新API呼び出し（Phase 3実装後に使用可能）"""
        try:
            # Phase 3+: 実際のライブラリAPI呼び出し
            from image_annotator_lib.core.registry import list_available_annotators_with_metadata

            raw_metadata = list_available_annotators_with_metadata()
            logger.info(f"実ライブラリから{len(raw_metadata)}件のモデルメタデータを取得しました")
            return list(raw_metadata.values())

        except ImportError as e:
            # Phase 1-2: モック実装フォールバック
            logger.warning(f"実ライブラリAPIが利用できません（{e}）。モック実装を使用します。")
            mock_adapter = MockAnnotatorLibAdapter(self.config_service)
            return mock_adapter.get_available_models_with_metadata()
        except Exception as e:
            # その他のエラーでもモック実装にフォールバック
            logger.error(f"実ライブラリAPI呼び出しエラー: {e}。モック実装を使用します。")
            mock_adapter = MockAnnotatorLibAdapter(self.config_service)
            return mock_adapter.get_available_models_with_metadata()


# Phase 1-2で使用するファクトリー関数
def create_annotator_lib_adapter(config_service: ConfigurationService) -> MockAnnotatorLibAdapter:
    """Phase 1-2用のアダプター作成ファクトリー"""
    return MockAnnotatorLibAdapter(config_service)


# Phase 4で使用するファクトリー関数
def create_production_annotator_lib_adapter(
    config_service: ConfigurationService, provider_manager: ProviderManagerProtocol | None = None
) -> AnnotatorLibAdapter:
    """Phase 4用の実装アダプター作成ファクトリー"""
    return AnnotatorLibAdapter(config_service, provider_manager)
