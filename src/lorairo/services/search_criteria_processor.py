"""
SearchCriteriaProcessor - 検索・フィルタリングビジネスロジック専用サービス

このサービスは検索条件の処理、フィルタリングロジック、検索実行の
ビジネスルールを担当します。GUIから分離された純粋なビジネスロジック層です。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from loguru import logger

from ..database.db_manager import ImageDatabaseManager
from .search_models import SearchConditions


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
        統一検索実行（直接呼び出し方式）

        SearchConditionsを使用してデータベース検索を実行し、
        フィルター処理も適用した結果を返します。

        Args:
            conditions: 検索条件オブジェクト

        Returns:
            tuple: (検索結果リスト, 総件数)
        """
        try:
            # フロントエンドフィルターが必要な条件のみ分離
            frontend_filters = {
                "aspect_ratio": conditions.aspect_ratio_filter,
                "exclude_duplicates": conditions.exclude_duplicates,
            }

            # DB検索実行（直接変換）
            db_args = conditions.to_db_filter_args()
            images, total_count = self.db_manager.get_images_by_filter(**db_args)

            # フロントエンドフィルター適用（必要時のみ）
            applied_frontend_filters = any(frontend_filters.values())
            if applied_frontend_filters:
                images = self._apply_simple_frontend_filters(images, conditions)

            # DB検索のみの場合はDB総件数を返す。フロントエンドフィルター適用時は件数が変わるためlen(images)を返す。
            reported_count = len(images) if applied_frontend_filters else total_count
            logger.info(
                "検索実行完了: DB引数=%s項目, 結果件数=%s, 総件数=%s, frontend_filter=%s",
                len(db_args),
                len(images),
                total_count,
                applied_frontend_filters,
            )
            return images, reported_count

        except Exception as e:
            logger.error(f"検索実行中にエラーが発生しました: {e}", exc_info=True)
            raise

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

    def _apply_simple_frontend_filters(
        self, images: list[dict[str, Any]], conditions: SearchConditions
    ) -> list[dict[str, Any]]:
        """
        シンプルなフロントエンドフィルターの適用

        データベースで処理できない条件をメモリ内で処理します。

        Args:
            images: 画像データリスト
            conditions: 検索条件

        Returns:
            list: フィルター済み画像データリスト
        """
        try:
            filtered_images = images

            # アスペクト比フィルター
            if conditions.aspect_ratio_filter:
                filtered_images = self._filter_by_aspect_ratio(
                    filtered_images, conditions.aspect_ratio_filter
                )

            # 重複除外フィルター
            if conditions.exclude_duplicates:
                filtered_images = self._filter_by_duplicate_exclusion(filtered_images)

            logger.debug(f"フロントエンドフィルター適用完了: {len(images)} -> {len(filtered_images)}件")
            return filtered_images

        except Exception as e:
            logger.error(f"フロントエンドフィルター適用中にエラー: {e}", exc_info=True)
            return images

    def _filter_by_aspect_ratio(  # noqa: C901
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

    def _filter_by_duplicate_exclusion(self, images: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        phashによる重複画像除外

        同一phashを持つ画像グループから最初に遭遇した画像のみを保持します。

        Args:
            images: 画像データリスト

        Returns:
            list: フィルター済み画像リスト
        """
        try:
            seen_phashes: dict[str, dict[str, Any]] = {}
            filtered_images: list[dict[str, Any]] = []

            for image in images:
                phash = image.get("phash")

                if not isinstance(phash, str) or not phash:
                    # pHashがない場合は重複判定不能のため、そのまま保持する
                    filtered_images.append(image)
                    continue

                if phash not in seen_phashes:
                    seen_phashes[phash] = image
                    filtered_images.append(image)
                # else: 重複のためスキップ（暗黙的）

            logger.debug(
                f"重複除外完了: {len(images)} -> {len(filtered_images)}件 "
                f"(重複除外: {len(images) - len(filtered_images)}件)"
            )
            return filtered_images

        except Exception as e:
            logger.error(f"重複除外フィルター中にエラー: {e}", exc_info=True)
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
