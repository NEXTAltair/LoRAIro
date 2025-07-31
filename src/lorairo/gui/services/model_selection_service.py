# src/lorairo/gui/services/model_selection_service.py

from dataclasses import dataclass
from typing import Any

from ...services.annotator_lib_adapter import AnnotatorLibAdapter
from ...utils.log import logger


@dataclass
class ModelInfo:
    """モデル情報データクラス"""

    name: str
    provider: str
    capabilities: list[str]  # ["caption", "tags", "scores"] - 実際の機能（ModelTypeと一致）
    api_model_id: str | None
    requires_api_key: bool
    estimated_size_gb: float | None
    is_recommended: bool = False


class ModelSelectionService:
    """
    モデル選択に関するビジネスロジックを処理するサービス

    責任:
    - AnnotatorLibAdapterからのモデル情報取得
    - モデル情報の変換・加工
    - フィルタリング・推奨判定ロジック
    - 選択状態の管理は行わない（UI側で管理）
    """

    def __init__(self, annotator_adapter: AnnotatorLibAdapter | None = None):
        self.annotator_adapter = annotator_adapter
        self._all_models: list[ModelInfo] = []

    def load_models(self) -> list[ModelInfo]:
        """モデル情報をAnnotatorLibAdapterから取得・変換"""
        try:
            if not self.annotator_adapter:
                logger.warning("AnnotatorLibAdapter not available")
                return []

            # モデル情報取得
            models_metadata = self.annotator_adapter.get_available_models_with_metadata()

            # ModelInfoに変換
            self._all_models = []
            for model_data in models_metadata:
                model_info = ModelInfo(
                    name=model_data.get("name", ""),
                    provider=model_data.get("provider", "unknown"),
                    capabilities=self._infer_capabilities(model_data),
                    api_model_id=model_data.get("api_model_id"),
                    requires_api_key=model_data.get("requires_api_key", False),
                    estimated_size_gb=model_data.get("estimated_size_gb"),
                    is_recommended=self._is_recommended_model(model_data.get("name", "")),
                )
                self._all_models.append(model_info)

            logger.info(f"Loaded {len(self._all_models)} models from AnnotatorLibAdapter")
            return self._all_models

        except Exception as e:
            logger.error(f"Failed to load models: {e}")
            return []

    def get_all_models(self) -> list[ModelInfo]:
        """すべてのモデル情報を取得"""
        return self._all_models.copy()

    def get_recommended_models(self) -> list[ModelInfo]:
        """推奨モデルのみを取得"""
        return [m for m in self._all_models if m.is_recommended]

    def filter_models(
        self, provider: str | None = None, capabilities: list[str] | None = None
    ) -> list[ModelInfo]:
        """指定した条件でモデルをフィルタリング"""
        filtered = self._all_models

        # プロバイダーフィルタ
        if provider and provider != "すべて":
            filtered = [m for m in filtered if m.provider.lower() == provider.lower()]

        # 機能フィルタ
        if capabilities:
            filtered = [m for m in filtered if any(cap in m.capabilities for cap in capabilities)]

        return filtered

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

    def _infer_capabilities(self, model_data: dict[str, Any]) -> list[str]:
        """モデルタイプから機能をマッピング"""
        model_type = model_data.get("model_type", "")

        # DBのmodel_typeカラムから機能をマッピング
        type_mapping = {
            "multimodal": ["caption", "tag"],
            "caption": ["caption"],
            "tag": ["tag"],
            "score": ["score"],
        }

        return type_mapping.get(model_type, ["caption"])

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
