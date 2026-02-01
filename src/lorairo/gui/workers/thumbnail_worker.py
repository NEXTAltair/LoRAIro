"""サムネイル読み込み専用ワーカー"""

import traceback
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage

from ...utils.log import logger
from .base import LoRAIroWorkerBase
from .progress_helper import ProgressHelper

if TYPE_CHECKING:
    from ...database.db_manager import ImageDatabaseManager

from .search_worker import SearchResult


@dataclass
class ThumbnailLoadResult:
    """サムネイル読み込み結果"""

    loaded_thumbnails: list[tuple[int, "QImage"]]  # (image_id, qimage)
    failed_count: int
    total_count: int
    processing_time: float
    image_metadata: list[dict[str, Any]] = None  # 検索結果メタデータ（DatasetStateManager同期用）


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
        """サムネイル読み込み処理を実行（バッチ処理最適化版）"""
        import time

        start_time = time.time()
        total_count = len(self.search_result.image_metadata)

        if total_count == 0:
            logger.warning("サムネイル読み込み対象がありません")
            return ThumbnailLoadResult([], 0, 0, 0.0, [])

        logger.info(f"サムネイル読み込み開始: {total_count}件")

        # 進捗初期化
        loaded_thumbnails = []
        failed_count = 0

        # 初期進捗報告
        self._report_progress_throttled(5, "サムネイル読み込み開始...", force_emit=True)

        # バッチ処理設定
        BATCH_SIZE = 100
        batch_boundaries = ProgressHelper.get_batch_boundaries(total_count, BATCH_SIZE)
        total_batches = len(batch_boundaries)

        logger.info(f"バッチ処理開始: {total_batches}バッチ（バッチサイズ: {BATCH_SIZE}）")

        # バッチ単位で処理
        for batch_idx, (start_idx, end_idx) in enumerate(batch_boundaries):
            # キャンセルチェック（バッチ境界で実行）
            self._check_cancellation()

            # 現在のバッチを取得
            batch_items = self.search_result.image_metadata[start_idx:end_idx]
            batch_loaded, batch_failed = self._process_batch(batch_items, loaded_thumbnails)

            # バッチ統計更新
            failed_count += batch_failed

            # バッチ境界での進捗報告（重要：シグナル発行はここのみ）
            percentage = ProgressHelper.calculate_percentage(end_idx, total_count, 5, 90)  # 5-95%
            current_item = f"バッチ {batch_idx + 1}/{total_batches}"

            self._report_progress_throttled(
                percentage,
                f"サムネイル読み込み中: {current_item}",
                current_item=current_item,
                processed_count=end_idx,
                total_count=total_count,
            )

            # バッチ進捗も報告
            self._report_batch_progress(end_idx, total_count, current_item)

            logger.debug(
                f"バッチ {batch_idx + 1}/{total_batches} 完了: 成功={batch_loaded}, 失敗={batch_failed}"
            )

        # 完了処理
        processing_time = time.time() - start_time
        self._report_progress_throttled(100, "サムネイル読み込み完了", force_emit=True)

        result = ThumbnailLoadResult(
            loaded_thumbnails=loaded_thumbnails,
            failed_count=failed_count,
            total_count=total_count,
            processing_time=processing_time,
            image_metadata=self.search_result.image_metadata,
        )

        logger.info(
            f"サムネイル読み込み完了: 成功={len(loaded_thumbnails)}, 失敗={failed_count}, "
            f"処理時間={processing_time:.3f}秒, バッチ数={total_batches}"
        )

        return result

    def _process_batch(
        self,
        batch_items: list[dict[str, Any]],
        loaded_thumbnails: list[tuple[int, QImage]],
    ) -> tuple[int, int]:
        """単一バッチのサムネイルを処理する。

        Args:
            batch_items: バッチ内の画像メタデータリスト。
            loaded_thumbnails: 読み込み成功したサムネイルリスト（直接追加される）。

        Returns:
            (成功数, 失敗数) のタプル。
        """
        batch_loaded = 0
        batch_failed = 0

        for image_data in batch_items:
            image_id = image_data.get("id")
            thumbnail_path = None
            try:
                if not image_id:
                    batch_failed += 1
                    continue

                # サムネイル用の最適な画像パスを取得
                thumbnail_path = self._get_thumbnail_path(image_data, image_id)

                if not thumbnail_path or not thumbnail_path.exists():
                    batch_failed += 1
                    continue

                # サムネイル読み込み（QImageでスレッドセーフ）
                qimage = QImage(str(thumbnail_path))
                if qimage.isNull():
                    batch_failed += 1
                    continue

                # サイズ調整
                scaled_qimage = qimage.scaled(
                    self.thumbnail_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )

                loaded_thumbnails.append((image_id, scaled_qimage))
                batch_loaded += 1

            except Exception as e:
                batch_failed += 1
                logger.error(f"サムネイル読み込みエラー: {e}")

                # エラーレコード保存（二次エラー対策付き）
                try:
                    self.db_manager.save_error_record(
                        operation_type="thumbnail",
                        error_type=type(e).__name__,
                        error_message=str(e),
                        image_id=image_id,
                        stack_trace=traceback.format_exc(),
                        file_path=str(thumbnail_path) if thumbnail_path else None,
                        model_name=None,
                    )
                except Exception as save_error:
                    logger.error(f"エラーレコード保存失敗（二次エラー）: {save_error}")

        return batch_loaded, batch_failed

    def _get_thumbnail_path(self, image_data: dict[str, Any], image_id: int):
        """サムネイル用の最適な画像パスを取得する。

        Args:
            image_data: 画像メタデータ辞書。
            image_id: 画像ID。

        Returns:
            サムネイル画像のPathオブジェクト。取得できない場合はNone。
        """
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
