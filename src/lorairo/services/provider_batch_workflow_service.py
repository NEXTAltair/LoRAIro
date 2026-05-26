"""Provider Batch API workflow service.

GUI / API / CLI entrypoints should use this Qt-free facade when they need the
common LoRAIro-side Provider Batch lifecycle. Provider-specific request shapes,
file identifiers, and artifact formats remain behind ProviderBatchAdapter.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lorairo.database.db_repository import ImageRepository
from lorairo.services.annotation_save_service import AnnotationSaveResult, AnnotationSaveService
from lorairo.services.configuration_service import ConfigurationService
from lorairo.services.provider_batch_service import (
    BatchJobHandle,
    BatchSubmitItem,
    BatchSubmitRequest,
    ProviderBatchAdapter,
    ProviderBatchArtifactRef,
    ProviderBatchArtifacts,
    ProviderBatchError,
    ProviderBatchFetchResult,
    ProviderBatchJobService,
    ProviderBatchRawPayload,
    ProviderBatchResultItem,
)
from lorairo.utils.log import logger

if TYPE_CHECKING:
    from lorairo.database.schema import ProviderBatchJob


@dataclass(frozen=True)
class ProviderBatchResultApplyResult:
    """Summary of applying normalized batch result item state."""

    updated_count: int
    missing_count: int
    total_count: int
    missing_custom_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProviderBatchImportResult:
    """Summary of importing normalized provider batch results into annotations."""

    save_result: AnnotationSaveResult
    apply_result: ProviderBatchResultApplyResult
    imported_count: int
    skipped_count: int
    error_count: int
    total_count: int
    missing_custom_ids: tuple[str, ...] = field(default_factory=tuple)
    job_imported: bool = False


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
        annotation_save_service: AnnotationSaveService | None = None,
    ) -> None:
        self._repository = repository
        self._config_service = config_service
        self._job_service = job_service or ProviderBatchJobService(repository, adapters)
        self._annotation_save_service = annotation_save_service or AnnotationSaveService(repository)

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
        fetch_result = self.fetch_results(job_id, destination_dir)
        return ProviderBatchArtifacts(
            provider_job_id=fetch_result.provider_job_id,
            artifacts=fetch_result.artifacts,
            raw_provider_payload=fetch_result.raw_provider_payload,
        )

    def fetch_results(
        self,
        job_id: int,
        destination_dir: str | Path | None = None,
    ) -> ProviderBatchFetchResult:
        """Fetch normalized provider results and apply per-item result state."""
        resolved_destination = (
            Path(destination_dir)
            if destination_dir is not None
            else self._config_service.get_batch_results_directory()
        )
        fetch_result = self._job_service.fetch_results(
            job_id,
            resolved_destination,
            api_keys=self._config_service.get_api_keys(),
        )
        if fetch_result.items:
            self.apply_result_items(job_id, fetch_result.provider_job_id, fetch_result.items)
        return fetch_result

    def import_results(
        self,
        job_id: int,
        fetch_result: ProviderBatchFetchResult | Mapping[str, Any] | Any | None = None,
        destination_dir: str | Path | None = None,
    ) -> ProviderBatchImportResult:
        """Import normalized provider batch results using custom_id as the mapping SSoT."""
        job = self._require_job(job_id)
        if job.status == "imported" or job.imported_at is not None:
            raise ProviderBatchError(f"Provider batch job は import 済みです: job_id={job_id}")
        if job.provider_job_id is None:
            raise ProviderBatchError(f"provider_job_id が未設定です: job_id={job_id}")

        normalized_fetch = (
            self._coerce_fetch_result(fetch_result, job.provider_job_id)
            if fetch_result is not None
            else self.fetch_results(job_id, destination_dir)
        )
        if normalized_fetch.provider_job_id != job.provider_job_id:
            raise ProviderBatchError(
                "Provider batch import job ID mismatch: "
                f"job_id={job_id}, expected={job.provider_job_id}, actual={normalized_fetch.provider_job_id}"
            )
        self._apply_fetch_job_state(job, normalized_fetch)

        apply_result = (
            self.apply_result_items(job_id, normalized_fetch.provider_job_id, normalized_fetch.items)
            if normalized_fetch.items
            else ProviderBatchResultApplyResult(updated_count=0, missing_count=0, total_count=0)
        )

        refreshed_job = self._require_job(job_id)
        items_by_custom_id = {item.custom_id: item for item in refreshed_job.items}
        results_by_image_id: dict[int, Any] = {}
        imported_custom_ids: list[str] = []
        missing_custom_ids: list[str] = list(apply_result.missing_custom_ids)

        for raw_item in normalized_fetch.items:
            item = self._coerce_result_item(raw_item)
            db_item = items_by_custom_id.get(item.custom_id)
            if db_item is None or db_item.image_id is None:
                missing_custom_ids.append(item.custom_id)
                continue
            if item.status not in {"succeeded", "completed", "imported"} or item.annotation is None:
                continue
            results_by_image_id[db_item.image_id] = item.annotation
            imported_custom_ids.append(item.custom_id)

        model_id = refreshed_job.model_id or self._first_item_model_id(refreshed_job)
        if results_by_image_id and model_id is None:
            raise ProviderBatchError(f"Provider batch import に model_id が必要です: job_id={job_id}")
        self._validate_importable_job_state(refreshed_job, results_by_image_id)
        model_name = self._model_name_for_job(refreshed_job, model_id)
        save_result = self._annotation_save_service.save_provider_batch_results_by_image_id(
            results_by_image_id,
            model_id=model_id,
            model_name=model_name,
        )

        unique_missing_custom_ids = tuple(sorted(set(missing_custom_ids)))
        job_imported = (
            save_result.success_count > 0 and save_result.error_count == 0 and not unique_missing_custom_ids
        )
        if job_imported:
            updates_by_custom_id = {custom_id: {"status": "imported"} for custom_id in imported_custom_ids}
            if updates_by_custom_id:
                self._repository.update_provider_batch_items_by_custom_id(job_id, updates_by_custom_id)
            self._repository.update_provider_batch_job(
                job_id,
                {"status": "imported", "imported_at": datetime.now(UTC)},
            )

        return ProviderBatchImportResult(
            save_result=save_result,
            apply_result=apply_result,
            imported_count=save_result.success_count,
            skipped_count=save_result.skip_count + len(unique_missing_custom_ids),
            error_count=save_result.error_count,
            total_count=len(normalized_fetch.items),
            missing_custom_ids=unique_missing_custom_ids,
            job_imported=job_imported,
        )

    @staticmethod
    def _validate_importable_job_state(
        job: ProviderBatchJob, results_by_image_id: Mapping[int, Any]
    ) -> None:
        if results_by_image_id:
            ProviderBatchJobService.validate_transition(job.status, "imported")

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

    def _apply_fetch_job_state(
        self,
        job: ProviderBatchJob,
        fetch_result: ProviderBatchFetchResult,
    ) -> None:
        provider_status = fetch_result.status or fetch_result.provider_status
        if not provider_status:
            return
        next_status = ProviderBatchJobService.normalize_status(job.provider, provider_status)
        should_preserve_imported = job.status == "imported" and next_status == "completed"
        if not should_preserve_imported:
            ProviderBatchJobService.validate_transition(job.status, next_status)
        updates: dict[str, Any] = {
            "provider_status": fetch_result.provider_status,
        }
        if not should_preserve_imported:
            updates["status"] = next_status
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
        self._repository.update_provider_batch_job(job.id, updates)

    def _require_job(self, job_id: int) -> ProviderBatchJob:
        job = self._repository.get_provider_batch_job(job_id)
        if job is None:
            raise ProviderBatchError(f"Provider batch job が見つかりません: job_id={job_id}")
        return job

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
            return ProviderBatchFetchResult(
                provider_job_id=str(result.get("provider_job_id") or fallback_provider_job_id),
                provider_status=str(result.get("provider_status") or result.get("status") or "completed"),
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
        return ProviderBatchFetchResult(
            provider_job_id=cls._optional_str(getattr(result, "provider_job_id", None))
            or fallback_provider_job_id,
            provider_status=str(
                getattr(result, "provider_status", None) or getattr(result, "status", None) or "completed"
            ),
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

    @staticmethod
    def _first_item_model_id(job: ProviderBatchJob) -> int | None:
        for item in job.items:
            if item.model_id is not None:
                return item.model_id
        return None

    @staticmethod
    def _model_name_for_job(job: ProviderBatchJob, model_id: int | None) -> str:
        model = job.model
        litellm_model_id = getattr(model, "litellm_model_id", None) if model is not None else None
        if litellm_model_id:
            return str(litellm_model_id)
        if model_id is not None:
            return f"__provider_batch_model_{model_id}__"
        return "__provider_batch_model_unknown__"

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
    def _serialize_payload(payload: ProviderBatchRawPayload) -> str | None:
        if payload is None:
            return None
        if isinstance(payload, str):
            return payload
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _extract_error_field(error: Any, field_name: str) -> Any:
        if error is None:
            return None
        if isinstance(error, Mapping):
            return error.get(field_name) or error.get(f"error_{field_name}")
        return getattr(error, field_name, None) or getattr(error, f"error_{field_name}", None)
