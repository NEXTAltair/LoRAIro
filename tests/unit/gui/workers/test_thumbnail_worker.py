"""ThumbnailWorker のユニットテスト。"""

from unittest.mock import Mock

from PySide6.QtCore import QSize
from PySide6.QtGui import QImage

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
