"""ライブラリとLoRAIro DB間のモデル同期サービス

image-annotator-lib の型安全 API (`list_annotator_info()` + `get_model_extras()`) を
DI 経由で受け取り、LoRAIro DB に同期する。
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any, ClassVar, Protocol, TypedDict

from image_annotator_lib import AnnotatorInfo
from image_annotator_lib.core.types import TaskCapability

from ..annotations.annotator_metadata import AnnotatorExtras
from ..database.db_repository import ImageRepository
from ..services.configuration_service import ConfigurationService
from ..utils.log import logger


class ModelMetadata(TypedDict):
    """モデルメタデータの型定義 (sync_service 内部表現)"""

    name: str
    provider: str | None
    class_name: str | None
    api_model_id: str | None
    model_type: str  # AnnotatorInfo.model_type ("tagger"/"scorer"/"captioner"/"vision")
    model_types: list[str]  # LoRAIro DB の model_types (マッピング後)
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
    """アノテーターライブラリのプロトコル定義（DI用）

    Issue #225: 型安全 API への migration 完了。
    `AnnotatorLibraryAdapter` または `MockAnnotatorLibrary` が実装する。
    """

    def list_annotator_info(self) -> list[AnnotatorInfo]:
        """利用可能アノテーターの型安全メタデータ一覧を返す"""
        ...

    def get_model_extras(self, name: str) -> AnnotatorExtras:
        """指定モデルの追加メタデータ (config_registry 由来) を返す"""
        ...


def _empty_extras() -> AnnotatorExtras:
    """全フィールド None の `AnnotatorExtras` を返す。"""
    return AnnotatorExtras(
        provider=None,
        class_name=None,
        api_model_id=None,
        estimated_size_gb=None,
        discontinued_at=None,
        max_output_tokens=None,
    )


class MockAnnotatorLibrary:
    """テスト/開発用のモックライブラリ実装。

    `AnnotatorLibraryProtocol` を満たし、5モデル分の固定データを返す。
    """

    _MODELS: ClassVar[tuple[AnnotatorInfo, ...]] = (
        AnnotatorInfo(
            name="gpt-4o",
            model_type="vision",
            capabilities=frozenset({TaskCapability.TAGS, TaskCapability.CAPTIONS}),
            is_local=False,
            is_api=True,
            device=None,
        ),
        AnnotatorInfo(
            name="claude-3-5-sonnet",
            model_type="vision",
            capabilities=frozenset({TaskCapability.TAGS, TaskCapability.CAPTIONS}),
            is_local=False,
            is_api=True,
            device=None,
        ),
        AnnotatorInfo(
            name="gemini-1.5-pro",
            model_type="vision",
            capabilities=frozenset({TaskCapability.TAGS, TaskCapability.CAPTIONS}),
            is_local=False,
            is_api=True,
            device=None,
        ),
        AnnotatorInfo(
            name="wd-v1-4-swinv2-tagger",
            model_type="tagger",
            capabilities=frozenset({TaskCapability.TAGS}),
            is_local=True,
            is_api=False,
            device="cuda",
        ),
        AnnotatorInfo(
            name="aesthetic-predictor",
            model_type="scorer",
            capabilities=frozenset({TaskCapability.SCORES}),
            is_local=True,
            is_api=False,
            device="cuda",
        ),
    )

    _EXTRAS: ClassVar[dict[str, AnnotatorExtras]] = {
        "gpt-4o": AnnotatorExtras(
            provider="openai",
            class_name="PydanticAIWebAPIAnnotator",
            api_model_id="gpt-4o",
            estimated_size_gb=None,
            discontinued_at=None,
            max_output_tokens=1800,
        ),
        "claude-3-5-sonnet": AnnotatorExtras(
            provider="anthropic",
            class_name="PydanticAIWebAPIAnnotator",
            api_model_id="claude-3-5-sonnet-20241022",
            estimated_size_gb=None,
            discontinued_at=None,
            max_output_tokens=1800,
        ),
        "gemini-1.5-pro": AnnotatorExtras(
            provider="google",
            class_name="PydanticAIWebAPIAnnotator",
            api_model_id="gemini-1.5-pro",
            estimated_size_gb=None,
            discontinued_at=None,
            max_output_tokens=1800,
        ),
        "wd-v1-4-swinv2-tagger": AnnotatorExtras(
            provider=None,
            class_name="WDTagger",
            api_model_id=None,
            estimated_size_gb=1.2,
            discontinued_at=None,
            max_output_tokens=None,
        ),
        "aesthetic-predictor": AnnotatorExtras(
            provider=None,
            class_name="AestheticPredictor",
            api_model_id=None,
            estimated_size_gb=0.8,
            discontinued_at=None,
            max_output_tokens=None,
        ),
    }

    def list_annotator_info(self) -> list[AnnotatorInfo]:
        """モックの AnnotatorInfo 一覧"""
        logger.debug("モックライブラリから AnnotatorInfo 一覧を取得")
        return list(self._MODELS)

    def get_model_extras(self, name: str) -> AnnotatorExtras:
        """モックの extras (未登録モデルは全 None)"""
        logger.debug(f"モックライブラリから {name} の extras を取得")
        return self._EXTRAS.get(name, _empty_extras())


class ModelSyncService:
    """ライブラリとLoRAIro DB間のモデル同期サービス

    image-annotator-lib が管理するアノテーション専用モデル (vision/scorer/tagger/
    captioner) を LoRAIro DB に同期する。upscaler 等の LoRAIro 独自機能は対象外。
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

        adapter_type = type(self.annotator_library).__name__
        if adapter_type == "MockAnnotatorLibrary":
            logger.info(f"ModelSyncService初期化完了（Mock実装 - {adapter_type}）")
        else:
            logger.info(f"ModelSyncService初期化完了（Protocol-based実装 - {adapter_type}）")

    def _map_library_model_type_to_db(self, info: AnnotatorInfo) -> list[str]:
        """`AnnotatorInfo.model_type` を LoRAIro DB の `model_types` リストに変換する。

        Args:
            info: アノテーター情報

        Returns:
            list[str]: LoRAIro DB の model_types リスト

        Mapping Rules:
            - "vision" → ["captioner"] (`info.is_api=True` の場合は ["llm", "captioner"])
            - "captioner" → ["captioner"]
            - "scorer" → ["score"]
            - "tagger" → ["tagger"]
            - その他 → ["captioner"] (警告ログ付き)
        """
        model_type = info.model_type
        if model_type == "vision":
            # WebAPI vision モデル (PydanticAI 経由) は LLM としても機能する
            return ["llm", "captioner"] if info.is_api else ["captioner"]
        if model_type == "captioner":
            return ["captioner"]
        if model_type == "scorer":
            return ["score"]
        if model_type == "tagger":
            return ["tagger"]
        logger.warning(f"Unknown library model_type: {model_type}, defaulting to ['captioner']")
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

        `list_annotator_info()` で取得した AnnotatorInfo と、各モデルに対する
        `get_model_extras()` を組み合わせて `ModelMetadata` を構築する。

        Returns:
            list[ModelMetadata]: アノテーション専用モデルメタデータのリスト
        """
        logger.debug("image-annotator-libからモデルメタデータを取得します")

        try:
            infos = self.annotator_library.list_annotator_info()

            models_metadata: list[ModelMetadata] = []
            for info in infos:
                extras = self.annotator_library.get_model_extras(info.name)
                db_model_types = self._map_library_model_type_to_db(info)

                # API モデルで provider 不明 (config_registry 未登録の PydanticAI 直接モデル等)
                # は "unknown" にフォールバック。ローカルモデルは provider=None のままにし
                # 既存の「provider=None → local」解釈 (model_selection_service の
                # exclude_local / "provider or 'local'") を維持する。
                provider = extras.provider or ("unknown" if info.is_api else None)

                metadata: ModelMetadata = {
                    "name": info.name,
                    "provider": provider,
                    "class_name": extras.class_name,
                    "api_model_id": extras.api_model_id,
                    "model_type": info.model_type,
                    "model_types": db_model_types,
                    "estimated_size_gb": extras.estimated_size_gb,
                    "requires_api_key": info.is_api,
                    "discontinued_at": extras.discontinued_at,
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
                existing_model = self.db_repository.get_model_by_name(model_metadata["name"])

                if existing_model is None:
                    logger.debug(f"新規アノテーションモデルを登録: {model_metadata['name']}")

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
                existing_model = self.db_repository.get_model_by_name(model_metadata["name"])

                if existing_model is not None:
                    logger.debug(f"既存アノテーションモデルの更新チェック: {model_metadata['name']}")

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

            providers: dict[str, int] = {}
            model_types: dict[str, int] = {}
            api_key_required = 0
            local_models = 0

            for model in models:
                provider = model["provider"] or "local"
                providers[provider] = providers.get(provider, 0) + 1

                model_type = model["model_type"]
                model_types[model_type] = model_types.get(model_type, 0) + 1

                if model["requires_api_key"]:
                    api_key_required += 1
                else:
                    local_models += 1

            return {
                "total_models": len(models),
                "providers": providers,
                "model_types": model_types,
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
            bool: image-annotator-lib の `AnnotatorInfo.model_type` Literal 値かどうか
        """
        valid_types = {"vision", "scorer", "tagger", "captioner"}
        return model_type in valid_types
