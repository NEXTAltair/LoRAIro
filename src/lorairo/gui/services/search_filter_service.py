# src/lorairo/gui/services/search_filter_service.py

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ...database.db_manager import ImageDatabaseManager
from ...services.annotator_lib_adapter import AnnotatorLibAdapter
from ...services.model_registry_protocol import ModelRegistryServiceProtocol, NullModelRegistry
from ...utils.log import logger
from .model_selection_service import ModelSelectionCriteria, ModelSelectionService, ModelInfo


@dataclass
class SearchConditions:
    """検索条件データクラス（Phase 3拡張版）"""

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
    """フィルター条件データクラス（検索条件から抽出）"""

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
    """アノテーション設定検証結果"""

    is_valid: bool
    settings: dict[str, Any] | None = None
    error_message: str | None = None


class SearchFilterService:
    """
    検索・フィルター処理に関するビジネスロジックを処理するサービス（Phase 3拡張版）

    責任:
    - 検索条件の解析・分離
    - フィルター条件の変換
    - 検索キーワードの処理
    - 解像度・アスペクト比の解析
    - 日付範囲の処理
    - データベース検索・フィルター処理
    - Phase 3: 高度なモデルフィルタリング（ModelSelectionService統合）
    """

    def __init__(
        self,
        db_manager: ImageDatabaseManager,
        annotator_adapter: "AnnotatorLibAdapter | None" = None,
        model_registry: ModelRegistryServiceProtocol | None = None,
        model_selection_service: ModelSelectionService | None = None,
    ):
        """SearchFilterService のコンストラクタ（Phase 3拡張版）

        Args:
            db_manager: データベースマネージャー（必須）
            annotator_adapter: レガシーアダプター（後方互換性）
            model_registry: モデルレジストリプロトコル（現代的アプローチ）
            model_selection_service: モデル選択サービス（Phase 2統合）
        """
        self.current_conditions: SearchConditions | None = None
        self.db_manager = db_manager

        # Legacy support for backward compatibility
        self.annotator_adapter = annotator_adapter

        # Phase 3: Modern protocol-based architecture
        self.model_registry = model_registry or NullModelRegistry()

        # Phase 2 Integration: ModelSelectionService
        if model_selection_service:
            self.model_selection_service = model_selection_service
        else:
            # Create ModelSelectionService with appropriate configuration
            self.model_selection_service = self._create_model_selection_service()

        logger.info("SearchFilterService initialized with Phase 3 enhancements")

    def _create_model_selection_service(self) -> ModelSelectionService:
        """ModelSelectionService を適切な設定で作成

        Returns:
            ModelSelectionService: 設定されたサービスインスタンス
        """
        # Modern approach: Use protocol-based creation if model_registry is available
        if (
            hasattr(self.model_registry, "get_available_models")
            and self.model_registry.__class__.__name__ != "NullModelRegistry"
        ):
            return ModelSelectionService.create(
                model_registry=self.model_registry, annotator_adapter=self.annotator_adapter
            )
        # Legacy approach: Use annotator_adapter directly
        else:
            return ModelSelectionService(annotator_adapter=self.annotator_adapter)

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

        # Phase 3: 高度なモデルフィルター情報を追加
        advanced_preview = self.create_advanced_model_search_preview(conditions)
        if advanced_preview.get("has_advanced_filters"):
            model_filters = []

            if advanced_preview.get("model_criteria_summary"):
                model_filters.append(f"モデル条件: {advanced_preview['model_criteria_summary']}")

            if advanced_preview.get("provider_filter_summary"):
                model_filters.append(f"プロバイダー: {advanced_preview['provider_filter_summary']}")

            if advanced_preview.get("function_filter_summary"):
                model_filters.append(f"機能: {advanced_preview['function_filter_summary']}")

            if model_filters:
                preview_parts.append("高度フィルター: " + " | ".join(model_filters))

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
        """

        try:
            # 検索条件とフィルター条件を分離
            search_conditions, filter_conditions = self.separate_search_and_filter_conditions(conditions)

            # データベース検索実行
            db_conditions = self._convert_to_db_query_conditions(search_conditions)
            images, total_count = self.db_manager.get_images_by_filter(**db_conditions)

            # フロントエンドフィルター適用（必要に応じて）
            filtered_images = self._apply_frontend_filters(images, filter_conditions)

            # Phase 3: 高度なモデルフィルタリング適用（パフォーマンス最適化版）
            if self._has_advanced_model_filters(conditions):
                # パフォーマンス最適化: 大量データの場合は最適化版を使用
                if len(filtered_images) > 100:  # 閾値は調整可能
                    filtered_images = self.optimize_advanced_filtering_performance(
                        filtered_images, conditions
                    )
                else:
                    filtered_images = self.apply_advanced_model_filters(filtered_images, conditions)

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

    # === アノテーション状態機能（拡張） ===

    def get_annotation_status_counts(self) -> AnnotationStatusCounts:
        """
        アノテーション状態カウントを取得

        Returns:
            AnnotationStatusCounts: アノテーション状態統計
        """
        try:
            session = self.db_manager.get_session()

            with session:
                # 総画像数取得
                total_images = session.execute("SELECT COUNT(*) FROM images").scalar() or 0

                # 完了画像数取得 (タグまたはキャプションが存在)
                completed_query = """
                    SELECT COUNT(DISTINCT i.id) FROM images i
                    LEFT JOIN tags t ON i.id = t.image_id
                    LEFT JOIN captions c ON i.id = c.image_id
                    WHERE t.id IS NOT NULL OR c.id IS NOT NULL
                """
                completed_images = session.execute(completed_query).scalar() or 0

                # エラー画像数取得 (TODO: エラー記録テーブルが必要)
                # 現在はプレースホルダー
                error_images = 0

                return AnnotationStatusCounts(
                    total=total_images, completed=completed_images, error=error_images
                )

        except Exception as e:
            logger.error(f"アノテーション状態カウント取得エラー: {e}")
            return AnnotationStatusCounts()

    def filter_by_annotation_status(
        self, completed: bool = False, error: bool = False
    ) -> list[dict[str, Any]]:
        """
        アノテーション状態でフィルタリング

        Args:
            completed: 完了画像のみ
            error: エラー画像のみ

        Returns:
            list: フィルター後の画像リスト
        """
        try:
            session = self.db_manager.get_session()

            with session:
                if completed:
                    # 完了画像（タグまたはキャプション有り）
                    query = """
                        SELECT DISTINCT i.* FROM images i
                        LEFT JOIN tags t ON i.id = t.image_id
                        LEFT JOIN captions c ON i.id = c.image_id
                        WHERE t.id IS NOT NULL OR c.id IS NOT NULL
                    """
                elif error:
                    # エラー画像（TODO: エラー記録テーブル参照）
                    query = "SELECT * FROM images WHERE 1=0"  # 現在は空結果
                else:
                    # 全ての画像
                    query = "SELECT * FROM images"

                result = session.execute(query).fetchall()
                return [dict(row._mapping) for row in result]

        except Exception as e:
            logger.error(f"アノテーション状態フィルタリングエラー: {e}")
            return []

    def filter_images_by_annotation_status(
        self, images: list[dict[str, Any]], completed: bool = False, error: bool = False
    ) -> list[dict[str, Any]]:
        """
        メモリ上の画像リストをアノテーション状態でフィルタリング（フロントエンド処理）

        Args:
            images: フィルタリング対象の画像リスト
            completed: 完了画像のみ
            error: エラー画像のみ

        Returns:
            list: フィルター後の画像リスト
        """
        if not completed and not error:
            return images  # フィルター条件なしの場合は全画像を返す

        filtered = []
        for img in images:
            img_id = img.get("id")
            if not img_id:
                continue

            try:
                # アノテーション状態を確認
                has_annotation = self._check_image_has_annotation(img_id)

                if completed and has_annotation:
                    filtered.append(img)
                elif error and not has_annotation:
                    # TODO: 実際のエラー状態確認ロジック追加
                    # 現在は未アノテーション画像をエラーとして扱う
                    filtered.append(img)

            except Exception as e:
                logger.debug(f"アノテーション状態確認エラー (image_id: {img_id}): {e}")
                continue

        return filtered

    def _check_image_has_annotation(self, image_id: int) -> bool:
        """
        画像にアノテーション（タグまたはキャプション）があるかチェック

        Args:
            image_id: 画像ID

        Returns:
            bool: アノテーション有無
        """
        try:
            session = self.db_manager.get_session()

            with session:
                query = """
                    SELECT 1 FROM images i
                    LEFT JOIN tags t ON i.id = t.image_id
                    LEFT JOIN captions c ON i.id = c.image_id
                    WHERE i.id = ? AND (t.id IS NOT NULL OR c.id IS NOT NULL)
                    LIMIT 1
                """
                result = session.execute(query, (image_id,)).fetchone()
                return result is not None

        except Exception as e:
            logger.debug(f"アノテーション状態確認エラー: {e}")
            return False

    # === Phase 2拡張機能：アノテーション系モデル管理 ===

    def get_annotation_models_list(self) -> list[dict[str, Any]]:
        """
        アノテーションモデル一覧取得（Phase 3現代化版：ModelSelectionService委譲）

        Returns:
            list: モデル情報のリスト（dict形式、後方互換性維持）
        """
        try:
            # Phase 3: Delegate to modernized ModelSelectionService
            models = self.model_selection_service.load_models()

            # Convert ModelInfo objects to dict format for backward compatibility
            models_list = []
            for model in models:
                model_info = {
                    "name": model.name,
                    "provider": model.provider,
                    "capabilities": model.capabilities,
                    "requires_api_key": model.requires_api_key,
                    "is_local": model.provider.lower() == "local",
                    "estimated_size_gb": model.estimated_size_gb,
                    "is_recommended": model.is_recommended,  # Phase 3 enhancement
                }
                models_list.append(model_info)

            logger.info(f"Retrieved {len(models_list)} models via ModelSelectionService")
            return models_list

        except Exception as e:
            logger.error(f"モデル一覧取得エラー: {e}", exc_info=True)
            return []

    def filter_models_by_criteria(
        self,
        models: list[dict[str, Any]] | None = None,
        function_types: list[str] | None = None,
        providers: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        モデルフィルタリング処理（Phase 3現代化版：ModelSelectionService活用）

        Args:
            models: フィルタリング対象のモデルリスト（Noneの場合は全モデルを取得）
            function_types: 必要な機能タイプ ["caption", "tags", "scores"]
            providers: 必要なプロバイダー ["web_api", "local"]

        Returns:
            list: フィルター後のモデルリスト（dict形式、後方互換性維持）
        """
        try:
            # Phase 3: Use ModelSelectionService for advanced filtering

            # Convert legacy provider format to ModelSelectionCriteria format
            provider_mapping = {"web_api": ["openai", "anthropic", "google"], "local": ["local"]}

            # Flatten provider list for ModelSelectionCriteria
            criteria_providers = []
            if providers:
                for provider in providers:
                    if provider in provider_mapping:
                        criteria_providers.extend(provider_mapping[provider])
                    else:
                        criteria_providers.append(provider)

            # Create modern filtering criteria
            criteria = ModelSelectionCriteria(
                capabilities=function_types,
                provider=criteria_providers[0] if len(criteria_providers) == 1 else None,
                only_available=True,  # Only show available models
            )

            # Use ModelSelectionService for filtering
            filtered_models_obj = self.model_selection_service.filter_models(criteria)

            # Convert back to dict format for backward compatibility
            filtered_models = []
            for model in filtered_models_obj:
                model_info = {
                    "name": model.name,
                    "provider": model.provider,
                    "capabilities": model.capabilities,
                    "requires_api_key": model.requires_api_key,
                    "is_local": model.provider.lower() == "local",
                    "estimated_size_gb": model.estimated_size_gb,
                    "is_recommended": model.is_recommended,
                }

                # Apply legacy provider filtering if multiple providers specified
                if len(criteria_providers) > 1:
                    if not self._model_matches_provider_filter(model_info, providers or []):
                        continue

                filtered_models.append(model_info)

            logger.debug(f"Filtered models: {len(filtered_models)} (via ModelSelectionService)")
            return filtered_models

        except Exception as e:
            logger.error(f"モデルフィルタリングエラー: {e}", exc_info=True)
            # Fallback to legacy implementation for error cases
            if models:
                return self._legacy_filter_models_by_criteria(models, function_types or [], providers or [])
            return []

    def _legacy_filter_models_by_criteria(
        self,
        models: list[dict[str, Any]],
        function_types: list[str],
        providers: list[str],
    ) -> list[dict[str, Any]]:
        """
        レガシーモデルフィルタリング処理（フォールバック用）

        Args:
            models: フィルタリング対象のモデルリスト
            function_types: 必要な機能タイプ
            providers: 必要なプロバイダー

        Returns:
            list: フィルター後のモデルリスト
        """
        try:
            filtered_models = []
            for model in models:
                # プロバイダーフィルター
                if not self._model_matches_provider_filter(model, providers):
                    continue

                # 機能フィルター
                if not self._model_matches_function_filter(model, function_types):
                    continue

                filtered_models.append(model)

            logger.debug(f"Legacy filtered models: {len(models)} -> {len(filtered_models)}")
            return filtered_models

        except Exception as e:
            logger.error(f"レガシーモデルフィルタリングエラー: {e}", exc_info=True)
            return []

    def validate_annotation_settings(self, settings: dict[str, Any]) -> ValidationResult:
        """
        アノテーション設定検証（新規）

        Args:
            settings: 検証対象の設定辞書

        Returns:
            ValidationResult: 検証結果
        """
        try:
            # 必須項目チェック
            if not settings.get("selected_models"):
                return ValidationResult(is_valid=False, error_message="選択されたモデルがありません")

            if not settings.get("selected_function_types"):
                return ValidationResult(is_valid=False, error_message="選択された機能タイプがありません")

            # 有効な設定として返す
            return ValidationResult(is_valid=True, settings=settings)

        except Exception as e:
            logger.error(f"アノテーション設定検証エラー: {e}")
            return ValidationResult(is_valid=False, error_message=f"設定検証中にエラーが発生しました: {e}")

    def infer_model_capabilities(self, model_data: dict[str, Any]) -> list[str]:
        """
        モデル機能推定（AnnotationControlWidgetから移行）

        Args:
            model_data: モデルメタデータ

        Returns:
            list: 推定される機能リスト ["caption", "tags", "scores"]
        """
        try:
            # Phase 3: ModelSelectionServiceの機能推定ロジックに委譲
            if self.model_selection_service:
                # Protocol-based ModelInfoから機能情報を取得
                models = self.model_selection_service.load_models()
                model_name = model_data.get("name", "")

                # 名前で一致するモデルを検索
                for model in models:
                    if model.name == model_name:
                        return model.capabilities

                # 見つからない場合は、ModelSelectionServiceの推論ロジックを使用
                return self.model_selection_service._infer_capabilities_legacy(model_data)

            # レガシーフォールバック: 直接推論
            return self._legacy_infer_model_capabilities(model_data)

        except Exception as e:
            logger.error(f"モデル機能推定エラー: {e}")
            return self._legacy_infer_model_capabilities(model_data)

    def _legacy_infer_model_capabilities(self, model_data: dict[str, Any]) -> list[str]:
        """レガシーモデル機能推定（後方互換用）"""
        name = model_data.get("name", "").lower()
        provider = model_data.get("provider", "").lower()

        capabilities = []

        # マルチモーダルLLM（Caption + Tags生成）
        if any(keyword in name for keyword in ["gpt-4", "claude", "gemini"]):
            capabilities = ["caption", "tags"]
        # Caption特化
        elif any(keyword in name for keyword in ["gpt-4o", "dall-e"]):
            capabilities = ["caption"]
        # タグ生成特化
        elif any(keyword in name for keyword in ["tagger", "danbooru", "wd-", "deepdanbooru"]):
            capabilities = ["tags"]
        # 品質評価特化
        elif any(keyword in name for keyword in ["aesthetic", "clip", "musiq", "quality", "score"]):
            capabilities = ["scores"]
        # プロバイダーベース推測
        elif provider in ["openai", "anthropic", "google"]:
            capabilities = ["caption", "tags"]
        else:
            capabilities = ["caption"]  # デフォルト

        return capabilities

    def _model_matches_provider_filter(self, model: dict[str, Any], providers: list[str]) -> bool:
        """
        モデルがプロバイダーフィルターに一致するかチェック（内部）

        Args:
            model: モデル情報（dict形式）
            providers: プロバイダーリスト

        Returns:
            bool: フィルター一致有無
        """
        if not providers:
            return False

        try:
            # Phase 3: ModelSelectionServiceを使用してプロバイダー判定を現代化
            if self.model_selection_service:
                models = self.model_selection_service.load_models()
                model_name = model.get("name", "")

                # 名前で一致するModelInfoを検索
                for modern_model in models:
                    if modern_model.name == model_name:
                        # web_api -> requires_api_key, local -> not requires_api_key
                        if "web_api" in providers and modern_model.requires_api_key:
                            return True
                        if "local" in providers and not modern_model.requires_api_key:
                            return True
                        # プロバイダー名による直接一致
                        if modern_model.provider.lower() in [p.lower() for p in providers]:
                            return True
                        break

            # レガシーフォールバック
            return self._legacy_model_matches_provider_filter(model, providers)

        except Exception as e:
            logger.warning(f"プロバイダーフィルターエラー、レガシー処理にフォールバック: {e}")
            return self._legacy_model_matches_provider_filter(model, providers)

    def _legacy_model_matches_provider_filter(self, model: dict[str, Any], providers: list[str]) -> bool:
        """レガシープロバイダーフィルター（後方互換用）"""
        if "web_api" in providers:
            if not model.get("is_local", True):  # is_localがFalseまたは存在しない
                return True

        if "local" in providers:
            if model.get("is_local", True):  # is_localがTrueまたは存在しない
                return True

        return False

    def _model_matches_function_filter(self, model: dict[str, Any], function_types: list[str]) -> bool:
        """
        モデルが機能フィルターに一致するかチェック（内部）

        Args:
            model: モデル情報（dict形式）
            function_types: 機能タイプリスト

        Returns:
            bool: フィルター一致有無
        """
        if not function_types:
            return False

        try:
            # Phase 3: ModelSelectionServiceを使用して機能判定を現代化
            if self.model_selection_service:
                models = self.model_selection_service.load_models()
                model_name = model.get("name", "")

                # 名前で一致するModelInfoを検索
                for modern_model in models:
                    if modern_model.name == model_name:
                        # ModelInfoのcapabilitiesと要求機能を比較
                        return any(func in modern_model.capabilities for func in function_types)

            # レガシーフォールバック
            return self._legacy_model_matches_function_filter(model, function_types)

        except Exception as e:
            logger.warning(f"機能フィルターエラー、レガシー処理にフォールバック: {e}")
            return self._legacy_model_matches_function_filter(model, function_types)

    def _legacy_model_matches_function_filter(
        self, model: dict[str, Any], function_types: list[str]
    ) -> bool:
        """レガシー機能フィルター（後方互換用）"""
        model_capabilities = model.get("capabilities", [])
        return any(func in model_capabilities for func in function_types)

    # ================================================================================
    # Phase 3: Enhanced Model Filtering Methods
    # ================================================================================

    def apply_advanced_model_filters(
        self, images: list[dict[str, Any]], conditions: SearchConditions
    ) -> list[dict[str, Any]]:
        """
        拡張されたモデルフィルタリング条件を適用（Phase 3新機能）

        Args:
            images: フィルタリング対象の画像リスト
            conditions: 検索条件（拡張モデルフィルターを含む）

        Returns:
            list: フィルタリング後の画像リスト
        """
        try:
            if not self._has_advanced_model_filters(conditions):
                return images  # フィルター条件がない場合はそのまま返す

            logger.info(f"高度なモデルフィルターを適用: {len(images)} 件の画像から開始")

            filtered_images = []

            for image in images:
                if self._image_matches_advanced_model_criteria(image, conditions):
                    filtered_images.append(image)

            logger.info(f"高度なモデルフィルター結果: {len(filtered_images)} 件の画像が条件に一致")
            return filtered_images

        except Exception as e:
            logger.error(f"高度なモデルフィルター適用エラー: {e}")
            return images  # エラー時は元の画像リストを返す

    def _has_advanced_model_filters(self, conditions: SearchConditions) -> bool:
        """拡張モデルフィルター条件が設定されているかチェック"""
        return bool(
            conditions.model_criteria
            or conditions.annotation_provider_filter
            or conditions.annotation_function_filter
        )

    def _image_matches_advanced_model_criteria(
        self, image: dict[str, Any], conditions: SearchConditions
    ) -> bool:
        """
        画像が高度なモデル条件に一致するかチェック

        Args:
            image: 画像情報
            conditions: 検索条件

        Returns:
            bool: 条件一致有無
        """
        try:
            # Phase 3: ModelSelectionServiceを使用してモデル情報を取得
            if not self.model_selection_service:
                logger.warning("ModelSelectionService未設定、高度フィルターをスキップ")
                return True

            available_models = self.model_selection_service.load_models()
            if not available_models:
                logger.warning("利用可能モデル情報なし、高度フィルターをスキップ")
                return True

            # アノテーション情報から使用されたモデルを特定
            used_models = self._extract_models_used_for_image(image, available_models)
            if not used_models:
                return False  # モデル情報が取得できない画像は除外

            # ModelSelectionCriteriaによるフィルタリング
            if conditions.model_criteria:
                matching_models = self.model_selection_service.filter_models(conditions.model_criteria)
                matching_model_names = {model.name for model in matching_models}

                if not any(model.name in matching_model_names for model in used_models):
                    return False

            # プロバイダーフィルタリング
            if conditions.annotation_provider_filter:
                if not self._models_match_provider_criteria(
                    used_models, conditions.annotation_provider_filter
                ):
                    return False

            # 機能フィルタリング
            if conditions.annotation_function_filter:
                if not self._models_match_function_criteria(
                    used_models, conditions.annotation_function_filter
                ):
                    return False

            return True

        except Exception as e:
            logger.error(f"高度モデル条件チェックエラー: {e}")
            return True  # エラー時は包含的に処理

    def _extract_models_used_for_image(
        self, image: dict[str, Any], available_models: list[ModelInfo]
    ) -> list[ModelInfo]:
        """
        画像で使用されたモデル情報を抽出

        Args:
            image: 画像情報
            available_models: 利用可能モデルリスト

        Returns:
            list: 使用されたModelInfoのリスト
        """
        try:
            used_models = []

            # アノテーション情報を確認
            annotations = image.get("annotations", [])

            for annotation in annotations:
                model_name = annotation.get("model_name")
                if model_name:
                    # 名前でModelInfoを検索
                    for model in available_models:
                        if model.name == model_name:
                            used_models.append(model)
                            break

            return used_models

        except Exception as e:
            logger.error(f"使用モデル抽出エラー: {e}")
            return []

    def _models_match_provider_criteria(
        self, used_models: list[ModelInfo], provider_filter: list[str]
    ) -> bool:
        """使用されたモデルがプロバイダー条件に一致するかチェック"""
        try:
            for model in used_models:
                # web_api -> requires_api_key, local -> not requires_api_key
                if "web_api" in provider_filter and model.requires_api_key:
                    return True
                if "local" in provider_filter and not model.requires_api_key:
                    return True
                # プロバイダー名による直接一致
                if model.provider.lower() in [p.lower() for p in provider_filter]:
                    return True
            return False

        except Exception as e:
            logger.error(f"プロバイダー条件チェックエラー: {e}")
            return True

    def _models_match_function_criteria(
        self, used_models: list[ModelInfo], function_filter: list[str]
    ) -> bool:
        """使用されたモデルが機能条件に一致するかチェック"""
        try:
            for model in used_models:
                if any(func in model.capabilities for func in function_filter):
                    return True
            return False

        except Exception as e:
            logger.error(f"機能条件チェックエラー: {e}")
            return True

    def create_advanced_model_search_preview(self, conditions: SearchConditions) -> dict[str, Any]:
        """
        高度なモデルフィルター条件のプレビューを作成

        Args:
            conditions: 検索条件

        Returns:
            dict: プレビュー情報
        """
        try:
            preview: dict[str, Any] = {
                "has_advanced_filters": self._has_advanced_model_filters(conditions),
                "model_criteria_summary": None,
                "provider_filter_summary": None,
                "function_filter_summary": None,
                "estimated_matches": None,
            }

            # ModelSelectionCriteriaサマリー
            if conditions.model_criteria:
                criteria = conditions.model_criteria
                summary_parts = []

                if criteria.provider:
                    summary_parts.append(f"プロバイダー: {criteria.provider}")
                if criteria.capabilities:
                    summary_parts.append(f"機能: {', '.join(criteria.capabilities)}")
                if criteria.only_recommended:
                    summary_parts.append("推奨モデルのみ")
                if criteria.only_available:
                    summary_parts.append("利用可能モデルのみ")

                preview["model_criteria_summary"] = " | ".join(summary_parts)

            # プロバイダーフィルターサマリー
            if conditions.annotation_provider_filter:
                preview["provider_filter_summary"] = ", ".join(conditions.annotation_provider_filter)

            # 機能フィルターサマリー
            if conditions.annotation_function_filter:
                preview["function_filter_summary"] = ", ".join(conditions.annotation_function_filter)

            return preview

        except Exception as e:
            logger.error(f"高度モデルフィルタープレビュー作成エラー: {e}")
            return {"has_advanced_filters": False, "error": str(e)}

    # ================================================================================
    # Phase 3: Performance Optimization Methods
    # ================================================================================

    def clear_model_cache(self) -> None:
        """
        モデルキャッシュをクリアして次回読み込み時に最新情報を取得（パフォーマンス最適化）
        """
        try:
            if self.model_selection_service:
                self.model_selection_service.refresh_models()
                logger.info("モデルキャッシュをクリアしました")
            else:
                logger.warning("ModelSelectionService未設定のためキャッシュクリアをスキップ")
        except Exception as e:
            logger.error(f"モデルキャッシュクリアエラー: {e}")

    def preload_models_for_filtering(self) -> bool:
        """
        フィルタリング処理を高速化するためにモデル情報を事前読み込み

        Returns:
            bool: 事前読み込み成功可否
        """
        try:
            if not self.model_selection_service:
                logger.warning("ModelSelectionService未設定のため事前読み込みをスキップ")
                return False

            models = self.model_selection_service.load_models()
            logger.info(f"モデル情報事前読み込み完了: {len(models)} 件")
            return len(models) > 0

        except Exception as e:
            logger.error(f"モデル事前読み込みエラー: {e}")
            return False

    def get_model_lookup_cache(self) -> dict[str, ModelInfo]:
        """
        モデル名による高速検索用キャッシュを構築

        Returns:
            dict: モデル名をキーとするModelInfo辞書
        """
        try:
            if not self.model_selection_service:
                return {}

            models = self.model_selection_service.load_models()
            return {model.name: model for model in models}

        except Exception as e:
            logger.error(f"モデル検索キャッシュ構築エラー: {e}")
            return {}

    def optimize_advanced_filtering_performance(
        self, images: list[dict[str, Any]], conditions: SearchConditions
    ) -> list[dict[str, Any]]:
        """
        高度フィルタリングのパフォーマンス最適化版

        Args:
            images: フィルタリング対象の画像リスト
            conditions: 検索条件

        Returns:
            list: フィルタリング後の画像リスト
        """
        try:
            if not self._has_advanced_model_filters(conditions):
                return images

            # パフォーマンス最適化: モデル検索キャッシュを事前構築
            model_cache = self.get_model_lookup_cache()
            if not model_cache:
                logger.warning("モデルキャッシュが空のため最適化フィルタリングをスキップ")
                return self.apply_advanced_model_filters(images, conditions)

            logger.info(f"最適化フィルタリング開始: {len(images)} 件の画像、{len(model_cache)} 件のモデル")

            # 事前に条件をチェックして処理を最適化
            filtered_models = None
            if conditions.model_criteria and self.model_selection_service:
                filtered_models = self.model_selection_service.filter_models(conditions.model_criteria)
                filtered_model_names = {model.name for model in filtered_models}

            filtered_images = []

            for image in images:
                if self._image_matches_criteria_optimized(
                    image, conditions, model_cache, filtered_model_names if filtered_models else None
                ):
                    filtered_images.append(image)

            logger.info(f"最適化フィルタリング完了: {len(filtered_images)} 件が条件に一致")
            return filtered_images

        except Exception as e:
            logger.error(f"最適化フィルタリングエラー、標準処理にフォールバック: {e}")
            return self.apply_advanced_model_filters(images, conditions)

    def _image_matches_criteria_optimized(
        self,
        image: dict[str, Any],
        conditions: SearchConditions,
        model_cache: dict[str, ModelInfo],
        filtered_model_names: set[str] | None = None,
    ) -> bool:
        """
        パフォーマンス最適化された画像条件一致チェック

        Args:
            image: 画像情報
            conditions: 検索条件
            model_cache: モデル名検索キャッシュ
            filtered_model_names: 事前フィルタリング済みモデル名セット

        Returns:
            bool: 条件一致有無
        """
        try:
            # アノテーション情報から使用モデルを高速抽出
            used_models = self._extract_models_optimized(image, model_cache)
            if not used_models:
                return False

            # ModelSelectionCriteriaによる事前フィルタリング結果を使用
            if filtered_model_names is not None:
                if not any(model.name in filtered_model_names for model in used_models):
                    return False

            # プロバイダーフィルタリング（最適化版）
            if conditions.annotation_provider_filter:
                if not self._models_match_provider_criteria(
                    used_models, conditions.annotation_provider_filter
                ):
                    return False

            # 機能フィルタリング（最適化版）
            if conditions.annotation_function_filter:
                if not self._models_match_function_criteria(
                    used_models, conditions.annotation_function_filter
                ):
                    return False

            return True

        except Exception as e:
            logger.error(f"最適化条件チェックエラー: {e}")
            return True

    def _extract_models_optimized(
        self, image: dict[str, Any], model_cache: dict[str, ModelInfo]
    ) -> list[ModelInfo]:
        """
        モデルキャッシュを使用した高速モデル抽出

        Args:
            image: 画像情報
            model_cache: モデル名検索キャッシュ

        Returns:
            list: 使用されたModelInfoのリスト
        """
        try:
            used_models = []
            annotations = image.get("annotations", [])

            for annotation in annotations:
                model_name = annotation.get("model_name")
                if model_name and model_name in model_cache:
                    used_models.append(model_cache[model_name])

            return used_models

        except Exception as e:
            logger.error(f"最適化モデル抽出エラー: {e}")
            return []

    def cleanup_legacy_dependencies(self) -> dict[str, Any]:
        """
        レガシー依存関係のクリーンアップ状況を報告

        Returns:
            dict: クリーンアップ状況レポート
        """
        try:
            report: dict[str, Any] = {
                "model_selection_service_available": self.model_selection_service is not None,
                "model_registry_available": self.model_registry is not None,
                "annotator_adapter_fallback": self.annotator_adapter is not None,
                "recommendations": [],
            }

            # ModelSelectionService利用推奨
            if not self.model_selection_service:
                report["recommendations"].append("ModelSelectionServiceの設定を推奨")

            # ModelRegistryProtocol利用推奨
            if not self.model_registry:
                report["recommendations"].append("ModelRegistryServiceProtocolの設定を推奨")

            # レガシーアダプターの段階的削除
            if self.annotator_adapter and self.model_selection_service:
                report["recommendations"].append(
                    "ModelSelectionService利用時はAnnotatorLibAdapterの段階的廃止を検討"
                )

            return report

        except Exception as e:
            logger.error(f"レガシー依存関係チェックエラー: {e}")
            return {"error": str(e)}
