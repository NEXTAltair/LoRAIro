"""
ModelFilterService - モデル管理・フィルタリング専用サービス

このサービスはAIモデルの管理、フィルタリング、検証、
高度なモデルベースの画像フィルタリングを担当します。
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from ..database.db_manager import ImageDatabaseManager
from ..gui.services.model_selection_service import ModelSelectionService
from ..gui.services.search_filter_service import (
    SearchConditions,
    ValidationResult,
)


class ModelFilterService:
    """
    モデル管理・フィルタリング専用サービス

    責任:
    - AIモデルの一覧取得と管理
    - モデル条件によるフィルタリング
    - モデル能力の推定と検証
    - 高度なモデルベース画像フィルタリング
    """

    def __init__(self, db_manager: ImageDatabaseManager, model_selection_service: ModelSelectionService):
        """
        ModelFilterServiceを初期化

        Args:
            db_manager: データベース操作用のImageDatabaseManager
            model_selection_service: モデル選択用のModelSelectionService
        """
        self.db_manager = db_manager
        self.model_selection_service = model_selection_service
        logger.debug("ModelFilterService initialized")

    def get_annotation_models_list(self) -> list[dict[str, Any]]:
        """
        アノテーションモデル一覧取得（Phase 3現代化版：ModelSelectionService委譲）

        Returns:
            list: モデル情報のリスト（dict形式、後方互換性維持）
        """
        try:
            # Phase 3: Delegate to modernized ModelSelectionService
            models = self.model_selection_service.load_models()

            # Convert Model objects/dicts to standardized dict format for backward compatibility
            models_list = []
            for model in models:
                # Handle both object and dict formats
                if isinstance(model, dict):
                    # Already in dict format (test scenarios)
                    model_info = {
                        "name": model.get("name"),
                        "provider": model.get("provider"),
                        "capabilities": model.get("capabilities", []),
                        "requires_api_key": model.get("requires_api_key", False),
                        "is_local": model.get("provider", "").lower() == "local",
                        "estimated_size_gb": model.get("estimated_size_gb", 0),
                        "is_recommended": model.get("is_recommended", False),
                    }
                else:
                    # Model object format (production scenarios)
                    model_info = {
                        "name": model.name,
                        "provider": model.provider,
                        "capabilities": model.capabilities,
                        "requires_api_key": model.requires_api_key,
                        "is_local": model.provider.lower() == "local",
                        "estimated_size_gb": model.estimated_size_gb,
                        "is_recommended": model.is_recommended,
                    }
                models_list.append(model_info)

            logger.info(f"Retrieved {len(models_list)} models via ModelSelectionService")
            return models_list

        except Exception as e:
            logger.error(f"モデル一覧取得エラー: {e}", exc_info=True)
            return []

    def filter_models_by_criteria(self, criteria: dict[str, Any]) -> list[dict[str, Any]]:
        """
        条件によるモデルフィルタリング

        指定された条件でモデルをフィルタリングします。

        Args:
            criteria: フィルタリング条件

        Returns:
            list: フィルター済みモデルリスト
        """
        try:
            all_models = self.get_annotation_models_list()
            filtered_models = []

            for model in all_models:
                if self._model_matches_criteria(model, criteria):
                    filtered_models.append(model)

            logger.debug(f"モデルフィルタリング完了: {len(all_models)} -> {len(filtered_models)}件")
            return filtered_models

        except Exception as e:
            logger.error(f"モデルフィルタリング中にエラー: {e}", exc_info=True)
            return []

    def infer_model_capabilities(self, model_data: dict[str, Any]) -> list[str]:
        """
        モデル能力の推定

        モデル情報からその能力を推定します。

        Args:
            model_data: モデル情報

        Returns:
            list: 推定された能力リスト
        """
        try:
            capabilities = []

            # プロバイダーベースの能力推定
            provider = model_data.get("provider", "").lower()
            model_name = model_data.get("name", "").lower()

            # 基本的な画像解析能力
            if any(keyword in model_name for keyword in ["vision", "image", "visual"]):
                capabilities.append("image_analysis")
                capabilities.append("object_detection")

            # テキスト生成能力
            if provider in ["openai", "anthropic", "google"]:
                capabilities.append("text_generation")
                capabilities.append("description_generation")

            # 高度な分析能力
            if any(keyword in model_name for keyword in ["gpt-4", "claude-3", "gemini"]):
                capabilities.extend(["advanced_reasoning", "contextual_analysis"])

            # ローカルモデル特有の能力
            if model_data.get("is_local", False):
                capabilities.append("offline_processing")

            # 既存の能力情報をマージ
            existing_capabilities = model_data.get("capabilities", [])
            if isinstance(existing_capabilities, list):
                capabilities.extend(existing_capabilities)

            # 重複除去
            capabilities = list(set(capabilities))

            logger.debug(f"モデル能力推定完了: {model_name} -> {capabilities}")
            return capabilities

        except Exception as e:
            logger.error(f"モデル能力推定中にエラー: {e}", exc_info=True)
            return []

    def validate_annotation_settings(self, settings: dict[str, Any]) -> ValidationResult:
        """
        アノテーション設定の検証

        アノテーション設定の妥当性を検証します。

        Args:
            settings: アノテーション設定

        Returns:
            ValidationResult: 検証結果
        """
        try:
            errors = []
            warnings = []

            # 選択されたモデルの検証
            selected_models = settings.get("selected_models", [])
            if not selected_models:
                errors.append("アノテーション用のモデルが選択されていません")
            else:
                available_models = self.get_annotation_models_list()
                available_model_names = {model["name"] for model in available_models}

                for model_name in selected_models:
                    if model_name not in available_model_names:
                        errors.append(f"選択されたモデル '{model_name}' が利用できません")

            # API キー設定の検証
            for model_name in selected_models:
                model_info = next((m for m in available_models if m["name"] == model_name), None)
                if model_info and model_info.get("requires_api_key", False):
                    api_key_key = f"{model_info['provider']}_api_key"
                    if not settings.get(api_key_key):
                        warnings.append(f"モデル '{model_name}' にはAPIキーが必要です")

            # バッチサイズの検証
            batch_size = settings.get("batch_size", 1)
            if batch_size < 1 or batch_size > 100:
                errors.append("バッチサイズは1から100の間で設定してください")

            # タイムアウト設定の検証
            timeout = settings.get("timeout", 30)
            if timeout < 5 or timeout > 300:
                warnings.append("タイムアウトは5秒から300秒の間での設定を推奨します")

            is_valid = len(errors) == 0
            result = ValidationResult(is_valid=is_valid, errors=errors, warnings=warnings)

            logger.debug(
                f"アノテーション設定検証完了: valid={is_valid}, errors={len(errors)}, warnings={len(warnings)}"
            )
            return result

        except Exception as e:
            logger.error(f"アノテーション設定検証中にエラー: {e}", exc_info=True)
            return ValidationResult(
                is_valid=False, errors=[f"検証中にエラーが発生しました: {e!s}"], warnings=[]
            )

    def apply_advanced_model_filters(
        self, images: list[dict[str, Any]], conditions: SearchConditions
    ) -> list[dict[str, Any]]:
        """
        高度なモデルフィルターの適用

        モデルベースの高度なフィルタリングを実行します。

        Args:
            images: 画像データリスト
            conditions: 検索条件

        Returns:
            list: フィルター済み画像リスト
        """
        try:
            if not self._has_advanced_model_filters(conditions):
                return images

            filtered_images = []

            for image in images:
                if self._image_matches_advanced_model_criteria(image, conditions):
                    filtered_images.append(image)

            logger.debug(f"高度なモデルフィルター適用完了: {len(images)} -> {len(filtered_images)}件")
            return filtered_images

        except Exception as e:
            logger.error(f"高度なモデルフィルター適用中にエラー: {e}", exc_info=True)
            return images

    def optimize_advanced_filtering_performance(
        self, images: list[dict[str, Any]], conditions: SearchConditions
    ) -> list[dict[str, Any]]:
        """
        高度なフィルタリングのパフォーマンス最適化

        大量データ処理時のパフォーマンス最適化版フィルタリングです。

        Args:
            images: 画像データリスト
            conditions: 検索条件

        Returns:
            list: フィルター済み画像リスト
        """
        try:
            # パフォーマンス最適化: バッチ処理
            batch_size = 50
            filtered_images = []

            for i in range(0, len(images), batch_size):
                batch = images[i : i + batch_size]
                batch_filtered = self.apply_advanced_model_filters(batch, conditions)
                filtered_images.extend(batch_filtered)

                # 進捗ログ
                if i % (batch_size * 10) == 0:
                    logger.debug(f"高度フィルタリング進捗: {i}/{len(images)}件処理完了")

            logger.info(f"高度フィルタリング最適化完了: {len(images)} -> {len(filtered_images)}件")
            return filtered_images

        except Exception as e:
            logger.error(f"高度フィルタリング最適化中にエラー: {e}", exc_info=True)
            return images

    def _model_matches_criteria(self, model: dict[str, Any], criteria: dict[str, Any]) -> bool:
        """
        モデルが条件に一致するかチェック

        Args:
            model: モデル情報
            criteria: フィルタリング条件

        Returns:
            bool: 条件一致するかどうか
        """
        try:
            # プロバイダーフィルター
            if not self._model_matches_provider_filter(model, criteria):
                return False

            # 機能フィルター
            if not self._model_matches_function_filter(model, criteria):
                return False

            # ローカルモデルフィルター
            if criteria.get("local_only"):
                if not model.get("is_local", False):
                    return False

            # 推奨モデルフィルター
            if criteria.get("recommended_only"):
                if not model.get("is_recommended", False):
                    return False

            return True

        except Exception as e:
            logger.error(f"モデル条件一致チェック中にエラー: {e}", exc_info=True)
            return False

    def _model_matches_provider_filter(self, model: dict[str, Any], criteria: dict[str, Any]) -> bool:
        """
        プロバイダーベースのモデルフィルタリング

        Args:
            model: モデル情報
            criteria: フィルタリング条件

        Returns:
            bool: プロバイダー条件に一致するか
        """
        try:
            provider_filter = criteria.get("provider_filter")
            if not provider_filter:
                return True

            model_provider = model.get("provider", "").lower()

            if isinstance(provider_filter, str):
                return model_provider == provider_filter.lower()
            elif isinstance(provider_filter, list):
                return model_provider in [p.lower() for p in provider_filter]

            return True

        except Exception as e:
            logger.error(f"プロバイダーフィルターチェック中にエラー: {e}", exc_info=True)
            return True

    def _model_matches_function_filter(self, model: dict[str, Any], criteria: dict[str, Any]) -> bool:
        """
        機能ベースのモデルフィルタリング

        Args:
            model: モデル情報
            criteria: フィルタリング条件

        Returns:
            bool: 機能条件に一致するか
        """
        try:
            function_filter = criteria.get("function_filter")
            if not function_filter:
                return True

            model_capabilities = model.get("capabilities", [])
            if not isinstance(model_capabilities, list):
                model_capabilities = []

            # 推定能力も考慮
            inferred_capabilities = self.infer_model_capabilities(model)
            all_capabilities = set(model_capabilities + inferred_capabilities)

            if isinstance(function_filter, str):
                return function_filter in all_capabilities
            elif isinstance(function_filter, list):
                return any(func in all_capabilities for func in function_filter)

            return True

        except Exception as e:
            logger.error(f"機能フィルターチェック中にエラー: {e}", exc_info=True)
            return True

    def _has_advanced_model_filters(self, conditions: SearchConditions) -> bool:
        """
        高度なモデルフィルターが指定されているかチェック

        Args:
            conditions: 検索条件

        Returns:
            bool: 高度なモデルフィルターが有効か
        """
        try:
            # 高度なモデルフィルター条件をチェック
            if hasattr(conditions, "model_filters") and conditions.model_filters:
                return True

            if hasattr(conditions, "advanced_model_criteria") and conditions.advanced_model_criteria:
                return True

            return False

        except Exception as e:
            logger.error(f"高度フィルター確認中にエラー: {e}", exc_info=True)
            return False

    def _image_matches_advanced_model_criteria(
        self, image: dict[str, Any], conditions: SearchConditions
    ) -> bool:
        """
        画像が高度なモデル条件に一致するかチェック

        Args:
            image: 画像情報
            conditions: 検索条件

        Returns:
            bool: 条件に一致するか
        """
        try:
            # 実装例：アノテーションモデルによる条件チェック
            if hasattr(conditions, "annotation_model_filter"):
                annotation_model = conditions.annotation_model_filter
                if annotation_model:
                    # 画像に対応するアノテーション情報を取得
                    image_id = image.get("id")
                    if image_id:
                        # データベースからアノテーション情報を取得し、モデル条件をチェック
                        # 実装詳細は要件に応じて調整
                        pass

            # 実装例：品質スコアによる条件チェック
            if hasattr(conditions, "quality_threshold"):
                quality_threshold = conditions.quality_threshold
                if quality_threshold:
                    image_quality = image.get("quality_score", 0)
                    if image_quality < quality_threshold:
                        return False

            return True

        except Exception as e:
            logger.error(f"高度モデル条件チェック中にエラー: {e}", exc_info=True)
            return True
