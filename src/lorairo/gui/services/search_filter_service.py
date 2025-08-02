# src/lorairo/gui/services/search_filter_service.py

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ...utils.log import logger

if TYPE_CHECKING:
    from ...database.db_manager import ImageDatabaseManager


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
    検索・フィルター処理に関するビジネスロジックを処理するサービス（拡張版）

    責任:
    - 検索条件の解析・分離
    - フィルター条件の変換
    - 検索キーワードの処理
    - 解像度・アスペクト比の解析
    - 日付範囲の処理
    - データベース検索・フィルター処理（拡張機能）
    """

    def __init__(self, db_manager: "ImageDatabaseManager | None" = None):
        """
        SearchFilterServiceのコンストラクタ

        Args:
            db_manager: データベースマネージャー（オプション）
                      None の場合は既存の機能のみ利用可能
        """
        self.current_conditions: SearchConditions | None = None
        self.db_manager = db_manager

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

    # === データベース統合機能（拡張版） ===

    def execute_search_with_filters(self, conditions: SearchConditions) -> tuple[list[dict[str, Any]], int]:
        """
        統一検索実行（DB分離後）

        SearchConditionsを使用してデータベース検索を実行し、
        フィルター処理も適用した結果を返します。

        Args:
            conditions: 検索条件オブジェクト

        Returns:
            tuple: (検索結果リスト, 総件数)

        Raises:
            ValueError: データベースマネージャーが設定されていない場合
        """
        if self.db_manager is None:
            raise ValueError(
                "データベースマネージャーが設定されていません。SearchFilterService初期化時にdb_managerを指定してください。"
            )

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

    def get_directory_images(self, directory_path: Path) -> list[dict[str, Any]]:
        """
        ディレクトリ内画像の取得（軽量な読み取り操作）

        Args:
            directory_path: 検索対象ディレクトリのパス

        Returns:
            list: ディレクトリ内の画像メタデータリスト
        """
        if self.db_manager is None:
            logger.warning("データベースマネージャーが設定されていません")
            return []

        try:
            image_ids = self.db_manager.get_image_ids_from_directory(directory_path)
            if not image_ids:
                return []

            # 画像IDリストからメタデータを取得
            images = []
            for image_id in image_ids:
                metadata = self.db_manager.get_image_metadata(image_id)
                if metadata:
                    images.append(metadata)

            return images

        except Exception as e:
            logger.error(f"ディレクトリ画像取得エラー: {directory_path}, {e}")
            return []

    def get_dataset_status(self) -> dict[str, Any]:
        """
        データセット状態の取得（軽量な読み取り操作）

        Returns:
            dict: データセット状態情報
        """
        if self.db_manager is None:
            return {"total_images": 0, "status": "no_db"}

        try:
            total_count = self.db_manager.get_total_image_count()
            return {"total_images": total_count, "status": "ready" if total_count > 0 else "empty"}
        except Exception as e:
            logger.error(f"データセット状態取得エラー: {e}")
            return {"total_images": 0, "status": "error"}

    def process_resolution_filter(self, conditions: dict[str, Any]) -> dict[str, Any]:
        """
        解像度フィルターのDB変換処理

        Args:
            conditions: 処理対象の条件辞書

        Returns:
            dict: 処理済み条件辞書
        """
        # FilterSearchPanelから移行されるロジック
        processed_conditions = conditions.copy()

        if "resolution_filter" in conditions:
            resolution_text = conditions["resolution_filter"]
            if resolution_text and resolution_text != "全て":
                resolution_value = self._parse_resolution_value(resolution_text)
                if resolution_value > 0:
                    processed_conditions["resolution"] = resolution_value

        return processed_conditions

    def process_date_filter(self, conditions: dict[str, Any]) -> dict[str, Any]:
        """
        日付フィルターのDB変換処理

        Args:
            conditions: 処理対象の条件辞書

        Returns:
            dict: 処理済み条件辞書
        """
        processed_conditions = conditions.copy()

        if conditions.get("date_filter_enabled") and "date_range" in conditions:
            start_date, end_date = conditions["date_range"]
            if start_date and end_date:
                processed_conditions["start_date"] = start_date.isoformat()
                processed_conditions["end_date"] = end_date.isoformat()

        return processed_conditions

    def apply_untagged_filter(self, conditions: dict[str, Any]) -> dict[str, Any]:
        """
        未タグフィルターのDB処理

        Args:
            conditions: 処理対象の条件辞書

        Returns:
            dict: 処理済み条件辞書
        """
        processed_conditions = conditions.copy()

        if conditions.get("only_untagged"):
            processed_conditions["include_untagged"] = True
            # タグ条件をクリア（矛盾するため）
            processed_conditions.pop("tags", None)
            processed_conditions.pop("use_and", None)

        return processed_conditions

    def apply_tagged_filter_logic(self, conditions: dict[str, Any]) -> dict[str, Any]:
        """
        タグ付きフィルターロジックのDB処理

        Args:
            conditions: 処理対象の条件辞書

        Returns:
            dict: 処理済み条件辞書
        """
        processed_conditions = conditions.copy()

        if conditions.get("tags") or conditions.get("caption"):
            # 検索条件がある場合は未タグを除外
            processed_conditions["include_untagged"] = False
        else:
            # 条件なしの場合は未タグも含める
            processed_conditions["include_untagged"] = True

        return processed_conditions

    # === プライベートヘルパーメソッド ===

    def _convert_to_db_query_conditions(self, search_conditions: dict[str, Any]) -> dict[str, Any]:
        """
        検索条件をデータベースクエリ用の形式に変換

        Args:
            search_conditions: 分離された検索条件

        Returns:
            dict: データベースクエリ用条件
        """
        db_conditions = {}

        # 基本検索条件の変換
        if "search_type" in search_conditions and "keywords" in search_conditions:
            keywords = search_conditions["keywords"]
            if search_conditions["search_type"] == "tags":
                db_conditions["tags"] = keywords
                db_conditions["use_and"] = search_conditions.get("tag_logic", "and") == "and"
            else:  # caption
                db_conditions["caption"] = " ".join(keywords)

        # オプション条件
        db_conditions["include_untagged"] = search_conditions.get("only_untagged", False)
        db_conditions["include_nsfw"] = False  # デフォルトでNSFWは除外

        return db_conditions

    def _apply_frontend_filters(
        self, images: list[dict[str, Any]], filter_conditions: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """
        フロントエンドフィルターを適用（後処理）

        Args:
            images: 画像メタデータリスト
            filter_conditions: フィルター条件

        Returns:
            list: フィルター適用後の画像リスト
        """
        if not filter_conditions:
            return images

        filtered_images = images.copy()

        # 解像度フィルター
        if "resolution" in filter_conditions:
            target_resolution = filter_conditions["resolution"]
            if isinstance(target_resolution, tuple):
                # カスタム解像度 (width, height)
                width, height = target_resolution
                filtered_images = [
                    img
                    for img in filtered_images
                    if img.get("width") == width and img.get("height") == height
                ]
            else:
                # 標準解像度
                filtered_images = [
                    img
                    for img in filtered_images
                    if max(img.get("width", 0), img.get("height", 0)) >= target_resolution
                ]

        # アスペクト比フィルター
        if "aspect_ratio" in filter_conditions:
            aspect_ratio = filter_conditions["aspect_ratio"]
            filtered_images = self._filter_by_aspect_ratio(filtered_images, aspect_ratio)

        # 日付範囲フィルター
        if "date_range" in filter_conditions:
            start_date, end_date = filter_conditions["date_range"]
            filtered_images = self._filter_by_date_range(filtered_images, start_date, end_date)

        return filtered_images

    def _parse_resolution_value(self, resolution_text: str) -> int:
        """
        解像度テキストを解析（FilterSearchPanelから移行）

        Args:
            resolution_text: 解像度テキスト

        Returns:
            int: 解像度値
        """
        if resolution_text.startswith("512"):
            return 512
        elif resolution_text.startswith("1024"):
            return 1024
        elif resolution_text.startswith("2048"):
            return 2048
        return 0

    def _filter_by_aspect_ratio(
        self, images: list[dict[str, Any]], aspect_ratio: str
    ) -> list[dict[str, Any]]:
        """
        アスペクト比でフィルター

        Args:
            images: 画像リスト
            aspect_ratio: アスペクト比文字列

        Returns:
            list: フィルター後の画像リスト
        """
        if aspect_ratio == "全て":
            return images

        filtered = []
        for img in images:
            width = img.get("width", 0)
            height = img.get("height", 0)
            if width <= 0 or height <= 0:
                continue

            ratio = width / height

            if aspect_ratio == "正方形 (1:1)" and 0.95 <= ratio <= 1.05:
                filtered.append(img)
            elif aspect_ratio == "風景 (16:9)" and 1.7 <= ratio <= 1.9:
                filtered.append(img)
            elif aspect_ratio == "縦長 (9:16)" and 0.5 <= ratio <= 0.6:
                filtered.append(img)
            elif aspect_ratio == "風景 (4:3)" and 1.25 <= ratio <= 1.4:
                filtered.append(img)
            elif aspect_ratio == "縦長 (3:4)" and 0.7 <= ratio <= 0.8:
                filtered.append(img)

        return filtered

    def _filter_by_date_range(
        self, images: list[dict[str, Any]], start_date: datetime, end_date: datetime
    ) -> list[dict[str, Any]]:
        """
        日付範囲でフィルター

        Args:
            images: 画像リスト
            start_date: 開始日
            end_date: 終了日

        Returns:
            list: フィルター後の画像リスト
        """
        filtered = []
        for img in images:
            if "created_at" in img:
                try:
                    # ISO形式の日付文字列を解析（Zタイムゾーン対応）
                    date_str = img["created_at"]
                    if date_str.endswith("Z"):
                        date_str = date_str.replace("Z", "+00:00")
                    img_date = datetime.fromisoformat(date_str)
                    
                    # タイムゾーンなしのstartDateとend_dateと比較するため、日付部分のみ比較
                    img_date_naive = img_date.replace(tzinfo=None)
                    if start_date <= img_date_naive <= end_date:
                        filtered.append(img)
                except (ValueError, TypeError) as e:
                    # 日付解析エラーの場合はログ出力してスキップ
                    logger.debug(f"日付解析エラー: {img['created_at']}, エラー: {e}")
                    continue

        return filtered
