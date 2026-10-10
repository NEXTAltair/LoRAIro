"""Cooperative cancellation checkpoints surround repository-owned queries."""

from unittest.mock import Mock

import pytest

from lorairo.gui.workers.annotation_refresh_worker import (
    AnnotationRefreshLoadWorker,
    AnnotationRefreshLookupWorker,
)
from lorairo.gui.workers.base import CancellationError


@pytest.mark.parametrize("operation", ["lookup", "load"])
def test_cancel_before_query_does_not_open_repository_session(operation):
    repo = Mock()
    worker = (
        AnnotationRefreshLookupWorker(repo, {"a"})
        if operation == "lookup"
        else AnnotationRefreshLoadWorker(repo, 1)
    )
    worker.cancel()
    with pytest.raises(CancellationError):
        worker.execute()
    repo.find_image_ids_by_phashes_multi.assert_not_called()
    repo.get_image_annotation_metadata.assert_not_called()


@pytest.mark.parametrize("operation", ["lookup", "load"])
def test_cancel_during_query_discards_result_after_repository_returns(operation):
    repo = Mock()
    worker = (
        AnnotationRefreshLookupWorker(repo, {"a"})
        if operation == "lookup"
        else AnnotationRefreshLoadWorker(repo, 1)
    )

    def query(_target):
        worker.cancel()
        return {"a": [1]} if operation == "lookup" else {"tags": []}

    repo.find_image_ids_by_phashes_multi.side_effect = query
    repo.get_image_annotation_metadata.side_effect = query
    with pytest.raises(CancellationError):
        worker.execute()
