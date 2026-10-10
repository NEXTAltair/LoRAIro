"""Use the real image repository and SQLite sessions inside Qt refresh workers."""

import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QThread
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from lorairo.database.repository.image import ImageRepository
from lorairo.database.schema import Base, Image, Tag
from lorairo.gui.state.dataset_state import DatasetStateManager


@pytest.mark.integration
def test_refresh_sessions_are_created_closed_on_worker_and_only_selected_versions_are_fetched(
    tmp_path, qapp, qtbot, monkeypatch
):
    engine = create_engine(f"sqlite:///{tmp_path / 'annotation-refresh.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        for image_id in (1, 2, 3):
            session.add(
                Image(
                    id=image_id,
                    uuid=f"image-{image_id}",
                    phash="same-phash",
                    original_image_path=f"/original/{image_id}.webp",
                    stored_image_path=f"/stored/{image_id}.webp",
                    width=1536,
                    height=1024,
                    format="WEBP",
                    extension=".webp",
                )
            )
            session.add(Tag(image_id=image_id, tag=f"new-{image_id}"))
        session.commit()

    sessions = []
    entered = []
    closed = []

    class WorkerSession(Session):
        def __enter__(self):
            entered.append((id(self), threading.get_ident()))
            return super().__enter__()

        def close(self):
            closed.append((id(self), threading.get_ident()))
            super().close()

    worker_factory = sessionmaker(bind=engine, class_=WorkerSession)

    def recording_factory():
        session = worker_factory()
        sessions.append(session)
        return session

    repository = ImageRepository(session_factory=recording_factory)
    full_fetch = Mock(side_effect=AssertionError("Refresh must not retrieve full metadata"))
    monkeypatch.setattr(repository, "get_image_metadata", full_fetch)
    monkeypatch.setattr(repository, "get_images_metadata_batch", full_fetch)
    annotation_reads = []
    original_annotation_query = repository.get_image_annotation_metadata

    def recording_annotation_query(image_id):
        annotation_reads.append(image_id)
        return original_annotation_query(image_id)

    monkeypatch.setattr(repository, "get_image_annotation_metadata", recording_annotation_query)
    state = DatasetStateManager()
    state.set_db_manager(SimpleNamespace(image_repo=repository))
    state.set_dataset_images(
        [
            {
                "id": image_id,
                "stored_image_path": f"/processed/{image_id}.webp",
                "width": 768,
                "height": 512,
                "tags": [],
                "tags_text": "old",
            }
            for image_id in (1, 2)
        ]
    )
    state.set_current_image(1)
    gui_updates = []
    state.current_image_data_changed.connect(
        lambda data: gui_updates.append((data.copy(), QThread.currentThread()))
    )
    try:
        state.refresh_annotations_after_execution({"same-phash"})
        qtbot.waitUntil(lambda: state.get_image_by_id(1).get("tags_text") == "new-1")
        assert annotation_reads == [1]
        assert state._annotation_invalidated_ids == {2}
        assert "tags" not in state.get_image_by_id(2)
        assert len(entered) == len(closed) == 2  # lookup and selected annotations
        assert entered == closed
        assert all(thread_id != threading.get_ident() for _, thread_id in entered)
        assert gui_updates[-1][1] == qapp.thread()
        assert gui_updates[-1][0]["stored_image_path"] == "/processed/1.webp"
        assert gui_updates[-1][0]["width"] == 768

        state.set_current_image(2)
        qtbot.waitUntil(lambda: state.get_image_by_id(2).get("tags_text") == "new-2")
        assert annotation_reads == [1, 2]  # search-result-external version 3 is never read
        assert len(entered) == len(closed) == 3
        assert entered == closed
        assert len({session_id for session_id, _ in entered}) == 3
        full_fetch.assert_not_called()
    finally:
        state.shutdown_annotation_refresh()
        qtbot.waitUntil(lambda: state._annotation_worker_manager.get_active_worker_count() == 0)
        qtbot.waitUntil(lambda: state._annotation_worker_manager.get_pending_thread_release_count() == 0)
        engine.dispose()
