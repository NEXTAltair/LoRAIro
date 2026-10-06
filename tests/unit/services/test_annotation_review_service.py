"""Exercise the actual Clef contract/transport without a network or DB writes."""

import json
import sys
from functools import partial
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from PIL import Image

from lorairo.services.annotation_review_service import AnnotationReviewService
from lorairo.services.configuration_service import ConfigurationService


@pytest.fixture
def review_context(tmp_path, monkeypatch):
    # The repository's native-library mock still allows this lightweight API.
    package = (
        Path(__file__).resolve().parents[3] / "local_packages/image-annotator-lib/src/image_annotator_lib"
    )
    monkeypatch.setattr(sys.modules["image_annotator_lib"], "__path__", [str(package)])
    from image_annotator_lib.decisions import CloudflareDecisionClient

    path = tmp_path / "crop.png"
    Image.new("RGB", (32, 32), "red").save(path)
    annotations = {
        "tags": [
            {"id": 11, "tag": "red_hair"},
            {"id": 12, "tag": "dog"},
            {"id": 13, "tag": "blue_hair", "rejected_at": "2026-10-06"},
        ],
        "captions": [{"id": 21, "caption": "A woman with red hair."}],
    }
    db = Mock()
    db.get_image_metadata.return_value = {"id": 7, "stored_image_path": str(path)}
    db.get_image_annotations.return_value = annotations
    config = ConfigurationService(
        shared_config={"api": {"cloudflare_account_id": "account", "cloudflare_api_token": "test-token"}}
    )
    requests = []

    def success(request):
        payload = json.loads(request.content)
        requests.append(payload)
        probabilities = {"tag_11": 0.9, "tag_12": 0.03, "caption_21": 0.2}
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": {
                    "model": "clef-flash",
                    "answers": {
                        key: {"type": "noul", "noul": probabilities.get(key, 0.7)}
                        for key in payload["questions"]
                    },
                },
            },
        )

    def make_service(handler=success):
        return AnnotationReviewService(
            config,
            db,
            client_factory=partial(CloudflareDecisionClient, transport=httpx.MockTransport(handler)),
        )

    return make_service, db, config, annotations, requests, path, success


def test_source_rows_probability_direction_threshold_and_read_only(review_context):
    make, db, _, annotations, requests, path, _ = review_context
    before = json.dumps(annotations)
    original_bytes = path.read_bytes()
    service = make()
    snapshot = service.prepare_review(7)
    result = service.review(snapshot)

    assert result.status == "completed"
    assert [(item.candidate_id, item.status, item.probability) for item in result.items] == [
        ("tag_11", "ok", 0.9),
        ("tag_12", "warning", 0.03),
        ("caption_21", "ok", 0.2),
    ]
    assert result.model_name == "@cf/cloudflare/clef-flash"
    assert len(requests) == 1
    assert set(requests[0]["questions"]) == {"tag_11", "tag_12", "caption_21"}
    assert requests[0]["state"]["annotations"]["tag_12"]["text"] == "dog"
    assert requests[0]["images"][0].startswith("data:image/png;base64,")
    assert json.dumps(annotations) == before
    assert path.read_bytes() == original_bytes
    assert {call[0] for call in db.method_calls} == {"get_image_metadata", "get_image_annotations"}


@pytest.mark.gui
def test_explicit_gui_click_runs_real_service_and_transport_in_worker(review_context, qtbot):
    from lorairo.gui.widgets.annotation_review_widget import AnnotationReviewWidget

    make, db, _, _, requests, _, _ = review_context
    widget = AnnotationReviewWidget()
    qtbot.addWidget(widget)
    widget.set_service(make())
    widget.set_image(7)
    assert requests == []
    widget.evaluate_button.click()
    qtbot.waitUntil(lambda: "評価完了" in widget.status_label.text(), timeout=5000)
    assert len(requests) == 1
    assert widget.results_table.rowCount() == 3
    assert widget.results_table.item(1, 1).text() == "dog"
    assert "要確認" in widget.results_table.item(1, 2).text()
    assert widget.results_table.item(1, 3).text() == "3.0%"
    assert {call[0] for call in db.method_calls} == {"get_image_metadata", "get_image_annotations"}
    widget.shutdown()


def test_large_annotation_set_chunks_and_retains_partial_failure(review_context):
    make, _, _, annotations, requests, _, success = review_context
    annotations["tags"] = [{"id": index, "tag": f"candidate {index}"} for index in range(130)]
    annotations["captions"] = []

    def second_chunk_fails(request):
        if requests:
            requests.append(json.loads(request.content))
            return httpx.Response(503, json={"error": "private-provider-detail"})
        return success(request)

    service = make(second_chunk_fails)
    result = service.review(service.prepare_review(7))
    assert result.status == "partial"
    assert [len(request["questions"]) for request in requests] == [64, 64]
    assert [len(request["state"]["annotations"]) for request in requests] == [64, 64]
    assert all(item.probability is not None for item in result.items[:64])
    assert all(item.status == "failed" and item.probability is None for item in result.items[64:128])
    assert all(item.status == "unevaluated" for item in result.items[128:])
    assert "private-provider-detail" not in str(result)


def test_three_chunks_cover_every_candidate_once(review_context):
    make, _, _, annotations, requests, _, _ = review_context
    annotations["tags"] = [{"id": index, "tag": str(index)} for index in range(130)]
    annotations["captions"] = []
    service = make()
    result = service.review(service.prepare_review(7))
    assert result.status == "completed"
    assert [len(request["questions"]) for request in requests] == [64, 64, 2]
    assert len(result.items) == 130
    assert len({item.candidate_id for item in result.items}) == 130


@pytest.mark.parametrize("failure", ["http", "missing_answer", "bad_probability"])
def test_failure_cannot_be_interpreted_as_no_warning(review_context, failure):
    make, _, _, _, _, _, _ = review_context

    def fail(request):
        if failure == "http":
            return httpx.Response(401, text="test-token private error")
        answers = {
            key: {"type": "noul", "noul": 1.5 if failure == "bad_probability" else 0.8}
            for key in json.loads(request.content)["questions"]
        }
        if failure == "missing_answer":
            del answers["tag_12"]
        return httpx.Response(200, json={"result": {"model": "clef-flash", "answers": answers}})

    service = make(fail)
    result = service.review(service.prepare_review(7))
    assert result.status == "failed"
    assert result.error
    assert all(item.status == "failed" and item.probability is None for item in result.items)
    assert "test-token" not in str(result)


def test_empty_candidates_do_not_send_or_require_credentials(review_context):
    make, _, config, annotations, requests, _, _ = review_context
    annotations["tags"] = []
    annotations["captions"] = []
    config.update_setting("api", "cloudflare_api_token", "")
    service = make()
    result = service.review(service.prepare_review(7))
    assert result.status == "unevaluated"
    assert result.items == ()
    assert requests == []


def test_missing_credentials_are_explicit_failure(review_context, monkeypatch):
    make, _, config, _, requests, _, _ = review_context
    for name in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_AUTH_TOKEN", "CLOUDFLARE_ACCOUNT_ID"):
        monkeypatch.delenv(name, raising=False)
    config.update_setting("api", "cloudflare_api_token", "")
    service = make()
    result = service.review(service.prepare_review(7))
    assert result.status == "failed"
    assert all(item.status == "failed" for item in result.items)
    assert requests == []


@pytest.mark.parametrize("change", ["edit", "reject", "image"])
def test_stale_snapshot_is_not_sent(review_context, change):
    make, _, _, annotations, requests, path, _ = review_context
    service = make()
    snapshot = service.prepare_review(7)
    if change == "edit":
        annotations["tags"][0]["tag"] = "new tag"
    elif change == "reject":
        annotations["tags"][0]["rejected_at"] = "now"
    else:
        Image.new("RGB", (40, 40), "blue").save(path)
    result = service.review(snapshot)
    assert result.status == "stale"
    assert all(item.status == "unevaluated" for item in result.items)
    assert requests == []


def test_edit_during_inference_invalidates_returned_probabilities(review_context):
    make, _, _, annotations, _, _, success = review_context

    def edit_then_answer(request):
        annotations["captions"][0]["caption"] = "A dog."
        return success(request)

    service = make(edit_then_answer)
    result = service.review(service.prepare_review(7))
    assert result.status == "stale"
    assert all(item.probability is None and item.status == "unevaluated" for item in result.items)


def test_cancel_before_inference_and_between_chunks(review_context):
    make, _, _, annotations, requests, _, success = review_context
    service = make()
    assert service.review(service.prepare_review(7), is_cancelled=lambda: True).status == "cancelled"
    assert requests == []
    annotations["tags"] = [{"id": index, "tag": str(index)} for index in range(130)]
    annotations["captions"] = []
    cancelled = False

    def cancel_then_answer(request):
        nonlocal cancelled
        cancelled = True
        return success(request)

    service = make(cancel_then_answer)
    result = service.review(service.prepare_review(7), is_cancelled=lambda: cancelled)
    assert result.status == "cancelled"
    assert len(requests) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("warning_threshold", float("nan")),
        ("warning_threshold", True),
        ("warning_threshold", -1),
        ("timeout", 0),
        ("model", "unknown"),
    ],
)
def test_invalid_config_is_rejected_offline(review_context, field, value):
    make, _, config, _, requests, _, _ = review_context
    config.update_setting("annotation_review", field, value)
    with pytest.raises(ValueError, match="annotation_review"):
        make()
    assert requests == []
