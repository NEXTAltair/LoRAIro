"""Clef command selection, exit status, streaming and discovery contracts."""

from __future__ import annotations

import json
from contextlib import contextmanager
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from lorairo.cli.commands import review
from lorairo.cli.main import app
from lorairo.public_api.exceptions import ImageNotFoundError
from lorairo.services import annotation_review_service
from lorairo.services.annotation_review_service import AnnotationReviewItem, AnnotationReviewResult

pytestmark = [pytest.mark.unit, pytest.mark.cli]
runner = CliRunner()


def _result(image_id=1, status="completed", *, probability=0.1, item_status="warning", error=None):
    items = (
        AnnotationReviewItem("tag_10", "tag", "猫", probability, item_status, error),
        AnnotationReviewItem("caption_20", "caption", "A cat.", probability, item_status, error),
    )
    if status == "unevaluated":
        items = ()
    return AnnotationReviewResult(
        image_id, "snapshot-fingerprint", "@cf/cloudflare/clef-flash", items, status, error
    )


def _rows(result):
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


@pytest.fixture
def api(monkeypatch):
    def execute(project, ids, *, on_result, collect_results):
        assert collect_results is False
        for image_id in dict.fromkeys(ids):
            on_result(_result(image_id))
        return []

    mocked = Mock(side_effect=execute)
    monkeypatch.setattr(review, "review_annotations", mocked)
    return mocked


def _invoke(*args):
    return runner.invoke(app, ["--json", "review", "run", "--project", "test-project", *args])


def test_warning_reviews_are_successful_and_emit_source_candidates(api):
    result = _invoke("--image-ids", "1,2")

    assert result.exit_code == 0, result.output
    rows = _rows(result)
    items = [row for row in rows if row.get("type") == "annotation_review"]
    assert {row["image_id"] for row in items} == {1, 2}
    assert {row["candidate_id"] for row in items} == {"tag_10", "caption_20"}
    assert {row["candidate_kind"] for row in items} == {"tag", "caption"}
    assert all(row["probability"] == 0.1 and row["status"] == "warning" for row in items)
    summary = rows[-1]
    assert summary["kind"] == "result" and summary["ok"] is True
    assert summary["successful"] == 2 and summary["warnings"] == 4 and summary["failed"] == 0
    assert summary["image_count"] == 2 and summary["item_count"] == 4
    api.assert_called_once()


@pytest.mark.parametrize(
    "args",
    [
        (),
        ("--image-ids", ""),
        ("--image-ids", "  ,  "),
        ("--image-ids", "1,no"),
        ("--image-ids", ",".join(str(value) for value in range(1, 502))),
        ("--image-ids", "1", "--image-ids-file", "ids.txt"),
    ],
)
def test_invalid_selection_never_calls_review(api, args):
    result = _invoke(*args)

    assert result.exit_code == 2, result.output
    assert _rows(result)[-1]["code"] == "INVALID_INPUT"
    api.assert_not_called()


@pytest.mark.parametrize("ids", ["0", "-1", "1,-1"])
def test_nonpositive_ids_fail_at_real_api_boundary_before_opening_project(monkeypatch, ids):
    from lorairo.public_api import review as review_api

    context = Mock(side_effect=AssertionError("Invalid input must not open a project"))
    monkeypatch.setattr(review_api, "_project_context", context)

    result = _invoke("--image-ids", ids)

    assert result.exit_code == 2, result.output
    assert _rows(result)[-1]["code"] == "VALIDATION_FAILED"
    context.assert_not_called()


def test_duplicate_selection_is_counted_once(api):
    result = _invoke("--image-ids", "2,1,2,1")
    assert result.exit_code == 0, result.output
    outcomes = [row for row in _rows(result) if row.get("type") == "annotation_review_outcome"]
    assert [row["image_id"] for row in outcomes] == [2, 1]
    assert _rows(result)[-1]["image_count"] == 2


@pytest.fixture
def real_review_api(monkeypatch):
    """Keep the facade's real bounds and validation, mock only its dependencies."""
    from lorairo.public_api import review as review_api

    container = Mock()
    container.db_manager.image_repo.get_candidate_image_ids.side_effect = lambda ids: ids

    @contextmanager
    def context(project_name):
        yield container

    context_factory = Mock(side_effect=context)
    monkeypatch.setattr(review_api, "_project_context", context_factory)
    service = Mock(model_name="@cf/cloudflare/clef-flash")
    service.prepare_review.side_effect = lambda image_id: image_id
    service.review.side_effect = lambda snapshot, **kwargs: _result(snapshot)
    service_factory = Mock(return_value=service)
    monkeypatch.setattr(annotation_review_service, "AnnotationReviewService", service_factory)
    network = Mock(side_effect=AssertionError("No network expected in bounded selection tests"))
    monkeypatch.setattr("socket.socket.connect", network)
    return context_factory, service_factory, service, network


def test_file_selection_above_500_returns_result_set_too_large_without_project_or_network(
    real_review_api, tmp_path
):
    context, factory, service, network = real_review_api
    ids_file = tmp_path / "501-images.txt"
    ids_file.write_text("\n".join(str(image_id) for image_id in range(1, 502)))

    result = _invoke("--image-ids-file", str(ids_file))

    assert result.exit_code == 2, result.output
    rows = _rows(result)
    assert len(rows) == 1 and rows[0]["kind"] == "error"
    assert rows[0]["code"] == "RESULT_SET_TOO_LARGE"
    assert rows[0]["details"] == {"limit": 500, "matched": 501}
    context.assert_not_called()
    factory.assert_not_called()
    service.prepare_review.assert_not_called()
    service.review.assert_not_called()
    network.assert_not_called()


@pytest.mark.parametrize("duplicate_ids", [[], [500, 1, 250, 500]])
def test_file_selection_accepts_500_unique_images_and_reviews_duplicates_once(
    real_review_api, tmp_path, duplicate_ids
):
    context, factory, service, network = real_review_api
    ids_file = tmp_path / "500-images.txt"
    ids = [*range(1, 501), *duplicate_ids]
    ids_file.write_text("\n".join(str(image_id) for image_id in ids))

    result = _invoke("--image-ids-file", str(ids_file))

    assert result.exit_code == 0, result.output
    summary = _rows(result)[-1]
    assert summary["image_count"] == summary["successful"] == 500
    assert service.prepare_review.call_count == service.review.call_count == 500
    assert [call.args[0] for call in service.prepare_review.call_args_list] == list(range(1, 501))
    context.assert_called_once_with("test-project")
    factory.assert_called_once()
    network.assert_not_called()


def test_file_selection_preserves_unique_id_order_and_streams(api, tmp_path):
    ids_file = tmp_path / "選択 images.txt"
    ids_file.write_text("3,1\n3\n2\n", encoding="utf-8")

    result = _invoke("--image-ids-file", str(ids_file))

    assert result.exit_code == 0, result.output
    assert api.call_args.args[:2] == ("test-project", [3, 1, 2])
    outcomes = [row for row in _rows(result) if row.get("type") == "annotation_review_outcome"]
    assert [row["image_id"] for row in outcomes] == [3, 1, 2]


@pytest.mark.parametrize("contents", ["", "0", "-1", "wrong"])
def test_invalid_file_selection_never_calls_review(api, tmp_path, contents):
    ids_file = tmp_path / "ids.txt"
    ids_file.write_text(contents)
    result = _invoke("--image-ids-file", str(ids_file))
    assert result.exit_code == 2, result.output
    api.assert_not_called()


def test_missing_image_uses_existing_not_found_error_contract(api):
    api.side_effect = ImageNotFoundError(99)
    result = _invoke("--image-ids", "1,99")
    assert result.exit_code == 1, result.output
    assert _rows(result)[-1]["code"] == "NOT_FOUND"


@pytest.mark.parametrize("status", ["partial", "failed", "cancelled", "stale"])
def test_operational_incomplete_review_returns_exit_one_with_complete_summary(api, status):
    def execute(project, ids, *, on_result, collect_results):
        on_result(_result(1))
        on_result(
            _result(2, status, probability=None, item_status="unevaluated", error="Review incomplete")
        )
        return []

    api.side_effect = execute
    result = _invoke("--image-ids", "1,2")

    assert result.exit_code == 1, result.output
    rows = _rows(result)
    summary = rows[-1]
    assert summary["ok"] is False and summary["status"] == "partial_success"
    assert summary["successful"] == 1 and summary[status] == 1
    assert summary["image_count"] == 2
    outcomes = [row for row in rows if row.get("type") == "annotation_review_outcome"]
    assert [row["status"] for row in outcomes] == ["completed", status]
    assert [row["image_id"] for row in outcomes] == [1, 2]


def test_empty_candidates_are_explicitly_unevaluated_without_claiming_review_success(api):
    def execute(project, ids, *, on_result, collect_results):
        on_result(_result(status="unevaluated"))
        return []

    api.side_effect = execute
    result = _invoke("--image-ids", "1")
    assert result.exit_code == 0, result.output
    rows = _rows(result)
    assert len(rows) == 2
    assert rows[0]["status"] == "unevaluated" and rows[0]["item_count"] == 0
    assert rows[-1]["successful"] == 0 and rows[-1]["unevaluated"] == 1
    assert rows[-1]["warnings"] == rows[-1]["item_count"] == 0


def test_review_command_supports_root_read_only(api):
    result = runner.invoke(
        app, ["--json", "--read-only", "review", "run", "--project", "test-project", "--image-ids", "1"]
    )
    assert result.exit_code == 0, result.output
    api.assert_called_once()


def test_human_output_includes_tag_caption_probabilities_and_warnings(api):
    result = runner.invoke(
        app, ["--no-json", "review", "run", "--project", "test-project", "--image-ids", "1"]
    )
    assert result.exit_code == 0, result.output
    assert "猫" in result.stdout and "A cat." in result.stdout
    assert "0.1000 (warning)" in result.stdout and "2 warnings" in result.stdout


def test_describe_publishes_read_only_network_and_nullable_probabilities():
    result = runner.invoke(app, ["--json", "describe", "review run", "--schema", "json_schema"])

    assert result.exit_code == 0, result.output
    rows = _rows(result)
    tool = rows[0]
    assert tool["read_only"] is tool["strict_read_only_supported"] is True
    assert set(tool["side_effects"]) == {"db_read", "file_read", "network"}
    assert tool["conditional_side_effects"] == []
    schemas = {row["name"]: row["schema"] for row in rows if row.get("type") == "schema"}
    assert {"ReviewRunInput", "ReviewRunItem", "ReviewRunOutcome", "ReviewRunResult"} <= set(schemas)
    assert set(schemas["ReviewRunInput"]["properties"]) == {"project", "image_ids", "image_ids_file"}
    probability = schemas["ReviewRunItem"]["properties"]["probability"]
    assert probability["anyOf"] == [{"maximum": 1.0, "minimum": 0.0, "type": "number"}, {"type": "null"}]
    assert {"unevaluated", "stale"} <= set(schemas["ReviewRunOutcome"]["properties"]["status"]["enum"])
    assert "warnings" in schemas["ReviewRunResult"]["properties"]
    file_description = schemas["ReviewRunInput"]["properties"]["image_ids_file"]["description"]
    assert "500 unique images" in file_description and "RESULT_SET_TOO_LARGE" in file_description
    assert "File reader accepts up to 100,000 IDs" in file_description
