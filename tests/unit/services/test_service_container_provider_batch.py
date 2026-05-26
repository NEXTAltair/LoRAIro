"""ServiceContainer provider batch workflow wiring tests."""

from __future__ import annotations

import pytest

from lorairo.services.provider_batch_workflow_service import ProviderBatchWorkflowService
from lorairo.services.service_container import ServiceContainer


@pytest.mark.unit
class TestServiceContainerProviderBatch:
    def test_provider_batch_workflow_service_is_lazy_singleton(self) -> None:
        container = ServiceContainer()

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
        service = container.provider_batch_workflow_service

        container.reset_container()
        container2 = ServiceContainer()

        assert container2._provider_batch_workflow_service is None
        assert container2.provider_batch_workflow_service is not service
