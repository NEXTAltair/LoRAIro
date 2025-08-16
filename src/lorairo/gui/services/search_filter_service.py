# src/lorairo/gui/services/search_filter_service.py

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ...database.db_manager import ImageDatabaseManager
from ...database.schema import Model
from ...services.model_registry_protocol import (
    ModelInfo as RegistryModelInfo,
)
from ...services.model_registry_protocol import (
    ModelRegistryServiceProtocol,
    NullModelRegistry,
    map_annotator_metadata_to_model_info,
)
from ...utils.log import logger
from .model_selection_service import ModelSelectionCriteria, ModelSelectionService


@dataclass
class SearchConditions:
    """検索条件データクラス(Phase 3拡張版)"""

    search_type: str  # "tags" or "caption"
    keywords: list[str]
    tag_logic: str  # "and" or "or"
    resolution_filter: str | None = None
    custom_width: int | None = None
    custom_height: int | None = None
    aspect_ratio_filter: str | None = None
    date_filter_enabled: bool = False
    date_range_start: datetime | None = None
    date_range_end: datetime | None = None
    only_untagged: bool = False
    only_uncaptioned: bool = False
    exclude_duplicates: bool = False

    # Phase 3: Advanced Model Filtering Extensions
    model_criteria: ModelSelectionCriteria | None = None
    annotation_provider_filter: list[str] | None = None  # ["web_api", "local"]
    annotation_function_filter: list[str] | None = None  # ["caption", "tags", "scores"]


@dataclass
class FilterConditions:
    """フィルター条件データクラス(検索条件から抽出)"""

    resolution: tuple[int, int] | None = None
    aspect_ratio: str | None = None
    date_range: tuple[datetime, datetime] | None = None
    only_untagged: bool = False
    only_uncaptioned: bool = False
    exclude_duplicates: bool = False


@dataclass
class AnnotationStatusCounts:
    """アノテーション状態カウント情報"""

    total: int = 0
    completed: int = 0
    error: int = 0

    @property
    def completion_rate(self) -> float:
        """完了率を取得"""
        if self.total == 0:
            return 0.0
        return (self.completed / self.total) * 100.0


@dataclass
class ValidationResult:
    """アノテーション設定検証結果(拡張版)"""

    is_valid: bool
    errors: list[str] = None
    warnings: list[str] = None
    settings: dict[str, Any] | None = None
    error_message: str | None = None

    def __post_init__(self):
        """デフォルト値設定"""
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []


class SearchFilterService:
    """
    GUI専用検索フィルターサービス(純化版・150行目標)

    責任:
    - UI入力の解析と変換
    - 検索条件プレビューの生成
    - GUI固有の設定データ提供
    - ビジネスロジックサービスとの統合
    """

    def __init__(
        self,
        db_manager: ImageDatabaseManager,
        model_selection_service: ModelSelectionService,
        model_registry: ModelRegistryServiceProtocol | None = None,
    ):
        """
        SearchFilterServiceを初期化(純化版)

        Args:
            db_manager: 後方互換性のために保持(将来的に削除予定)
            model_selection_service: モデル選択サービス
            model_registry: モデルレジストリ(オプション)
        """
        # 後方互換性のために一時的に保持
        self.db_manager = db_manager
        self.model_selection_service = model_selection_service
        self.model_registry = model_registry or NullModelRegistry()

        # 新しいサービス層(依存性注入)
        from ...services.model_filter_service import ModelFilterService
        from ...services.search_criteria_processor import SearchCriteriaProcessor

        self.criteria_processor = SearchCriteriaProcessor(db_manager)
        self.model_filter_service = ModelFilterService(db_manager, model_selection_service)

        # UI状態管理
        self.current_conditions: SearchConditions | None = None

        logger.info("SearchFilterService (純化版) initialized with new service layer integration")

    def parse_search_input(self, input_text: str) -> list[str]:
        """
        UI入力テキストの解析とキーワード抽出

        Args:
            input_text: ユーザー入力テキスト

        Returns:
            list: 抽出されたキーワードリスト
        """
        if not input_text:
            return []

        # 基本的なキーワード分割(カンマ、スペース区切り)
        keywords = [keyword.strip() for keyword in input_text.replace(",", " ").split() if keyword.strip()]
        logger.debug(f"入力解析完了: '{input_text}' -> {keywords}")
        return keywords

    def create_search_conditions(
        self,
        search_type: str,
        keywords: list[str],
        tag_logic: str = "and",
        resolution_filter: str | None = None,
        custom_width: int | None = None,
        custom_height: int | None = None,
        aspect_ratio_filter: str | None = None,
        date_filter_enabled: bool = False,
        date_range_start: datetime | None = None,
        date_range_end: datetime | None = None,
        only_untagged: bool = False,
        only_uncaptioned: bool = False,
        exclude_duplicates: bool = False,
        model_criteria: ModelSelectionCriteria | None = None,
        annotation_provider_filter: list[str] | None = None,
        annotation_function_filter: list[str] | None = None,
    ) -> SearchConditions:
        """
        UIフォームデータからSearchConditionsオブジェクトを作成

        Args:
            各種UI入力パラメータ

        Returns:
            SearchConditions: 検索条件オブジェクト
        """
        conditions = SearchConditions(
            search_type=search_type,
            keywords=keywords,
            tag_logic=tag_logic,
            resolution_filter=resolution_filter,
            custom_width=custom_width,
            custom_height=custom_height,
            aspect_ratio_filter=aspect_ratio_filter,
            date_filter_enabled=date_filter_enabled,
            date_range_start=date_range_start,
            date_range_end=date_range_end,
            only_untagged=only_untagged,
            only_uncaptioned=only_uncaptioned,
            exclude_duplicates=exclude_duplicates,
            model_criteria=model_criteria,
            annotation_provider_filter=annotation_provider_filter,
            annotation_function_filter=annotation_function_filter,
        )

        self.current_conditions = conditions
        logger.debug(f"検索条件作成完了: {conditions}")
        return conditions

    def create_search_preview(self, conditions: SearchConditions) -> str:
        """
        人間が読みやすい検索条件プレビューの生成

        Args:
            conditions: 検索条件

        Returns:
            str: プレビューテキスト
        """
        preview_parts = []

        # 基本検索条件
        if conditions.keywords:
            keyword_text = f" {conditions.tag_logic.upper()} ".join(conditions.keywords)
            preview_parts.append(f"キーワード: {keyword_text} ({conditions.search_type})")

        # フィルター条件
        if conditions.resolution_filter:
            preview_parts.append(f"解像度: {conditions.resolution_filter}")

        if conditions.custom_width and conditions.custom_height:
            preview_parts.append(f"カスタム解像度: {conditions.custom_width}x{conditions.custom_height}")

        if conditions.aspect_ratio_filter:
            preview_parts.append(f"アスペクト比: {conditions.aspect_ratio_filter}")

        if conditions.date_filter_enabled:
            date_info = []
            if conditions.date_range_start:
                date_info.append(f"開始: {conditions.date_range_start.strftime('%Y-%m-%d')}")
            if conditions.date_range_end:
                date_info.append(f"終了: {conditions.date_range_end.strftime('%Y-%m-%d')}")
            if date_info:
                preview_parts.append(f"日付範囲: {', '.join(date_info)}")

        # 特殊条件
        if conditions.only_untagged:
            preview_parts.append("未タグ付きのみ")
        if conditions.only_uncaptioned:
            preview_parts.append("未キャプションのみ")
        if conditions.exclude_duplicates:
            preview_parts.append("重複除外")

        # モデルフィルター
        if conditions.model_criteria:
            preview_parts.append("高度なモデルフィルター有効")

        if not preview_parts:
            return "すべての画像"

        preview = " | ".join(preview_parts)
        logger.debug(f"プレビュー生成完了: {preview}")
        return preview

    def get_available_resolutions(self) -> list[str]:
        """
        UI選択肢用の利用可能解像度リストを取得

        Returns:
            list: 解像度選択肢リスト
        """
        return [
            "512x512",
            "768x768",
            "1024x1024",
            "1280x720",
            "1920x1080",
            "2560x1440",
            "3840x2160",
            "カスタム",
        ]

    def get_available_aspect_ratios(self) -> list[str]:
        """
        UI選択肢用の利用可能アスペクト比リストを取得

        Returns:
            list: アスペクト比選択肢リスト
        """
        return [
            "1:1 (正方形)",
            "4:3 (標準)",
            "16:9 (ワイド)",
            "3:2 (一眼レフ)",
            "2:3 (ポートレート)",
            "9:16 (縦長ワイド)",
        ]

    def validate_ui_inputs(self, inputs: dict[str, Any]) -> ValidationResult:
        """
        UI入力の妥当性検証

        Args:
            inputs: UI入力データ辞書

        Returns:
            ValidationResult: 検証結果
        """
        errors = []
        warnings = []

        # キーワード検証
        keywords = inputs.get("keywords", [])
        if not keywords and not any(
            [
                inputs.get("only_untagged"),
                inputs.get("only_uncaptioned"),
                inputs.get("resolution_filter"),
                inputs.get("date_filter_enabled"),
            ]
        ):
            warnings.append("検索条件が指定されていません。すべての画像が対象になります。")

        # 解像度検証
        custom_width = inputs.get("custom_width")
        custom_height = inputs.get("custom_height")
        if inputs.get("resolution_filter") == "カスタム":
            if not custom_width or not custom_height:
                errors.append("カスタム解像度を選択した場合は幅と高さを指定してください。")
            elif custom_width <= 0 or custom_height <= 0:
                errors.append("幅と高さは正の値で指定してください。")

        # 日付範囲検証
        if inputs.get("date_filter_enabled"):
            start_date = inputs.get("date_range_start")
            end_date = inputs.get("date_range_end")
            if start_date and end_date and start_date > end_date:
                errors.append("開始日付は終了日付より前に設定してください。")

        is_valid = len(errors) == 0
        return ValidationResult(is_valid=is_valid, errors=errors, warnings=warnings)

    def clear_conditions(self) -> None:
        """UI状態管理:検索条件をクリア"""
        self.current_conditions = None

    def get_current_conditions(self) -> SearchConditions | None:
        """UI状態管理:現在の検索条件を取得"""
        return self.current_conditions

    # === 後方互換性ラッパーメソッド(段階的移行用) ===

    def execute_search_with_filters(self, conditions: SearchConditions) -> tuple[list[dict[str, Any]], int]:
        """後方互換性ラッパー:SearchCriteriaProcessorに委譲"""
        return self.criteria_processor.execute_search_with_filters(conditions)

    def get_annotation_models_list(self) -> list[dict[str, Any]]:
        """後方互換性ラッパー:ModelFilterServiceに委譲"""
        return self.model_filter_service.get_annotation_models_list()

    def validate_annotation_settings(self, settings: dict[str, Any]) -> ValidationResult:
        """後方互換性ラッパー:ModelFilterServiceに委譲"""
        return self.model_filter_service.validate_annotation_settings(settings)
