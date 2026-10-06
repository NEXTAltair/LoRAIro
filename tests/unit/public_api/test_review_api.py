"""Read-only review facade preserves exact selection and per-image outcomes."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import OperationalError

import lorairo.public_api as public_api
from lorairo.database.access_policy import is_read_only
from lorairo.public_api import review
from lorairo.public_api.exceptions import ImageNotFoundError, InvalidInputError
from lorairo.services import annotation_review_service
from lorairo.services.annotation_review_service import AnnotationReviewItem, AnnotationReviewResult

pytestmark = pytest.mark.unit


def _result(image_id=1, status="completed"):
    items = (AnnotationReviewItem("tag_10", "tag", "cat", 0.1, "warning"),)
    if status == "unevaluated":
        items = ()
    return AnnotationReviewResult(image_id, "fingerprint", "@cf/cloudflare/clef-flash", items, status)


@pytest.fixture
def services(monkeypatch):
    container = Mock()
    container.db_manager.image_repo.get_candidate_image_ids.side_effect = lambda ids: ids

    @contextmanager
    def context(project_name):
        assert project_name == "project"
        yield container

    monkeypatch.setattr(review, "_project_context", context)
    service = Mock(model_name="@cf/cloudflare/clef-flash")
    service.prepare_review.side_effect = lambda image_id: image_id
    service.review.side_effect = lambda snapshot, **kwargs: _result(snapshot)
    factory = Mock(return_value=service)
    monkeypatch.setattr(annotation_review_service, "AnnotationReviewService", factory)
    return container, service, factory


@pytest.mark.parametrize("ids", [[], [0], [-1], [True], ["1"], [1.0]])
def test_invalid_explicit_ids_fail_before_context_or_service(services, ids):
    container, _service, factory = services
    with pytest.raises(InvalidInputError):
        review.review_annotations("project", ids)
    factory.assert_not_called()
    container.db_manager.image_repo.get_candidate_image_ids.assert_not_called()


def test_duplicate_ids_reviewed_once_in_first_occurrence_order(services):
    container, service, factory = services
    results = review.review_annotations("project", [3, 1, 3, 2, 1])
    assert [result.image_id for result in results] == [3, 1, 2]
    assert [call.args[0] for call in service.prepare_review.call_args_list] == [3, 1, 2]
    container.db_manager.image_repo.get_candidate_image_ids.assert_called_once_with([3, 1, 2])
    factory.assert_called_once_with(container.config_service, container.db_manager)


def test_entire_large_selection_checked_before_first_paid_request(services):
    container, service, _factory = services
    ids = list(range(1, 1202))

    def validate(chunk):
        service.review.assert_not_called()
        return chunk

    container.db_manager.image_repo.get_candidate_image_ids.side_effect = validate
    results = review.review_annotations("project", ids)
    assert [
        len(call.args[0]) for call in container.db_manager.image_repo.get_candidate_image_ids.call_args_list
    ] == [500, 500, 201]
    assert [result.image_id for result in results] == ids


def test_missing_id_aborts_complete_selection_before_any_review(services):
    container, service, factory = services
    container.db_manager.image_repo.get_candidate_image_ids.return_value = [1]
    container.db_manager.image_repo.get_candidate_image_ids.side_effect = None
    with pytest.raises(ImageNotFoundError) as error:
        review.review_annotations("project", [1, 99])
    assert error.value.image_id == 99
    factory.assert_not_called()
    service.review.assert_not_called()


def test_streaming_preserves_empty_failure_and_warning_results(services):
    _container, service, _factory = services
    expected = [_result(1), _result(2, "unevaluated"), _result(3, "failed")]
    service.review.side_effect = expected
    observed = []

    def cancellation():
        return False

    results = review.review_annotations(
        "project", [1, 2, 3], on_result=observed.append, collect_results=False, is_cancelled=cancellation
    )

    assert results == [] and observed == expected
    assert all(call.kwargs["is_cancelled"] is cancellation for call in service.review.call_args_list)
    assert observed[0].items[0].status == "warning"
    assert observed[1].items == () and observed[1].status == "unevaluated"
    assert observed[2].status == "failed"


@pytest.mark.parametrize(
    "error",
    [
        ValueError("sensitive annotation"),
        OSError("secret path"),
        OperationalError("sensitive SQL", {}, Exception("secret token")),
    ],
)
def test_expected_snapshot_failure_is_safe_and_does_not_discard_other_images(services, error):
    _container, service, _factory = services
    service.prepare_review.side_effect = [1, error, 3]

    results = review.review_annotations("project", [1, 2, 3])

    assert [result.status for result in results] == ["completed", "failed", "completed"]
    assert [result.image_id for result in results] == [1, 2, 3]
    assert results[1].fingerprint == "" and results[1].items == ()
    assert results[1].error == f"Could not prepare or evaluate this image ({type(error).__name__})."
    assert "sensitive" not in results[1].error and "secret" not in results[1].error


def test_programmer_error_propagates_instead_of_fabricating_review_result(services):
    _container, service, _factory = services
    service.review.side_effect = TypeError("programmer error")
    with pytest.raises(TypeError, match="programmer error"):
        review.review_annotations("project", [1])


def test_expected_evaluation_failure_preserves_candidate_mapping_and_fingerprint(services, tmp_path):
    _container, service, _factory = services
    snapshot = annotation_review_service.ReviewSnapshot(
        1,
        tmp_path / "image.png",
        (annotation_review_service.ReviewCandidate("tag_10", "tag", "cat"),),
        (annotation_review_service.ReviewCandidate("caption_20", "caption", "A cat."),),
        "prepared-fingerprint",
    )
    service.prepare_review.return_value = snapshot
    service.prepare_review.side_effect = None
    service.review.side_effect = OSError("secret filesystem detail")

    results = review.review_annotations("project", [1])

    assert len(results) == 1 and results[0].status == "failed"
    assert results[0].fingerprint == "prepared-fingerprint"
    assert [item.candidate_id for item in results[0].items] == ["tag_10", "caption_20"]
    assert all(item.status == "failed" and item.probability is None for item in results[0].items)
    assert all("secret" not in item.error for item in results[0].items)


def test_project_context_activates_strict_read_only_and_restores_policy(monkeypatch):
    container = Mock()

    @contextmanager
    def scope():
        assert is_read_only()
        yield container

    monkeypatch.setattr("lorairo.services.service_container.service_container_scope", scope)
    assert not is_read_only()
    with review._project_context("project") as actual:
        assert actual is container and is_read_only()
        container.set_active_project.assert_called_once_with("project")
    assert not is_read_only()


def test_review_function_is_lazily_exported():
    assert public_api.review_annotations is review.review_annotations
    assert "review_annotations" in public_api.__all__


@pytest.mark.parametrize("database_state", ["current", "missing", "old"])
def test_real_project_review_never_prepares_or_changes_database(tmp_path, monkeypatch, database_state):
    """Exercise the actual facade, container, read-only SQLite and empty-review service."""
    from sqlalchemy import event, text
    from sqlalchemy.engine import Engine
    from sqlalchemy.orm import Session

    from lorairo.database import db_core
    from lorairo.database.schema import Image
    from lorairo.public_api.exceptions import ReadOnlyPreconditionError
    from lorairo.services.project_management_service import ProjectManagementService
    from lorairo.utils.config import resolve_runtime_configuration, runtime_configuration_scope

    workspace = tmp_path / "review-workspace"
    configuration = resolve_runtime_configuration(workspace, None)
    with runtime_configuration_scope(configuration):
        info = ProjectManagementService().create_project("project")
    db = info.path / "image_database.db"
    engine = db_core._prepare_project_database(db)
    stored_image = info.path / "image_dataset" / "original_images" / "sample.png"
    stored_image.write_bytes(b"empty-candidates never need to decode this image")
    with Session(engine) as session:
        session.add(
            Image(
                id=1,
                uuid="synthetic-review-image",
                phash="synthetic-review-phash",
                original_image_path=str(stored_image),
                stored_image_path=str(stored_image),
                width=32,
                height=32,
                format="PNG",
                extension=".png",
            )
        )
        session.commit()
    if database_state == "old":
        with engine.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num='synthetic_old_revision'"))
    engine.dispose()
    if database_state == "missing":
        db.unlink()

    def snapshot():
        return {
            str(path.relative_to(workspace)): path.read_bytes()
            for path in workspace.rglob("*")
            if path.is_file() and not path.name.endswith(("-wal", "-shm"))
        }

    before = snapshot()
    directories_before = {
        str(path.relative_to(workspace)) for path in workspace.rglob("*") if path.is_dir()
    }
    monkeypatch.setattr(
        db_core, "_prepare_project_database", Mock(side_effect=AssertionError("no preparation"))
    )
    monkeypatch.setattr(
        "lorairo.filesystem.FileSystemManager.initialize",
        Mock(side_effect=AssertionError("no directories")),
    )
    monkeypatch.setattr(
        "lorairo.services.configuration_service.ensure_config_file",
        Mock(side_effect=AssertionError("no config writes")),
    )
    monkeypatch.setattr("socket.socket.connect", Mock(side_effect=AssertionError("no network")))
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    previous_db = db_core.IMG_DB_PATH
    event.listen(Engine, "before_cursor_execute", capture)
    try:
        with runtime_configuration_scope(configuration):
            if database_state == "current":
                results = review.review_annotations("project", [1])
                assert len(results) == 1 and results[0].status == "unevaluated"
                assert results[0].items == () and results[0].error is None
            else:
                with pytest.raises(ReadOnlyPreconditionError):
                    review.review_annotations("project", [1])
        if database_state == "current":
            # A direct API caller has no CLI runtime scope. Missing configuration
            # must still stay absent instead of ConfigurationService creating it.
            monkeypatch.chdir(workspace)
            monkeypatch.setattr(
                "lorairo.utils.config.DEFAULT_CONFIG_PATH", workspace / "config" / "lorairo.toml"
            )
            results = review.review_annotations("project", [1])
            assert results[0].status == "unevaluated"
            assert not (workspace / "config" / "lorairo.toml").exists()
    finally:
        event.remove(Engine, "before_cursor_execute", capture)

    assert db_core.IMG_DB_PATH == previous_db and not is_read_only()
    assert snapshot() == before
    assert {
        str(path.relative_to(workspace)) for path in workspace.rglob("*") if path.is_dir()
    } == directories_before
    assert not any(
        sql.lstrip().upper().startswith(("CREATE", "INSERT", "UPDATE", "DELETE", "ALTER"))
        for sql in statements
    )
