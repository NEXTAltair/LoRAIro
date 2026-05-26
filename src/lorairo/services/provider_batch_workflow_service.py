"""Provider Batch API workflow service.

GUI / API / CLI entrypoints should use this Qt-free facade when they need the
common LoRAIro-side Provider Batch lifecycle. Provider-specific request shapes,
file identifiers, and artifact formats remain behind ProviderBatchAdapter.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lorairo.database.db_repository import ImageRepository
from lorairo.services.configuration_service import ConfigurationService
from lorairo.services.provider_batch_service import (
    BatchJobHandle,
    BatchSubmitItem,
    BatchSubmitRequest,
    ProviderBatchAdapter,
    ProviderBatchArtifacts,
    ProviderBatchError,
    ProviderBatchJobService,
    ProviderBatchRawPayload,
)
from lorairo.utils.log import logger

if TYPE_CHECKING:
    from lorairo.database.schema import ProviderBatchJob


@dataclass(frozen=True)
class ProviderBatchResultItem:
    """Provider-neutral batch result item state for LoRAIro persistence."""

    custom_id: str
    status: str
    error_type: str | None = None
    error_message: str | None = None
    raw_response: ProviderBatchRawPayload = None


@dataclass(frozen=True)
class ProviderBatchResultApplyResult:
    """Summary of applying normalized batch result item state."""

    updated_count: int
    missing_count: int
    total_count: int
    missing_custom_ids: tuple[str, ...] = field(default_factory=tuple)


class ProviderBatchLibraryAdapter:
    """Adapter that forwards provider batch operations to image-annotator-lib."""

    def __init__(self, provider: str, client: Any) -> None:
        self.provider = provider
        self._client = client

    def submit_batch(self, request: BatchSubmitRequest) -> Any:
        return self._call_client("submit_batch", request)

    def retrieve_batch(self, handle: BatchJobHandle) -> Any:
        return self._call_client("retrieve_batch", handle)

    def cancel_batch(self, handle: BatchJobHandle) -> Any:
        return self._call_client("cancel_batch", handle)

    def fetch_batch_results(self, handle: BatchJobHandle, destination_dir: Path) -> Any:
        return self._call_client("fetch_batch_results", handle, destination_dir)

    def _call_client(self, method_name: str, *args: Any) -> Any:
        method = getattr(self._client, method_name, None)
        if method is None:
            raise ProviderBatchError(f"image-annotator-lib batch API method is unavailable: {method_name}")
        return method(*args)


class ProviderBatchWorkflowService:
    """Reusable LoRAIro-side Provider Batch workflow boundary."""

    def __init__(
        self,
        repository: ImageRepository,
        config_service: ConfigurationService,
        job_service: ProviderBatchJobService | None = None,
        adapters: Mapping[str, ProviderBatchAdapter] | None = None,
    ) -> None:
        self._repository = repository
        self._config_service = config_service
        self._job_service = job_service or ProviderBatchJobService(repository, adapters)

    def register_adapter(self, adapter: ProviderBatchAdapter) -> None:
        """Register a provider adapter with the underlying job service."""
        self._job_service.register_adapter(adapter)

    def build_submit_request(
        self,
        *,
        provider: str,
        endpoint: str,
        litellm_model_id: str,
        prompt_profile: str,
        image_ids: Sequence[int],
        model_id: int | None = None,
        image_paths: Mapping[int, str | Path] | None = None,
        description: str | None = None,
        request_artifact_path: str | Path | None = None,
        raw_provider_payload: ProviderBatchRawPayload = None,
    ) -> BatchSubmitRequest:
        """Build an ADR 0038 submit request from LoRAIro image IDs."""
        if not image_ids:
            raise ProviderBatchError("Provider batch submit image_ids が空です")

        metadata_by_id = {
            int(row["id"]): row for row in self._repository.get_images_metadata_batch(list(image_ids))
        }
        missing_image_ids = [image_id for image_id in image_ids if image_id not in metadata_by_id]
        if missing_image_ids:
            raise ProviderBatchError(f"Provider batch submit 対象画像が見つかりません: {missing_image_ids}")

        path_overrides = image_paths or {}
        items: list[BatchSubmitItem] = []
        for image_id in image_ids:
            image_path = path_overrides.get(image_id)
            if image_path is None:
                stored_path = metadata_by_id[image_id].get("stored_image_path")
                if not stored_path:
                    raise ProviderBatchError(
                        f"Provider batch submit 対象画像に stored_image_path がありません: image_id={image_id}"
                    )
                image_path = stored_path

            items.append(
                BatchSubmitItem(
                    custom_id=ProviderBatchJobService.build_custom_id(image_id),
                    image_id=image_id,
                    image_path=Path(image_path),
                    model_id=model_id,
                )
            )

        return BatchSubmitRequest(
            provider=provider,
            endpoint=endpoint,
            litellm_model_id=litellm_model_id,
            prompt_profile=prompt_profile,
            api_keys=self._config_service.get_api_keys(),
            items=tuple(items),
            model_id=model_id,
            description=description,
            request_artifact_path=Path(request_artifact_path)
            if request_artifact_path is not None
            else None,
            raw_provider_payload=raw_provider_payload,
        )

    def submit_images(
        self,
        *,
        provider: str,
        endpoint: str,
        litellm_model_id: str,
        prompt_profile: str,
        image_ids: Sequence[int],
        model_id: int | None = None,
        image_paths: Mapping[int, str | Path] | None = None,
        description: str | None = None,
        request_artifact_path: str | Path | None = None,
        raw_provider_payload: ProviderBatchRawPayload = None,
    ) -> int:
        """Build and submit a provider batch job for LoRAIro image IDs."""
        request = self.build_submit_request(
            provider=provider,
            endpoint=endpoint,
            litellm_model_id=litellm_model_id,
            prompt_profile=prompt_profile,
            image_ids=image_ids,
            model_id=model_id,
            image_paths=image_paths,
            description=description,
            request_artifact_path=request_artifact_path,
            raw_provider_payload=raw_provider_payload,
        )
        return self._job_service.submit_batch(request)

    def refresh(self, job_id: int) -> ProviderBatchJob:
        """Refresh a provider batch job using configured API keys."""
        return self._job_service.refresh(job_id, api_keys=self._config_service.get_api_keys())

    def cancel(self, job_id: int) -> ProviderBatchJob:
        """Cancel a provider batch job using configured API keys."""
        return self._job_service.cancel(job_id, api_keys=self._config_service.get_api_keys())

    def download_results(
        self,
        job_id: int,
        destination_dir: str | Path | None = None,
    ) -> ProviderBatchArtifacts:
        """Download provider artifacts into the configured batch results directory by default."""
        resolved_destination = (
            Path(destination_dir)
            if destination_dir is not None
            else self._config_service.get_batch_results_directory()
        )
        return self._job_service.download_results(
            job_id,
            resolved_destination,
            api_keys=self._config_service.get_api_keys(),
        )

    def apply_result_items(
        self,
        job_id: int,
        provider_job_id: str,
        items: Sequence[ProviderBatchResultItem | Mapping[str, Any] | Any],
    ) -> ProviderBatchResultApplyResult:
        """Apply normalized provider-neutral item statuses to DB records."""
        job = self._repository.get_provider_batch_job(job_id)
        if job is None:
            raise ProviderBatchError(f"Provider batch job が見つかりません: job_id={job_id}")
        if job.provider_job_id != provider_job_id:
            raise ProviderBatchError(
                "Provider batch result job ID mismatch: "
                f"job_id={job_id}, expected={job.provider_job_id}, actual={provider_job_id}"
            )

        updates_by_custom_id: dict[str, dict[str, Any]] = {}
        for raw_item in items:
            item = self._coerce_result_item(raw_item)
            updates_by_custom_id[item.custom_id] = {
                "status": item.status,
                "error_type": item.error_type,
                "error_message": item.error_message,
                "raw_response": self._serialize_payload(item.raw_response),
            }

        updated_custom_ids = self._repository.update_provider_batch_items_by_custom_id(
            job_id,
            updates_by_custom_id,
        )
        missing_custom_ids = sorted(set(updates_by_custom_id) - updated_custom_ids)

        if missing_custom_ids:
            logger.warning(
                f"Provider batch result に DB item が見つからない custom_id があります: {missing_custom_ids}"
            )
        return ProviderBatchResultApplyResult(
            updated_count=len(updated_custom_ids),
            missing_count=len(missing_custom_ids),
            total_count=len(items),
            missing_custom_ids=tuple(missing_custom_ids),
        )

    @classmethod
    def _coerce_result_item(
        cls, item: ProviderBatchResultItem | Mapping[str, Any] | Any
    ) -> ProviderBatchResultItem:
        if isinstance(item, ProviderBatchResultItem):
            return item
        if isinstance(item, Mapping):
            return ProviderBatchResultItem(
                custom_id=str(item["custom_id"]),
                status=str(item["status"]),
                error_type=cls._optional_str(item.get("error_type")),
                error_message=cls._optional_str(item.get("error_message")),
                raw_response=item.get("raw_response"),
            )
        return ProviderBatchResultItem(
            custom_id=str(item.custom_id),
            status=str(item.status),
            error_type=cls._optional_str(getattr(item, "error_type", None)),
            error_message=cls._optional_str(getattr(item, "error_message", None)),
            raw_response=getattr(item, "raw_response", None),
        )

    @staticmethod
    def _optional_str(value: Any) -> str | None:
        if value is None:
            return None
        return str(value)

    @staticmethod
    def _serialize_payload(payload: ProviderBatchRawPayload) -> str | None:
        if payload is None:
            return None
        if isinstance(payload, str):
            return payload
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)
