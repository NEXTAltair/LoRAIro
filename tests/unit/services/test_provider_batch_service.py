"""ProviderBatchJobService tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from lorairo.database.db_repository import ImageRepository
from lorairo.services.provider_batch_service import (
    BatchSubmitMetadata,
    InvalidProviderBatchStatusTransition,
    ProviderBatchAdapterNotFoundError,
    ProviderBatchArtifactRef,
    ProviderBatchArtifacts,
    ProviderBatchError,
    ProviderBatchJobService,
    ProviderBatchStatus,
    ProviderBatchSubmission,
)


class FakeProviderBatchAdapter:
    provider = "openai"

    def __init__(self) -> None:
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

    def submit(self, request_file: Path, metadata: BatchSubmitMetadata) -> ProviderBatchSubmission:
        return self.submission

    def retrieve(self, provider_job_id: str) -> ProviderBatchStatus:
        return self.retrieve_status

    def cancel(self, provider_job_id: str) -> ProviderBatchStatus:
        return self.cancel_status

    def download_results(self, provider_job_id: str, destination_dir: Path) -> ProviderBatchArtifacts:
        return self.artifacts


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
    def test_submit_creates_job_with_normalized_status_and_raw_payload(
        self,
        test_repository: ImageRepository,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        service = ProviderBatchJobService(test_repository, {"openai": adapter})

        job_id = service.submit(
            Path("/tmp/input.jsonl"),
            BatchSubmitMetadata(provider="openai", endpoint="/v1/responses", request_count=1),
        )

        job = test_repository.get_provider_batch_job(job_id)
        assert job is not None
        assert job.provider == "openai"
        assert job.provider_job_id == "batch_123"
        assert job.status == "validating"
        assert job.provider_status == "validating"
        assert job.endpoint == "/v1/responses"
        assert job.request_count == 2
        assert job.input_artifact_path == "/tmp/input.jsonl"
        assert job.raw_provider_payload == '{"id": "batch_123", "status": "validating"}'

    def test_submit_preserves_empty_submission_payload(
        self,
        test_repository: ImageRepository,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        adapter.submission = replace(adapter.submission, raw_provider_payload={})
        service = ProviderBatchJobService(test_repository, {"openai": adapter})

        job_id = service.submit(
            Path("/tmp/input.jsonl"),
            BatchSubmitMetadata(provider="openai", raw_provider_payload={"request": "metadata"}),
        )

        job = test_repository.get_provider_batch_job(job_id)
        assert job is not None
        assert job.raw_provider_payload == "{}"

    def test_submit_normalizes_provider_before_persisting(
        self,
        test_repository: ImageRepository,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        service = ProviderBatchJobService(test_repository, {"openai": adapter})

        job_id = service.submit(
            Path("/tmp/input.jsonl"),
            BatchSubmitMetadata(provider=" OpenAI ", endpoint="/v1/responses"),
        )

        job = test_repository.get_provider_batch_job(job_id)
        assert job is not None
        assert job.provider == "openai"
        assert test_repository.get_provider_batch_job_by_provider_id("openai", "batch_123") is not None
        assert [listed.id for listed in test_repository.list_provider_batch_jobs(provider="openai")] == [
            job_id
        ]

    def test_refresh_updates_job_status_counts_and_raw_payload(
        self,
        test_repository: ImageRepository,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        service = ProviderBatchJobService(test_repository, {"openai": adapter})
        job_id = service.submit(Path("/tmp/input.jsonl"), BatchSubmitMetadata(provider="openai"))

        refreshed = service.refresh(job_id)

        assert refreshed.status == "completed"
        assert refreshed.provider_status == "completed"
        assert refreshed.succeeded_count == 2
        assert refreshed.failed_count == 0
        assert refreshed.raw_provider_payload == '{"id": "batch_123", "status": "completed"}'

    def test_refresh_preserves_anthropic_terminal_counts_when_ended(
        self,
        test_repository: ImageRepository,
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
        service = ProviderBatchJobService(test_repository, {"anthropic": adapter})
        job_id = service.submit(Path("/tmp/input.jsonl"), BatchSubmitMetadata(provider="anthropic"))

        refreshed = service.refresh(job_id)

        assert refreshed.status == "completed"
        assert refreshed.provider_status == "ended"
        assert refreshed.succeeded_count == 1
        assert refreshed.failed_count == 1

    def test_refresh_allows_anthropic_canceling_to_end_as_completed(
        self,
        test_repository: ImageRepository,
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
        service = ProviderBatchJobService(test_repository, {"anthropic": adapter})
        job_id = service.submit(Path("/tmp/input.jsonl"), BatchSubmitMetadata(provider="anthropic"))

        canceling = service.cancel(job_id)
        refreshed = service.refresh(job_id)

        assert canceling.status == "canceling"
        assert refreshed.status == "completed"
        assert refreshed.provider_status == "ended"
        assert refreshed.canceled_count == 2

    def test_refresh_preserves_raw_payload_when_provider_omits_payload(
        self,
        test_repository: ImageRepository,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        adapter.retrieve_status = replace(adapter.retrieve_status, raw_provider_payload=None)
        service = ProviderBatchJobService(test_repository, {"openai": adapter})
        job_id = service.submit(Path("/tmp/input.jsonl"), BatchSubmitMetadata(provider="openai"))

        refreshed = service.refresh(job_id)

        assert refreshed.status == "completed"
        assert refreshed.raw_provider_payload == '{"id": "batch_123", "status": "validating"}'

    def test_refresh_rejects_mismatched_provider_job_id(
        self,
        test_repository: ImageRepository,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        adapter.retrieve_status = replace(adapter.retrieve_status, provider_job_id="batch_other")
        service = ProviderBatchJobService(test_repository, {"openai": adapter})
        job_id = service.submit(Path("/tmp/input.jsonl"), BatchSubmitMetadata(provider="openai"))

        with pytest.raises(ProviderBatchError, match="job ID mismatch"):
            service.refresh(job_id)

        job = test_repository.get_provider_batch_job(job_id)
        assert job is not None
        assert job.status == "validating"

    def test_cancel_validates_transition_and_updates_job(
        self,
        test_repository: ImageRepository,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        adapter.submission = replace(adapter.submission, provider_status="in_progress")
        service = ProviderBatchJobService(test_repository, {"openai": adapter})
        job_id = service.submit(Path("/tmp/input.jsonl"), BatchSubmitMetadata(provider="openai"))

        canceled = service.cancel(job_id)

        assert canceled.status == "canceled"
        assert canceled.provider_status == "cancelled"
        assert canceled.canceled_count == 2

    def test_cancel_rejects_completed_job(self, test_repository: ImageRepository) -> None:
        adapter = FakeProviderBatchAdapter()
        service = ProviderBatchJobService(test_repository, {"openai": adapter})
        job_id = service.submit(Path("/tmp/input.jsonl"), BatchSubmitMetadata(provider="openai"))
        service.refresh(job_id)

        with pytest.raises(InvalidProviderBatchStatusTransition):
            service.cancel(job_id)

    def test_download_results_registers_artifacts_and_updates_paths(
        self,
        test_repository: ImageRepository,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        service = ProviderBatchJobService(test_repository, {"openai": adapter})
        job_id = service.submit(Path("/tmp/input.jsonl"), BatchSubmitMetadata(provider="openai"))

        artifacts = service.download_results(job_id, Path("/tmp"))

        assert len(artifacts.artifacts) == 2
        registered = test_repository.list_provider_batch_artifacts(job_id)
        assert [artifact.artifact_type for artifact in registered] == ["output", "error"]
        job = test_repository.get_provider_batch_job(job_id)
        assert job is not None
        assert job.output_artifact_path == "/tmp/output.jsonl"
        assert job.error_artifact_path == "/tmp/error.jsonl"
        assert job.raw_provider_payload == '{"output_file_id": "file_out"}'

    def test_download_results_is_idempotent_for_existing_artifacts(
        self,
        test_repository: ImageRepository,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        service = ProviderBatchJobService(test_repository, {"openai": adapter})
        job_id = service.submit(Path("/tmp/input.jsonl"), BatchSubmitMetadata(provider="openai"))

        service.download_results(job_id, Path("/tmp"))
        service.download_results(job_id, Path("/tmp"))

        registered = test_repository.list_provider_batch_artifacts(job_id)
        assert len(registered) == 2
        assert [artifact.artifact_type for artifact in registered] == ["output", "error"]

    def test_download_results_rejects_mismatched_provider_job_id(
        self,
        test_repository: ImageRepository,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        adapter.artifacts = replace(adapter.artifacts, provider_job_id="batch_other")
        service = ProviderBatchJobService(test_repository, {"openai": adapter})
        job_id = service.submit(Path("/tmp/input.jsonl"), BatchSubmitMetadata(provider="openai"))

        with pytest.raises(ProviderBatchError, match="job ID mismatch"):
            service.download_results(job_id, Path("/tmp"))

        assert test_repository.list_provider_batch_artifacts(job_id) == []

    def test_missing_adapter_raises(self, test_repository: ImageRepository) -> None:
        service = ProviderBatchJobService(test_repository)

        with pytest.raises(ProviderBatchAdapterNotFoundError):
            service.submit(Path("/tmp/input.jsonl"), BatchSubmitMetadata(provider="openai"))
