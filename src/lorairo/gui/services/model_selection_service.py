# src/lorairo/gui/services/model_selection_service.py

from dataclasses import dataclass
from typing import Any, overload

from ...services.annotator_lib_adapter import AnnotatorLibAdapter
from ...services.model_registry_protocol import (
    ModelInfo as ProtocolModelInfo,
)
from ...services.model_registry_protocol import (
    ModelRegistryServiceProtocol,
    NullModelRegistry,
    map_annotator_metadata_to_model_info,
)
from ...utils.log import logger


@dataclass
class ModelInfo:
    """モデル情報データクラス（後方互換性維持版）"""

    name: str
    provider: str
    capabilities: list[str]  # ["caption", "tags", "scores"] - 実際の機能（ModelTypeと一致）
    api_model_id: str | None
    requires_api_key: bool
    estimated_size_gb: float | None
    is_recommended: bool = False


@dataclass
class ModelSelectionCriteria:
    """モデル選択条件データクラス"""

    provider: str | None = None
    capabilities: list[str] | None = None
    only_recommended: bool = False
    only_available: bool = True


class ModelSelectionService:
    """
    モデル選択に関するビジネスロジックを処理するサービス（現代化版）

    責任:
    - ModelRegistryServiceProtocol経由でのモデル情報取得
    - モデル情報のフィルタリング・推奨判定ロジック
    - 選択状態の管理は行わない（UI側で管理）
    - 後方互換性維持（AnnotatorLibAdapter support）
    """

    def __init__(self, annotator_adapter: AnnotatorLibAdapter | None = None):
        """Initialize ModelSelectionService with backward compatibility.

        Legacy signature: ModelSelectionService(annotator_adapter)
        New approach: Use create() class method for modern initialization
        """
        self.model_registry: ModelRegistryServiceProtocol = NullModelRegistry()
        self.annotator_adapter = annotator_adapter
        self._all_models: list[ModelInfo] = []
        self._cached_models: list[ModelInfo] | None = None

    @classmethod
    def create(
        cls,
        model_registry: ModelRegistryServiceProtocol | None = None,
        annotator_adapter: AnnotatorLibAdapter | None = None,
    ) -> "ModelSelectionService":
        """Create ModelSelectionService with modern protocol-based approach."""
        instance = cls.__new__(cls)
        instance.model_registry = model_registry or NullModelRegistry()
        instance.annotator_adapter = annotator_adapter
        instance._all_models = []
        instance._cached_models = None
        return instance

    def load_models(self) -> list[ModelInfo]:
        """モデル情報を取得・変換（Protocol-based + backward compatibility）"""
        try:
            # キャッシュがあれば返す（パフォーマンス最適化）
            if self._cached_models is not None:
                return self._cached_models

            # Protocol-based approach (preferred)
            try:
                protocol_models = self.model_registry.get_available_models()
                if protocol_models:
                    # Protocol ModelInfo を 後方互換性 ModelInfo に変換
                    compat_models = [self._convert_protocol_to_compat(model) for model in protocol_models]
                    self._all_models = compat_models
                    self._cached_models = compat_models
                    logger.info(f"Loaded {len(compat_models)} models from ModelRegistry")
                    return compat_models
            except Exception as e:
                logger.warning(f"ModelRegistry load failed, trying fallback: {e}")

            # Backward compatibility fallback
            if self.annotator_adapter:
                return self._load_models_legacy()

            logger.warning("No model source available")
            return []

        except Exception as e:
            logger.error(f"Failed to load models: {e}")
            return []

    def _load_models_legacy(self) -> list[ModelInfo]:
        """レガシーAnnotatorLibAdapter経由でのモデル読み込み"""
        try:
            if not self.annotator_adapter:
                logger.warning("AnnotatorLibAdapter not available for legacy loading")
                return []

            # モデル情報取得
            models_metadata = self.annotator_adapter.get_available_models_with_metadata()

            # Protocol準拠のModelInfoに変換
            protocol_models = map_annotator_metadata_to_model_info(models_metadata)

            # Protocol ModelInfo を 後方互換性 ModelInfo に変換
            compat_models = [self._convert_protocol_to_compat(model) for model in protocol_models]

            self._all_models = compat_models
            self._cached_models = compat_models
            logger.info(f"Loaded {len(compat_models)} models from AnnotatorLibAdapter (legacy)")
            return compat_models

        except Exception as e:
            logger.error(f"Legacy model loading failed: {e}")
            return []

    def _convert_protocol_to_compat(self, protocol_model: ProtocolModelInfo) -> ModelInfo:
        """Protocol ModelInfo を 後方互換性 ModelInfo に変換"""
        return ModelInfo(
            name=protocol_model.name,
            provider=protocol_model.provider,
            capabilities=protocol_model.capabilities,
            api_model_id=protocol_model.api_model_id,
            requires_api_key=protocol_model.requires_api_key,
            estimated_size_gb=protocol_model.estimated_size_gb,
            is_recommended=self._is_recommended_model(protocol_model.name),
        )

    def refresh_models(self) -> list[ModelInfo]:
        """モデルキャッシュをクリアして再読み込み"""
        self._cached_models = None
        self._all_models = []
        return self.load_models()

    def get_all_models(self) -> list[ModelInfo]:
        """すべてのモデル情報を取得"""
        return self._all_models.copy()

    def get_recommended_models(self) -> list[ModelInfo]:
        """推奨モデルのみを取得"""
        return [m for m in self._all_models if self._is_recommended_model(m.name)]

    def filter_models(
        self,
        criteria: ModelSelectionCriteria | None = None,
        # Legacy parameters for backward compatibility
        provider: str | None = None,
        capabilities: list[str] | None = None,
    ) -> list[ModelInfo]:
        """指定した条件でモデルをフィルタリング（現代化版 + 後方互換性）"""

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
            filtered = [m for m in filtered if m.provider.lower() == criteria.provider.lower()]

        # 機能フィルタ
        if criteria.capabilities:
            filtered = [m for m in filtered if any(cap in m.capabilities for cap in criteria.capabilities)]

        # 推奨フィルタ
        if criteria.only_recommended:
            filtered = [m for m in filtered if self._is_recommended_model(m.name)]

        # 利用可能フィルタ（API keyチェックなど）
        if criteria.only_available:
            filtered = [m for m in filtered if self._is_model_available(m)]

        return filtered

    def _is_model_available(self, model: ModelInfo) -> bool:
        """モデルが利用可能かチェック（API keyなど）"""
        # APIキーが必要なモデルの場合、設定チェックが必要
        # 今回は簡易実装として常にTrue
        return True

    def group_models_by_provider(self, models: list[ModelInfo]) -> dict[str, list[ModelInfo]]:
        """プロバイダー別にモデルをグループ化"""
        groups: dict[str, list[ModelInfo]] = {}
        for model in models:
            provider = model.provider or "local"
            if provider not in groups:
                groups[provider] = []
            groups[provider].append(model)
        return groups

    def create_model_tooltip(self, model: ModelInfo) -> str:
        """モデル用ツールチップを作成"""
        tooltip_parts = [f"プロバイダー: {model.provider}", f"機能: {', '.join(model.capabilities)}"]

        if model.api_model_id:
            tooltip_parts.append(f"API ID: {model.api_model_id}")

        if model.estimated_size_gb:
            tooltip_parts.append(f"サイズ: {model.estimated_size_gb:.1f}GB")

        tooltip_parts.append(f"APIキー必要: {'Yes' if model.requires_api_key else 'No'}")

        return "\n".join(tooltip_parts)

    def create_model_display_name(self, model: ModelInfo) -> str:
        """モデルの表示名を作成"""
        display_name = model.name
        if model.requires_api_key:
            display_name += " (API)"
        if model.estimated_size_gb:
            display_name += f" ({model.estimated_size_gb:.1f}GB)"
        return display_name

    # Legacy capability inference (移行期間中は保持)
    def _infer_capabilities_legacy(self, model_data: dict[str, Any]) -> list[str]:
        """モデルタイプから機能をマッピング（レガシー版）"""
        model_type = model_data.get("model_type", "")

        # DBのmodel_typeカラムから機能をマッピング
        type_mapping = {
            "multimodal": ["caption", "tags"],  # "tag" → "tags" に統一
            "caption": ["caption"],
            "tag": ["tags"],
            "score": ["scores"],
        }

        return type_mapping.get(model_type, ["caption"])

    # Backward compatibility alias for tests
    def _infer_capabilities(self, model_data: dict[str, Any]) -> list[str]:
        """Backward compatibility wrapper for _infer_capabilities_legacy"""
        return self._infer_capabilities_legacy(model_data)

    def _is_recommended_model(self, model_name: str) -> bool:
        """推奨モデルかどうか判定"""
        name_lower = model_name.lower()

        # 高品質Caption生成モデル
        caption_recommended = ["gpt-4o", "claude-3-5-sonnet", "claude-3-sonnet", "gemini-pro"]

        # 高精度タグ生成モデル
        tags_recommended = ["wd-v1-4", "wd-tagger", "deepdanbooru", "wd-swinv2"]

        # 品質評価モデル
        scores_recommended = ["clip-aesthetic", "musiq", "aesthetic-scorer"]

        all_recommended = caption_recommended + tags_recommended + scores_recommended

        return any(rec in name_lower for rec in all_recommended)
