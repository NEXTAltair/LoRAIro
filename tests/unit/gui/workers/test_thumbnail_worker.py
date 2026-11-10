"""ThumbnailWorker のユニットテスト。"""

from unittest.mock import Mock

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QImage

from lorairo.gui.workers.base import CancellationError
from lorairo.gui.workers.search_worker import SearchResult
from lorairo.gui.workers.thumbnail_worker import ThumbnailWorker
from lorairo.services.search_models import SearchConditions


def _build_search_result(metadata: list[dict]) -> SearchResult:
    return SearchResult(
        image_metadata=metadata,
        total_count=len(metadata),
        search_time=0.1,
        filter_conditions=SearchConditions(search_type="tags", keywords=[], tag_logic="and"),
    )


def _fake_process_batch(batch_items, loaded_thumbnails):
    for image_data in batch_items:
        image_id = image_data.get("id")
        qimage = QImage(16, 16, QImage.Format.Format_RGB32)
        qimage.fill(0xFFAA00)
        loaded_thumbnails.append((image_id, qimage))
    return len(batch_items), 0


class TestThumbnailWorkerPaging:
    """ページ単位サムネイル読み込みのテスト。"""

    def test_execute_with_image_id_filter_keeps_order(self):
        metadata = [
            {"id": 1, "stored_image_path": "/test/1.png"},
            {"id": 2, "stored_image_path": "/test/2.png"},
            {"id": 3, "stored_image_path": "/test/3.png"},
        ]
        search_result = _build_search_result(metadata)
        db_manager = Mock()

        worker = ThumbnailWorker(
            search_result=search_result,
            thumbnail_size=QSize(128, 128),
            db_manager=db_manager,
            image_id_filter=[3, 1],
            request_id="req_page_1",
            page_num=1,
        )
        worker._process_batch = _fake_process_batch  # type: ignore[method-assign]

        result = worker.execute()

        assert result.total_count == 2
        assert result.request_id == "req_page_1"
        assert result.page_num == 1
        assert result.image_ids == [3, 1]
        assert [item["id"] for item in result.image_metadata] == [3, 1]
        assert [image_id for image_id, _ in result.loaded_thumbnails] == [3, 1]

    def test_execute_with_nonexistent_filter_returns_empty_result(self):
        metadata = [{"id": 1, "stored_image_path": "/test/1.png"}]
        search_result = _build_search_result(metadata)
        db_manager = Mock()

        worker = ThumbnailWorker(
            search_result=search_result,
            thumbnail_size=QSize(128, 128),
            db_manager=db_manager,
            image_id_filter=[999],
            request_id="req_empty",
            page_num=5,
        )

        result = worker.execute()

        assert result.total_count == 0
        assert result.failed_count == 0
        assert result.page_num == 5
        assert result.request_id == "req_empty"
        assert result.image_ids == []
        assert result.loaded_thumbnails == []

    def test_execute_without_filter_uses_all_metadata(self):
        metadata = [
            {"id": 10, "stored_image_path": "/test/10.png"},
            {"id": 20, "stored_image_path": "/test/20.png"},
        ]
        search_result = _build_search_result(metadata)
        db_manager = Mock()

        worker = ThumbnailWorker(
            search_result=search_result,
            thumbnail_size=QSize(128, 128),
            db_manager=db_manager,
            request_id="req_all",
            page_num=2,
        )
        worker._process_batch = _fake_process_batch  # type: ignore[method-assign]

        result = worker.execute()

        assert result.total_count == 2
        assert result.image_ids == [10, 20]
        assert [image_id for image_id, _ in result.loaded_thumbnails] == [10, 20]

    def test_process_batch_checks_cancellation_per_image(self):
        """バッチ境界 (100枚) を待たずに1枚ごとのループで協調キャンセルが効く (#1540)。"""
        metadata = [{"id": idx, "stored_image_path": f"/test/{idx}.png"} for idx in range(1, 6)]
        search_result = _build_search_result(metadata)
        db_manager = Mock()

        worker = ThumbnailWorker(
            search_result=search_result,
            thumbnail_size=QSize(128, 128),
            db_manager=db_manager,
            request_id="req_cancel_mid_page",
            page_num=1,
        )

        processed_ids: list[int] = []

        def fake_get_thumbnail_path(image_data: dict, image_id: int):
            processed_ids.append(image_id)
            if image_id == 2:
                worker.cancel()
            return None

        worker._get_thumbnail_path = fake_get_thumbnail_path  # type: ignore[method-assign]

        with pytest.raises(CancellationError, match="キャンセル"):
            worker.execute()

        # 2枚目処理中に cancel() されたため、3枚目以降は処理されない
        assert processed_ids == [1, 2]

    def test_execute_prefetches_low_res_paths_batch_and_falls_back_when_missing(self, tmp_path):
        """512px低解像度パスを一括先読みし、存在すれば優先・未存在なら元画像へフォールバックする (#1542)。"""
        orig_1 = tmp_path / "orig_1.png"
        orig_2 = tmp_path / "orig_2.png"
        low_1 = tmp_path / "low_1.png"

        img_orig = QImage(256, 128, QImage.Format.Format_RGB32)
        img_orig.fill(0x00FF00)
        assert img_orig.save(str(orig_1))
        assert img_orig.save(str(orig_2))

        img_low = QImage(128, 64, QImage.Format.Format_RGB32)
        img_low.fill(0x0000FF)
        assert img_low.save(str(low_1))

        metadata = [
            {"id": 1, "stored_image_path": str(orig_1)},
            {"id": 2, "stored_image_path": str(orig_2)},
        ]
        search_result = _build_search_result(metadata)
        db_manager = Mock()
        db_manager.get_low_res_image_paths_batch.return_value = {
            1: str(low_1),
            2: str(tmp_path / "missing_low_2.png"),
        }

        worker = ThumbnailWorker(
            search_result=search_result,
            thumbnail_size=QSize(64, 64),
            db_manager=db_manager,
            request_id="req_low_res",
            page_num=1,
        )

        result = worker.execute()

        db_manager.get_low_res_image_paths_batch.assert_called_once_with([1, 2])
        assert len(result.loaded_thumbnails) == 2
        id_to_img = dict(result.loaded_thumbnails)
        assert id_to_img[1].size() == QSize(64, 32)
        assert id_to_img[1].pixelColor(0, 0).blue() == 255
        assert id_to_img[2].size() == QSize(64, 32)
        assert id_to_img[2].pixelColor(0, 0).green() == 255

    def test_explicit_thumbnail_worker_uses_qimagereader_scaled_decode(self, tmp_path):
        """ExplicitThumbnailWorker.load_image も QImageReader で縮小デコードする (#1542)。"""
        from lorairo.gui.workers.explicit_thumbnail_worker import ExplicitThumbnailWorker

        img_path = tmp_path / "large.png"
        large = QImage(512, 256, QImage.Format.Format_RGB32)
        large.fill(0xFF0000)
        assert large.save(str(img_path))

        decoded = ExplicitThumbnailWorker.load_image((img_path, 128, 128))
        assert not decoded.isNull()
        assert decoded.size() == QSize(128, 64)
        assert decoded.pixelColor(0, 0).red() == 255
