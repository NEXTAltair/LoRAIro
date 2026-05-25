"""Provider Batch API job service boundary.

ADR 0038 の共通 job lifecycle 層。ここでは provider 実 API は実装せず、
OpenAI / Anthropic / Google adapter を差し替え可能な Protocol と永続 job 更新を扱う。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from lorairo.database.db_repository import ImageRepository
from lorairo.database.schema import ProviderBatchJob
from lorairo.utils.log import logger

ProviderBatchRawPayload = Mapping[str, Any] | str | None


class ProviderBatchError(RuntimeError):
    """Provider Batch service の基底例外。"""


class ProviderBatchAdapterNotFoundError(ProviderBatchError):
    """指定 provider の adapter が登録されていない。"""


class InvalidProviderBatchStatusTransition(ProviderBatchError):
    """Provider Batch job status transition が許可されていない。"""


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


class ProviderBatchAdapter(Protocol):
    """Provider Batch API adapter interface."""

    provider: str

    def submit(self, request_file: Path, metadata: BatchSubmitMetadata) -> ProviderBatchSubmission:
        """Provider batch job を投入する。"""
        ...

    def retrieve(self, provider_job_id: str) -> ProviderBatchStatus:
        """Provider batch job の最新状態を取得する。"""
        ...

    def cancel(self, provider_job_id: str) -> ProviderBatchStatus:
        """Provider batch job を cancel する。"""
        ...

    def download_results(self, provider_job_id: str, destination_dir: Path) -> ProviderBatchArtifacts:
        """Provider batch job の output/error artifacts を download する。"""
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

    def submit(self, request_file: Path, metadata: BatchSubmitMetadata) -> int:
        """Provider batch job を投入し、DB job を作成する。"""
        provider = self._normalize_provider_name(metadata.provider)
        adapter = self._get_adapter(provider)
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

    def refresh(self, job_id: int) -> ProviderBatchJob:
        """Provider から最新 status を取得し、DB job を更新する。"""
        job = self._require_job(job_id)
        if job.provider_job_id is None:
            raise ProviderBatchError(f"provider_job_id が未設定です: job_id={job_id}")

        adapter = self._get_adapter(job.provider)
        provider_status = adapter.retrieve(job.provider_job_id)
        return self._apply_status(job, provider_status)

    def cancel(self, job_id: int) -> ProviderBatchJob:
        """Provider batch job を cancel し、DB job を更新する。"""
        job = self._require_job(job_id)
        if job.provider_job_id is None:
            raise ProviderBatchError(f"provider_job_id が未設定です: job_id={job_id}")
        self.validate_transition(job.status, "canceling")

        adapter = self._get_adapter(job.provider)
        provider_status = adapter.cancel(job.provider_job_id)
        return self._apply_status(job, provider_status)

    def download_results(self, job_id: int, destination_dir: Path) -> ProviderBatchArtifacts:
        """Provider result artifacts を download し、artifact records を保存する。"""
        job = self._require_job(job_id)
        if job.provider_job_id is None:
            raise ProviderBatchError(f"provider_job_id が未設定です: job_id={job_id}")

        adapter = self._get_adapter(job.provider)
        artifacts = adapter.download_results(job.provider_job_id, destination_dir)
        self._validate_provider_job_id(job, artifacts.provider_job_id)

        updates: dict[str, Any] = {}
        existing_artifact_keys = {
            (registered.artifact_type, registered.local_path)
            for registered in self._repository.list_provider_batch_artifacts(job_id)
        }
        for artifact in artifacts.artifacts:
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

        if artifacts.raw_provider_payload is not None:
            updates["raw_provider_payload"] = self._serialize_payload(artifacts.raw_provider_payload)
        if updates:
            self._repository.update_provider_batch_job(job_id, updates)

        return artifacts

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
    def _serialize_payload(payload: ProviderBatchRawPayload) -> str | None:
        if payload is None:
            return None
        if isinstance(payload, str):
            return payload
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)
