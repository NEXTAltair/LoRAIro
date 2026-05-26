# src/lorairo/services/model_selection_service.py

from __future__ import annotations

from dataclasses import dataclass

from ..database.repository.image import ImageRepository
from ..database.schema import Model
from ..utils.log import logger
from .model_route_service import DisplayModelOption, RoutePreference, build_display_options


@dataclass
class ModelSelectionCriteria:
    """モデル選択条件データクラス"""

    provider: str | None = None
    capabilities: list[str] | None = None
    only_recommended: bool = False
    only_available: bool = True
    exclude_local: bool = False  # True の場合、provider が local/None のモデルを除外
    execution_env: str | None = None  # "APIモデルのみ" or "ローカルモデルのみ" or None/"すべて"
    annotation_only: bool = False  # True の場合、batch annotation 対象モデルだけに絞る


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

    _LEGACY_SENTINEL_PREFIX = "__legacy_"
    _LEGACY_SENTINEL_SUFFIX = "__"

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

    @staticmethod
    def _provider_key(provider: str | None) -> str:
        """フィルタ比較用の provider 正規化キーを返す。"""
        if not provider:
            return "local"
        return provider.lower()

    @staticmethod
    def _is_legacy_sentinel_model_name(model_name: str | None) -> bool:
        """legacy fallback sentinel (`__legacy_<id>__`) モデル名か判定する。"""
        if not isinstance(model_name, str):
            return False
        if not (
            model_name.startswith(ModelSelectionService._LEGACY_SENTINEL_PREFIX)
            and model_name.endswith(ModelSelectionService._LEGACY_SENTINEL_SUFFIX)
        ):
            return False
        body = model_name[
            len(ModelSelectionService._LEGACY_SENTINEL_PREFIX) : -len(
                ModelSelectionService._LEGACY_SENTINEL_SUFFIX
            )
        ]
        return body.isdecimal()

    @staticmethod
    def _model_capability_names(model: Model) -> set[str]:
        """Model capabilities/model_types から構造化された capability 名を取得する。"""
        capabilities = getattr(model, "capabilities", None)
        if capabilities is not None:
            return {str(capability) for capability in capabilities}

        model_types = getattr(model, "model_types", [])
        return {
            str(getattr(model_type, "name", model_type))
            for model_type in model_types
            if getattr(model_type, "name", model_type) is not None
        }

    @classmethod
    def _is_annotation_eligible_model(cls, model: Model) -> bool:
        """Batch annotation に使える model_types/capabilities を持つか判定する。"""
        if cls._is_legacy_sentinel_model_name(model.name):
            return False
        annotation_types = {"caption", "tags", "scores", "ratings", "multimodal"}
        return bool(cls._model_capability_names(model) & annotation_types)

    @classmethod
    def _filter_annotation_eligible(
        cls,
        models: list[Model],
        annotation_only: bool,
    ) -> list[Model]:
        """annotation_only が有効な場合だけ batch annotation 対象モデルに絞る。"""
        if not annotation_only:
            return models
        filtered = [model for model in models if cls._is_annotation_eligible_model(model)]
        logger.debug(f"  アノテーション対象フィルタ後: {len(filtered)}件")
        return filtered

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
            f"annotation_only={criteria.annotation_only}, "
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
            provider_key = self._provider_key(criteria.provider)
            filtered = [m for m in filtered if self._provider_key(m.provider) == provider_key]
            logger.debug(f"  プロバイダーフィルタ後: {len(filtered)}件 (provider={criteria.provider})")

        # ローカルモデル除外フィルタ（provider=None はローカルモデル扱い）
        if criteria.exclude_local:
            filtered = [m for m in filtered if self._provider_key(m.provider) != "local"]
            logger.debug(f"  ローカルモデル除外後: {len(filtered)}件")

        # Batch annotation 対象モデルのみ: upscaler 専用など annotation 非対応モデルを除外
        filtered = self._filter_annotation_eligible(filtered, criteria.annotation_only)

        # 機能フィルタ
        if criteria.capabilities:
            filtered = [
                m
                for m in filtered
                if any(cap in self._model_capability_names(m) for cap in criteria.capabilities)
            ]
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
            provider = self._provider_key(model.provider)
            if provider not in groups:
                groups[provider] = []
            groups[provider].append(model)
        return groups

    def load_grouped_models(
        self,
        criteria: ModelSelectionCriteria | None = None,
        route_preference: RoutePreference = "auto",
        available_providers: set[str] | None = None,
    ) -> list[DisplayModelOption]:
        """Issue #241: フィルタ後の Model を canonical_key で畳んで 1 モデル 1 行に。

        既存 ``load_models()`` / ``filter_models()`` の結果に対し、
        ``model_route_service.build_display_options()`` を適用して
        direct / openrouter 経路を ``DisplayModelOption`` に集約する。

        Args:
            criteria: 既存のフィルタ条件 (provider / capabilities など)。
            route_preference: ``"auto"`` / ``"direct"`` / ``"openrouter"`` / ``"all"``。
            available_providers: API key 設定済み provider 集合。None の場合は
                「全 provider が available」として扱い、route 畳み込みのみ行う
                (CLI でテスト時など key 状況を考慮しないケース用)。

        Returns:
            DisplayModelOption リスト (display_name 昇順ソート済み)。
            ``route_preference="all"`` 時は alternatives に残り全 candidate が
            含まれるので、caller は ``option.all_candidates`` で展開する。
        """
        self.load_models()  # _all_models のキャッシュを populate
        filtered = self.filter_models(criteria)
        options = build_display_options(filtered, available_providers, route_preference)
        logger.debug(
            "load_grouped_models: filtered=%d, options=%d, preference=%s, available=%s",
            len(filtered),
            len(options),
            route_preference,
            sorted(available_providers) if available_providers else None,
        )
        return options

    # create_model_tooltip メソッド削除 - Widgetに移動

    # create_model_display_name メソッド削除 - Widgetに移動

    # _is_recommended_model メソッド削除 - DB Model.is_recommended プロパティを使用
