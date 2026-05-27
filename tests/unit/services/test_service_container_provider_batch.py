"""ServiceContainer provider batch workflow wiring tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock

import pytest

from lorairo.services.provider_batch_service import (
    BatchJobHandle,
    BatchSubmitRequest,
    ProviderBatchFetchResult,
    ProviderBatchResultItem,
    ProviderBatchSubmission,
)
from lorairo.services.provider_batch_workflow_service import ProviderBatchWorkflowService
from lorairo.services.service_container import ServiceContainer


class FakeBatchAnnotatorLibrary:
    def __init__(self) -> None:
        self.submitted_request: BatchSubmitRequest | None = None
        self.fetch_call: tuple[BatchJobHandle, Path] | None = None

    def submit_batch(self, request: BatchSubmitRequest) -> ProviderBatchSubmission:
        self.submitted_request = request
        return ProviderBatchSubmission(provider_job_id="batch_container", provider_status="validating")

    def fetch_batch_results(
        self,
        handle: BatchJobHandle,
        destination_dir: Path,
    ) -> ProviderBatchFetchResult:
        self.fetch_call = (handle, destination_dir)
        return ProviderBatchFetchResult(
            provider_job_id=handle.provider_job_id,
            provider_status="completed",
            items=(
                ProviderBatchResultItem(custom_id="img-1", status="succeeded", annotation={"tag": "ok"}),
            ),
        )


@pytest.mark.unit
class TestServiceContainerProviderBatch:
    def test_provider_batch_workflow_service_is_lazy_singleton(self) -> None:
        container = ServiceContainer()
        container._annotator_library = cast(Any, object())

        assert container._provider_batch_workflow_service is None

        service = container.provider_batch_workflow_service

        assert isinstance(service, ProviderBatchWorkflowService)
        assert service is container.provider_batch_workflow_service
        assert (
            container.get_service_summary()["initialized_services"]["provider_batch_workflow_service"]
            is True
        )

    def test_reset_container_clears_provider_batch_workflow_service(self) -> None:
        container = ServiceContainer()
        container._annotator_library = cast(Any, object())
        service = container.provider_batch_workflow_service

        container.reset_container()
        container2 = ServiceContainer()
        container2._annotator_library = cast(Any, object())

        assert container2._provider_batch_workflow_service is None
        assert container2.provider_batch_workflow_service is not service

    def test_provider_batch_workflow_service_registers_annotator_library_adapters(self) -> None:
        container = ServiceContainer()
        fake_library = FakeBatchAnnotatorLibrary()
        # ADR 0035 段階 6 (#423): facade 撤廃後、workflow service は manager 経由で
        # image_repo / provider_batch_repo / annotation_repo を取得する。Manager を
        # Mock 化し、各 Repo を個別に stub する。
        image_repo = Mock()
        image_repo.get_images_metadata_batch.return_value = [
            {"id": 1, "stored_image_path": "/tmp/container-image.webp"}
        ]
        provider_batch_repo = Mock()
        provider_batch_repo.create_provider_batch_job_with_items.return_value = 123
        annotation_repo = Mock()
        manager = Mock()
        manager.image_repo = image_repo
        manager.provider_batch_repo = provider_batch_repo
        manager.annotation_repo = annotation_repo
        config = Mock()
        config.get_api_keys.return_value = {"openai": "sk-test"}
        container._annotator_library = cast(Any, fake_library)
        container._db_manager = manager
        container._config_service = config

        job_id = container.provider_batch_workflow_service.submit_images(
            provider="openai",
            endpoint="/v1/moderations",
            litellm_model_id="openai/omni-moderation-latest",
            prompt_profile="default",
            image_ids=[1],
            model_id=10,
            task_type="rating_preflight",
        )

        assert job_id == 123
        assert fake_library.submitted_request is not None
        assert fake_library.submitted_request.provider == "openai"
        assert fake_library.submitted_request.endpoint == "/v1/moderations"
        assert fake_library.submitted_request.items[0].task_type == "rating_preflight"
        assert fake_library.submitted_request.items[0].image_path == Path("/tmp/container-image.webp")

    def test_provider_batch_adapter_fetch_passes_destination_dir(self, tmp_path: Path) -> None:
        container = ServiceContainer()
        fake_library = FakeBatchAnnotatorLibrary()
        container._annotator_library = cast(Any, fake_library)

        service = container.provider_batch_workflow_service
        adapter = cast(Any, service)._job_service._adapters["openai"]
        result = adapter.fetch_batch_results(
            BatchJobHandle(provider="openai", provider_job_id="batch_container", api_keys={}),
            tmp_path,
        )

        assert result.items[0].annotation == {"tag": "ok"}
        assert fake_library.fetch_call is not None
        handle, destination_dir = fake_library.fetch_call
        assert handle.provider_job_id == "batch_container"
        assert destination_dir == tmp_path
