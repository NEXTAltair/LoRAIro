"""起動時の背景初期化 worker (#1438) のユニットテスト。"""

from unittest.mock import MagicMock

import pytest

from lorairo.gui.workers.search_facets_worker import SearchFacetsResult, SearchFacetsWorker
from lorairo.gui.workers.tag_db_warmup_worker import TagDbWarmupWorker


@pytest.mark.unit
def test_warmup_initializes_reader_and_tag_management():
    container = MagicMock()
    container.db_manager.annotation_repo.get_merged_reader.return_value = object()

    result = TagDbWarmupWorker(container).execute()

    assert result.reader_ready is True
    assert result.tag_management_ready is True
    container.db_manager.annotation_repo.get_merged_reader.assert_called_once()


@pytest.mark.unit
def test_warmup_degrades_when_reader_unavailable():
    container = MagicMock()
    container.db_manager.annotation_repo.get_merged_reader.return_value = None

    result = TagDbWarmupWorker(container).execute()

    assert result.reader_ready is False


@pytest.mark.unit
def test_warmup_degrades_when_tag_management_fails():
    container = MagicMock()
    container.db_manager.annotation_repo.get_merged_reader.return_value = object()
    type(container).tag_management_service = property(
        lambda _self: (_ for _ in ()).throw(RuntimeError("Tag database initialization failed"))
    )

    result = TagDbWarmupWorker(container).execute()

    assert result.reader_ready is True
    assert result.tag_management_ready is False


@pytest.mark.unit
def test_facets_worker_collects_models_and_histogram():
    source = MagicMock()
    source.get_recently_used_model_ids.return_value = ["a", "b"]
    source.get_created_at_histogram.return_value = []

    result = SearchFacetsWorker(source).execute()

    assert isinstance(result, SearchFacetsResult)
    assert result.model_ids == ["a", "b"]
    assert result.histogram_bins == []


@pytest.mark.unit
def test_facets_worker_skips_unsupported_source_methods():
    result = SearchFacetsWorker(object()).execute()

    assert result.model_ids is None
    assert result.histogram_bins is None
