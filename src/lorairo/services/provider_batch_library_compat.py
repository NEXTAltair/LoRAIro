"""Compatibility helpers for image-annotator-lib Provider Batch DTOs."""

from __future__ import annotations

import importlib
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from lorairo.services.provider_batch_service import (
    BatchJobHandle,
    BatchSubmitRequest,
    ProviderBatchArtifactRef,
    ProviderBatchError,
    ProviderBatchFetchResult,
    ProviderBatchResultItem,
    ProviderBatchStatus,
    ProviderBatchSubmission,
)


def to_library_submit_request(request: Any) -> Any:
    """Convert LoRAIro submit request to the installed library DTO when available."""
    if not isinstance(request, BatchSubmitRequest):
        return request
    try:
        image_annotator_lib = importlib.import_module("image_annotator_lib")
        LibraryBatchSubmitItem = image_annotator_lib.BatchSubmitItem
        LibraryBatchSubmitRequest = image_annotator_lib.BatchSubmitRequest
    except (ImportError, AttributeError):
        return request

    return LibraryBatchSubmitRequest(
        **_supported_kwargs(
            LibraryBatchSubmitRequest,
            {
                "provider": request.provider,
                "endpoint": request.endpoint,
                "litellm_model_id": request.litellm_model_id,
                "prompt_profile": request.prompt_profile,
                "description": request.description,
                "api_keys": dict(request.api_keys),
                "items": [
                    LibraryBatchSubmitItem(
                        **_supported_kwargs(
                            LibraryBatchSubmitItem,
                            {
                                "custom_id": item.custom_id,
                                "image_id": item.image_id,
                                "image_path": item.image_path,
                                "task_type": item.task_type,
                                "model_id": item.model_id,
                                "raw_request": _strip_lorairo_private_keys(item.raw_request),
                            },
                        )
                    )
                    for item in request.items
                ],
                "model_id": request.model_id,
                "request_artifact_path": request.request_artifact_path,
                "raw_provider_payload": request.raw_provider_payload,
            },
        )
    )


def to_library_handle(handle: Any) -> Any:
    """Convert LoRAIro job handle to the installed library DTO when available."""
    if not isinstance(handle, BatchJobHandle):
        return handle
    try:
        image_annotator_lib = importlib.import_module("image_annotator_lib")
        LibraryBatchJobHandle = image_annotator_lib.BatchJobHandle
    except (ImportError, AttributeError):
        return handle

    return LibraryBatchJobHandle(
        provider=handle.provider,
        provider_job_id=handle.provider_job_id,
        api_keys=dict(handle.api_keys),
    )


def to_provider_batch_submission(result: Any, provider: str) -> ProviderBatchSubmission:
    """Normalize object/mapping library submit results to LoRAIro's internal DTO."""
    if isinstance(result, ProviderBatchSubmission):
        return result
    status = _status_value(_value(result, "status"))
    provider_status = _status_value(_value(result, "provider_status")) or status
    return ProviderBatchSubmission(
        provider_job_id=_required_str(result, "provider_job_id"),
        provider_status=provider_status,
        status=status,
        request_count=_optional_int(_value(result, "request_count")),
        submitted_at=_datetime_or_none(_value(result, "submitted_at"), "submitted_at"),
        expires_at=_datetime_or_none(_value(result, "expires_at"), "expires_at"),
        raw_provider_payload=_raw_provider_payload_or_none(result),
    )


def to_provider_batch_status(result: Any, provider: str) -> ProviderBatchStatus:
    """Normalize object/mapping library status results to LoRAIro's internal DTO."""
    if isinstance(result, ProviderBatchStatus):
        return result
    status = _status_value(_value(result, "status"))
    provider_status = _status_value(_value(result, "provider_status")) or status
    return ProviderBatchStatus(
        provider_job_id=_required_str(result, "provider_job_id"),
        provider_status=provider_status,
        status=status,
        request_count=_optional_int(_value(result, "request_count")),
        succeeded_count=_optional_int(_value(result, "succeeded_count")),
        failed_count=_optional_int(_value(result, "failed_count")),
        canceled_count=_optional_int(_value(result, "canceled_count")),
        expired_count=_optional_int(_value(result, "expired_count")),
        submitted_at=_datetime_or_none(_value(result, "submitted_at"), "submitted_at"),
        completed_at=_datetime_or_none(_value(result, "completed_at"), "completed_at"),
        canceled_at=_datetime_or_none(_value(result, "canceled_at"), "canceled_at"),
        expires_at=_datetime_or_none(_value(result, "expires_at"), "expires_at"),
        raw_provider_payload=_raw_provider_payload_or_none(result),
    )


def to_provider_batch_fetch_result(
    result: Any,
    provider: str,
    destination_dir: Path,
    fallback_provider_job_id: str | None = None,
) -> ProviderBatchFetchResult:
    """Normalize object/mapping library fetch results to LoRAIro's internal DTO."""
    if isinstance(result, ProviderBatchFetchResult):
        return result
    status = _status_value(_value(result, "status"))
    provider_status = _status_value(_value(result, "provider_status")) or status
    provider_job_id = _required_str(result, "provider_job_id", fallback=fallback_provider_job_id)
    return ProviderBatchFetchResult(
        provider_job_id=provider_job_id,
        provider_status=provider_status,
        status=status,
        request_count=_optional_int(_value(result, "request_count")),
        succeeded_count=_optional_int(_value(result, "succeeded_count")),
        failed_count=_optional_int(_value(result, "failed_count")),
        canceled_count=_optional_int(_value(result, "canceled_count")),
        expired_count=_optional_int(_value(result, "expired_count")),
        completed_at=_datetime_or_none(_value(result, "completed_at"), "completed_at"),
        expires_at=_datetime_or_none(_value(result, "expires_at"), "expires_at"),
        artifacts=tuple(_to_artifact_ref(artifact) for artifact in _value(result, "artifacts", ()) or ()),
        items=tuple(_to_result_item(item) for item in _value(result, "items", ()) or ()),
        raw_provider_payload=_raw_provider_payload_or_none(result),
    )


def to_provider_batch_models(result: Any) -> tuple[Any, ...]:
    """Return library batch-capable model metadata as an immutable sequence."""
    if result is None:
        return ()
    if isinstance(result, Sequence) and not isinstance(result, (str, bytes)):
        return tuple(result)
    if isinstance(result, (str, bytes)):
        return (result,)
    return (result,)


def _to_result_item(item: Any) -> ProviderBatchResultItem:
    if isinstance(item, ProviderBatchResultItem):
        return item
    error = _value(item, "error")
    return ProviderBatchResultItem(
        custom_id=_required_str(item, "custom_id"),
        status=_required_status(item, "status"),
        annotation=_value(item, "annotation"),
        error_type=_optional_str(
            _coalesce_none(_value(item, "error_type"), _value(error, "code"), _value(error, "type"))
        ),
        error_message=_optional_str(
            _coalesce_none(_value(item, "error_message"), _value(item, "message"), _value(error, "message"))
        ),
        raw_response=_raw_response(item),
    )


def _to_artifact_ref(artifact: Any) -> ProviderBatchArtifactRef:
    if isinstance(artifact, ProviderBatchArtifactRef):
        return artifact
    return ProviderBatchArtifactRef(
        artifact_type=str(_value(artifact, "artifact_type")),
        local_path=Path(_value(artifact, "local_path")),
        provider_file_id=_optional_str(_value(artifact, "provider_file_id")),
        sha256=_optional_str(_value(artifact, "sha256")),
    )


def _raw_response(item: Any) -> Any:
    raw = _value(item, "raw_response")
    if raw is not None:
        return raw
    error = _value(item, "error")
    provider_status = _status_value(_value(item, "provider_status"))
    payload: dict[str, Any] = {}
    if provider_status:
        payload["provider_status"] = provider_status
    if error is not None:
        payload["error"] = {
            "phase": _status_value(_value(error, "phase")),
            "code": _value(error, "code"),
            "message": _value(error, "message"),
            "retryable": _value(error, "retryable"),
        }
    return payload or None


def _value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _coalesce_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _required_str(result: Any, key: str, *, fallback: str | None = None) -> str:
    value = _value(result, key)
    if value is None and fallback is not None:
        value = fallback
    if value is None:
        raise ProviderBatchError(f"image-annotator-lib batch result is missing required field: {key}")
    return str(value)


def _required_status(result: Any, key: str) -> str:
    value = _status_value(_value(result, key))
    if not value:
        raise ProviderBatchError(f"image-annotator-lib batch result is missing required field: {key}")
    return value


def _datetime_or_none(value: Any, field_name: str) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            return datetime.fromisoformat(normalized)
        except ValueError as e:
            raise ProviderBatchError(
                f"image-annotator-lib batch result has invalid datetime field: {field_name}={value!r}"
            ) from e
    raise ProviderBatchError(
        f"image-annotator-lib batch result has invalid datetime field type: "
        f"{field_name}={type(value).__name__}"
    )


def _raw_provider_payload_or_none(result: Any) -> Any:
    return _value(result, "raw_provider_payload")


# ADR 0062: BatchSubmitItem.raw_request は LoRAIro local 用途も兼ねる
# (custom_id -> image_id[] 対応を持つ)。``lorairo_`` prefix のキーは LoRAIro 専用で、
# provider payload へ転送してはならない (DB image ID 漏洩 / provider request 検証破壊を防ぐ)。
_LORAIRO_PRIVATE_RAW_REQUEST_PREFIX = "lorairo_"


def _strip_lorairo_private_keys(raw_request: Any) -> Any:
    """``raw_request`` から LoRAIro 専用キー (``lorairo_*``) を除いて library へ渡す。

    Mapping の場合のみフィルタする。str / None / その他はそのまま返す。除去後に空 Mapping に
    なる場合は ``None`` を返す (provider に空 payload を渡さない)。
    """
    if not isinstance(raw_request, Mapping):
        return raw_request
    filtered = {
        key: value
        for key, value in raw_request.items()
        if not (isinstance(key, str) and key.startswith(_LORAIRO_PRIVATE_RAW_REQUEST_PREFIX))
    }
    return filtered or None


def _supported_kwargs(cls: Any, values: Mapping[str, Any]) -> dict[str, Any]:
    field_names: set[str] = set()
    dataclass_fields = getattr(cls, "__dataclass_fields__", {})
    if dataclass_fields:
        field_names.update(dataclass_fields.keys())

    model_fields = getattr(cls, "model_fields", None)
    if isinstance(model_fields, dict):
        field_names.update(model_fields.keys())
    elif model_fields is not None:
        field_names.update(str(field_name) for field_name in model_fields.keys())

    if not field_names:
        return dict(values)
    return {key: value for key, value in values.items() if key in field_names}


def _status_value(value: Any) -> str:
    if value is None:
        return ""
    enum_value = getattr(value, "value", None)
    return str(enum_value if enum_value is not None else value)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)
