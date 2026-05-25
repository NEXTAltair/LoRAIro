"""Provider Batch API job repository tests."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from lorairo.database.db_repository import ImageRepository


@pytest.mark.unit
class TestProviderBatchRepository:
    def test_create_get_list_and_update_job(self, test_repository: ImageRepository) -> None:
        job_id = test_repository.create_provider_batch_job(
            {
                "provider": "openai",
                "provider_job_id": "batch_123",
                "status": "submitted",
                "provider_status": "validating",
                "endpoint": "/v1/responses",
                "request_count": 3,
                "raw_provider_payload": '{"id":"batch_123"}',
            }
        )

        job = test_repository.get_provider_batch_job(job_id)
        assert job is not None
        assert job.provider == "openai"
        assert job.provider_job_id == "batch_123"
        assert job.request_count == 3

        by_provider = test_repository.get_provider_batch_job_by_provider_id("openai", "batch_123")
        assert by_provider is not None
        assert by_provider.id == job_id

        assert [job.id for job in test_repository.list_provider_batch_jobs(provider="openai")] == [job_id]
        assert test_repository.update_provider_batch_job(
            job_id,
            {
                "status": "completed",
                "provider_status": "completed",
                "succeeded_count": 3,
            },
        )

        updated = test_repository.get_provider_batch_job(job_id)
        assert updated is not None
        assert updated.status == "completed"
        assert updated.succeeded_count == 3

    def test_provider_job_id_unique_per_provider(self, test_repository: ImageRepository) -> None:
        data = {
            "provider": "openai",
            "provider_job_id": "batch_dupe",
            "status": "submitted",
        }
        test_repository.create_provider_batch_job(data)

        with pytest.raises(IntegrityError):
            test_repository.create_provider_batch_job(data)

        other_provider_id = test_repository.create_provider_batch_job(
            {
                "provider": "anthropic",
                "provider_job_id": "batch_dupe",
                "status": "submitted",
            }
        )
        assert other_provider_id > 0

    def test_job_with_null_provider_job_id_can_be_created_multiple_times(
        self,
        test_repository: ImageRepository,
    ) -> None:
        first_id = test_repository.create_provider_batch_job({"provider": "openai", "status": "draft"})
        second_id = test_repository.create_provider_batch_job({"provider": "openai", "status": "draft"})

        assert first_id != second_id

    def test_items_artifacts_and_delete_job(self, test_repository: ImageRepository) -> None:
        job_id = test_repository.create_provider_batch_job(
            {
                "provider": "openai",
                "provider_job_id": "batch_items",
                "status": "submitted",
            }
        )
        item_id = test_repository.create_provider_batch_item(
            {
                "job_id": job_id,
                "custom_id": "img-1-model-1-task-tags-run-abcd",
                "task_type": "tags",
                "status": "submitted",
                "raw_request": '{"custom_id":"img-1-model-1-task-tags-run-abcd"}',
            }
        )
        artifact_id = test_repository.create_provider_batch_artifact(
            {
                "job_id": job_id,
                "artifact_type": "input",
                "local_path": "/tmp/batch.jsonl",
                "provider_file_id": "file_123",
                "sha256": "abc",
            }
        )

        assert item_id > 0
        assert artifact_id > 0
        assert len(test_repository.list_provider_batch_items(job_id)) == 1
        assert len(test_repository.list_provider_batch_artifacts(job_id)) == 1

        assert test_repository.update_provider_batch_item_by_custom_id(
            job_id,
            "img-1-model-1-task-tags-run-abcd",
            {
                "status": "failed",
                "error_type": "provider_error",
                "error_message": "bad request",
            },
        )
        failed_items = test_repository.list_provider_batch_items(job_id, status="failed")
        assert len(failed_items) == 1
        assert failed_items[0].error_message == "bad request"

        assert test_repository.delete_provider_batch_job(job_id)
        assert test_repository.get_provider_batch_job(job_id) is None
        assert test_repository.list_provider_batch_items(job_id) == []
        assert test_repository.list_provider_batch_artifacts(job_id) == []

    def test_update_rejects_unknown_fields(self, test_repository: ImageRepository) -> None:
        job_id = test_repository.create_provider_batch_job({"provider": "openai", "status": "draft"})

        with pytest.raises(ValueError):
            test_repository.update_provider_batch_job(job_id, {"provider": "anthropic"})

        with pytest.raises(ValueError):
            test_repository.update_provider_batch_item_by_custom_id(job_id, "missing", {"custom_id": "x"})
