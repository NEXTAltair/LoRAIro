"""アノテーション用モデル情報管理サービス

HybridAnnotationController向けのモデル情報取得・フィルタリング機能を提供。
ModelSyncServiceと連携してライブラリとDB間のモデル情報を統合管理。
"""

import datetime
from dataclasses import dataclass
from typing import Any, TypedDict

from ..database.db_repository import ImageRepository
from ..services.configuration_service import ConfigurationService
from ..services.model_sync_service import AnnotatorLibraryProtocol, ModelSyncService
from ..utils.log import logger


class ModelInfo(TypedDict):
    """UI表示用モデル情報の型定義"""

    id: int | None  # DBに登録済みの場合のID、未登録の場合はNone
    name: str
    provider: str | None
    model_type: str  # "vision", "score", "tagger"
    requires_api_key: bool
    estimated_size_gb: float | None
    api_model_id: str | None
    discontinued_at: datetime.datetime | None
    available: bool  # APIキー設定状況等を考慮した利用可能性


@dataclass
class ModelFilterCriteria:
    """モデルフィルタリング条件"""

    model_types: list[str] | None = None  # フィルター対象のモデルタイプ
    providers: list[str] | None = None  # フィルター対象のプロバイダー
    requires_api_key: bool | None = None  # APIキー要件でフィルター
    only_available: bool = True  # 利用可能なモデルのみ表示


class ModelInfoManager:
    """アノテーション用モデル情報管理サービス

    HybridAnnotationController向けに以下の機能を提供:
    - ライブラリ + DB統合モデル情報取得
    - モデル利用可能性判定（APIキー設定状況等）
    - フィルタリング機能（プロバイダー、モデルタイプ別）
    - 表示用モデル情報の提供
    """

    def __init__(
        self,
        db_repository: ImageRepository,
        config_service: ConfigurationService,
        model_sync_service: ModelSyncService | None = None,
        annotator_library: AnnotatorLibraryProtocol | None = None,
    ):
        """ModelInfoManager初期化

        Args:
            db_repository: 画像データベースリポジトリ
            config_service: 設定サービス
            model_sync_service: モデル同期サービス（オプション）
            annotator_library: アノテーターライブラリアダプター（オプション）
        """
        self.db_repository = db_repository
        self.config_service = config_service

        # ModelSyncServiceの初期化（DI or 自動生成）
        if model_sync_service is not None:
            self.model_sync_service = model_sync_service
        else:
            self.model_sync_service = ModelSyncService(
                db_repository=db_repository,
                config_service=config_service,
                annotator_library=annotator_library,
            )

        logger.info("ModelInfoManager初期化完了")

    def get_available_models(self, filter_criteria: ModelFilterCriteria | None = None) -> list[ModelInfo]:
        """利用可能なアノテーションモデル一覧を取得

        ライブラリからの最新情報とDB情報を統合し、
        APIキー設定状況等を考慮した利用可能性を判定。

        Args:
            filter_criteria: フィルタリング条件

        Returns:
            list[ModelInfo]: フィルタリング済みモデル情報リスト
        """
        logger.debug("利用可能なアノテーションモデル一覧を取得します")

        try:
            # 1. ライブラリから最新のモデル情報を取得
            library_models = self.model_sync_service.get_model_metadata_from_library()

            # 2. DB情報と照合・統合してModelInfo形式に変換
            model_infos = self._convert_to_model_info_list(library_models)

            # 3. フィルタリング適用
            if filter_criteria:
                model_infos = self._apply_filters(model_infos, filter_criteria)

            logger.debug(f"アノテーションモデル情報取得完了: {len(model_infos)}件")
            return model_infos

        except Exception as e:
            logger.error(f"アノテーションモデル情報取得中にエラー: {e}", exc_info=True)
            return []

    def get_models_by_type(self, model_type: str) -> list[ModelInfo]:
        """指定タイプのモデル一覧を取得

        Args:
            model_type: モデルタイプ ("vision", "score", "tagger")

        Returns:
            list[ModelInfo]: 指定タイプのモデル情報リスト
        """
        filter_criteria = ModelFilterCriteria(model_types=[model_type], only_available=True)
        return self.get_available_models(filter_criteria)

    def get_providers_list(self) -> list[str]:
        """利用可能なプロバイダー一覧を取得

        Returns:
            list[str]: プロバイダー名リスト（ローカルは"local"として扱う）
        """
        try:
            models = self.get_available_models()
            providers = set()

            for model in models:
                provider = model["provider"] or "local"
                providers.add(provider)

            return sorted(list(providers))

        except Exception as e:
            logger.error(f"プロバイダー一覧取得エラー: {e}")
            return []

    def get_model_types_list(self) -> list[str]:
        """利用可能なモデルタイプ一覧を取得

        Returns:
            list[str]: モデルタイプリスト（アノテーション専用）
        """
        try:
            models = self.get_available_models()
            model_types = set()

            for model in models:
                model_types.add(model["model_type"])

            return sorted(list(model_types))

        except Exception as e:
            logger.error(f"モデルタイプ一覧取得エラー: {e}")
            return []

    def check_model_availability(self, model_name: str) -> bool:
        """指定モデルの利用可能性をチェック

        Args:
            model_name: チェック対象モデル名

        Returns:
            bool: 利用可能かどうか
        """
        try:
            models = self.get_available_models()

            for model in models:
                if model["name"] == model_name:
                    return model["available"]

            return False

        except Exception as e:
            logger.error(f"モデル利用可能性チェックエラー ({model_name}): {e}")
            return False

    def get_model_summary_stats(self) -> dict[str, Any]:
        """モデル統計情報を取得

        Returns:
            dict[str, Any]: 統計情報（プロバイダー別、タイプ別等）
        """
        try:
            models = self.get_available_models()

            stats = {
                "total_models": len(models),
                "available_models": len([m for m in models if m["available"]]),
                "providers": {},
                "model_types": {},
                "api_key_required": 0,
                "local_models": 0,
            }

            for model in models:
                # プロバイダー別集計
                provider = model["provider"] or "local"
                stats["providers"][provider] = stats["providers"].get(provider, 0) + 1

                # モデルタイプ別集計
                model_type = model["model_type"]
                stats["model_types"][model_type] = stats["model_types"].get(model_type, 0) + 1

                # APIキー・ローカルモデル集計
                if model["requires_api_key"]:
                    stats["api_key_required"] += 1
                else:
                    stats["local_models"] += 1

            return stats

        except Exception as e:
            logger.error(f"モデル統計情報取得エラー: {e}")
            return {}

    def _convert_to_model_info_list(self, library_models: list[dict[str, Any]]) -> list[ModelInfo]:
        """ライブラリモデル情報をModelInfo形式に変換

        Args:
            library_models: ライブラリから取得したモデル情報

        Returns:
            list[ModelInfo]: ModelInfo形式のモデル情報リスト
        """
        model_infos: list[ModelInfo] = []

        for library_model in library_models:
            try:
                # DB情報との照合（Phase 4で実装）
                db_model_id = self._get_db_model_id(library_model["name"])

                # 利用可能性判定
                availability = self._check_model_availability(library_model)

                model_info: ModelInfo = {
                    "id": db_model_id,
                    "name": library_model["name"],
                    "provider": library_model.get("provider"),
                    "model_type": library_model.get("model_type", "unknown"),
                    "requires_api_key": library_model.get("requires_api_key", False),
                    "estimated_size_gb": library_model.get("estimated_size_gb"),
                    "api_model_id": library_model.get("api_model_id"),
                    "discontinued_at": library_model.get("discontinued_at"),
                    "available": availability,
                }

                model_infos.append(model_info)

            except Exception as e:
                logger.warning(f"モデル情報変換エラー ({library_model.get('name', 'unknown')}): {e}")
                continue

        return model_infos

    def _get_db_model_id(self, model_name: str) -> int | None:
        """DB登録済みモデルのIDを取得

        Args:
            model_name: モデル名

        Returns:
            int | None: DB内のモデルID（未登録の場合はNone）
        """
        try:
            return self.db_repository._get_model_id(model_name)
        except Exception as e:
            logger.debug(f"DBモデルID取得エラー ({model_name}): {e}")
            return None

    def _check_model_availability(self, library_model: dict[str, Any]) -> bool:
        """モデルの利用可能性を判定

        APIキー要件と設定状況を照合して利用可能性を判定。

        Args:
            library_model: ライブラリから取得したモデル情報

        Returns:
            bool: 利用可能かどうか
        """
        try:
            # APIキーが不要なローカルモデルの場合
            if not library_model.get("requires_api_key", False):
                return True

            # APIキーが必要な場合、プロバイダー別に設定をチェック
            provider = library_model.get("provider")
            if not provider:
                return False

            # 設定サービスからAPIキー設定をチェック
            config = self.config_service.get_config()
            api_config = config.get("api", {})

            api_key_mapping = {
                "openai": api_config.get("openai_key"),
                "anthropic": api_config.get("claude_key"),
                "google": api_config.get("google_key"),
            }

            api_key = api_key_mapping.get(provider)
            return bool(api_key and api_key.strip())

        except Exception as e:
            logger.debug(f"モデル利用可能性判定エラー ({library_model.get('name', 'unknown')}): {e}")
            return False

    def _apply_filters(
        self, model_infos: list[ModelInfo], filter_criteria: ModelFilterCriteria
    ) -> list[ModelInfo]:
        """フィルタリング条件を適用

        Args:
            model_infos: フィルタリング対象モデル情報リスト
            filter_criteria: フィルタリング条件

        Returns:
            list[ModelInfo]: フィルタリング済みモデル情報リスト
        """
        filtered_models = model_infos.copy()

        # 利用可能性フィルター
        if filter_criteria.only_available:
            filtered_models = [m for m in filtered_models if m["available"]]

        # モデルタイプフィルター
        if filter_criteria.model_types:
            filtered_models = [m for m in filtered_models if m["model_type"] in filter_criteria.model_types]

        # プロバイダーフィルター
        if filter_criteria.providers:
            filtered_models = [
                m for m in filtered_models if (m["provider"] or "local") in filter_criteria.providers
            ]

        # APIキー要件フィルター
        if filter_criteria.requires_api_key is not None:
            filtered_models = [
                m for m in filtered_models if m["requires_api_key"] == filter_criteria.requires_api_key
            ]

        return filtered_models
