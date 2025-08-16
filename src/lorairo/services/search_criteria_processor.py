"""
SearchCriteriaProcessor - 検索・フィルタリングビジネスロジック専用サービス

このサービスは検索条件の処理、フィルタリングロジック、検索実行の
ビジネスルールを担当します。GUIから分離された純粋なビジネスロジック層です。
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from ..database.db_manager import ImageDatabaseManager
from ..gui.services.search_filter_service import (
    FilterConditions,
    SearchConditions,
)


class SearchCriteriaProcessor:
    """
    検索・フィルタリングビジネスロジック専用サービス

    責任:
    - 検索条件の分析と変換
    - データベース検索とフロントエンドフィルタリングの分離
    - フィルタリングアルゴリズムの実装
    - 検索パフォーマンスの最適化
    """

    def __init__(self, db_manager: ImageDatabaseManager):
        """
        SearchCriteriaProcessorを初期化

        Args:
            db_manager: データベース操作用のImageDatabaseManager
        """
        self.db_manager = db_manager
        logger.debug("SearchCriteriaProcessor initialized")

    def execute_search_with_filters(self, conditions: SearchConditions) -> tuple[list[dict[str, Any]], int]:
        """
        統一検索実行（DB分離後）

        SearchConditionsを使用してデータベース検索を実行し、
        フィルター処理も適用した結果を返します。

        Args:
            conditions: 検索条件オブジェクト

        Returns:
            tuple: (検索結果リスト, 総件数)
        """
        try:
            # 検索条件とフィルター条件を分離
            search_conditions, filter_conditions = self.separate_search_and_filter_conditions(conditions)

            # データベース検索実行
            db_conditions = self._convert_to_db_query_conditions(search_conditions)
            images, total_count = self.db_manager.get_images_by_filter(**db_conditions)

            # フロントエンドフィルター適用（必要に応じて）
            filtered_images = self._apply_frontend_filters(images, filter_conditions)

            logger.info(f"検索実行完了: 条件={search_conditions}, 結果件数={len(filtered_images)}")
            return filtered_images, len(filtered_images)

        except Exception as e:
            logger.error(f"検索実行中にエラーが発生しました: {e}", exc_info=True)
            raise

    def separate_search_and_filter_conditions(
        self, conditions: SearchConditions
    ) -> tuple[dict[str, Any], FilterConditions]:
        """
        検索条件とフィルター条件を分離

        データベースで効率的に処理できる条件と、
        フロントエンドで処理が必要な条件を分離します。

        Args:
            conditions: 元の検索条件

        Returns:
            tuple: (DB検索条件, フロントエンドフィルター条件)
        """
        try:
            # データベースで処理可能な条件
            search_conditions = {}

            # 基本的な検索条件
            if conditions.keywords:
                search_conditions["keywords"] = conditions.keywords
                search_conditions["search_type"] = conditions.search_type
                search_conditions["tag_logic"] = conditions.tag_logic

            # 解像度条件（範囲指定の場合はDBで処理）
            if conditions.resolution_filter:
                resolution_data = self.process_resolution_filter(conditions)
                search_conditions.update(resolution_data)

            # 特殊条件
            if conditions.only_untagged:
                search_conditions["only_untagged"] = conditions.only_untagged
            if conditions.only_uncaptioned:
                search_conditions["only_uncaptioned"] = conditions.only_uncaptioned

            # フロントエンドで処理が必要な条件
            date_range = None
            if conditions.date_filter_enabled and conditions.date_range_start and conditions.date_range_end:
                date_range = (conditions.date_range_start, conditions.date_range_end)

            filter_conditions = FilterConditions(
                aspect_ratio=conditions.aspect_ratio_filter,
                date_range=date_range,
                only_untagged=conditions.only_untagged,
                only_uncaptioned=conditions.only_uncaptioned,
                exclude_duplicates=conditions.exclude_duplicates,
            )

            logger.debug(
                f"条件分離完了: DB条件={len(search_conditions)}項目, フィルター条件={filter_conditions}"
            )
            return search_conditions, filter_conditions

        except Exception as e:
            logger.error(f"条件分離中にエラーが発生しました: {e}", exc_info=True)
            raise

    def process_resolution_filter(self, conditions: SearchConditions) -> dict[str, Any]:
        """
        解像度フィルター処理と検証

        解像度条件を処理し、データベースクエリに適した形式に変換します。

        Args:
            conditions: 検索条件

        Returns:
            dict: 処理済み解像度条件
        """
        try:
            resolution_conditions = {}

            # 基本的な解像度フィルター処理
            if conditions.resolution_filter and conditions.resolution_filter != "全て":
                if (
                    conditions.resolution_filter == "カスタム"
                    and conditions.custom_width
                    and conditions.custom_height
                ):
                    resolution_conditions["min_width"] = conditions.custom_width
                    resolution_conditions["min_height"] = conditions.custom_height
                    resolution_conditions["max_width"] = conditions.custom_width
                    resolution_conditions["max_height"] = conditions.custom_height
                else:
                    # 標準解像度の場合
                    width, height = self._parse_resolution_value(conditions.resolution_filter)
                    if width and height:
                        resolution_conditions["min_width"] = width
                        resolution_conditions["min_height"] = height

            logger.debug(f"解像度条件処理完了: {resolution_conditions}")
            return resolution_conditions

        except Exception as e:
            logger.error(f"解像度フィルター処理中にエラー: {e}", exc_info=True)
            return {}

    def process_date_filter(self, conditions: SearchConditions) -> dict[str, Any]:
        """
        日付フィルター処理

        日付範囲条件を処理し、データベースクエリに適した形式に変換します。

        Args:
            conditions: 検索条件

        Returns:
            dict: 処理済み日付条件
        """
        try:
            date_conditions = {}

            if conditions.date_filter_enabled:
                if conditions.date_range_start:
                    date_conditions["start_date"] = conditions.date_range_start
                if conditions.date_range_end:
                    date_conditions["end_date"] = conditions.date_range_end

            logger.debug(f"日付条件処理完了: {date_conditions}")
            return date_conditions

        except Exception as e:
            logger.error(f"日付フィルター処理中にエラー: {e}", exc_info=True)
            return {}

    def apply_untagged_filter(self, conditions: SearchConditions) -> dict[str, Any]:
        """
        未タグ付きフィルターの適用

        未タグ付き画像の検索条件を処理します。

        Args:
            conditions: 検索条件

        Returns:
            dict: 未タグ付きフィルター条件
        """
        try:
            untagged_conditions = {}

            if conditions.only_untagged:
                untagged_conditions["has_tags"] = False

            # tagged_onlyプロパティがある場合の処理
            if hasattr(conditions, "tagged_only") and getattr(conditions, "tagged_only", False):
                untagged_conditions["has_tags"] = True

            logger.debug(f"未タグ付きフィルター処理完了: {untagged_conditions}")
            return untagged_conditions

        except Exception as e:
            logger.error(f"未タグ付きフィルター処理中にエラー: {e}", exc_info=True)
            return {}

    def apply_tagged_filter_logic(self, conditions: SearchConditions) -> dict[str, Any]:
        """
        タグ付きフィルターロジックの適用

        論理演算子を含むタグフィルタリングの処理を行います。

        Args:
            conditions: 検索条件

        Returns:
            dict: 処理済みタグ条件
        """
        try:
            tag_conditions = {}

            if conditions.keywords and conditions.search_type == "tags":
                tag_conditions["tags"] = conditions.keywords
                tag_conditions["tag_operator"] = conditions.tag_logic

            logger.debug(f"タグフィルターロジック処理完了: {tag_conditions}")
            return tag_conditions

        except Exception as e:
            logger.error(f"タグフィルターロジック処理中にエラー: {e}", exc_info=True)
            return {}

    def _convert_to_db_query_conditions(self, search_conditions: dict[str, Any]) -> dict[str, Any]:
        """
        検索条件をデータベースクエリ形式に変換

        サービス層の検索条件をデータベース層で処理可能な形式に変換します。

        Args:
            search_conditions: 検索条件辞書

        Returns:
            dict: データベースクエリ条件
        """
        try:
            db_conditions = {}

            # 条件をそのまま渡すか、必要に応じて変換
            for key, value in search_conditions.items():
                if value is not None:
                    db_conditions[key] = value

            logger.debug(f"DB条件変換完了: {len(db_conditions)}項目")
            return db_conditions

        except Exception as e:
            logger.error(f"DB条件変換中にエラー: {e}", exc_info=True)
            return {}

    def _apply_frontend_filters(
        self, images: list[dict[str, Any]], filter_conditions: FilterConditions
    ) -> list[dict[str, Any]]:
        """
        フロントエンドフィルターの適用

        データベースで処理できない条件をメモリ内で処理します。

        Args:
            images: 画像データリスト
            filter_conditions: フィルター条件

        Returns:
            list: フィルター済み画像データリスト
        """
        try:
            filtered_images = images

            # アスペクト比フィルター
            if filter_conditions.aspect_ratio:
                filtered_images = self._filter_by_aspect_ratio(
                    filtered_images, filter_conditions.aspect_ratio
                )

            # 日付範囲フィルター
            if filter_conditions.date_range:
                start_date, end_date = filter_conditions.date_range
                date_filter = {"start_date": start_date, "end_date": end_date}
                filtered_images = self._filter_by_date_range(filtered_images, date_filter)

            logger.debug(f"フロントエンドフィルター適用完了: {len(images)} -> {len(filtered_images)}件")
            return filtered_images

        except Exception as e:
            logger.error(f"フロントエンドフィルター適用中にエラー: {e}", exc_info=True)
            return images

    def _filter_by_aspect_ratio(
        self, images: list[dict[str, Any]], aspect_ratio_filter: str
    ) -> list[dict[str, Any]]:
        """
        アスペクト比フィルタリング

        指定されたアスペクト比条件で画像をフィルタリングします。

        Args:
            images: 画像データリスト
            aspect_ratio_filter: アスペクト比フィルター条件（文字列）

        Returns:
            list: フィルター済み画像リスト
        """
        try:
            if not aspect_ratio_filter or aspect_ratio_filter == "全て":
                return images

            filtered_images = []

            # アスペクト比の目標値を設定
            target_ratio = 1.0  # デフォルト
            tolerance = 0.1

            if "正方形" in aspect_ratio_filter or "1:1" in aspect_ratio_filter:
                target_ratio = 1.0
            elif "風景" in aspect_ratio_filter or "16:9" in aspect_ratio_filter:
                target_ratio = 16 / 9
            elif "4:3" in aspect_ratio_filter:
                target_ratio = 4 / 3
            elif "9:16" in aspect_ratio_filter:
                target_ratio = 9 / 16
            elif "3:4" in aspect_ratio_filter:
                target_ratio = 3 / 4

            for image in images:
                width = image.get("width", 0)
                height = image.get("height", 0)

                if width > 0 and height > 0:
                    image_ratio = width / height
                    if abs(image_ratio - target_ratio) <= tolerance:
                        filtered_images.append(image)

            logger.debug(f"アスペクト比フィルター完了: {len(images)} -> {len(filtered_images)}件")
            return filtered_images

        except Exception as e:
            logger.error(f"アスペクト比フィルター中にエラー: {e}", exc_info=True)
            return images

    def _filter_by_date_range(
        self, images: list[dict[str, Any]], date_filter: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """
        日付範囲フィルタリング

        指定された日付範囲で画像をフィルタリングします。

        Args:
            images: 画像データリスト
            date_filter: 日付フィルター条件

        Returns:
            list: フィルター済み画像リスト
        """
        try:
            if not date_filter:
                return images

            filtered_images = []
            start_date = date_filter.get("start_date")
            end_date = date_filter.get("end_date")

            for image in images:
                image_date = image.get("created_at") or image.get("modified_at")
                if image_date:
                    if isinstance(image_date, str):
                        # ISO文字列の「Z」サフィックスを適切に処理
                        if image_date.endswith("Z"):
                            image_date = image_date[:-1] + "+00:00"
                        image_date = datetime.fromisoformat(image_date)

                    # timezone-aware/naive問題を修正：両方ともnaiveにする
                    if image_date.tzinfo is not None:
                        image_date = image_date.replace(tzinfo=None)

                    # start_date/end_dateもnaiveに統一
                    start_date_naive = (
                        start_date.replace(tzinfo=None) if start_date and start_date.tzinfo else start_date
                    )
                    end_date_naive = (
                        end_date.replace(tzinfo=None) if end_date and end_date.tzinfo else end_date
                    )

                    if start_date_naive and image_date < start_date_naive:
                        continue
                    if end_date_naive and image_date > end_date_naive:
                        continue

                    filtered_images.append(image)

            logger.debug(f"日付範囲フィルター完了: {len(images)} -> {len(filtered_images)}件")
            return filtered_images

        except Exception as e:
            logger.error(f"日付範囲フィルター中にエラー: {e}", exc_info=True)
            return images

    def filter_images_by_annotation_status(
        self, images: list[dict[str, Any]], annotation_status: str
    ) -> list[dict[str, Any]]:
        """
        アノテーション状態による画像フィルタリング

        メモリ内でアノテーション状態による画像フィルタリングを実行します。

        Args:
            images: 画像データリスト
            annotation_status: アノテーション状態

        Returns:
            list: フィルター済み画像リスト
        """
        try:
            if not annotation_status or annotation_status == "all":
                return images

            filtered_images = []

            for image in images:
                image_id = image.get("id")
                if image_id:
                    has_annotation = self.db_manager.check_image_has_annotation(image_id)

                    if annotation_status == "annotated" and has_annotation:
                        filtered_images.append(image)
                    elif annotation_status == "not_annotated" and not has_annotation:
                        filtered_images.append(image)

            logger.debug(f"アノテーション状態フィルター完了: {len(images)} -> {len(filtered_images)}件")
            return filtered_images

        except Exception as e:
            logger.error(f"アノテーション状態フィルター中にエラー: {e}", exc_info=True)
            return images

    def _parse_resolution_value(self, resolution_str: str) -> tuple[int | None, int | None]:
        """
        解像度文字列をパースして幅と高さを取得

        Args:
            resolution_str: 解像度文字列 (例: "1920x1080")

        Returns:
            tuple: (幅, 高さ) または (None, None)
        """
        try:
            if not resolution_str:
                return None, None

            # "1920x1080" 形式のパース
            match = re.match(r"(\d+)x(\d+)", resolution_str)
            if match:
                width = int(match.group(1))
                height = int(match.group(2))
                return width, height

            return None, None

        except Exception as e:
            logger.error(f"解像度文字列パース中にエラー: {e}", exc_info=True)
            return None, None
