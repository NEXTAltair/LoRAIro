# src/lorairo/workers/database_worker.py

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap

from ...utils.log import logger
from .base import LoRAIroWorkerBase


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
        self,
        directory: Path,
        db_manager: "ImageDatabaseManager",
        fsm: "FileSystemManager",
    ):
        super().__init__()
        self.directory = directory
        self.db_manager = db_manager
        self.fsm = fsm

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
        base_path = image_path.with_suffix("")  # 拡張子を除いたパス

        # .txtファイル（タグ）の処理
        txt_file = base_path.with_suffix(".txt")
        if txt_file.exists():
            try:
                tags_content = txt_file.read_text(encoding="utf-8").strip()
                if tags_content:
                    # カンマ区切りのタグを分割
                    tag_strings = [tag.strip() for tag in tags_content.split(",") if tag.strip()]
                    if tag_strings:
                        # TagAnnotationDataのリストを作成
                        from ...database.db_repository import TagAnnotationData

                        tags_data: list[TagAnnotationData] = []
                        for tag_string in tag_strings:
                            tag_data: TagAnnotationData = {
                                "tag_id": None,  # 新規タグとして追加
                                "model_id": None,  # ファイルからの読み込みなのでモデルなし
                                "tag": tag_string,
                                "confidence_score": None,
                                "existing": True,  # ファイルから読み込んだ既存タグ
                                "is_edited_manually": False,
                            }
                            tags_data.append(tag_data)

                        self.db_manager.save_tags(image_id, tags_data)
                        logger.info(f"タグを追加: {image_path.name} - {len(tag_strings)}個のタグ")
                    else:
                        logger.debug(f"タグファイルが空: {txt_file.name}")
            except Exception as e:
                logger.error(f"タグファイル読み込みエラー: {txt_file.name} - {e}")

        # .captionファイル（キャプション）の処理
        caption_file = base_path.with_suffix(".caption")
        if caption_file.exists():
            try:
                caption_content = caption_file.read_text(encoding="utf-8").strip()
                if caption_content:
                    # CaptionAnnotationDataを作成
                    from ...database.db_repository import CaptionAnnotationData

                    caption_data: CaptionAnnotationData = {
                        "model_id": None,  # ファイルからの読み込みなのでモデルなし
                        "caption": caption_content,
                        "existing": False,  # 新規キャプション
                        "is_edited_manually": False,
                    }
                    self.db_manager.save_captions(image_id, [caption_data])
                    logger.info(f"キャプションを追加: {image_path.name}")
                else:
                    logger.debug(f"キャプションファイルが空: {caption_file.name}")
            except Exception as e:
                logger.error(f"キャプションファイル読み込みエラー: {caption_file.name} - {e}")


@dataclass
class SearchResult:
    """検索結果"""

    image_metadata: list[dict]
    total_count: int
    search_time: float
    filter_conditions: dict


class SearchWorker(LoRAIroWorkerBase[SearchResult]):
    """データベース検索専用ワーカー"""

    def __init__(self, db_manager: "ImageDatabaseManager", filter_conditions: dict):
        super().__init__()
        self.db_manager = db_manager
        self.filter_conditions = filter_conditions

    def execute(self) -> SearchResult:
        """検索処理を実行"""
        import time

        start_time = time.time()

        # 検索開始
        self._report_progress(20, "データベース検索を開始...")

        # フィルター条件の解析
        tags = self.filter_conditions.get("tags", [])
        caption = self.filter_conditions.get("caption", "")
        resolution = self.filter_conditions.get("resolution", 0)
        use_and = self.filter_conditions.get("use_and", True)
        date_range = self.filter_conditions.get("date_range", (None, None))
        include_untagged = self.filter_conditions.get("include_untagged", False)

        # 検索実行
        self._report_progress(60, "フィルター条件を適用中...")

        # キャンセルチェック
        self._check_cancellation()

        image_metadata, total_count = self.db_manager.get_images_by_filter(
            tags=tags,
            caption=caption,
            resolution=resolution,
            use_and=use_and,
            start_date=date_range[0],
            end_date=date_range[1],
            include_untagged=include_untagged,
        )

        search_time = time.time() - start_time

        # 完了
        self._report_progress(100, f"検索完了: {total_count}件の画像が見つかりました")

        result = SearchResult(
            image_metadata=image_metadata,
            total_count=total_count,
            search_time=search_time,
            filter_conditions=self.filter_conditions,
        )

        logger.info(f"検索完了: {total_count}件, 処理時間={search_time:.3f}秒")

        return result

    def _process_associated_files(self, image_path: Path, image_id: int) -> None:
        """
        画像ファイルに関連する.txtと.captionファイルを処理し、データベースに登録する

        Args:
            image_path: 画像ファイルのパス
            image_id: データベースの画像ID
        """
        base_path = image_path.with_suffix("")  # 拡張子を除いたパス

        # .txtファイル（タグ）の処理
        txt_file = base_path.with_suffix(".txt")
        if txt_file.exists():
            try:
                tags_content = txt_file.read_text(encoding="utf-8").strip()
                if tags_content:
                    # カンマ区切りのタグを分割
                    tag_strings = [tag.strip() for tag in tags_content.split(",") if tag.strip()]
                    if tag_strings:
                        # TagAnnotationDataのリストを作成
                        from ...database.db_repository import TagAnnotationData

                        tags_data: list[TagAnnotationData] = []
                        for tag_string in tag_strings:
                            tag_data: TagAnnotationData = {
                                "tag_id": None,  # 新規タグとして追加
                                "model_id": None,  # ファイルからの読み込みなのでモデルなし
                                "tag": tag_string,
                                "confidence_score": None,
                                "existing": True,  # ファイルから読み込んだ既存タグ
                                "is_edited_manually": False,
                            }
                            tags_data.append(tag_data)

                        self.db_manager.save_tags(image_id, tags_data)
                        logger.info(f"タグを追加: {image_path.name} - {len(tag_strings)}個のタグ")
                    else:
                        logger.debug(f"タグファイルが空: {txt_file.name}")
            except Exception as e:
                logger.error(f"タグファイル読み込みエラー: {txt_file.name} - {e}")

        # .captionファイル（キャプション）の処理
        caption_file = base_path.with_suffix(".caption")
        if caption_file.exists():
            try:
                caption_content = caption_file.read_text(encoding="utf-8").strip()
                if caption_content:
                    # CaptionAnnotationDataを作成
                    from ...database.db_repository import CaptionAnnotationData

                    caption_data: CaptionAnnotationData = {
                        "model_id": None,  # ファイルからの読み込みなのでモデルなし
                        "caption": caption_content,
                        "existing": False,  # 新規キャプション
                        "is_edited_manually": False,
                    }
                    self.db_manager.save_captions(image_id, [caption_data])
                    logger.info(f"キャプションを追加: {image_path.name}")
                else:
                    logger.debug(f"キャプションファイルが空: {caption_file.name}")
            except Exception as e:
                logger.error(f"キャプションファイル読み込みエラー: {caption_file.name} - {e}")


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
        image_metadata: list[dict],
        thumbnail_size: QSize,
        db_manager: "ImageDatabaseManager",
    ):
        super().__init__()
        self.image_metadata = image_metadata
        self.thumbnail_size = thumbnail_size
        self.db_manager = db_manager

    def execute(self) -> ThumbnailLoadResult:
        """サムネイル読み込み処理を実行"""
        import time

        start_time = time.time()
        total_count = len(self.image_metadata)

        if total_count == 0:
            logger.warning("サムネイル読み込み対象がありません")
            return ThumbnailLoadResult([], 0, 0, 0.0)

        logger.info(f"サムネイル読み込み開始: {total_count}件")

        # 進捗初期化
        loaded_thumbnails = []
        failed_count = 0

        # 初期進捗報告
        self._report_progress(5, "サムネイル読み込み開始...")

        for i, image_data in enumerate(self.image_metadata):
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

                # 進捗報告
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

    def _get_thumbnail_path(self, image_data: dict, image_id: int) -> Path | None:
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
