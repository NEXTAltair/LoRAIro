"""ServiceContainer provider batch workflow wiring tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from lorairo.services.provider_batch_service import BatchSubmitRequest, ProviderBatchSubmission
from lorairo.services.provider_batch_workflow_service import ProviderBatchWorkflowService
from lorairo.services.service_container import ServiceContainer


class FakeBatchAnnotatorLibrary:
    def __init__(self) -> None:
        self.submitted_request: BatchSubmitRequest | None = None

    def submit_batch(self, request: BatchSubmitRequest) -> ProviderBatchSubmission:
        self.submitted_request = request
        return ProviderBatchSubmission(provider_job_id="batch_container", provider_status="validating")


@pytest.mark.unit
class TestServiceContainerProviderBatch:
    def test_provider_batch_workflow_service_is_lazy_singleton(self) -> None:
        container = ServiceContainer()
        container._annotator_library = object()

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
        container._annotator_library = object()
        service = container.provider_batch_workflow_service

        container.reset_container()
        container2 = ServiceContainer()
        container2._annotator_library = object()

        assert container2._provider_batch_workflow_service is None
        assert container2.provider_batch_workflow_service is not service

    def test_provider_batch_workflow_service_registers_annotator_library_adapters(self) -> None:
        container = ServiceContainer()
        fake_library = FakeBatchAnnotatorLibrary()
        repository = Mock()
        repository.get_images_metadata_batch.return_value = [
            {"id": 1, "stored_image_path": "/tmp/container-image.webp"}
        ]
        repository.create_provider_batch_job_with_items.return_value = 123
        config = Mock()
        config.get_api_keys.return_value = {"openai": "sk-test"}
        container._annotator_library = fake_library
        container._image_repository = repository
        container._config_service = config

        job_id = container.provider_batch_workflow_service.submit_images(
            provider="openai",
            endpoint="responses",
            litellm_model_id="openai/gpt-test",
            prompt_profile="default",
            image_ids=[1],
        )

        assert job_id == 123
        assert fake_library.submitted_request is not None
        assert fake_library.submitted_request.provider == "openai"
        assert fake_library.submitted_request.items[0].image_path == Path("/tmp/container-image.webp")
