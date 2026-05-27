"""ProviderBatchJobService tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from lorairo.database.repository.provider_batch import ProviderBatchRepository
from lorairo.services.provider_batch_service import (
    BatchJobHandle,
    BatchSubmitItem,
    BatchSubmitMetadata,
    BatchSubmitRequest,
    InvalidProviderBatchRequest,
    InvalidProviderBatchStatusTransition,
    ProviderBatchAdapterNotFoundError,
    ProviderBatchArtifactRef,
    ProviderBatchArtifacts,
    ProviderBatchError,
    ProviderBatchFetchResult,
    ProviderBatchJobService,
    ProviderBatchResultItem,
    ProviderBatchStatus,
    ProviderBatchSubmission,
)


class FakeProviderBatchAdapter:
    provider = "openai"

    def __init__(self) -> None:
        self.submitted_request: BatchSubmitRequest | None = None
        self.retrieve_handle: BatchJobHandle | None = None
        self.cancel_handle: BatchJobHandle | None = None
        self.fetch_handle: BatchJobHandle | None = None
        self.fetch_destination: Path | None = None
        self.submission = ProviderBatchSubmission(
            provider_job_id="batch_123",
            provider_status="validating",
            request_count=2,
            submitted_at=datetime(2026, 5, 25, tzinfo=UTC),
            raw_provider_payload={"id": "batch_123", "status": "validating"},
        )
        self.retrieve_status = ProviderBatchStatus(
            provider_job_id="batch_123",
            provider_status="completed",
            request_count=2,
            succeeded_count=2,
            failed_count=0,
            completed_at=datetime(2026, 5, 25, 1, tzinfo=UTC),
            raw_provider_payload={"id": "batch_123", "status": "completed"},
        )
        self.cancel_status = ProviderBatchStatus(
            provider_job_id="batch_123",
            provider_status="cancelled",
            canceled_count=2,
            canceled_at=datetime(2026, 5, 25, 1, tzinfo=UTC),
            raw_provider_payload={"id": "batch_123", "status": "cancelled"},
        )
        self.artifacts = ProviderBatchArtifacts(
            provider_job_id="batch_123",
            artifacts=(
                ProviderBatchArtifactRef("output", Path("/tmp/output.jsonl"), "file_out", "abc"),
                ProviderBatchArtifactRef("error", Path("/tmp/error.jsonl"), "file_err", "def"),
            ),
            raw_provider_payload={"output_file_id": "file_out"},
        )
        self.fetch_result: ProviderBatchFetchResult | ProviderBatchArtifacts = self.artifacts

    def submit_batch(self, request: BatchSubmitRequest) -> ProviderBatchSubmission:
        self.submitted_request = request
        return self.submission

    def retrieve_batch(self, handle: BatchJobHandle) -> ProviderBatchStatus:
        self.retrieve_handle = handle
        return self.retrieve_status

    def cancel_batch(self, handle: BatchJobHandle) -> ProviderBatchStatus:
        self.cancel_handle = handle
        return self.cancel_status

    def fetch_batch_results(
        self, handle: BatchJobHandle, destination_dir: Path
    ) -> ProviderBatchFetchResult | ProviderBatchArtifacts:
        self.fetch_handle = handle
        self.fetch_destination = destination_dir
        return self.fetch_result


class LegacyProviderBatchAdapter(FakeProviderBatchAdapter):
    def submit(self, request_file: Path, metadata: BatchSubmitMetadata) -> ProviderBatchSubmission:
        return self.submission

    def retrieve(self, provider_job_id: str) -> ProviderBatchStatus:
        return self.retrieve_status

    def cancel(self, provider_job_id: str) -> ProviderBatchStatus:
        return self.cancel_status

    def download_results(self, provider_job_id: str, destination_dir: Path) -> ProviderBatchArtifacts:
        return self.artifacts


def make_submit_request(
    *,
    provider: str = "openai",
    items: tuple[BatchSubmitItem, ...] | None = None,
) -> BatchSubmitRequest:
    return BatchSubmitRequest(
        provider=provider,
        endpoint="responses",
        litellm_model_id="openai/gpt-4.1-mini",
        prompt_profile="default",
        api_keys={"openai_key": "sk-test"},
        model_id=10,
        request_artifact_path=Path("/tmp/input.jsonl"),
        items=items
        if items is not None
        else (
            BatchSubmitItem(
                custom_id="img-1",
                image_id=1,
                image_path=Path("/tmp/images/1.webp"),
                raw_request={"custom_id": "img-1"},
            ),
            BatchSubmitItem(
                custom_id="img-2",
                image_id=2,
                image_path=Path("/tmp/images/2.webp"),
                model_id=11,
            ),
        ),
    )


@pytest.mark.unit
class TestProviderBatchStatusMapping:
    def test_openai_status_mapping(self) -> None:
        assert ProviderBatchJobService.normalize_status("openai", "validating") == "validating"
        assert ProviderBatchJobService.normalize_status("openai", "in_progress") == "running"
        assert ProviderBatchJobService.normalize_status("openai", "finalizing") == "running"
        assert ProviderBatchJobService.normalize_status("openai", "completed") == "completed"
        assert ProviderBatchJobService.normalize_status("openai", "cancelled") == "canceled"

    def test_anthropic_status_mapping(self) -> None:
        assert ProviderBatchJobService.normalize_status("anthropic", "in_progress") == "running"
        assert ProviderBatchJobService.normalize_status("anthropic", "ended") == "completed"

    def test_google_status_mapping(self) -> None:
        assert ProviderBatchJobService.normalize_status("google", "JOB_STATE_PENDING") == "validating"
        assert ProviderBatchJobService.normalize_status("google", "JOB_STATE_RUNNING") == "running"
        assert ProviderBatchJobService.normalize_status("google", "JOB_STATE_SUCCEEDED") == "completed"
        assert ProviderBatchJobService.normalize_status("google", "JOB_STATE_PARTIALLY_SUCCEEDED") == (
            "completed"
        )

    def test_unknown_status_raises(self) -> None:
        with pytest.raises(ProviderBatchError):
            ProviderBatchJobService.normalize_status("openai", "mystery")

    def test_invalid_transition_raises(self) -> None:
        ProviderBatchJobService.validate_transition("running", "completed")
        ProviderBatchJobService.validate_transition("canceling", "completed")
        ProviderBatchJobService.validate_transition("completed", "completed")

        with pytest.raises(InvalidProviderBatchStatusTransition):
            ProviderBatchJobService.validate_transition("completed", "running")


@pytest.mark.unit
class TestProviderBatchJobService:
    def test_submit_batch_calls_library_boundary_and_creates_job_items(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        service = ProviderBatchJobService(test_provider_batch_repository, {"openai": adapter})

        job_id = service.submit_batch(make_submit_request(provider=" OpenAI "))

        job = test_provider_batch_repository.get_provider_batch_job(job_id)
        assert job is not None
        assert adapter.submitted_request is not None
        assert adapter.submitted_request.provider == "openai"
        assert adapter.submitted_request.endpoint == "responses"
        assert adapter.submitted_request.api_keys == {"openai": "sk-test"}
        assert job.provider == "openai"
        assert job.provider_job_id == "batch_123"
        assert job.status == "validating"
        assert job.provider_status == "validating"
        assert job.endpoint == "responses"
        assert job.model_id == 10
        assert job.request_count == 2
        assert job.input_artifact_path == "/tmp/input.jsonl"
        assert job.raw_provider_payload == '{"id": "batch_123", "status": "validating"}'
        items = test_provider_batch_repository.list_provider_batch_items(job_id)
        assert [(item.custom_id, item.image_id, item.model_id, item.status) for item in items] == [
            ("img-1", 1, 10, "validating"),
            ("img-2", 2, 11, "validating"),
        ]
        assert items[0].raw_request == '{"custom_id": "img-1"}'

    def test_submit_batch_validates_custom_id_contract(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        service = ProviderBatchJobService(test_provider_batch_repository, {"openai": adapter})

        with pytest.raises(InvalidProviderBatchRequest, match="custom_id"):
            service.submit_batch(
                make_submit_request(
                    items=(
                        BatchSubmitItem(
                            custom_id="image-1",
                            image_id=1,
                            image_path=Path("/tmp/images/1.webp"),
                        ),
                    )
                )
            )

    def test_submit_batch_rejects_duplicate_custom_ids(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        service = ProviderBatchJobService(test_provider_batch_repository, {"openai": adapter})

        with pytest.raises(InvalidProviderBatchRequest, match="重複"):
            service.submit_batch(
                make_submit_request(
                    items=(
                        BatchSubmitItem("img-1", 1, Path("/tmp/1.webp")),
                        BatchSubmitItem("img-1", 1, Path("/tmp/1-copy.webp")),
                    )
                )
            )

    def test_submit_preserves_empty_submission_payload_for_legacy_wrapper(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
    ) -> None:
        adapter = LegacyProviderBatchAdapter()
        adapter.submission = replace(adapter.submission, raw_provider_payload={})
        service = ProviderBatchJobService(test_provider_batch_repository, {"openai": adapter})

        job_id = service.submit(
            Path("/tmp/input.jsonl"),
            BatchSubmitMetadata(provider="openai", raw_provider_payload={"request": "metadata"}),
        )

        job = test_provider_batch_repository.get_provider_batch_job(job_id)
        assert job is not None
        assert job.raw_provider_payload == "{}"

    def test_legacy_submit_normalizes_provider_before_persisting(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
    ) -> None:
        adapter = LegacyProviderBatchAdapter()
        service = ProviderBatchJobService(test_provider_batch_repository, {"openai": adapter})

        job_id = service.submit(
            Path("/tmp/input.jsonl"),
            BatchSubmitMetadata(provider=" OpenAI ", endpoint="/v1/responses"),
        )

        job = test_provider_batch_repository.get_provider_batch_job(job_id)
        assert job is not None
        assert job.provider == "openai"
        assert (
            test_provider_batch_repository.get_provider_batch_job_by_provider_id("openai", "batch_123")
            is not None
        )
        assert [
            listed.id
            for listed in test_provider_batch_repository.list_provider_batch_jobs(provider="openai")
        ] == [job_id]

    def test_legacy_submit_rejects_new_batch_client_without_empty_item_fallback(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        service = ProviderBatchJobService(test_provider_batch_repository, {"openai": adapter})

        with pytest.raises(ProviderBatchError, match="Use submit_batch"):
            service.submit(Path("/tmp/input.jsonl"), BatchSubmitMetadata(provider="openai"))

        assert test_provider_batch_repository.list_provider_batch_jobs(provider="openai") == []

    def test_refresh_updates_job_status_counts_and_raw_payload(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        service = ProviderBatchJobService(test_provider_batch_repository, {"openai": adapter})
        job_id = service.submit_batch(make_submit_request())

        refreshed = service.refresh(job_id, api_keys={"openai_key": "sk-test"})

        assert adapter.retrieve_handle == BatchJobHandle(
            provider="openai", provider_job_id="batch_123", api_keys={"openai": "sk-test"}
        )
        assert refreshed.status == "completed"
        assert refreshed.provider_status == "completed"
        assert refreshed.succeeded_count == 2
        assert refreshed.failed_count == 0
        assert refreshed.raw_provider_payload == '{"id": "batch_123", "status": "completed"}'

    def test_refresh_preserves_anthropic_terminal_counts_when_ended(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        adapter.provider = "anthropic"
        adapter.submission = replace(adapter.submission, provider_status="in_progress")
        adapter.retrieve_status = replace(
            adapter.retrieve_status,
            provider_status="ended",
            succeeded_count=1,
            failed_count=1,
            canceled_count=0,
            expired_count=0,
        )
        service = ProviderBatchJobService(test_provider_batch_repository, {"anthropic": adapter})
        job_id = service.submit_batch(make_submit_request(provider="anthropic"))

        refreshed = service.refresh(job_id)

        assert refreshed.status == "completed"
        assert refreshed.provider_status == "ended"
        assert refreshed.succeeded_count == 1
        assert refreshed.failed_count == 1

    def test_refresh_allows_anthropic_canceling_to_end_as_completed(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        adapter.provider = "anthropic"
        adapter.submission = replace(adapter.submission, provider_status="in_progress")
        adapter.cancel_status = replace(adapter.cancel_status, provider_status="canceling")
        adapter.retrieve_status = replace(
            adapter.retrieve_status,
            provider_status="ended",
            succeeded_count=0,
            failed_count=0,
            canceled_count=2,
        )
        service = ProviderBatchJobService(test_provider_batch_repository, {"anthropic": adapter})
        job_id = service.submit_batch(make_submit_request(provider="anthropic"))

        canceling = service.cancel(job_id)
        refreshed = service.refresh(job_id)

        assert canceling.status == "canceling"
        assert refreshed.status == "completed"
        assert refreshed.provider_status == "ended"
        assert refreshed.canceled_count == 2

    def test_refresh_preserves_raw_payload_when_provider_omits_payload(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        adapter.retrieve_status = replace(adapter.retrieve_status, raw_provider_payload=None)
        service = ProviderBatchJobService(test_provider_batch_repository, {"openai": adapter})
        job_id = service.submit_batch(make_submit_request())

        refreshed = service.refresh(job_id)

        assert refreshed.status == "completed"
        assert refreshed.raw_provider_payload == '{"id": "batch_123", "status": "validating"}'

    def test_refresh_rejects_mismatched_provider_job_id(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        adapter.retrieve_status = replace(adapter.retrieve_status, provider_job_id="batch_other")
        service = ProviderBatchJobService(test_provider_batch_repository, {"openai": adapter})
        job_id = service.submit_batch(make_submit_request())

        with pytest.raises(ProviderBatchError, match="job ID mismatch"):
            service.refresh(job_id)

        job = test_provider_batch_repository.get_provider_batch_job(job_id)
        assert job is not None
        assert job.status == "validating"

    def test_cancel_validates_transition_and_updates_job(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        adapter.submission = replace(adapter.submission, provider_status="in_progress")
        service = ProviderBatchJobService(test_provider_batch_repository, {"openai": adapter})
        job_id = service.submit_batch(make_submit_request())

        canceled = service.cancel(job_id, api_keys={"claude_key": "unused", "openai_key": "sk-test"})

        assert adapter.cancel_handle == BatchJobHandle(
            provider="openai",
            provider_job_id="batch_123",
            api_keys={"anthropic": "unused", "openai": "sk-test"},
        )
        assert canceled.status == "canceled"
        assert canceled.provider_status == "cancelled"
        assert canceled.canceled_count == 2

    def test_cancel_rejects_completed_job(
        self, test_provider_batch_repository: ProviderBatchRepository
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        service = ProviderBatchJobService(test_provider_batch_repository, {"openai": adapter})
        job_id = service.submit_batch(make_submit_request())
        service.refresh(job_id)

        with pytest.raises(InvalidProviderBatchStatusTransition):
            service.cancel(job_id)

    def test_download_results_registers_artifacts_and_updates_paths(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        service = ProviderBatchJobService(test_provider_batch_repository, {"openai": adapter})
        job_id = service.submit_batch(make_submit_request())

        artifacts = service.download_results(job_id, Path("/tmp/batch_results"))

        assert adapter.fetch_handle == BatchJobHandle(
            provider="openai", provider_job_id="batch_123", api_keys={}
        )
        assert adapter.fetch_destination == Path("/tmp/batch_results")
        assert len(artifacts.artifacts) == 2
        registered = test_provider_batch_repository.list_provider_batch_artifacts(job_id)
        assert [artifact.artifact_type for artifact in registered] == ["output", "error"]
        job = test_provider_batch_repository.get_provider_batch_job(job_id)
        assert job is not None
        assert job.output_artifact_path == "/tmp/output.jsonl"
        assert job.error_artifact_path == "/tmp/error.jsonl"
        assert job.raw_provider_payload == '{"output_file_id": "file_out"}'

    def test_fetch_results_registers_artifacts_items_and_updates_job_status(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        adapter.fetch_result = ProviderBatchFetchResult(
            provider_job_id="batch_123",
            provider_status="completed",
            request_count=2,
            succeeded_count=1,
            failed_count=1,
            completed_at=datetime(2026, 5, 25, 2, tzinfo=UTC),
            artifacts=(ProviderBatchArtifactRef("output", Path("/tmp/output.jsonl"), "file_out"),),
            items=(
                ProviderBatchResultItem("img-1", "succeeded", annotation={"tags": ["safe"]}),
                ProviderBatchResultItem("img-2", "failed", error_type="PARSE", error_message="bad"),
            ),
            raw_provider_payload={"status": "completed"},
        )
        service = ProviderBatchJobService(test_provider_batch_repository, {"openai": adapter})
        job_id = service.submit_batch(make_submit_request())

        fetch_result = service.fetch_results(job_id, Path("/tmp/batch_results"))

        assert fetch_result.items[0].annotation == {"tags": ["safe"]}
        assert len(test_provider_batch_repository.list_provider_batch_artifacts(job_id)) == 1
        job = test_provider_batch_repository.get_provider_batch_job(job_id)
        assert job is not None
        assert job.status == "completed"
        assert job.provider_status == "completed"
        assert job.succeeded_count == 1
        assert job.failed_count == 1
        assert job.output_artifact_path == "/tmp/output.jsonl"
        assert job.raw_provider_payload == '{"status": "completed"}'

    def test_download_results_is_idempotent_for_existing_artifacts(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        service = ProviderBatchJobService(test_provider_batch_repository, {"openai": adapter})
        job_id = service.submit_batch(make_submit_request())

        service.download_results(job_id, Path("/tmp"))
        service.download_results(job_id, Path("/tmp"))

        registered = test_provider_batch_repository.list_provider_batch_artifacts(job_id)
        assert len(registered) == 2
        assert [artifact.artifact_type for artifact in registered] == ["output", "error"]

    def test_download_results_rejects_mismatched_provider_job_id(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        adapter.artifacts = replace(adapter.artifacts, provider_job_id="batch_other")
        adapter.fetch_result = adapter.artifacts
        service = ProviderBatchJobService(test_provider_batch_repository, {"openai": adapter})
        job_id = service.submit_batch(make_submit_request())

        with pytest.raises(ProviderBatchError, match="job ID mismatch"):
            service.download_results(job_id, Path("/tmp"))

        assert test_provider_batch_repository.list_provider_batch_artifacts(job_id) == []

    def test_download_results_allows_completed_provider_status_after_import(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        adapter.fetch_result = ProviderBatchFetchResult(
            provider_job_id="batch_123",
            provider_status="completed",
            artifacts=(ProviderBatchArtifactRef("output", Path("/tmp/output.jsonl")),),
        )
        service = ProviderBatchJobService(test_provider_batch_repository, {"openai": adapter})
        job_id = service.submit_batch(make_submit_request())
        test_provider_batch_repository.update_provider_batch_job(job_id, {"status": "imported"})

        service.download_results(job_id, Path("/tmp"))

        job = test_provider_batch_repository.get_provider_batch_job(job_id)
        assert job is not None
        assert job.status == "imported"
        assert job.provider_status == "completed"
        assert job.output_artifact_path == "/tmp/output.jsonl"

    def test_download_results_does_not_rewrite_terminal_status_for_legacy_artifacts(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        adapter.fetch_result = ProviderBatchArtifacts(
            provider_job_id="batch_123",
            artifacts=(ProviderBatchArtifactRef("error", Path("/tmp/error.jsonl")),),
        )
        service = ProviderBatchJobService(test_provider_batch_repository, {"openai": adapter})
        job_id = service.submit_batch(make_submit_request())
        test_provider_batch_repository.update_provider_batch_job(job_id, {"status": "failed"})

        service.download_results(job_id, Path("/tmp"))

        job = test_provider_batch_repository.get_provider_batch_job(job_id)
        assert job is not None
        assert job.status == "failed"
        assert job.error_artifact_path == "/tmp/error.jsonl"

    def test_fetch_results_coerces_mapping_artifacts_and_timestamps(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        adapter.fetch_result = {
            "provider_job_id": "batch_123",
            "provider_status": "completed",
            "completed_at": "2026-05-25T02:00:00+00:00",
            "artifacts": [
                {
                    "artifact_type": "output",
                    "local_path": "/tmp/output.jsonl",
                    "provider_file_id": "file_out",
                    "sha256": "abc",
                }
            ],
        }
        service = ProviderBatchJobService(test_provider_batch_repository, {"openai": adapter})
        job_id = service.submit_batch(make_submit_request())

        fetch_result = service.fetch_results(job_id, Path("/tmp"))

        assert fetch_result.artifacts[0].local_path == Path("/tmp/output.jsonl")
        job = test_provider_batch_repository.get_provider_batch_job(job_id)
        assert job is not None
        assert job.completed_at is not None
        assert job.completed_at.isoformat() == "2026-05-25T02:00:00"
        assert job.output_artifact_path == "/tmp/output.jsonl"

    def test_fetch_results_does_not_complete_mapping_without_provider_status(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        adapter.fetch_result = {
            "provider_job_id": "batch_123",
            "artifacts": [{"artifact_type": "output", "local_path": "/tmp/output.jsonl"}],
        }
        service = ProviderBatchJobService(test_provider_batch_repository, {"openai": adapter})
        job_id = service.submit_batch(make_submit_request())

        service.fetch_results(job_id, Path("/tmp"))

        job = test_provider_batch_repository.get_provider_batch_job(job_id)
        assert job is not None
        assert job.status == "validating"
        assert job.provider_status == "validating"
        assert job.output_artifact_path == "/tmp/output.jsonl"

    def test_missing_adapter_raises(self, test_provider_batch_repository: ProviderBatchRepository) -> None:
        service = ProviderBatchJobService(test_provider_batch_repository)

        with pytest.raises(ProviderBatchAdapterNotFoundError):
            service.submit_batch(make_submit_request())
