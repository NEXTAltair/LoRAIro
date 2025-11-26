"""
SearchModels - 検索・フィルタリング用データクラス定義

このモジュールはサービス層で共通利用される検索・フィルタリング関連の
データクラスを定義します。依存関係の正常化のため、GUI層から分離されました。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .model_selection_service import ModelSelectionCriteria


@dataclass
class SearchConditions:
    """検索条件データクラス"""

    search_type: str  # "tags" or "caption"
    keywords: list[str]
    tag_logic: str  # "and" or "or"
    resolution_filter: str | None = None
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

    # Rating Filter Extensions
    include_nsfw: bool = True  # NSFWコンテンツを含むか（デフォルト: True for 後方互換性）
    rating_filter: str | None = None  # 手動Rating値でフィルタ ('PG', 'PG-13', 'R', 'X', 'XXX')
    ai_rating_filter: str | None = None  # AI評価Rating値でフィルタ (PG, PG-13, R, X, XXX) - 多数決ロジック
    include_unrated: bool = True  # 未評価画像を含むか (Either: 手動またはAI評価のいずれか1つ以上)

    def to_db_filter_args(self) -> dict[str, Any]:
        """DB APIの引数に直接変換"""
        return {
            "tags": self.keywords if self.search_type == "tags" else None,
            "caption": self.keywords[0] if self.search_type == "caption" and self.keywords else None,
            "resolution": self._resolve_resolution(),
            "use_and": self.tag_logic == "and",
            "include_untagged": self.only_untagged,
            "start_date": self.date_range_start.isoformat() if self.date_range_start else None,
            "end_date": self.date_range_end.isoformat() if self.date_range_end else None,
            "include_nsfw": self.include_nsfw,
            "include_unrated": self.include_unrated,  # Either-based: 手動またはAI評価のいずれか1つ以上
            "manual_rating_filter": self.rating_filter,  # 手動評価フィルタ
            "ai_rating_filter": self.ai_rating_filter,  # AI評価フィルタ (多数決ロジック)
        }

    def _resolve_resolution(self) -> int:
        """解像度条件を長辺値に変換"""
        if self.resolution_filter and "x" in self.resolution_filter:
            try:
                w, h = map(int, self.resolution_filter.split("x"))
                return max(w, h)
            except (ValueError, AttributeError):
                return 0
        return 0


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
class ValidationResult:
    """アノテーション設定検証結果(拡張版)"""

    is_valid: bool
    errors: list[str] | None = None
    warnings: list[str] | None = None
    settings: dict[str, Any] | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        """デフォルト値設定"""
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []
