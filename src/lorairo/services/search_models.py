"""SearchModels - 検索・フィルタリング用データクラス定義

このモジュールはサービス層で共通利用される検索・フィルタリング関連の
データクラスを定義します。依存関係の正常化のため、GUI層から分離されました。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from .model_selection_service import ModelSelectionCriteria

if TYPE_CHECKING:
    from ..database.filter_criteria import ImageFilterCriteria


@dataclass
class SearchConditions:
    """検索条件データクラス"""

    search_type: str  # "tags" or "caption"
    keywords: list[str]
    tag_logic: str  # "and" or "or"
    excluded_keywords: list[str] | None = None
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
    # Issue #811: マルチセレクト chip 対応で単一値 (str) / 複数値 (list[str]) を受ける。
    # 複数値は選択集合の OR。
    rating_filter: str | list[str] | None = None  # 手動Rating値でフィルタ ('PG', 'PG-13', 'R', 'X', 'XXX')
    ai_rating_filter: str | list[str] | None = None  # AI評価Rating値 (多数決) でフィルタ
    rating_combine: str = "and"  # manual / AI レーティングの組合せ ("and" | "or")
    include_unrated: bool = True  # 未評価画像を含むか (Either: 手動またはAI評価のいずれか1つ以上)

    # Score Filter Extensions
    score_min: float | None = None  # 最小スコア値（0.0-10.0）
    score_max: float | None = None  # 最大スコア値（0.0-10.0）

    # Phase 4: Search サイドバー強化 facet fields
    manual_edit_filter: bool | None = None  # 手動編集あり/なし/全て
    reviewed_at_filter: str | None = None  # "unreviewed" | "reviewed" | None=全て
    error_state_filter: str | None = None  # "has_error" | "no_error" | None=全て
    model_filter: list[str] | None = None  # litellm_id リスト。None=全モデル

    def to_filter_criteria(self) -> ImageFilterCriteria:
        """DB層のImageFilterCriteriaオブジェクトに変換

        Returns:
            ImageFilterCriteria: データベース層のフィルター条件オブジェクト
        """
        from ..database.filter_criteria import ImageFilterCriteria

        return ImageFilterCriteria(
            tags=self.keywords if self.search_type == "tags" else None,
            excluded_tags=self.excluded_keywords if self.search_type == "tags" else None,
            caption=self.keywords[0] if self.search_type == "caption" and self.keywords else None,
            resolution=self._resolve_resolution(),
            use_and=self.tag_logic == "and",
            include_untagged=self.only_untagged,
            start_date=self.date_range_start.isoformat() if self.date_range_start else None,
            end_date=self.date_range_end.isoformat() if self.date_range_end else None,
            include_nsfw=self.include_nsfw,
            include_unrated=self.include_unrated,
            manual_rating_filter=self.rating_filter,
            ai_rating_filter=self.ai_rating_filter,
            rating_combine=self.rating_combine,
            score_min=self.score_min,
            score_max=self.score_max,
            manual_edit_filter=self.manual_edit_filter,
            reviewed_at_filter=self.reviewed_at_filter,
            error_state_filter=self.error_state_filter,
            model_filter=self.model_filter,
            # Issue #965: 検索フェーズではアノテーションを先読みしない。
            # tags/captions/scores 等はサムネ選択 → プレビュー表示時に遅延取得する。
            include_annotations=False,
        )

    def to_db_filter_args(self) -> dict[str, Any]:
        """DB APIの引数に直接変換（非推奨: 後方互換性用）

        Warning:
            このメソッドは後方互換性のために残されています。
            新しいコードでは to_filter_criteria() を使用してください。

        Returns:
            dict[str, Any]: フィルター条件の辞書
        """
        return self.to_filter_criteria().to_dict()

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
