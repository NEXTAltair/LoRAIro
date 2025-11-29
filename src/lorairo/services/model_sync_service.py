"""ライブラリとLoRAIro DB間のモデル同期サービス

Phase 1-2: モック実装による独立開発
Phase 4: 実ライブラリ統合実装
"""

import datetime
from dataclasses import dataclass
from typing import Any, Protocol, TypedDict

from ..database.db_repository import ImageRepository
from ..services.configuration_service import ConfigurationService
from ..utils.log import logger


class ModelMetadata(TypedDict):
    """モデルメタデータの型定義"""

    name: str
    provider: str | None
    class_name: str
    api_model_id: str | None
    model_type: str  # "vision", "score", "tagger" (ライブラリから取得)
    model_types: list[str]  # LoRAIro DBのmodel_types (マッピング後)
    estimated_size_gb: float | None
    requires_api_key: bool
    discontinued_at: datetime.datetime | None


@dataclass
class ModelSyncResult:
    """モデル同期結果"""

    total_library_models: int
    new_models_registered: int
    existing_models_updated: int
    errors: list[str]

    @property
    def success(self) -> bool:
        """同期が成功したかどうか"""
        return len(self.errors) == 0

    @property
    def summary(self) -> str:
        """同期結果のサマリー"""
        return (
            f"同期完了: ライブラリモデル {self.total_library_models}件, "
            f"新規登録 {self.new_models_registered}件, "
            f"更新 {self.existing_models_updated}件, "
            f"エラー {len(self.errors)}件"
        )


class AnnotatorLibraryProtocol(Protocol):
    """アノテーターライブラリのプロトコル定義（DI用）"""

    def get_available_models_with_metadata(self) -> list[dict[str, Any]]:
        """利用可能アノテーターのメタデータ付き一覧を返す（Protocol-based仕様）"""
        ...


class MockAnnotatorLibrary:
    """Phase 1-2用のモックライブラリ実装"""

    def get_available_models_with_metadata(self) -> list[dict[str, Any]]:
        """モックのメタデータ付きモデル一覧"""
        logger.debug("モックライブラリからメタデータ付きモデル一覧を取得")

        # モックデータ - Protocol-based仕様に合わせてlist形式で返却
        return [
            {
                "name": "gpt-4o",
                "class": "PydanticAIWebAPIAnnotator",
                "provider": "openai",
                "api_model_id": "gpt-4o",
                "max_output_tokens": 1800,
                "model_type": "vision",
                "estimated_size_gb": None,
                "requires_api_key": True,
                "discontinued_at": None,
            },
            {
                "name": "claude-3-5-sonnet",
                "class": "PydanticAIWebAPIAnnotator",
                "provider": "anthropic",
                "api_model_id": "claude-3-5-sonnet-20241022",
                "max_output_tokens": 1800,
                "model_type": "vision",
                "estimated_size_gb": None,
                "requires_api_key": True,
                "discontinued_at": None,
            },
            {
                "name": "gemini-1.5-pro",
                "class": "PydanticAIWebAPIAnnotator",
                "provider": "google",
                "api_model_id": "gemini-1.5-pro",
                "max_output_tokens": 1800,
                "model_type": "vision",
                "estimated_size_gb": None,
                "requires_api_key": True,
                "discontinued_at": None,
            },
            {
                "name": "wd-v1-4-swinv2-tagger",
                "class": "WDTagger",
                "provider": None,
                "api_model_id": None,
                "max_output_tokens": None,
                "model_type": "tagger",
                "estimated_size_gb": 1.2,
                "requires_api_key": False,
                "discontinued_at": None,
            },
            {
                "name": "aesthetic-predictor",
                "class": "AestheticPredictor",
                "provider": None,
                "api_model_id": None,
                "max_output_tokens": None,
                "model_type": "score",
                "estimated_size_gb": 0.8,
                "requires_api_key": False,
                "discontinued_at": None,
            },
        ]


class ModelSyncService:
    """ライブラリとLoRAIro DB間のモデル同期サービス

    image-annotator-libが管理するアノテーション専用モデル（vision, score, tagger）の
    LoRAIro DBとの同期を担当。upscaler等のLoRAIro独自機能は対象外。

    Phase 4: 実ライブラリ統合実装
    Protocol-based経由で実ライブラリまたはMockと連携
    """

    def __init__(
        self,
        db_repository: ImageRepository,
        config_service: ConfigurationService,
        annotator_library: AnnotatorLibraryProtocol | None = None,
    ):
        """ModelSyncService初期化

        Args:
            db_repository: 画像データベースリポジトリ
            config_service: 設定サービス
            annotator_library: アノテーターライブラリアダプター（Protocol-based or Mock）
        """
        self.db_repository = db_repository
        self.config_service = config_service
        self.annotator_library = annotator_library or MockAnnotatorLibrary()

        # Phase 4: 実ライブラリかMockかの判定
        adapter_type = type(self.annotator_library).__name__
        if adapter_type == "MockAnnotatorLibrary":
            logger.info(f"ModelSyncService初期化完了（Mock実装 - {adapter_type}）")
        else:
            logger.info(f"ModelSyncService初期化完了（Protocol-based実装 - {adapter_type}）")

    def _map_library_model_type_to_db(
        self, library_model_type: str, model_name: str, class_name: str
    ) -> list[str]:
        """image-annotator-libのmodel_typeをLoRAIro DBのmodel_typesにマッピング

        Args:
            library_model_type: ライブラリのmodel_type（"vision", "score", "tagger"）
            model_name: モデル名（判定補助用）
            class_name: モデルクラス名（判定補助用）

        Returns:
            list[str]: LoRAIroのmodel_typesリスト

        Mapping Rules:
            - "vision" → ["captioner"] （デフォルト）
                - PydanticAI WebAPIモデルの場合 → ["llm", "captioner"]
                - class_name に "llm" が含まれる場合 → ["llm"]
            - "score" → ["score"]
            - "tagger" → ["tagger"]
        """
        if library_model_type == "vision":
            # PydanticAI WebAPIモデル（GPT-4, Claude, Gemini等）はLLMとしても機能
            if "pydanticai" in class_name.lower() or "webapi" in class_name.lower():
                return ["llm", "captioner"]
            # LLM専用モデル
            elif "llm" in class_name.lower() or "llm" in model_name.lower():
                return ["llm"]
            # その他のvisionモデルはcaptionerとして扱う
            else:
                return ["captioner"]

        elif library_model_type == "score":
            return ["score"]

        elif library_model_type == "tagger":
            return ["tagger"]

        else:
            # 未知のタイプは警告してcaptionerとして扱う
            logger.warning(f"Unknown library model_type: {library_model_type}, defaulting to ['captioner']")
            return ["captioner"]

    def sync_available_models(self) -> ModelSyncResult:
        """利用可能モデルの自動同期

        Returns:
            ModelSyncResult: 同期結果
        """
        logger.info("アノテーションモデル同期処理を開始します")

        try:
            # 1. ライブラリからモデルメタデータ取得
            library_models = self.get_model_metadata_from_library()

            # 2. 新規モデル登録
            new_count = self.register_new_models_to_db(library_models)

            # 3. 既存モデル更新
            update_count = self.update_existing_models(library_models)

            result = ModelSyncResult(
                total_library_models=len(library_models),
                new_models_registered=new_count,
                existing_models_updated=update_count,
                errors=[],
            )

            logger.info(f"アノテーションモデル同期完了: {result.summary}")
            return result

        except Exception as e:
            logger.error(f"モデル同期処理中にエラーが発生しました: {e}", exc_info=True)
            return ModelSyncResult(
                total_library_models=0, new_models_registered=0, existing_models_updated=0, errors=[str(e)]
            )

    def get_model_metadata_from_library(self) -> list[ModelMetadata]:
        """ライブラリからモデルメタデータ取得

        Returns:
            list[ModelMetadata]: アノテーション専用モデルメタデータのリスト
        """
        logger.debug("image-annotator-libからモデルメタデータを取得します")

        try:
            # ライブラリAPIからメタデータ付きモデル一覧を取得
            raw_models = self.annotator_library.get_available_models_with_metadata()

            models_metadata: list[ModelMetadata] = []
            for model_info in raw_models:
                # ライブラリのmodel_typeをLoRAIro DBのmodel_typesにマッピング
                library_model_type = model_info.get("model_type", "vision")
                db_model_types = self._map_library_model_type_to_db(
                    library_model_type,
                    model_info.get("name", "unknown"),
                    model_info.get("class", "Unknown"),
                )

                # ModelMetadata形式に変換
                metadata: ModelMetadata = {
                    "name": model_info.get("name", "unknown"),
                    "provider": model_info.get("provider"),
                    "class_name": model_info.get("class", "Unknown"),
                    "api_model_id": model_info.get("api_model_id"),
                    "model_type": library_model_type,
                    "model_types": db_model_types,  # マッピング後のリスト
                    "estimated_size_gb": model_info.get("estimated_size_gb"),
                    "requires_api_key": model_info.get("requires_api_key", False),
                    "discontinued_at": model_info.get(
                        "discontinued_at"
                    ),  # Issue #5解決: ライブラリから取得
                }
                models_metadata.append(metadata)

            logger.debug(
                f"image-annotator-libから {len(models_metadata)}件のアノテーションモデルを取得しました"
            )
            return models_metadata

        except Exception as e:
            logger.error(f"ライブラリからのモデルメタデータ取得中にエラー: {e}")
            raise

    def register_new_models_to_db(self, models: list[ModelMetadata]) -> int:
        """新規モデルのDB登録

        Args:
            models: 登録対象のモデルメタデータリスト

        Returns:
            int: 登録された新規モデル数
        """
        logger.debug("新規アノテーションモデルのDB登録を開始します")

        new_count = 0

        for model_metadata in models:
            try:
                # 既存モデルチェック（公開APIを使用）
                existing_model = self.db_repository.get_model_by_name(model_metadata["name"])

                if existing_model is None:
                    # 新規モデル登録
                    logger.debug(f"新規アノテーションモデルを登録: {model_metadata['name']}")

                    # 実際のDB登録実装（Phase 4完了）
                    model_id = self.db_repository.insert_model(
                        name=model_metadata["name"],
                        provider=model_metadata.get("provider"),
                        model_types=model_metadata["model_types"],
                        api_model_id=model_metadata.get("api_model_id"),
                        estimated_size_gb=model_metadata.get("estimated_size_gb"),
                        requires_api_key=model_metadata.get("requires_api_key", False),
                        discontinued_at=model_metadata.get("discontinued_at"),
                    )
                    logger.info(
                        f"新規アノテーションモデル登録成功: {model_metadata['name']} "
                        f"(ID={model_id}, types={model_metadata['model_types']})"
                    )
                    new_count += 1

            except Exception as e:
                logger.error(f"アノテーションモデル登録エラー {model_metadata['name']}: {e}")
                continue

        logger.info(f"新規アノテーションモデル登録完了: {new_count}件")
        return new_count

    def update_existing_models(self, models: list[ModelMetadata]) -> int:
        """既存モデル情報の更新

        Args:
            models: 更新対象のモデルメタデータリスト

        Returns:
            int: 更新された既存モデル数
        """
        logger.debug("既存アノテーションモデル情報の更新を開始します")

        update_count = 0

        for model_metadata in models:
            try:
                # 既存モデルチェック（公開APIを使用）
                existing_model = self.db_repository.get_model_by_name(model_metadata["name"])

                if existing_model is not None:
                    # 既存モデル更新判定・実行（Phase 4完了）
                    logger.debug(f"既存アノテーションモデルの更新チェック: {model_metadata['name']}")

                    # 実際の更新判定・DB更新実装（差分検出はリポジトリ層で実施）
                    was_updated = self.db_repository.update_model(
                        model_id=existing_model.id,
                        provider=model_metadata.get("provider"),
                        model_types=model_metadata["model_types"],
                        api_model_id=model_metadata.get("api_model_id"),
                        estimated_size_gb=model_metadata.get("estimated_size_gb"),
                        requires_api_key=model_metadata.get("requires_api_key", False),
                        discontinued_at=model_metadata.get("discontinued_at"),
                    )

                    if was_updated:
                        logger.info(
                            f"既存アノテーションモデル更新成功: {model_metadata['name']} "
                            f"(ID={existing_model.id}, types={model_metadata['model_types']})"
                        )
                        update_count += 1
                    else:
                        logger.debug(f"既存アノテーションモデル変更なし: {model_metadata['name']}")

            except Exception as e:
                logger.error(f"アノテーションモデル更新エラー {model_metadata['name']}: {e}")
                continue

        logger.info(f"既存アノテーションモデル更新完了: {update_count}件")
        return update_count

    def get_library_models_summary(self) -> dict[str, Any]:
        """ライブラリモデルのサマリー情報取得

        Returns:
            dict[str, Any]: アノテーションモデルサマリー情報
        """
        try:
            models = self.get_model_metadata_from_library()

            # プロバイダー別・タイプ別の集計
            providers: dict[str, int] = {}
            model_types: dict[str, int] = {}
            api_key_required = 0
            local_models = 0

            for model in models:
                # プロバイダー集計
                provider = model["provider"] or "local"
                providers[provider] = providers.get(provider, 0) + 1

                # モデルタイプ集計（アノテーション専用）
                model_type = model["model_type"]
                model_types[model_type] = model_types.get(model_type, 0) + 1

                # APIキー要件・ローカルモデル集計
                if model["requires_api_key"]:
                    api_key_required += 1
                else:
                    local_models += 1

            return {
                "total_models": len(models),
                "providers": providers,
                "model_types": model_types,  # vision, score, tagger のみ
                "api_key_required": api_key_required,
                "local_models": local_models,
            }

        except Exception as e:
            logger.error(f"ライブラリモデルサマリー取得エラー: {e}")
            return {}

    def validate_annotation_model_type(self, model_type: str) -> bool:
        """アノテーションモデルタイプの妥当性検証

        Args:
            model_type: 検証するモデルタイプ

        Returns:
            bool: image-annotator-libの責務範囲内かどうか
        """
        valid_types = {"vision", "score", "tagger"}
        return model_type in valid_types
