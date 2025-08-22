# src/lorairo/workers/database_worker.py

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap

from ...annotations.existing_file_reader import ExistingFileReader
from ...utils.log import logger
from .base import LoRAIroWorkerBase

if TYPE_CHECKING:
    from ...database.db_manager import ImageDatabaseManager
    from ...services.search_models import SearchConditions
    from ...storage.file_system import FileSystemManager


@dataclass
class DatabaseRegistrationResult:
    """データベース登録結果"""

    registered_count: int
    skipped_count: int
    error_count: int
    processed_paths: list[Path]
    total_processing_time: float


class DatabaseRegistrationWorker(LoRAIroWorkerBase[DatabaseRegistrationResult]):
    """データベース登録専用ワーカー"""

    def __init__(
        self, directory: Path, db_manager: "ImageDatabaseManager", fsm: "FileSystemManager"
    ) -> None:
        super().__init__()
        self.directory = directory
        self.db_manager = db_manager
        self.fsm = fsm
        self.file_reader = ExistingFileReader()

    def execute(self) -> DatabaseRegistrationResult:
        """データベース登録処理を実行"""
        import time

        start_time = time.time()

        # 画像ファイル一覧取得
        self._report_progress(5, "画像ファイルを検索中...")
        image_files = list(self.fsm.get_image_files(self.directory))
        total_count = len(image_files)

        if total_count == 0:
            logger.warning(f"画像ファイルが見つかりません: {self.directory}")
            return DatabaseRegistrationResult(0, 0, 0, [], 0.0)

        logger.info(f"登録対象画像: {total_count}件")

        # 進捗初期化
        registered = 0
        skipped = 0
        errors = 0
        processed_paths = []

        # バッチ処理開始
        self._report_progress(10, f"バッチ登録開始: {total_count}件")

        for i, image_path in enumerate(image_files):
            # キャンセルチェック
            self._check_cancellation()

            try:
                # バッチ進捗報告
                self._report_batch_progress(i + 1, total_count, image_path.name)

                # 重複チェック
                duplicate_image_id = self.db_manager.detect_duplicate_image(image_path)
                if duplicate_image_id:
                    # 重複画像でも関連ファイル（.txt/.caption）を処理
                    self._process_associated_files(image_path, duplicate_image_id)
                    skipped += 1
                    logger.debug(f"スキップ (重複): {image_path} - 関連ファイルは処理")
                else:
                    # データベース登録
                    result = self.db_manager.register_original_image(image_path, self.fsm)
                    if result:
                        image_id, _ = result
                        # 関連ファイル（.txt/.caption）の処理
                        self._process_associated_files(image_path, image_id)
                        registered += 1
                        processed_paths.append(image_path)
                        logger.debug(f"登録完了: {image_path}")
                    else:
                        errors += 1
                        logger.error(f"画像登録失敗: {image_path}")

                # 進捗報告
                percentage = 10 + int((i + 1) / total_count * 85)  # 10-95%
                self._report_progress(
                    percentage,
                    f"登録中: {image_path.name}",
                    current_item=str(image_path),
                    processed_count=i + 1,
                    total_count=total_count,
                )

            except Exception as e:
                errors += 1
                logger.error(f"画像登録エラー: {image_path}, {e}")

        # 完了処理
        processing_time = time.time() - start_time
        self._report_progress(100, "データベース登録完了")

        result = DatabaseRegistrationResult(
            registered_count=registered,
            skipped_count=skipped,
            error_count=errors,
            processed_paths=processed_paths,
            total_processing_time=processing_time,
        )

        logger.info(
            f"データベース登録完了: 登録={registered}, スキップ={skipped}, "
            f"エラー={errors}, 処理時間={processing_time:.2f}秒"
        )

        return result

    def _process_associated_files(self, image_path: Path, image_id: int) -> None:
        """
        画像ファイルに関連する.txtと.captionファイルを処理し、データベースに登録する

        Args:
            image_path: 画像ファイルのパス
            image_id: データベースの画像ID
        """
        annotations = self.file_reader.get_existing_annotations(image_path)
        if not annotations:
            return

        tags = annotations.get("tags", [])
        if tags:
            from ...database.db_repository import TagAnnotationData

            tags_data: list[TagAnnotationData] = [
                {
                    "tag_id": None,
                    "model_id": None,
                    "tag": tag,
                    "confidence_score": None,
                    "existing": True,
                    "is_edited_manually": False,
                }
                for tag in tags
            ]
            self.db_manager.save_tags(image_id, tags_data)
            logger.info(f"タグを追加: {image_path.name} - {len(tags)}個のタグ")

        captions = annotations.get("captions", [])
        if captions:
            from ...database.db_repository import CaptionAnnotationData

            captions_data: list[CaptionAnnotationData] = [
                {
                    "model_id": None,
                    "caption": caption,
                    "existing": False,
                    "is_edited_manually": False,
                }
                for caption in captions
            ]
            self.db_manager.save_captions(image_id, captions_data)
            logger.info(f"キャプションを追加: {image_path.name}")


@dataclass
class SearchResult:
    """検索結果"""

    image_metadata: list[dict[str, Any]]
    total_count: int
    search_time: float
    filter_conditions: dict[str, Any]


class SearchWorker(LoRAIroWorkerBase[SearchResult]):
    """データベース検索専用ワーカー"""

    def __init__(self, db_manager: "ImageDatabaseManager", search_conditions: "SearchConditions"):
        super().__init__()
        self.db_manager = db_manager
        self.search_conditions = search_conditions

    def execute(self) -> SearchResult:
        """検索処理を実行"""
        import time

        start_time = time.time()

        # 検索開始
        self._report_progress(20, "データベース検索を開始...")

        # SearchConditionsから条件を抽出
        if self.search_conditions.search_type == "tags":
            tags = self.search_conditions.keywords
            caption = None
        elif self.search_conditions.search_type == "caption":
            tags = None
            caption = self.search_conditions.keywords[0] if self.search_conditions.keywords else ""
        else:
            tags = None
            caption = None

        # 解像度フィルター
        resolution = self.search_conditions._resolve_resolution()

        # タグロジック
        use_and = self.search_conditions.tag_logic == "and"

        # 日付範囲
        date_range_start = self.search_conditions.date_range_start
        date_range_end = self.search_conditions.date_range_end

        # その他のオプション
        include_untagged = self.search_conditions.only_untagged

        # 検索実行
        self._report_progress(60, "フィルター条件を適用中...")

        # キャンセルチェック
        self._check_cancellation()

        image_metadata, total_count = self.db_manager.get_images_by_filter(
            tags=tags,
            caption=caption,
            resolution=resolution,
            use_and=use_and,
            start_date=date_range_start.isoformat() if date_range_start else None,
            end_date=date_range_end.isoformat() if date_range_end else None,
            include_untagged=include_untagged,
        )

        # Option B: バッチ進捗報告を追加（検索結果処理）
        if total_count > 0:
            # 検索結果を一件ずつ処理するバッチ進捗として報告
            batch_size = min(100, total_count)  # 100件ずつバッチ処理をシミュレート
            for i in range(0, total_count, batch_size):
                self._check_cancellation()  # キャンセルチェック

                current_batch = min(i + batch_size, total_count)
                # ファイル名の代わりに件数情報を使用
                self._report_batch_progress(
                    current_batch, total_count, f"search_batch_{i // batch_size + 1}"
                )

        search_time = time.time() - start_time

        # 完了
        self._report_progress(100, f"検索完了: {total_count}件の画像が見つかりました")

        result = SearchResult(
            image_metadata=image_metadata,
            total_count=total_count,
            search_time=search_time,
            filter_conditions=self.search_conditions,
        )

        logger.info(f"検索完了: {total_count}件, 処理時間={search_time:.3f}秒")

        return result


@dataclass
class ThumbnailLoadResult:
    """サムネイル読み込み結果"""

    loaded_thumbnails: list[tuple[int, QPixmap]]  # (image_id, pixmap)
    failed_count: int
    total_count: int
    processing_time: float


class ThumbnailWorker(LoRAIroWorkerBase[ThumbnailLoadResult]):
    """サムネイル読み込み専用ワーカー"""

    def __init__(
        self,
        search_result: "SearchResult",
        thumbnail_size: QSize,
        db_manager: "ImageDatabaseManager",
    ):
        super().__init__()
        self.search_result = search_result
        self.thumbnail_size = thumbnail_size
        self.db_manager = db_manager

    def execute(self) -> ThumbnailLoadResult:
        """サムネイル読み込み処理を実行"""
        import time

        start_time = time.time()
        total_count = len(self.search_result.image_metadata)

        if total_count == 0:
            logger.warning("サムネイル読み込み対象がありません")
            return ThumbnailLoadResult([], 0, 0, 0.0)

        logger.info(f"サムネイル読み込み開始: {total_count}件")

        # 進捗初期化
        loaded_thumbnails = []
        failed_count = 0

        # 初期進捗報告
        self._report_progress(5, "サムネイル読み込み開始...")

        for i, image_data in enumerate(self.search_result.image_metadata):
            # キャンセルチェック
            self._check_cancellation()

            try:
                image_id = image_data.get("id")
                if not image_id:
                    failed_count += 1
                    continue

                # サムネイル用の最適な画像パスを取得
                thumbnail_path = self._get_thumbnail_path(image_data, image_id)

                if not thumbnail_path or not thumbnail_path.exists():
                    failed_count += 1
                    logger.debug(f"サムネイル画像が見つかりません: {thumbnail_path}")
                    continue

                # サムネイル読み込み
                pixmap = QPixmap(str(thumbnail_path))
                if pixmap.isNull():
                    failed_count += 1
                    logger.debug(f"サムネイル読み込み失敗: {thumbnail_path}")
                    continue

                # サイズ調整
                scaled_pixmap = pixmap.scaled(
                    self.thumbnail_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )

                loaded_thumbnails.append((image_id, scaled_pixmap))

                # Option B: バッチ進捗報告を追加
                filename = thumbnail_path.name if thumbnail_path else f"image_{image_id}"
                self._report_batch_progress(i + 1, total_count, filename)

                # 従来の進捗報告も継続
                percentage = 5 + int((i + 1) / total_count * 90)  # 5-95%
                self._report_progress(
                    percentage,
                    f"サムネイル読み込み中: {i + 1}/{total_count}",
                    current_item=str(thumbnail_path),
                    processed_count=i + 1,
                    total_count=total_count,
                )

            except Exception as e:
                failed_count += 1
                logger.error(f"サムネイル読み込みエラー: {e}")

        # 完了処理
        processing_time = time.time() - start_time
        self._report_progress(100, "サムネイル読み込み完了")

        result = ThumbnailLoadResult(
            loaded_thumbnails=loaded_thumbnails,
            failed_count=failed_count,
            total_count=total_count,
            processing_time=processing_time,
        )

        logger.info(
            f"サムネイル読み込み完了: 成功={len(loaded_thumbnails)}, 失敗={failed_count}, "
            f"処理時間={processing_time:.3f}秒"
        )

        return result

    def _get_thumbnail_path(self, image_data: dict[str, Any], image_id: int) -> Path | None:
        """サムネイル用の最適な画像パスを取得"""
        try:
            # 512px画像が利用可能な場合はそれを使用
            existing_512px = self.db_manager.check_processed_image_exists(image_id, 512)
            if existing_512px and "stored_image_path" in existing_512px:
                from ...database.db_core import resolve_stored_path

                path = resolve_stored_path(existing_512px["stored_image_path"])
                if path.exists():
                    return path

            # フォールバック: 元画像を使用
            stored_path = image_data.get("stored_image_path")
            if stored_path:
                from ...database.db_core import resolve_stored_path

                return resolve_stored_path(stored_path)

        except Exception as e:
            logger.warning(f"サムネイルパス取得エラー: {e}")

        return None
