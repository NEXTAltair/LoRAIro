from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import image_annotator_lib
import pytest

from lorairo.services.provider_batch_library_compat import (
    to_library_handle,
    to_library_submit_request,
    to_provider_batch_fetch_result,
    to_provider_batch_models,
    to_provider_batch_status,
    to_provider_batch_submission,
)
from lorairo.services.provider_batch_service import (
    BatchJobHandle,
    BatchSubmitItem,
    BatchSubmitRequest,
    ProviderBatchError,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "payload",
    [
        SimpleNamespace(
            provider_job_id="batch_123",
            provider_status="validating",
            status="submitted",
            request_count=0,
            submitted_at="2026-05-26T12:00:00Z",
            expires_at="2026-05-27T12:00:00+00:00",
            raw_provider_payload={"request_id": "req_1"},
        ),
        {
            "provider_job_id": "batch_123",
            "provider_status": "validating",
            "status": "submitted",
            "request_count": 0,
            "submitted_at": "2026-05-26T12:00:00Z",
            "expires_at": "2026-05-27T12:00:00+00:00",
            "raw_provider_payload": {"request_id": "req_1"},
        },
    ],
)
def test_submission_conversion_accepts_object_and_mapping(payload: object) -> None:
    result = to_provider_batch_submission(payload, "anthropic")

    assert result.provider_job_id == "batch_123"
    assert result.provider_status == "validating"
    assert result.request_count == 0
    assert result.submitted_at == datetime(2026, 5, 26, 12, 0, tzinfo=UTC)
    assert result.expires_at == datetime(2026, 5, 27, 12, 0, tzinfo=UTC)
    assert result.raw_provider_payload == {"request_id": "req_1"}


@pytest.mark.unit
def test_submission_conversion_keeps_missing_raw_payload_none() -> None:
    result = to_provider_batch_submission(
        {
            "provider_job_id": "batch_123",
            "provider_status": "validating",
            "submitted_at": "",
            "expires_at": None,
        },
        "anthropic",
    )

    assert result.submitted_at is None
    assert result.expires_at is None
    assert result.raw_provider_payload is None


@pytest.mark.unit
@pytest.mark.parametrize("payload", [{}, {"provider_job_id": None}])
def test_submission_conversion_rejects_missing_provider_job_id(payload: dict[str, object]) -> None:
    with pytest.raises(ProviderBatchError, match="provider_job_id"):
        to_provider_batch_submission(payload, "anthropic")


@pytest.mark.unit
def test_status_conversion_coerces_datetimes_and_keeps_falsy_counts() -> None:
    result = to_provider_batch_status(
        SimpleNamespace(
            provider_job_id="batch_123",
            provider_status="ended",
            status="completed",
            request_count=0,
            succeeded_count=0,
            failed_count=0,
            canceled_count=0,
            expired_count=0,
            submitted_at="2026-05-26T12:00:00Z",
            completed_at="2026-05-26T13:00:00Z",
            canceled_at="",
            expires_at=None,
        ),
        "anthropic",
    )

    assert result.request_count == 0
    assert result.succeeded_count == 0
    assert result.failed_count == 0
    assert result.canceled_count == 0
    assert result.expired_count == 0
    assert result.submitted_at == datetime(2026, 5, 26, 12, 0, tzinfo=UTC)
    assert result.completed_at == datetime(2026, 5, 26, 13, 0, tzinfo=UTC)
    assert result.canceled_at is None
    assert result.expires_at is None
    assert result.raw_provider_payload is None


@pytest.mark.unit
def test_status_conversion_rejects_invalid_datetime() -> None:
    with pytest.raises(ProviderBatchError, match="invalid datetime"):
        to_provider_batch_status(
            {
                "provider_job_id": "batch_123",
                "provider_status": "running",
                "submitted_at": "not-a-date",
            },
            "anthropic",
        )


@pytest.mark.unit
def test_fetch_result_accepts_mapping_payload(tmp_path: Path) -> None:
    result = to_provider_batch_fetch_result(
        {
            "provider_job_id": "batch_123",
            "provider_status": "ended",
            "status": "completed",
            "request_count": 1,
            "succeeded_count": 0,
            "failed_count": 1,
            "completed_at": "2026-05-26T13:00:00Z",
            "expires_at": "2026-05-27T13:00:00Z",
            "raw_provider_payload": {"provider_error": {"code": "job_failed"}},
            "artifacts": [
                {
                    "artifact_type": "output",
                    "local_path": str(tmp_path / "output.jsonl"),
                    "provider_file_id": "file_123",
                    "sha256": "abc",
                }
            ],
            "items": [
                {
                    "custom_id": "image-1",
                    "status": "failed",
                    "error": {
                        "phase": "result",
                        "code": "bad_response",
                        "message": "invalid json",
                        "retryable": False,
                    },
                }
            ],
        },
        "anthropic",
        tmp_path,
    )

    assert result.provider_job_id == "batch_123"
    assert result.provider_status == "ended"
    assert result.raw_provider_payload == {"provider_error": {"code": "job_failed"}}
    assert result.completed_at == datetime(2026, 5, 26, 13, 0, tzinfo=UTC)
    assert result.expires_at == datetime(2026, 5, 27, 13, 0, tzinfo=UTC)
    assert result.artifacts[0].local_path == tmp_path / "output.jsonl"
    assert result.artifacts[0].provider_file_id == "file_123"
    assert result.items[0].custom_id == "image-1"
    assert result.items[0].error_type == "bad_response"
    assert result.items[0].raw_response == {
        "error": {
            "phase": "result",
            "code": "bad_response",
            "message": "invalid json",
            "retryable": False,
        }
    }


@pytest.mark.unit
def test_submit_conversion_preserves_metadata_when_library_dto_supports_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    @dataclass(frozen=True)
    class LibraryBatchSubmitItem:
        custom_id: str
        image_id: int
        image_path: Path
        task_type: str
        model_id: int | None
        raw_request: Any

    @dataclass(frozen=True)
    class LibraryBatchSubmitRequest:
        provider: str
        endpoint: str
        litellm_model_id: str
        prompt_profile: str
        description: str | None
        api_keys: dict[str, str]
        items: list[LibraryBatchSubmitItem]
        model_id: int | None
        request_artifact_path: Path | None
        raw_provider_payload: Any

    monkeypatch.setattr(image_annotator_lib, "BatchSubmitItem", LibraryBatchSubmitItem, raising=False)
    monkeypatch.setattr(image_annotator_lib, "BatchSubmitRequest", LibraryBatchSubmitRequest, raising=False)

    request = BatchSubmitRequest(
        provider="anthropic",
        endpoint="messages",
        litellm_model_id="anthropic/claude-test",
        prompt_profile="default",
        api_keys={"anthropic": "test"},
        items=(
            BatchSubmitItem(
                custom_id="image-1",
                image_id=1,
                image_path=tmp_path / "image.webp",
                task_type="caption",
                model_id=10,
                raw_request={"temperature": 0.1},
            ),
        ),
        model_id=10,
        request_artifact_path=tmp_path / "request.jsonl",
        raw_provider_payload={"metadata": "kept"},
    )

    converted = to_library_submit_request(request)

    assert converted.model_id == 10
    assert converted.request_artifact_path == tmp_path / "request.jsonl"
    assert converted.raw_provider_payload == {"metadata": "kept"}
    assert converted.items[0].task_type == "caption"
    assert converted.items[0].model_id == 10
    assert converted.items[0].raw_request == {"temperature": 0.1}


@pytest.mark.unit
def test_submit_conversion_strips_lorairo_private_raw_request_keys(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Codex #646 P2: ``lorairo_*`` private キーは provider payload へ転送しない。"""

    @dataclass(frozen=True)
    class LibraryBatchSubmitItem:
        custom_id: str
        image_id: int
        image_path: Path
        task_type: str
        model_id: int | None
        raw_request: Any

    @dataclass(frozen=True)
    class LibraryBatchSubmitRequest:
        provider: str
        endpoint: str
        litellm_model_id: str
        prompt_profile: str
        description: str | None
        api_keys: dict[str, str]
        items: list[LibraryBatchSubmitItem]
        model_id: int | None
        request_artifact_path: Path | None
        raw_provider_payload: Any

    monkeypatch.setattr(image_annotator_lib, "BatchSubmitItem", LibraryBatchSubmitItem, raising=False)
    monkeypatch.setattr(image_annotator_lib, "BatchSubmitRequest", LibraryBatchSubmitRequest, raising=False)

    request = BatchSubmitRequest(
        provider="anthropic",
        endpoint="messages",
        litellm_model_id="anthropic/claude-test",
        prompt_profile="default",
        api_keys={"anthropic": "test"},
        items=(
            BatchSubmitItem(
                custom_id="ph:abc:le:1024",
                image_id=1,
                image_path=tmp_path / "image.webp",
                task_type="annotation",
                model_id=10,
                raw_request={"lorairo_image_ids": [1, 2], "temperature": 0.1},
            ),
            BatchSubmitItem(
                custom_id="ph:def:le:768",
                image_id=3,
                image_path=tmp_path / "image2.webp",
                task_type="annotation",
                model_id=10,
                raw_request={"lorairo_image_ids": [3]},
            ),
        ),
        model_id=10,
    )

    converted = to_library_submit_request(request)

    # lorairo_* は除去、それ以外のキーは保持。
    assert converted.items[0].raw_request == {"temperature": 0.1}
    # 残りが lorairo_* のみなら None に畳む (空 payload を provider へ渡さない)。
    assert converted.items[1].raw_request is None


@pytest.mark.unit
def test_library_conversion_is_idempotent_for_already_converted_dtos() -> None:
    submit_request = SimpleNamespace(provider="anthropic", items=[])
    handle = SimpleNamespace(provider="anthropic", provider_job_id="batch_123")

    assert to_library_submit_request(submit_request) is submit_request
    assert to_library_handle(handle) is handle

    lorairo_handle = BatchJobHandle(provider="anthropic", provider_job_id="batch_123", api_keys={})
    assert to_library_handle(lorairo_handle).provider_job_id == "batch_123"


@pytest.mark.unit
def test_batch_models_wraps_scalar_model_id() -> None:
    assert to_provider_batch_models("anthropic/claude-test") == ("anthropic/claude-test",)
    assert to_provider_batch_models(123) == (123,)


@pytest.mark.unit
def test_fetch_result_rejects_missing_provider_job_id(tmp_path: Path) -> None:
    with pytest.raises(ProviderBatchError, match="provider_job_id"):
        to_provider_batch_fetch_result({"provider_status": "completed"}, "anthropic", tmp_path)


@pytest.mark.unit
def test_fetch_result_uses_fallback_provider_job_id_when_payload_omits_it(tmp_path: Path) -> None:
    result = to_provider_batch_fetch_result(
        {"provider_status": "completed"},
        "anthropic",
        tmp_path,
        fallback_provider_job_id="batch_123",
    )

    assert result.provider_job_id == "batch_123"


@pytest.mark.unit
def test_fetch_result_without_raw_payload_keeps_payload_none(tmp_path: Path) -> None:
    result = to_provider_batch_fetch_result(
        {"provider_job_id": "batch_123", "provider_status": "completed", "items": []},
        "anthropic",
        tmp_path,
    )

    assert result.raw_provider_payload is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "item",
    [
        {"status": "failed"},
        {"custom_id": "image-1"},
        {"custom_id": "image-1", "status": ""},
    ],
)
def test_fetch_result_rejects_items_missing_required_fields(
    tmp_path: Path,
    item: dict[str, object],
) -> None:
    with pytest.raises(ProviderBatchError, match="required field"):
        to_provider_batch_fetch_result(
            {"provider_job_id": "batch_123", "provider_status": "completed", "items": [item]},
            "anthropic",
            tmp_path,
        )


@pytest.mark.unit
def test_fetch_result_item_error_fallbacks_preserve_diagnostics(tmp_path: Path) -> None:
    result = to_provider_batch_fetch_result(
        {
            "provider_job_id": "batch_123",
            "provider_status": "completed",
            "items": [
                {
                    "custom_id": "image-1",
                    "status": "failed",
                    "message": "top-level message",
                    "error": {
                        "type": "invalid_request",
                        "message": "nested message",
                        "retryable": False,
                    },
                }
            ],
        },
        "anthropic",
        tmp_path,
    )

    assert result.items[0].error_type == "invalid_request"
    assert result.items[0].error_message == "top-level message"
    assert result.items[0].raw_response == {
        "error": {
            "phase": "",
            "code": None,
            "message": "nested message",
            "retryable": False,
        }
    }
