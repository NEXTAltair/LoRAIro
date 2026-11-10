"""サムネイル読み込み専用ワーカー"""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QImageReader

from ...utils.log import logger
from .base import LoRAIroWorkerBase
from .progress_helper import ProgressHelper

if TYPE_CHECKING:
    from ...database.db_manager import ImageDatabaseManager

from .search_worker import SearchResult

_QtQImage = QImage


@dataclass
class ThumbnailLoadResult:
    """サムネイル読み込み結果"""

    loaded_thumbnails: list[tuple[int, "QImage"]]  # (image_id, qimage)
    failed_count: int
    total_count: int
    processing_time: float
    image_metadata: list[dict[str, Any]] | None = None  # 検索結果メタデータ（DatasetStateManager同期用）
    request_id: str | None = None  # リクエスト識別子（古い結果の破棄用）
    page_num: int | None = None  # ページ番号（ページネーション用）
    image_ids: list[int] | None = None  # 処理対象画像ID（ページ単位表示用）


class ThumbnailWorker(LoRAIroWorkerBase[ThumbnailLoadResult]):
    """サムネイル読み込み専用ワーカー"""

    _OPERATION_TYPE = "thumbnail"

    def __init__(
        self,
        search_result: "SearchResult",
        thumbnail_size: QSize,
        db_manager: "ImageDatabaseManager",
        image_id_filter: list[int] | None = None,
        request_id: str | None = None,
        page_num: int | None = None,
    ):
        super().__init__(db_manager=db_manager)
        self.search_result = search_result
        self.thumbnail_size = thumbnail_size
        self.db_manager = db_manager
        self.image_id_filter = image_id_filter
        self.request_id = request_id
        self.page_num = page_num
        self._low_res_map: dict[int, str] = {}

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
            logger.debug(
                f"サムネイル読み込み開始: page={self.page_num}, 件数={total_count}, request_id={self.request_id}"
            )
        else:
            logger.info(f"サムネイル読み込み開始: {total_count}件")

        # 進捗初期化
        loaded_thumbnails: list[tuple[int, QImage]] = []
        failed_count = 0

        # 512px 等の低解像度処理済み画像パスをバッチで一括先読み (#1542)
        target_ids = [item["id"] for item in target_metadata if isinstance(item.get("id"), int)]
        low_res_map: dict[int, str] = {}
        if target_ids and hasattr(self.db_manager, "get_low_res_image_paths_batch"):
            try:
                batch_res = self.db_manager.get_low_res_image_paths_batch(target_ids)
                if isinstance(batch_res, dict):
                    low_res_map = batch_res
            except Exception as e:
                logger.warning(f"低解像度画像パス一括取得エラー（元画像へフォールバック）: error={e}")
        self._low_res_map = low_res_map

        # 初期進捗報告
        self._report_progress_throttled(5, "サムネイル読み込み開始...", force_emit=True)

        # バッチ処理設定
        BATCH_SIZE = 25
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

            # バッチ境界での進捗報告（重要:シグナル発行はここのみ）
            force_progress_emit = batch_idx == 0 or batch_idx + 1 == total_batches
            percentage = ProgressHelper.calculate_percentage(end_idx, total_count, 5, 90)  # 5-95%
            current_item = f"バッチ {batch_idx + 1}/{total_batches}"

            self._report_progress_throttled(
                percentage,
                f"サムネイル読み込み中: {current_item}",
                current_item=current_item,
                processed_count=end_idx,
                total_count=total_count,
                force_emit=force_progress_emit,
            )

            # バッチ進捗も報告
            self._report_batch_progress_throttled(
                end_idx, total_count, current_item, force_emit=force_progress_emit
            )

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

        logger.debug(
            f"サムネイル読み込み完了: page={self.page_num}, 成功={len(loaded_thumbnails)}, "
            f"失敗={failed_count}, 処理時間={processing_time:.3f}秒"
        )

        return result

    def _process_batch(
        self,
        batch_items: list[dict[str, Any]],
        loaded_thumbnails: list[tuple[int, QImage]],
        low_res_map: dict[int, str] | None = None,
    ) -> tuple[int, int]:
        """単一バッチのサムネイルを処理する。

        Args:
            batch_items: バッチ内の画像メタデータリスト。
            loaded_thumbnails: 読み込み成功したサムネイルリスト（直接追加される）。
            low_res_map: 画像IDから低解像度画像パスへのマッピング（省略時は self._low_res_map）。

        Returns:
            (成功数, 失敗数) のタプル。
        """
        if low_res_map is not None:
            self._low_res_map = low_res_map

        batch_loaded = 0
        batch_failed = 0

        for image_data in batch_items:
            self._check_cancellation()
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

                # サムネイル読み込み（QImageReaderで縮小デコード、スレッドセーフ）
                thumbnail_path, scaled_qimage = self._decode_thumbnail_with_fallback(
                    thumbnail_path, image_data
                )
                if scaled_qimage.isNull():
                    batch_failed += 1
                    continue

                loaded_thumbnails.append((image_id, scaled_qimage))
                batch_loaded += 1

            except Exception as e:
                batch_failed += 1
                logger.error(
                    f"サムネイル読み込みエラー: image_id={image_id}, path={thumbnail_path}, error={e}"
                )
                self.db_manager.save_error_record(
                    operation_type="thumbnail",
                    error_type=type(e).__name__,
                    error_message=str(e),
                    image_id=image_id,
                    file_path=str(thumbnail_path) if thumbnail_path else None,
                )

        return batch_loaded, batch_failed

    def _is_image_smaller_than_target(self, path: Path) -> bool:
        """指定パスの画像解像度が要求サムネイルサイズより小さいか判定する (#1542 Codex P2)。"""
        if self.thumbnail_size.isEmpty():
            return False
        reader = QImageReader(str(path))
        orig_size = reader.size()
        return (
            orig_size.isValid()
            and max(orig_size.width(), orig_size.height())
            < max(self.thumbnail_size.width(), self.thumbnail_size.height())
        )

    def _decode_thumbnail_with_fallback(
        self, thumbnail_path: Path, image_data: dict[str, Any]
    ) -> tuple[Path, QImage]:
        """サムネイルをデコードし、破損またはサイズ不足時は元画像へフォールバックする (#1542 Codex P2)。"""
        scaled_qimage = self._decode_thumbnail(thumbnail_path)
        fallback_path = self._get_original_thumbnail_path(image_data)
        if not (fallback_path and fallback_path != thumbnail_path and fallback_path.exists()):
            return thumbnail_path, scaled_qimage

        should_fallback = scaled_qimage.isNull() or self._is_image_smaller_than_target(
            thumbnail_path
        )
        if should_fallback:
            return fallback_path, self._decode_thumbnail(fallback_path)
        return thumbnail_path, scaled_qimage

    def _decode_thumbnail(self, thumbnail_path: Path) -> QImage:
        """QImageReader の setScaledSize を用いて縮小デコードを行う (#1542)。"""
        if QImage is not _QtQImage:
            qimage = QImage(str(thumbnail_path))
            if qimage.isNull():
                return qimage
            return qimage.scaled(
                self.thumbnail_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

        reader = QImageReader(str(thumbnail_path))
        reader.setAutoTransform(True)
        orig_size = reader.size()
        target_scaled_size = (
            orig_size.scaled(self.thumbnail_size, Qt.AspectRatioMode.KeepAspectRatio)
            if orig_size.isValid() and not self.thumbnail_size.isEmpty()
            else QSize()
        )
        if target_scaled_size.isValid():
            reader.setScaledSize(target_scaled_size)
        qimage = reader.read()
        if qimage.isNull():
            qimage = QImage(str(thumbnail_path))
        if qimage.isNull():
            return qimage
        if not self.thumbnail_size.isEmpty() and (
            qimage.width() > self.thumbnail_size.width()
            or qimage.height() > self.thumbnail_size.height()
            or (target_scaled_size.isValid() and qimage.size() != target_scaled_size)
        ):
            qimage = qimage.scaled(
                self.thumbnail_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        return qimage

    def _get_original_thumbnail_path(self, image_data: dict[str, Any]) -> Path | None:
        """元画像 (stored_image_path) の Path を解決して返す (#1542)。"""
        try:
            stored_path = image_data.get("stored_image_path")
            if isinstance(stored_path, str | Path) and stored_path:
                from ...database.db_core import resolve_stored_path

                return resolve_stored_path(str(stored_path))
        except Exception as e:
            logger.warning(f"元画像パス取得エラー: image_id={image_data.get('id')}, error={e}")
        return None

    def _resolve_low_res_path(
        self, image_id: int, low_res_map: dict[int, str] | None = None
    ) -> Path | None:
        """低解像度画像のパスを解決して存在を確認する。"""
        from ...database.db_core import resolve_stored_path

        effective_low_res_map = low_res_map if low_res_map is not None else self._low_res_map
        if not isinstance(effective_low_res_map, dict):
            return None
        low_res_stored = effective_low_res_map.get(image_id)
        if not (isinstance(low_res_stored, str | Path) and low_res_stored):
            return None
        low_res_path = resolve_stored_path(str(low_res_stored))
        return low_res_path if low_res_path.exists() else None

    def _get_thumbnail_path(
        self,
        image_data: dict[str, Any],
        image_id: int,
        low_res_map: dict[int, str] | None = None,
    ) -> Path | None:
        """サムネイル用の最適な画像パスを取得する。

        Args:
            image_data: 画像メタデータ辞書。
            image_id: 画像ID。
            low_res_map: 画像IDから低解像度画像パスへのマッピング（省略時は self._low_res_map）。

        Returns:
            サムネイル画像のPathオブジェクト。取得できない場合はNone。
        """
        try:
            from ...database.db_core import resolve_stored_path

            low_res_path = self._resolve_low_res_path(image_id, low_res_map)
            low_res_candidate: Path | None = None
            if low_res_path is not None:
                if self._is_image_smaller_than_target(low_res_path):
                    low_res_candidate = low_res_path
                else:
                    return low_res_path

            stored_path = image_data.get("stored_image_path")
            if isinstance(stored_path, str | Path) and stored_path:
                stored_resolved = resolve_stored_path(str(stored_path))
                if stored_resolved.exists():
                    return stored_resolved
                return low_res_candidate or stored_resolved

            return low_res_candidate

        except Exception as e:
            logger.warning(f"サムネイルパス取得エラー: image_id={image_id}, error={e}")

        return None
