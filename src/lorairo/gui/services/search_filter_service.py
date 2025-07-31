# src/lorairo/gui/services/search_filter_service.py

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ...utils.log import logger


@dataclass
class SearchConditions:
    """検索条件データクラス"""

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


@dataclass
class FilterConditions:
    """フィルター条件データクラス（検索条件から抽出）"""

    resolution: tuple[int, int] | None = None
    aspect_ratio: str | None = None
    date_range: tuple[datetime, datetime] | None = None
    only_untagged: bool = False
    only_uncaptioned: bool = False
    exclude_duplicates: bool = False


class SearchFilterService:
    """
    検索・フィルター処理に関するビジネスロジックを処理するサービス

    責任:
    - 検索条件の解析・分離
    - フィルター条件の変換
    - 検索キーワードの処理
    - 解像度・アスペクト比の解析
    - 日付範囲の処理
    """

    def __init__(self):
        self.current_conditions: SearchConditions | None = None

    def parse_search_input(self, search_text: str, search_type: str, tag_logic: str) -> list[str]:
        """検索テキストをキーワードリストに変換"""
        if not search_text.strip():
            return []

        if search_type == "tags":
            # タグ検索の場合はカンマ区切りで分割
            keywords = [kw.strip() for kw in search_text.split(",")]
            return [kw for kw in keywords if kw]  # 空文字列を除去
        else:
            # キャプション検索の場合はスペース区切りで分割
            keywords = search_text.strip().split()
            return keywords

    def create_search_conditions(
        self,
        search_text: str,
        search_type: str,
        tag_logic: str,
        resolution_filter: str,
        custom_width: str,
        custom_height: str,
        aspect_ratio_filter: str,
        date_filter_enabled: bool,
        date_range_start: datetime | None,
        date_range_end: datetime | None,
        only_untagged: bool,
        only_uncaptioned: bool,
        exclude_duplicates: bool,
    ) -> SearchConditions:
        """UI入力から検索条件オブジェクトを作成"""
        keywords = self.parse_search_input(search_text, search_type, tag_logic)

        # カスタム解像度の処理
        custom_width_int = None
        custom_height_int = None
        if resolution_filter == "カスタム...":
            # 幅の処理
            try:
                custom_width_int = int(custom_width) if custom_width.strip() else None
            except ValueError:
                logger.warning(f"Invalid custom width: {custom_width}")
                custom_width_int = None

            # 高さの処理
            try:
                custom_height_int = int(custom_height) if custom_height.strip() else None
            except ValueError:
                logger.warning(f"Invalid custom height: {custom_height}")
                custom_height_int = None

        conditions = SearchConditions(
            search_type=search_type,
            keywords=keywords,
            tag_logic=tag_logic,
            resolution_filter=resolution_filter if resolution_filter != "全て" else None,
            custom_width=custom_width_int,
            custom_height=custom_height_int,
            aspect_ratio_filter=aspect_ratio_filter if aspect_ratio_filter != "全て" else None,
            date_filter_enabled=date_filter_enabled,
            date_range_start=date_range_start,
            date_range_end=date_range_end,
            only_untagged=only_untagged,
            only_uncaptioned=only_uncaptioned,
            exclude_duplicates=exclude_duplicates,
        )

        self.current_conditions = conditions
        return conditions

    def separate_search_and_filter_conditions(
        self, conditions: SearchConditions
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """検索条件をデータベース検索用とフィルター用に分離"""
        search_conditions: dict[str, Any] = {}
        filter_conditions: dict[str, Any] = {}

        # 検索条件（データベースクエリ用）
        if conditions.keywords:
            search_conditions["search_type"] = conditions.search_type
            search_conditions["keywords"] = conditions.keywords
            search_conditions["tag_logic"] = conditions.tag_logic

        search_conditions["only_untagged"] = conditions.only_untagged
        search_conditions["only_uncaptioned"] = conditions.only_uncaptioned

        # フィルター条件（後処理用）
        if conditions.resolution_filter:
            if conditions.resolution_filter == "カスタム...":
                if conditions.custom_width and conditions.custom_height:
                    filter_conditions["resolution"] = (conditions.custom_width, conditions.custom_height)
            else:
                resolution = self._parse_resolution_string(conditions.resolution_filter)
                if resolution:
                    filter_conditions["resolution"] = resolution

        if conditions.aspect_ratio_filter:
            filter_conditions["aspect_ratio"] = conditions.aspect_ratio_filter

        if conditions.date_filter_enabled and conditions.date_range_start and conditions.date_range_end:
            filter_conditions["date_range"] = (conditions.date_range_start, conditions.date_range_end)

        filter_conditions["exclude_duplicates"] = conditions.exclude_duplicates

        return search_conditions, filter_conditions

    def create_search_preview(self, conditions: SearchConditions) -> str:
        """検索条件のプレビューテキストを作成"""
        preview_parts = []

        if conditions.keywords:
            keywords_text = ", ".join(conditions.keywords)
            logic_text = "すべて含む" if conditions.tag_logic == "and" else "いずれか含む"
            preview_parts.append(f"{conditions.search_type}: {keywords_text} ({logic_text})")

        if conditions.resolution_filter:
            if conditions.resolution_filter == "カスタム...":
                if conditions.custom_width and conditions.custom_height:
                    preview_parts.append(f"解像度: {conditions.custom_width}x{conditions.custom_height}")
            else:
                preview_parts.append(f"解像度: {conditions.resolution_filter}")

        if conditions.aspect_ratio_filter:
            preview_parts.append(f"アスペクト比: {conditions.aspect_ratio_filter}")

        if conditions.date_filter_enabled:
            if conditions.date_range_start and conditions.date_range_end:
                start_str = conditions.date_range_start.strftime("%Y-%m-%d")
                end_str = conditions.date_range_end.strftime("%Y-%m-%d")
                preview_parts.append(f"日付: {start_str} ～ {end_str}")

        options = []
        if conditions.only_untagged:
            options.append("未タグ画像のみ")
        if conditions.only_uncaptioned:
            options.append("未キャプション画像のみ")
        if conditions.exclude_duplicates:
            options.append("重複除外")

        if options:
            preview_parts.append(f"オプション: {', '.join(options)}")

        return "\n".join(preview_parts) if preview_parts else "検索条件なし"

    def get_available_resolutions(self) -> list[str]:
        """利用可能な解像度選択肢を取得"""
        return [
            "全て",
            "512x512",
            "1024x1024",
            "1024x768",
            "768x1024",
            "1920x1080",
            "1080x1920",
            "2048x2048",
            "カスタム...",
        ]

    def get_available_aspect_ratios(self) -> list[str]:
        """利用可能なアスペクト比選択肢を取得"""
        return [
            "全て",
            "正方形 (1:1)",
            "風景 (16:9)",
            "縦長 (9:16)",
            "風景 (4:3)",
            "縦長 (3:4)",
        ]

    def _parse_resolution_string(self, resolution_str: str) -> tuple[int, int] | None:
        """解像度文字列を(width, height)タプルに変換"""
        try:
            if "x" in resolution_str:
                width_str, height_str = resolution_str.split("x")
                return (int(width_str), int(height_str))
        except ValueError:
            logger.warning(f"Failed to parse resolution string: {resolution_str}")
        return None

    def clear_conditions(self) -> None:
        """保存された検索条件をクリア"""
        self.current_conditions = None

    def get_current_conditions(self) -> SearchConditions | None:
        """現在の検索条件を取得"""
        return self.current_conditions
