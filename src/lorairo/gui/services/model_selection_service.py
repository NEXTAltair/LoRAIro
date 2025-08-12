# src/lorairo/gui/services/model_selection_service.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import Mock

from ...database.db_repository import ImageRepository
from ...database.schema import Model
from ...services.model_info_manager import ModelInfo, ModelInfoManager
from ...utils.log import logger

# ModelInfo dataclass 削除 - DB Modelを直接使用


@dataclass
class ModelSelectionCriteria:
    """モデル選択条件データクラス"""

    provider: str | None = None
    capabilities: list[str] | None = None
    only_recommended: bool = False
    only_available: bool = True


class ModelSelectionService:
    """
    モデル選択に関するビジネスロジックを処理するサービス（DB中心アプローチ）

    責任:
    - DB経由でのモデル情報取得（直接利用）
    - モデル情報のフィルタリング・推奨判定ロジック
    - 選択状態の管理は行わない（UI側で管理）
    """

    def __init__(
        self, model_manager: ModelInfoManager | None = None, db_repository: ImageRepository | None = None
    ):
        """Initialize ModelSelectionService with DB-centric approach."""
        # 注入がない場合は一時的に空のマネージャーを使用（後で修正）
        self.model_manager = model_manager
        self.db_repository = db_repository
        self._all_models: list[Model] = []
        self._cached_models: list[Model] | None = None

    @classmethod
    def create(
        cls,
        model_manager: ModelInfoManager | None = None,
        db_repository: ImageRepository | None = None,
    ) -> ModelSelectionService:
        """Create ModelSelectionService with DB-centric approach."""
        return cls(model_manager=model_manager, db_repository=db_repository)

    def load_models(self) -> list[Model]:
        """モデル情報をDBから直接取得（DB-centric implementation）"""
        try:
            # キャッシュがあれば返す（パフォーマンス最適化）
            if self._cached_models is not None:
                return self._cached_models

            # DBから直接取得（簡素化）
            if self.db_repository:
                # DBからdict形式で取得してModelオブジェクトに変換
                db_model_dicts = self.db_repository.get_models()
                db_models = self._convert_db_dicts_to_models(db_model_dicts)
            elif self.model_manager:
                # ModelInfoManager経由でTypedDictを取得して変換
                model_infos = self.model_manager.get_available_models()
                db_models = self._convert_model_infos_to_models(model_infos)
            else:
                # 一時的フォールバック（空リスト）
                db_models = []

            self._all_models = db_models
            self._cached_models = db_models
            logger.info(f"Loaded {len(db_models)} models from DB")
            return db_models

        except Exception as e:
            logger.error(f"Failed to load models from DB: {e}")
            return []

    # _convert_protocol_to_compat メソッド削除 - DB Modelを直接使用するため不要

    def refresh_models(self) -> list[Model]:
        """モデルキャッシュをクリアして再読み込み"""
        self._cached_models = None
        self._all_models = []
        return self.load_models()

    def get_all_models(self) -> list[Model]:
        """すべてのモデル情報を取得"""
        return self._all_models.copy()

    def get_recommended_models(self) -> list[Model]:
        """推奨モデルのみを取得（DB Modelプロパティ使用）"""
        return [m for m in self._all_models if m.is_recommended]

    def filter_models(
        self,
        criteria: ModelSelectionCriteria | None = None,
        # Legacy parameters for backward compatibility
        provider: str | None = None,
        capabilities: list[str] | None = None,
    ) -> list[Model]:
        """指定した条件でモデルをフィルタリング（DB Model直接使用）"""

        # 後方互換性: 旧シグネチャ (provider, capabilities) の処理
        if criteria is None and (provider is not None or capabilities is not None):
            criteria = ModelSelectionCriteria(
                provider=provider,
                capabilities=capabilities,
            )
        elif criteria is None:
            criteria = ModelSelectionCriteria()

        filtered = self._all_models

        # プロバイダーフィルタ
        if criteria.provider and criteria.provider != "すべて":
            filtered = [
                m for m in filtered if m.provider and m.provider.lower() == criteria.provider.lower()
            ]

        # 機能フィルタ
        if criteria.capabilities:
            filtered = [m for m in filtered if any(cap in m.capabilities for cap in criteria.capabilities)]

        # 推奨フィルタ（DB Modelプロパティ使用）
        if criteria.only_recommended:
            filtered = [m for m in filtered if m.is_recommended]

        # 利用可能フィルタ（DB Modelプロパティ使用）
        if criteria.only_available:
            filtered = [m for m in filtered if m.available]

        return filtered

    # _is_model_available メソッド削除 - DB Model.available プロパティを使用

    def group_models_by_provider(self, models: list[Model]) -> dict[str, list[Model]]:
        """プロバイダー別にモデルをグループ化（DB Model使用）"""
        groups: dict[str, list[Model]] = {}
        for model in models:
            provider = model.provider or "local"
            if provider not in groups:
                groups[provider] = []
            groups[provider].append(model)
        return groups

    def _convert_model_infos_to_models(self, model_infos: list[ModelInfo]) -> list[Model]:
        """モデル情報TypedDictをDB Modelオブジェクトに変換（Cプランブリッジ）

        Args:
            model_infos: ModelInfoManagerからのTypedDict形式のモデル情報

        Returns:
            list[Model]: DB Modelオブジェクトのリスト
        """
        converted_models: list[Model] = []

        for model_info in model_infos:
            try:
                # Mock Modelオブジェクトを作成（Cプランのブリッジ実装）
                mock_model = Mock(spec=Model)
                mock_model.id = model_info.get("id")
                mock_model.name = model_info["name"]
                mock_model.provider = model_info.get("provider")
                mock_model.api_model_id = model_info.get("api_model_id")
                mock_model.requires_api_key = model_info.get("requires_api_key", False)
                mock_model.estimated_size_gb = model_info.get("estimated_size_gb")
                mock_model.discontinued_at = model_info.get("discontinued_at")

                # UIプロパティの設定
                mock_model.available = model_info.get("available", True)
                # model_typeをcapabilitiesに変換
                model_type = model_info.get("model_type", "")
                if model_type == "vision":
                    mock_model.capabilities = ["caption"]
                elif model_type == "tagger":
                    mock_model.capabilities = ["tags"]
                elif model_type == "score":
                    mock_model.capabilities = ["scores"]
                else:
                    mock_model.capabilities = ["caption"]  # デフォルト

                # is_recommendedプロパティの計算
                name_lower = mock_model.name.lower() if mock_model.name else ""
                caption_recommended = ["gpt-4o", "claude-3-5-sonnet", "claude-3-sonnet", "gemini-pro"]
                tags_recommended = ["wd-v1-4", "wd-tagger", "deepdanbooru", "wd-swinv2"]
                scores_recommended = ["clip-aesthetic", "musiq", "aesthetic-scorer"]
                all_recommended = caption_recommended + tags_recommended + scores_recommended
                mock_model.is_recommended = any(rec in name_lower for rec in all_recommended)

                converted_models.append(mock_model)

            except Exception as e:
                logger.warning(
                    f"Failed to convert model info to Model object for {model_info.get('name', 'unknown')}: {e}"
                )
                continue

        logger.debug(f"Converted {len(converted_models)} ModelInfo objects to Model objects")
        return converted_models

    def _convert_db_dicts_to_models(self, db_dicts: list[dict[str, Any]]) -> list[Model]:
        """データベース辞書形式をDB Modelオブジェクトに変換（Cプランブリッジ）

        Args:
            db_dicts: DBからの辞書形式のモデル情報

        Returns:
            list[Model]: DB Modelオブジェクトのリスト
        """
        converted_models: list[Model] = []

        for db_dict in db_dicts:
            try:
                # Mock Modelオブジェクトを作成（Cプランのブリッジ実装）
                mock_model = Mock(spec=Model)
                mock_model.id = db_dict.get("id")
                mock_model.name = db_dict.get("name", "")
                mock_model.provider = db_dict.get("provider")
                mock_model.discontinued_at = db_dict.get("discontinued_at")
                mock_model.created_at = db_dict.get("created_at")
                mock_model.updated_at = db_dict.get("updated_at")

                # model_typesをcapabilitiesに変換
                model_types = db_dict.get("model_types", [])
                mock_model.capabilities = model_types

                # UIプロパティの設定
                mock_model.available = mock_model.discontinued_at is None

                # is_recommendedプロパティの計算
                name_lower = mock_model.name.lower() if mock_model.name else ""
                caption_recommended = ["gpt-4o", "claude-3-5-sonnet", "claude-3-sonnet", "gemini-pro"]
                tags_recommended = ["wd-v1-4", "wd-tagger", "deepdanbooru", "wd-swinv2"]
                scores_recommended = ["clip-aesthetic", "musiq", "aesthetic-scorer"]
                all_recommended = caption_recommended + tags_recommended + scores_recommended
                mock_model.is_recommended = any(rec in name_lower for rec in all_recommended)

                # その他のフィールドはデフォルト値
                mock_model.api_model_id = None
                mock_model.requires_api_key = False
                mock_model.estimated_size_gb = None

                converted_models.append(mock_model)

            except Exception as e:
                logger.warning(
                    f"Failed to convert db dict to Model object for {db_dict.get('name', 'unknown')}: {e}"
                )
                continue

        logger.debug(f"Converted {len(converted_models)} DB dict objects to Model objects")
        return converted_models

    # create_model_tooltip メソッド削除 - Widgetに移動

    # create_model_display_name メソッド削除 - Widgetに移動

    # _is_recommended_model メソッド削除 - DB Model.is_recommended プロパティを使用
