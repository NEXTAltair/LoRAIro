"""Provider Batch API job service boundary.

ADR 0038 の共通 job lifecycle 層。ここでは provider 実 API は実装せず、
OpenAI / Anthropic / Google adapter を差し替え可能な Protocol と永続 job 更新を扱う。
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from lorairo.database.db_repository import ImageRepository
from lorairo.database.schema import ProviderBatchJob
from lorairo.utils.log import logger

ProviderBatchRawPayload = Mapping[str, Any] | str | None
_CUSTOM_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class ProviderBatchError(RuntimeError):
    """Provider Batch service の基底例外。"""


class ProviderBatchAdapterNotFoundError(ProviderBatchError):
    """指定 provider の adapter が登録されていない。"""


class InvalidProviderBatchStatusTransition(ProviderBatchError):
    """Provider Batch job status transition が許可されていない。"""


class InvalidProviderBatchRequest(ProviderBatchError):
    """Provider Batch submit request が ADR 0038 contract を満たしていない。"""


@dataclass(frozen=True)
class BatchSubmitItem:
    """LoRAIro から library batch API に渡す job item。"""

    custom_id: str
    image_id: int
    image_path: Path
    task_type: str = "annotation"
    model_id: int | None = None
    raw_request: ProviderBatchRawPayload = None


@dataclass(frozen=True)
class BatchSubmitRequest:
    """Provider 非依存の batch submit request。

    Provider 固有 payload 構築、upload、response parse は image-annotator-lib 側に閉じ込める。
    """

    provider: str
    endpoint: str
    litellm_model_id: str
    prompt_profile: str
    api_keys: Mapping[str, str]
    items: tuple[BatchSubmitItem, ...]
    model_id: int | None = None
    description: str | None = None
    request_artifact_path: Path | None = None
    raw_provider_payload: ProviderBatchRawPayload = None


@dataclass(frozen=True)
class BatchJobHandle:
    """Provider batch job の stable handle。"""

    provider: str
    provider_job_id: str
    api_keys: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class BatchSubmitMetadata:
    """Provider batch submit 時に LoRAIro 側から渡す metadata。"""

    provider: str
    endpoint: str | None = None
    model_id: int | None = None
    request_count: int = 0
    input_artifact_path: str | None = None
    raw_provider_payload: ProviderBatchRawPayload = None


@dataclass(frozen=True)
class ProviderBatchSubmission:
    """Provider adapter の submit 結果。"""

    provider_job_id: str
    provider_status: str
    status: str | None = None
    request_count: int | None = None
    submitted_at: datetime | None = None
    expires_at: datetime | None = None
    raw_provider_payload: ProviderBatchRawPayload = None


@dataclass(frozen=True)
class ProviderBatchStatus:
    """Provider adapter の retrieve / cancel 結果。"""

    provider_job_id: str
    provider_status: str
    status: str | None = None
    request_count: int | None = None
    succeeded_count: int | None = None
    failed_count: int | None = None
    canceled_count: int | None = None
    expired_count: int | None = None
    submitted_at: datetime | None = None
    completed_at: datetime | None = None
    canceled_at: datetime | None = None
    expires_at: datetime | None = None
    raw_provider_payload: ProviderBatchRawPayload = None


@dataclass(frozen=True)
class ProviderBatchArtifactRef:
    """Downloaded provider batch artifact metadata."""

    artifact_type: str
    local_path: Path
    provider_file_id: str | None = None
    sha256: str | None = None


@dataclass(frozen=True)
class ProviderBatchArtifacts:
    """Provider adapter の download_results 結果。"""

    provider_job_id: str
    artifacts: tuple[ProviderBatchArtifactRef, ...] = field(default_factory=tuple)
    raw_provider_payload: ProviderBatchRawPayload = None


@dataclass(frozen=True)
class ProviderBatchResultItem:
    """Provider-neutral normalized batch result item."""

    custom_id: str
    status: str
    annotation: Any | None = None
    error_type: str | None = None
    error_message: str | None = None
    raw_response: ProviderBatchRawPayload = None


@dataclass(frozen=True)
class ProviderBatchFetchResult:
    """Provider adapter の normalized fetch/import 結果。"""

    provider_job_id: str
    provider_status: str
    status: str | None = None
    request_count: int | None = None
    succeeded_count: int | None = None
    failed_count: int | None = None
    canceled_count: int | None = None
    expired_count: int | None = None
    completed_at: datetime | None = None
    expires_at: datetime | None = None
    artifacts: tuple[ProviderBatchArtifactRef, ...] = field(default_factory=tuple)
    items: tuple[ProviderBatchResultItem, ...] = field(default_factory=tuple)
    raw_provider_payload: ProviderBatchRawPayload = None


class ProviderBatchAdapter(Protocol):
    """image-annotator-lib batch API client interface."""

    provider: str

    def submit_batch(self, request: BatchSubmitRequest) -> ProviderBatchSubmission:
        """Provider batch job を投入する。"""
        ...

    def retrieve_batch(self, handle: BatchJobHandle) -> ProviderBatchStatus:
        """Provider batch job の最新状態を取得する。"""
        ...

    def cancel_batch(self, handle: BatchJobHandle) -> ProviderBatchStatus:
        """Provider batch job を cancel する。"""
        ...

    def fetch_batch_results(
        self, handle: BatchJobHandle, destination_dir: Path
    ) -> ProviderBatchFetchResult:
        """Provider batch job の normalized result と artifacts を取得する。"""
        ...


_COMMON_STATUSES = {
    "draft",
    "submitted",
    "validating",
    "running",
    "completed",
    "failed",
    "canceling",
    "canceled",
    "expired",
    "imported",
}

_PROVIDER_STATUS_MAP: dict[str, dict[str, str]] = {
    "openai": {
        "validating": "validating",
        "in_progress": "running",
        "finalizing": "running",
        "completed": "completed",
        "failed": "failed",
        "expired": "expired",
        "cancelling": "canceling",
        "canceling": "canceling",
        "cancelled": "canceled",
        "canceled": "canceled",
    },
    "anthropic": {
        "in_progress": "running",
        "canceling": "canceling",
        "canceled": "canceled",
        "ended": "completed",
        "completed": "completed",
        "failed": "failed",
        "expired": "expired",
    },
    "google": {
        "JOB_STATE_PENDING": "validating",
        "JOB_STATE_QUEUED": "validating",
        "JOB_STATE_RUNNING": "running",
        "JOB_STATE_SUCCEEDED": "completed",
        "JOB_STATE_PARTIALLY_SUCCEEDED": "completed",
        "JOB_STATE_FAILED": "failed",
        "JOB_STATE_CANCELLING": "canceling",
        "JOB_STATE_CANCELLED": "canceled",
        "JOB_STATE_EXPIRED": "expired",
        "pending": "validating",
        "running": "running",
        "succeeded": "completed",
        "partially_succeeded": "completed",
        "failed": "failed",
        "cancelled": "canceled",
        "canceled": "canceled",
    },
}

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "draft": {
        "submitted",
        "validating",
        "running",
        "completed",
        "failed",
        "canceling",
        "canceled",
        "expired",
    },
    "submitted": {"validating", "running", "completed", "failed", "canceling", "canceled", "expired"},
    "validating": {"running", "completed", "failed", "canceling", "canceled", "expired"},
    "running": {"completed", "failed", "canceling", "canceled", "expired"},
    "canceling": {"completed", "canceled", "failed"},
    "completed": {"imported"},
    "failed": set(),
    "canceled": set(),
    "expired": set(),
    "imported": set(),
}


class ProviderBatchJobService:
    """Provider Batch API job lifecycle service."""

    def __init__(
        self,
        repository: ImageRepository,
        adapters: Mapping[str, ProviderBatchAdapter] | None = None,
    ) -> None:
        self._repository = repository
        self._adapters = {
            self._normalize_provider_name(name): adapter for name, adapter in (adapters or {}).items()
        }

    def register_adapter(self, adapter: ProviderBatchAdapter) -> None:
        """Provider adapter を追加登録する。"""
        self._adapters[self._normalize_provider_name(adapter.provider)] = adapter

    @staticmethod
    def build_custom_id(image_id: int) -> str:
        """ADR 0038 の custom_id を生成する。"""
        return f"img-{image_id}"

    def submit_batch(self, request: BatchSubmitRequest) -> int:
        """Provider batch job を投入し、job/items を DB に保存する。"""
        request = replace(
            request,
            provider=self._normalize_provider_name(request.provider),
            api_keys=self._normalize_api_keys(request.api_keys),
        )
        self._validate_submit_request(request)
        adapter = self._get_adapter(request.provider)
        submission = adapter.submit_batch(request)
        status = self.normalize_status(
            request.provider,
            submission.status or submission.provider_status,
        )
        request_count = (
            submission.request_count if submission.request_count is not None else len(request.items)
        )

        job_id = self._repository.create_provider_batch_job_with_items(
            {
                "provider": request.provider,
                "provider_job_id": submission.provider_job_id,
                "status": status,
                "provider_status": submission.provider_status,
                "endpoint": request.endpoint,
                "model_id": request.model_id,
                "request_count": request_count,
                "submitted_at": submission.submitted_at,
                "expires_at": submission.expires_at,
                "input_artifact_path": str(request.request_artifact_path)
                if request.request_artifact_path is not None
                else None,
                "raw_provider_payload": self._serialize_payload(
                    submission.raw_provider_payload
                    if submission.raw_provider_payload is not None
                    else request.raw_provider_payload
                ),
            },
            [
                {
                    "job_id": 0,
                    "custom_id": item.custom_id,
                    "image_id": item.image_id,
                    "model_id": item.model_id if item.model_id is not None else request.model_id,
                    "task_type": item.task_type,
                    "status": status,
                    "raw_request": self._serialize_payload(item.raw_request),
                }
                for item in request.items
            ],
        )
        logger.info(
            f"Provider batch job submitted: provider={request.provider}, "
            f"provider_job_id={submission.provider_job_id}, job_id={job_id}, status={status}, "
            f"items={len(request.items)}"
        )
        return job_id

    def submit(self, request_file: Path, metadata: BatchSubmitMetadata) -> int:
        """Provider batch job を投入し、DB job を作成する。

        互換 wrapper。新規経路は ADR 0038 の ``submit_batch()`` を使う。
        """
        provider = self._normalize_provider_name(metadata.provider)
        adapter = self._get_adapter(provider)
        if not hasattr(adapter, "submit"):
            raise ProviderBatchError(
                "Legacy submit() requires a legacy adapter with submit(). "
                "Use submit_batch() for ADR 0038 batch clients."
            )
        submission = adapter.submit(request_file, metadata)
        status = self.normalize_status(
            provider,
            submission.status or submission.provider_status,
        )

        job_id = self._repository.create_provider_batch_job(
            {
                "provider": provider,
                "provider_job_id": submission.provider_job_id,
                "status": status,
                "provider_status": submission.provider_status,
                "endpoint": metadata.endpoint,
                "model_id": metadata.model_id,
                "request_count": submission.request_count
                if submission.request_count is not None
                else metadata.request_count,
                "submitted_at": submission.submitted_at,
                "expires_at": submission.expires_at,
                "input_artifact_path": metadata.input_artifact_path or str(request_file),
                "raw_provider_payload": self._serialize_payload(
                    submission.raw_provider_payload
                    if submission.raw_provider_payload is not None
                    else metadata.raw_provider_payload
                ),
            }
        )
        logger.info(
            f"Provider batch job submitted: provider={provider}, "
            f"provider_job_id={submission.provider_job_id}, job_id={job_id}, status={status}"
        )
        return job_id

    def refresh(self, job_id: int, api_keys: Mapping[str, str] | None = None) -> ProviderBatchJob:
        """Provider から最新 status を取得し、DB job を更新する。"""
        job = self._require_job(job_id)
        if job.provider_job_id is None:
            raise ProviderBatchError(f"provider_job_id が未設定です: job_id={job_id}")

        adapter = self._get_adapter(job.provider)
        if hasattr(adapter, "retrieve_batch"):
            provider_status = adapter.retrieve_batch(self._build_handle(job, api_keys))
        else:
            provider_status = adapter.retrieve(job.provider_job_id)  # type: ignore[attr-defined]
        return self._apply_status(job, provider_status)

    def cancel(self, job_id: int, api_keys: Mapping[str, str] | None = None) -> ProviderBatchJob:
        """Provider batch job を cancel し、DB job を更新する。"""
        job = self._require_job(job_id)
        if job.provider_job_id is None:
            raise ProviderBatchError(f"provider_job_id が未設定です: job_id={job_id}")
        self.validate_transition(job.status, "canceling")

        adapter = self._get_adapter(job.provider)
        if hasattr(adapter, "cancel_batch"):
            provider_status = adapter.cancel_batch(self._build_handle(job, api_keys))
        else:
            provider_status = adapter.cancel(job.provider_job_id)  # type: ignore[attr-defined]
        return self._apply_status(job, provider_status)

    def download_results(
        self,
        job_id: int,
        destination_dir: Path,
        api_keys: Mapping[str, str] | None = None,
    ) -> ProviderBatchArtifacts:
        """Provider result artifacts を download し、artifact records を保存する。

        互換 wrapper。正規化済み result item を扱う新規経路は ``fetch_results()`` を使う。
        """
        fetch_result = self.fetch_results(job_id, destination_dir, api_keys=api_keys)
        return ProviderBatchArtifacts(
            provider_job_id=fetch_result.provider_job_id,
            artifacts=fetch_result.artifacts,
            raw_provider_payload=fetch_result.raw_provider_payload,
        )

    def fetch_results(
        self,
        job_id: int,
        destination_dir: Path,
        api_keys: Mapping[str, str] | None = None,
    ) -> ProviderBatchFetchResult:
        """Provider result を取得し、job/artifact metadata を保存する。"""
        job = self._require_job(job_id)
        if job.provider_job_id is None:
            raise ProviderBatchError(f"provider_job_id が未設定です: job_id={job_id}")

        fetch_result = self._fetch_from_adapter(job, destination_dir, api_keys)
        self._validate_provider_job_id(job, fetch_result.provider_job_id)

        updates = self._register_fetch_artifacts(job_id, fetch_result.artifacts)
        updates.update(self._build_fetch_job_updates(job, fetch_result))
        if fetch_result.raw_provider_payload is not None:
            updates["raw_provider_payload"] = self._serialize_payload(fetch_result.raw_provider_payload)
        if updates:
            self._repository.update_provider_batch_job(job_id, updates)

        return fetch_result

    def _fetch_from_adapter(
        self,
        job: ProviderBatchJob,
        destination_dir: Path,
        api_keys: Mapping[str, str] | None,
    ) -> ProviderBatchFetchResult:
        adapter = self._get_adapter(job.provider)
        if hasattr(adapter, "fetch_batch_results"):
            raw_result = adapter.fetch_batch_results(self._build_handle(job, api_keys), destination_dir)
        else:
            raw_result = adapter.download_results(  # type: ignore[attr-defined]
                job.provider_job_id,
                destination_dir,
            )
        return self._coerce_fetch_result(raw_result, job.provider_job_id or "")

    def _register_fetch_artifacts(
        self,
        job_id: int,
        artifacts: tuple[ProviderBatchArtifactRef, ...],
    ) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        existing_artifact_keys = {
            (registered.artifact_type, registered.local_path)
            for registered in self._repository.list_provider_batch_artifacts(job_id)
        }
        for artifact in artifacts:
            local_path = str(artifact.local_path)
            artifact_key = (artifact.artifact_type, local_path)
            if artifact_key not in existing_artifact_keys:
                self._repository.create_provider_batch_artifact(
                    {
                        "job_id": job_id,
                        "artifact_type": artifact.artifact_type,
                        "local_path": local_path,
                        "provider_file_id": artifact.provider_file_id,
                        "sha256": artifact.sha256,
                    }
                )
                existing_artifact_keys.add(artifact_key)
            if artifact.artifact_type == "input":
                updates["input_artifact_path"] = local_path
            elif artifact.artifact_type == "output":
                updates["output_artifact_path"] = local_path
            elif artifact.artifact_type == "error":
                updates["error_artifact_path"] = local_path
        return updates

    def _build_fetch_job_updates(
        self,
        job: ProviderBatchJob,
        fetch_result: ProviderBatchFetchResult,
    ) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        provider_status = fetch_result.status or fetch_result.provider_status
        if provider_status:
            next_status = self.normalize_status(job.provider, provider_status)
            if not (job.status == "imported" and next_status == "completed"):
                self.validate_transition(job.status, next_status)
                updates["status"] = next_status
            updates["provider_status"] = fetch_result.provider_status
        optional_fields = {
            "request_count": fetch_result.request_count,
            "succeeded_count": fetch_result.succeeded_count,
            "failed_count": fetch_result.failed_count,
            "canceled_count": fetch_result.canceled_count,
            "expired_count": fetch_result.expired_count,
            "completed_at": fetch_result.completed_at,
            "expires_at": fetch_result.expires_at,
        }
        updates.update({key: value for key, value in optional_fields.items() if value is not None})
        return updates

    @classmethod
    def normalize_status(cls, provider: str, provider_status: str) -> str:
        """provider 固有 status を ADR 0038 共通 status に変換する。"""
        status = provider_status.strip()
        if status in _COMMON_STATUSES:
            return status

        provider_map = _PROVIDER_STATUS_MAP.get(cls._normalize_provider_name(provider), {})
        normalized = provider_map.get(status) or provider_map.get(status.lower())
        if normalized is None:
            raise ProviderBatchError(
                f"未対応の provider status: provider={provider}, status={provider_status}"
            )
        return normalized

    @classmethod
    def validate_transition(cls, current_status: str, next_status: str) -> None:
        """ADR 0038 共通 status transition を検証する。"""
        if current_status == next_status:
            return
        allowed = _ALLOWED_TRANSITIONS.get(current_status)
        if allowed is None:
            raise ProviderBatchError(f"未対応の現在 status: {current_status}")
        if next_status not in allowed:
            raise InvalidProviderBatchStatusTransition(
                f"Provider batch status transition は許可されていません: {current_status} -> {next_status}"
            )

    def _apply_status(
        self, job: ProviderBatchJob, provider_status: ProviderBatchStatus
    ) -> ProviderBatchJob:
        self._validate_provider_job_id(job, provider_status.provider_job_id)
        next_status = self.normalize_status(
            job.provider, provider_status.status or provider_status.provider_status
        )
        self.validate_transition(job.status, next_status)

        updates: dict[str, Any] = {
            "status": next_status,
            "provider_status": provider_status.provider_status,
        }
        if provider_status.raw_provider_payload is not None:
            updates["raw_provider_payload"] = self._serialize_payload(provider_status.raw_provider_payload)
        optional_fields = {
            "request_count": provider_status.request_count,
            "succeeded_count": provider_status.succeeded_count,
            "failed_count": provider_status.failed_count,
            "canceled_count": provider_status.canceled_count,
            "expired_count": provider_status.expired_count,
            "submitted_at": provider_status.submitted_at,
            "completed_at": provider_status.completed_at,
            "canceled_at": provider_status.canceled_at,
            "expires_at": provider_status.expires_at,
        }
        updates.update({key: value for key, value in optional_fields.items() if value is not None})

        self._repository.update_provider_batch_job(job.id, updates)
        refreshed = self._repository.get_provider_batch_job(job.id)
        if refreshed is None:
            raise ProviderBatchError(f"更新後の provider batch job が見つかりません: job_id={job.id}")
        return refreshed

    @classmethod
    def _coerce_fetch_result(
        cls,
        result: ProviderBatchFetchResult | ProviderBatchArtifacts | Mapping[str, Any] | Any,
        fallback_provider_job_id: str,
    ) -> ProviderBatchFetchResult:
        if isinstance(result, ProviderBatchFetchResult):
            return result
        if isinstance(result, ProviderBatchArtifacts):
            return ProviderBatchFetchResult(
                provider_job_id=result.provider_job_id,
                provider_status="",
                artifacts=result.artifacts,
                raw_provider_payload=result.raw_provider_payload,
            )
        if isinstance(result, Mapping):
            provider_job_id = cls._optional_str(result.get("provider_job_id")) or fallback_provider_job_id
            provider_status = cls._optional_str(result.get("provider_status") or result.get("status")) or ""
            return ProviderBatchFetchResult(
                provider_job_id=provider_job_id,
                provider_status=provider_status,
                status=cls._optional_str(result.get("status")),
                request_count=cls._optional_int(result.get("request_count")),
                succeeded_count=cls._optional_int(result.get("succeeded_count")),
                failed_count=cls._optional_int(result.get("failed_count")),
                canceled_count=cls._optional_int(result.get("canceled_count")),
                expired_count=cls._optional_int(result.get("expired_count")),
                completed_at=cls._optional_datetime(result.get("completed_at")),
                expires_at=cls._optional_datetime(result.get("expires_at")),
                artifacts=tuple(
                    cls._coerce_artifact_ref(artifact) for artifact in result.get("artifacts") or ()
                ),
                items=tuple(cls._coerce_result_item(item) for item in result.get("items") or ()),
                raw_provider_payload=result.get("raw_provider_payload"),
            )

        provider_job_id = (
            cls._optional_str(getattr(result, "provider_job_id", None)) or fallback_provider_job_id
        )
        provider_status = (
            cls._optional_str(getattr(result, "provider_status", None) or getattr(result, "status", None))
            or ""
        )
        return ProviderBatchFetchResult(
            provider_job_id=provider_job_id,
            provider_status=provider_status,
            status=cls._optional_str(getattr(result, "status", None)),
            request_count=cls._optional_int(getattr(result, "request_count", None)),
            succeeded_count=cls._optional_int(getattr(result, "succeeded_count", None)),
            failed_count=cls._optional_int(getattr(result, "failed_count", None)),
            canceled_count=cls._optional_int(getattr(result, "canceled_count", None)),
            expired_count=cls._optional_int(getattr(result, "expired_count", None)),
            completed_at=cls._optional_datetime(getattr(result, "completed_at", None)),
            expires_at=cls._optional_datetime(getattr(result, "expires_at", None)),
            artifacts=tuple(
                cls._coerce_artifact_ref(artifact) for artifact in getattr(result, "artifacts", ()) or ()
            ),
            items=tuple(cls._coerce_result_item(item) for item in getattr(result, "items", ()) or ()),
            raw_provider_payload=getattr(result, "raw_provider_payload", None),
        )

    @classmethod
    def _coerce_artifact_ref(
        cls,
        artifact: ProviderBatchArtifactRef | Mapping[str, Any] | Any,
    ) -> ProviderBatchArtifactRef:
        if isinstance(artifact, ProviderBatchArtifactRef):
            return artifact
        if isinstance(artifact, Mapping):
            return ProviderBatchArtifactRef(
                artifact_type=str(artifact["artifact_type"]),
                local_path=Path(artifact["local_path"]),
                provider_file_id=cls._optional_str(artifact.get("provider_file_id")),
                sha256=cls._optional_str(artifact.get("sha256")),
            )
        return ProviderBatchArtifactRef(
            artifact_type=str(artifact.artifact_type),
            local_path=Path(artifact.local_path),
            provider_file_id=cls._optional_str(getattr(artifact, "provider_file_id", None)),
            sha256=cls._optional_str(getattr(artifact, "sha256", None)),
        )

    @classmethod
    def _coerce_result_item(
        cls, item: ProviderBatchResultItem | Mapping[str, Any] | Any
    ) -> ProviderBatchResultItem:
        if isinstance(item, ProviderBatchResultItem):
            return item
        if isinstance(item, Mapping):
            error = item.get("error")
            return ProviderBatchResultItem(
                custom_id=str(item["custom_id"]),
                status=str(item["status"]),
                annotation=item.get("annotation"),
                error_type=cls._optional_str(
                    item.get("error_type") or cls._extract_error_field(error, "type")
                ),
                error_message=cls._optional_str(
                    item.get("error_message")
                    or item.get("message")
                    or cls._extract_error_field(error, "message")
                ),
                raw_response=item.get("raw_response"),
            )
        error = getattr(item, "error", None)
        return ProviderBatchResultItem(
            custom_id=str(item.custom_id),
            status=str(item.status),
            annotation=getattr(item, "annotation", None),
            error_type=cls._optional_str(
                getattr(item, "error_type", None) or cls._extract_error_field(error, "type")
            ),
            error_message=cls._optional_str(
                getattr(item, "error_message", None) or cls._extract_error_field(error, "message")
            ),
            raw_response=getattr(item, "raw_response", None),
        )

    def _require_job(self, job_id: int) -> ProviderBatchJob:
        job = self._repository.get_provider_batch_job(job_id)
        if job is None:
            raise ProviderBatchError(f"Provider batch job が見つかりません: job_id={job_id}")
        return job

    def _get_adapter(self, provider: str) -> ProviderBatchAdapter:
        adapter = self._adapters.get(self._normalize_provider_name(provider))
        if adapter is None:
            raise ProviderBatchAdapterNotFoundError(f"Provider batch adapter 未登録: {provider}")
        return adapter

    def _build_handle(self, job: ProviderBatchJob, api_keys: Mapping[str, str] | None) -> BatchJobHandle:
        if job.provider_job_id is None:
            raise ProviderBatchError(f"provider_job_id が未設定です: job_id={job.id}")
        return BatchJobHandle(
            provider=job.provider,
            provider_job_id=job.provider_job_id,
            api_keys=self._normalize_api_keys(api_keys or {}),
        )

    @classmethod
    def _validate_submit_request(cls, request: BatchSubmitRequest) -> None:
        if not request.items:
            raise InvalidProviderBatchRequest("batch submit item が空です")
        custom_ids: set[str] = set()
        for item in request.items:
            expected_custom_id = cls.build_custom_id(item.image_id)
            if item.custom_id != expected_custom_id:
                raise InvalidProviderBatchRequest(
                    f"custom_id は {expected_custom_id!r} である必要があります: {item.custom_id!r}"
                )
            if _CUSTOM_ID_PATTERN.fullmatch(item.custom_id) is None:
                raise InvalidProviderBatchRequest(f"不正な custom_id です: {item.custom_id!r}")
            if item.custom_id in custom_ids:
                raise InvalidProviderBatchRequest(f"custom_id が重複しています: {item.custom_id!r}")
            custom_ids.add(item.custom_id)

    @staticmethod
    def _normalize_api_keys(api_keys: Mapping[str, str]) -> dict[str, str]:
        key_aliases = {
            "openai_key": "openai",
            "claude_key": "anthropic",
            "anthropic_key": "anthropic",
            "google_key": "google",
            "openrouter_key": "openrouter",
        }
        normalized: dict[str, str] = {}
        for key, value in api_keys.items():
            if not value or not value.strip():
                continue
            normalized[key_aliases.get(key, key)] = value
        return normalized

    @staticmethod
    def _validate_provider_job_id(job: ProviderBatchJob, provider_job_id: str) -> None:
        if job.provider_job_id != provider_job_id:
            raise ProviderBatchError(
                "Provider batch adapter response job ID mismatch: "
                f"job_id={job.id}, expected={job.provider_job_id}, actual={provider_job_id}"
            )

    @staticmethod
    def _normalize_provider_name(provider: str) -> str:
        return provider.strip().lower()

    @staticmethod
    def _optional_str(value: Any) -> str | None:
        if value is None:
            return None
        return str(value)

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None:
            return None
        return int(value)

    @staticmethod
    def _optional_datetime(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        raise ProviderBatchError(f"datetime に変換できない値です: {value!r}")

    @staticmethod
    def _extract_error_field(error: Any, field_name: str) -> Any:
        if error is None:
            return None
        if isinstance(error, Mapping):
            return error.get(field_name) or error.get(f"error_{field_name}")
        return getattr(error, field_name, None) or getattr(error, f"error_{field_name}", None)

    @staticmethod
    def _serialize_payload(payload: ProviderBatchRawPayload) -> str | None:
        if payload is None:
            return None
        if isinstance(payload, str):
            return payload
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)
