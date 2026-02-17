# src/lorairo/services/model_selection_service.py

from __future__ import annotations

from dataclasses import dataclass

from ..database.db_repository import ImageRepository
from ..database.schema import Model
from ..utils.log import logger


@dataclass
class ModelSelectionCriteria:
    """モデル選択条件データクラス"""

    provider: str | None = None
    capabilities: list[str] | None = None
    only_recommended: bool = False
    only_available: bool = True
    exclude_local: bool = False  # True の場合、provider="local" を除外（API モデルのみ表示）
    execution_env: str | None = None  # "APIモデルのみ" or "ローカルモデルのみ" or None/"すべて"


class ModelSelectionService:
    """
    モデル選択に関するビジネスロジックを処理するサービス（DB中心アプローチ）

    責任:
    - DB経由でのモデル情報取得（直接利用）
    - モデル情報のフィルタリング・推奨判定ロジック
    - 選択状態の管理は行わない（UI側で管理）
    """

    def __init__(self, db_repository: ImageRepository):
        """Initialize ModelSelectionService with DB-centric architecture."""
        self.db_repository = db_repository
        self._all_models: list[Model] = []
        self._cached_models: list[Model] | None = None

    @classmethod
    def create(cls, db_repository: ImageRepository) -> ModelSelectionService:
        """Create ModelSelectionService with DB-centric architecture."""
        return cls(db_repository=db_repository)

    def load_models(self) -> list[Model]:
        """モデル情報をDBから直接取得（真のDB中心実装）"""
        try:
            # キャッシュがあれば返す（パフォーマンス最適化）
            if self._cached_models is not None:
                logger.debug(f"モデルキャッシュヒット: {len(self._cached_models)}件")
                return self._cached_models

            # DBから直接Model オブジェクトを取得（変換レイヤーなし）
            db_models = self.db_repository.get_model_objects()

            self._all_models = db_models
            self._cached_models = db_models
            logger.info(f"Loaded {len(db_models)} models directly from DB")

            # モデル詳細をデバッグ出力
            for model in db_models:
                logger.debug(
                    f"  モデル読込: name={model.name}, provider={model.provider}, "
                    f"available={model.available}, recommended={model.is_recommended}"
                )

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
    ) -> list[Model]:
        """指定した条件でモデルをフィルタリング（DB Model直接使用）"""

        if criteria is None:
            criteria = ModelSelectionCriteria()

        logger.debug(
            f"モデルフィルタリング開始: provider={criteria.provider}, "
            f"exclude_local={criteria.exclude_local}, execution_env={criteria.execution_env}, "
            f"capabilities={criteria.capabilities}, "
            f"only_recommended={criteria.only_recommended}, only_available={criteria.only_available}, "
            f"対象モデル数={len(self._all_models)}"
        )

        filtered = self._all_models

        # 実行環境フィルタ（execution_env による分類）
        if criteria.execution_env and criteria.execution_env != "すべて":
            if criteria.execution_env == "APIモデルのみ":
                filtered = [m for m in filtered if m.requires_api_key]
                logger.debug(f"  実行環境フィルタ後（APIモデルのみ）: {len(filtered)}件")
            elif criteria.execution_env == "ローカルモデルのみ":
                filtered = [m for m in filtered if not m.requires_api_key]
                logger.debug(f"  実行環境フィルタ後（ローカルモデルのみ）: {len(filtered)}件")

        # プロバイダーフィルタ
        if criteria.provider and criteria.provider != "すべて":
            filtered = [
                m for m in filtered if m.provider and m.provider.lower() == criteria.provider.lower()
            ]
            logger.debug(f"  プロバイダーフィルタ後: {len(filtered)}件 (provider={criteria.provider})")

        # ローカルモデル除外フィルタ（API モデルのみ表示）
        if criteria.exclude_local:
            filtered = [m for m in filtered if m.provider and m.provider.lower() != "local"]
            logger.debug(f"  ローカルモデル除外後: {len(filtered)}件")

        # 機能フィルタ
        if criteria.capabilities:
            filtered = [m for m in filtered if any(cap in m.capabilities for cap in criteria.capabilities)]
            logger.debug(f"  機能フィルタ後: {len(filtered)}件 (capabilities={criteria.capabilities})")

        # 推奨フィルタ（DB Modelプロパティ使用）
        if criteria.only_recommended:
            filtered = [m for m in filtered if m.is_recommended]
            logger.debug(f"  推奨フィルタ後: {len(filtered)}件")

        # 利用可能フィルタ（DB Modelプロパティ使用）
        if criteria.only_available:
            filtered = [m for m in filtered if m.available]
            logger.debug(f"  利用可能フィルタ後: {len(filtered)}件")

        logger.debug(
            f"モデルフィルタリング完了: {len(self._all_models)} -> {len(filtered)}件, "
            f"結果=[{', '.join(m.name for m in filtered)}]"
        )

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

    # create_model_tooltip メソッド削除 - Widgetに移動

    # create_model_display_name メソッド削除 - Widgetに移動

    # _is_recommended_model メソッド削除 - DB Model.is_recommended プロパティを使用
