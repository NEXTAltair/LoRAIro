"""ProviderBatchWorkflowService tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import sessionmaker

from lorairo.database.db_repository import ImageRepository
from lorairo.database.schema import Image
from lorairo.services.provider_batch_service import (
    BatchJobHandle,
    BatchSubmitRequest,
    ProviderBatchArtifactRef,
    ProviderBatchArtifacts,
    ProviderBatchError,
    ProviderBatchStatus,
    ProviderBatchSubmission,
)
from lorairo.services.provider_batch_workflow_service import (
    ProviderBatchResultItem,
    ProviderBatchWorkflowService,
)


class FakeProviderBatchAdapter:
    provider = "openai"

    def __init__(self) -> None:
        self.submitted_request: BatchSubmitRequest | None = None
        self.fetch_handle: BatchJobHandle | None = None
        self.fetch_destination: Path | None = None
        self.retrieve_handle: BatchJobHandle | None = None
        self.cancel_handle: BatchJobHandle | None = None
        self.submission = ProviderBatchSubmission(
            provider_job_id="batch_123",
            provider_status="validating",
        )
        self.retrieve_status = ProviderBatchStatus(
            provider_job_id="batch_123",
            provider_status="completed",
        )
        self.cancel_status = ProviderBatchStatus(
            provider_job_id="batch_123",
            provider_status="cancelled",
        )
        self.artifacts = ProviderBatchArtifacts(
            provider_job_id="batch_123",
            artifacts=(
                ProviderBatchArtifactRef("output", Path("/tmp/output.jsonl")),
                ProviderBatchArtifactRef("error", Path("/tmp/error.jsonl")),
            ),
        )

    def submit_batch(self, request: BatchSubmitRequest) -> ProviderBatchSubmission:
        self.submitted_request = request
        return self.submission

    def retrieve_batch(self, handle: BatchJobHandle) -> ProviderBatchStatus:
        self.retrieve_handle = handle
        return self.retrieve_status

    def cancel_batch(self, handle: BatchJobHandle) -> ProviderBatchStatus:
        self.cancel_handle = handle
        return self.cancel_status

    def fetch_batch_results(self, handle: BatchJobHandle, destination_dir: Path) -> ProviderBatchArtifacts:
        self.fetch_handle = handle
        self.fetch_destination = destination_dir
        return self.artifacts


@pytest.fixture
def batch_config(tmp_path: Path) -> Mock:
    config = Mock()
    config.get_api_keys.return_value = {"openai_key": "sk-test"}
    config.get_batch_results_directory.return_value = tmp_path / "batch_results"
    return config


@pytest.fixture
def workflow(
    test_repository: ImageRepository,
    batch_config: Mock,
) -> tuple[ProviderBatchWorkflowService, FakeProviderBatchAdapter]:
    adapter = FakeProviderBatchAdapter()
    service = ProviderBatchWorkflowService(test_repository, batch_config, adapters={"openai": adapter})
    return service, adapter


def _insert_image(session_factory: sessionmaker, image_id: int, stored_path: str) -> None:
    with session_factory() as session:
        session.add(
            Image(
                id=image_id,
                uuid=f"test-provider-batch-{image_id}",
                phash=f"providerbatch{image_id:04d}",
                original_image_path=stored_path,
                stored_image_path=stored_path,
                width=100,
                height=100,
                format="WEBP",
                mode="RGB",
                has_alpha=False,
                filename=Path(stored_path).name,
                extension=Path(stored_path).suffix,
            )
        )
        session.commit()


@pytest.mark.unit
class TestProviderBatchWorkflowService:
    def test_submit_images_builds_request_from_image_ids(
        self,
        workflow: tuple[ProviderBatchWorkflowService, FakeProviderBatchAdapter],
        test_repository: ImageRepository,
        db_session_factory: sessionmaker,
    ) -> None:
        service, adapter = workflow
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")
        _insert_image(db_session_factory, 2, "/tmp/images/two.webp")

        job_id = service.submit_images(
            provider="openai",
            endpoint="responses",
            litellm_model_id="openai/gpt-test",
            prompt_profile="default",
            image_ids=[1, 2],
        )

        assert adapter.submitted_request is not None
        assert adapter.submitted_request.api_keys == {"openai": "sk-test"}
        assert [
            (item.custom_id, item.image_id, item.image_path) for item in adapter.submitted_request.items
        ] == [
            ("img-1", 1, Path("/tmp/images/one.webp")),
            ("img-2", 2, Path("/tmp/images/two.webp")),
        ]
        job = test_repository.get_provider_batch_job(job_id)
        assert job is not None
        assert job.provider_job_id == "batch_123"
        assert [item.custom_id for item in test_repository.list_provider_batch_items(job_id)] == [
            "img-1",
            "img-2",
        ]

    def test_submit_images_uses_path_overrides(
        self,
        workflow: tuple[ProviderBatchWorkflowService, FakeProviderBatchAdapter],
        db_session_factory: sessionmaker,
    ) -> None:
        service, adapter = workflow
        _insert_image(db_session_factory, 1, "/tmp/images/original.webp")

        service.submit_images(
            provider="openai",
            endpoint="responses",
            litellm_model_id="openai/gpt-test",
            prompt_profile="default",
            image_ids=[1],
            image_paths={1: Path("/tmp/resized/one.webp")},
        )

        assert adapter.submitted_request is not None
        assert adapter.submitted_request.items[0].image_path == Path("/tmp/resized/one.webp")

    def test_submit_images_rejects_missing_image_id(
        self,
        workflow: tuple[ProviderBatchWorkflowService, FakeProviderBatchAdapter],
    ) -> None:
        service, _adapter = workflow

        with pytest.raises(ProviderBatchError, match="対象画像が見つかりません"):
            service.submit_images(
                provider="openai",
                endpoint="responses",
                litellm_model_id="openai/gpt-test",
                prompt_profile="default",
                image_ids=[999],
            )

    def test_download_results_uses_configured_directory(
        self,
        workflow: tuple[ProviderBatchWorkflowService, FakeProviderBatchAdapter],
        db_session_factory: sessionmaker,
        batch_config: Mock,
    ) -> None:
        service, adapter = workflow
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")
        job_id = service.submit_images(
            provider="openai",
            endpoint="responses",
            litellm_model_id="openai/gpt-test",
            prompt_profile="default",
            image_ids=[1],
        )

        service.download_results(job_id)

        assert adapter.fetch_destination == batch_config.get_batch_results_directory.return_value
        assert adapter.fetch_handle == BatchJobHandle(
            provider="openai",
            provider_job_id="batch_123",
            api_keys={"openai": "sk-test"},
        )

    def test_refresh_uses_configured_api_keys(
        self,
        workflow: tuple[ProviderBatchWorkflowService, FakeProviderBatchAdapter],
        db_session_factory: sessionmaker,
    ) -> None:
        service, adapter = workflow
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")
        job_id = service.submit_images(
            provider="openai",
            endpoint="responses",
            litellm_model_id="openai/gpt-test",
            prompt_profile="default",
            image_ids=[1],
        )

        refreshed = service.refresh(job_id)

        assert refreshed.status == "completed"
        assert adapter.retrieve_handle == BatchJobHandle(
            provider="openai",
            provider_job_id="batch_123",
            api_keys={"openai": "sk-test"},
        )

    def test_cancel_uses_configured_api_keys(
        self,
        workflow: tuple[ProviderBatchWorkflowService, FakeProviderBatchAdapter],
        db_session_factory: sessionmaker,
    ) -> None:
        service, adapter = workflow
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")
        job_id = service.submit_images(
            provider="openai",
            endpoint="responses",
            litellm_model_id="openai/gpt-test",
            prompt_profile="default",
            image_ids=[1],
        )

        canceled = service.cancel(job_id)

        assert canceled.status == "canceled"
        assert adapter.cancel_handle == BatchJobHandle(
            provider="openai",
            provider_job_id="batch_123",
            api_keys={"openai": "sk-test"},
        )

    def test_apply_result_items_updates_normalized_item_state(
        self,
        workflow: tuple[ProviderBatchWorkflowService, FakeProviderBatchAdapter],
        test_repository: ImageRepository,
        db_session_factory: sessionmaker,
    ) -> None:
        service, _adapter = workflow
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")
        _insert_image(db_session_factory, 2, "/tmp/images/two.webp")
        job_id = service.submit_images(
            provider="openai",
            endpoint="responses",
            litellm_model_id="openai/gpt-test",
            prompt_profile="default",
            image_ids=[1, 2],
        )

        result = service.apply_result_items(
            job_id,
            "batch_123",
            [
                ProviderBatchResultItem("img-1", "succeeded", raw_response={"ok": True}),
                {"custom_id": "img-2", "status": "failed", "error_type": "PARSE", "error_message": "bad"},
                SimpleNamespace(custom_id="img-404", status="failed", error_message="missing"),
            ],
        )

        assert result.updated_count == 2
        assert result.missing_count == 1
        assert result.missing_custom_ids == ("img-404",)
        items = {item.custom_id: item for item in test_repository.list_provider_batch_items(job_id)}
        assert items["img-1"].status == "succeeded"
        assert items["img-1"].raw_response == '{"ok": true}'
        assert items["img-2"].status == "failed"
        assert items["img-2"].error_type == "PARSE"
        assert items["img-2"].error_message == "bad"

    def test_apply_result_items_rejects_provider_job_id_mismatch(
        self,
        workflow: tuple[ProviderBatchWorkflowService, FakeProviderBatchAdapter],
        db_session_factory: sessionmaker,
    ) -> None:
        service, _adapter = workflow
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")
        job_id = service.submit_images(
            provider="openai",
            endpoint="responses",
            litellm_model_id="openai/gpt-test",
            prompt_profile="default",
            image_ids=[1],
        )

        with pytest.raises(ProviderBatchError, match="job ID mismatch"):
            service.apply_result_items(
                job_id,
                "batch_other",
                [ProviderBatchResultItem("img-1", "succeeded")],
            )
