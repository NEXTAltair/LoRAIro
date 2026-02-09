"""サムネイル読み込み専用ワーカー"""

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
    request_id: str | None = None  # リクエスト識別子（古い結果の破棄用）
    page_num: int | None = None  # ページ番号（ページネーション用）
    image_ids: list[int] | None = None  # 処理対象画像ID（ページ単位表示用）


class ThumbnailWorker(LoRAIroWorkerBase[ThumbnailLoadResult]):
    """サムネイル読み込み専用ワーカー"""

    def __init__(
        self,
        search_result: "SearchResult",
        thumbnail_size: QSize,
        db_manager: "ImageDatabaseManager",
        image_id_filter: list[int] | None = None,
        request_id: str | None = None,
        page_num: int | None = None,
    ):
        super().__init__()
        self.search_result = search_result
        self.thumbnail_size = thumbnail_size
        self.db_manager = db_manager
        self.image_id_filter = image_id_filter
        self.request_id = request_id
        self.page_num = page_num

    def execute(self) -> ThumbnailLoadResult:
        """サムネイル読み込み処理を実行（バッチ処理最適化版）"""
        import time

        start_time = time.time()
        source_metadata = self.search_result.image_metadata
        target_metadata = source_metadata

        if self.image_id_filter:
            metadata_by_id = {
                item.get("id"): item for item in source_metadata if item.get("id") is not None
            }
            target_metadata = [
                metadata_by_id[image_id] for image_id in self.image_id_filter if image_id in metadata_by_id
            ]

        total_count = len(target_metadata)

        if total_count == 0:
            logger.warning(
                f"サムネイル読み込み対象がありません: page={self.page_num}, "
                f"filter_count={len(self.image_id_filter) if self.image_id_filter else 0}, "
                f"source_count={len(source_metadata)}"
            )
            return ThumbnailLoadResult(
                loaded_thumbnails=[],
                failed_count=0,
                total_count=0,
                processing_time=0.0,
                image_metadata=target_metadata,
                request_id=self.request_id,
                page_num=self.page_num,
                image_ids=[],
            )

        if self.page_num is not None:
            logger.info(
                f"サムネイル読み込み開始: page={self.page_num}, 件数={total_count}, request_id={self.request_id}"
            )
        else:
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

        logger.debug(f"バッチ処理開始: {total_batches}バッチ（バッチサイズ: {BATCH_SIZE}）")

        # バッチ単位で処理
        for batch_idx, (start_idx, end_idx) in enumerate(batch_boundaries):
            # キャンセルチェック（バッチ境界で実行）
            self._check_cancellation()

            # 現在のバッチを取得
            batch_items = target_metadata[start_idx:end_idx]
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
            image_metadata=target_metadata,
            request_id=self.request_id,
            page_num=self.page_num,
            image_ids=[
                item_id for item_id in (item.get("id") for item in target_metadata) if item_id is not None
            ],
        )

        logger.info(
            f"サムネイル読み込み完了: page={self.page_num}, 成功={len(loaded_thumbnails)}, "
            f"失敗={failed_count}, 処理時間={processing_time:.3f}秒"
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

                if not thumbnail_path:
                    batch_failed += 1
                    continue

                if not thumbnail_path.exists():
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
                # ワーカースレッドではDB保存不可（スレッドセーフティ）、ログのみ
                logger.error(
                    f"サムネイル読み込みエラー: image_id={image_id}, path={thumbnail_path}, error={e}"
                )

        return batch_loaded, batch_failed

    def _get_thumbnail_path(self, image_data: dict[str, Any], image_id: int):
        """サムネイル用の最適な画像パスを取得する。

        Args:
            image_data: 画像メタデータ辞書。
            image_id: 画像ID。

        Returns:
            サムネイル画像のPathオブジェクト。取得できない場合はNone。

        Note:
            ワーカースレッドで実行されるため、db_managerへのアクセスは禁止。
            SQLite接続はスレッド間で共有できない (sqlite3.InterfaceError回避)。
            メタデータ内の stored_image_path を直接使用する。
        """
        try:
            # メタデータから直接パスを取得（DB呼び出しはスレッドセーフでないため禁止）
            stored_path = image_data.get("stored_image_path")
            if stored_path:
                from ...database.db_core import resolve_stored_path

                return resolve_stored_path(stored_path)

        except Exception as e:
            logger.warning(f"サムネイルパス取得エラー: image_id={image_id}, error={e}")

        return None
