"""AnnotatorLibraryAdapter provider batch API forwarding tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import image_annotator_lib
import pytest

from lorairo.annotations.annotator_adapter import AnnotatorLibraryAdapter
from lorairo.services.provider_batch_service import (
    BatchJobHandle,
    BatchSubmitRequest,
    ProviderBatchArtifactRef,
    ProviderBatchArtifacts,
    ProviderBatchError,
    ProviderBatchStatus,
    ProviderBatchSubmission,
)


@pytest.fixture
def adapter() -> AnnotatorLibraryAdapter:
    return AnnotatorLibraryAdapter(Mock())


@pytest.mark.unit
class TestAnnotatorAdapterProviderBatch:
    def test_provider_batch_methods_forward_to_image_annotator_lib(
        self,
        adapter: AnnotatorLibraryAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        calls: list[tuple[str, object]] = []

        def submit_batch(request: BatchSubmitRequest) -> ProviderBatchSubmission:
            calls.append(("submit", request))
            return ProviderBatchSubmission(provider_job_id="batch_123", provider_status="validating")

        def retrieve_batch(handle: BatchJobHandle) -> ProviderBatchStatus:
            calls.append(("retrieve", handle))
            return ProviderBatchStatus(provider_job_id="batch_123", provider_status="completed")

        def cancel_batch(handle: BatchJobHandle) -> ProviderBatchStatus:
            calls.append(("cancel", handle))
            return ProviderBatchStatus(provider_job_id="batch_123", provider_status="cancelled")

        def fetch_batch_results(handle: BatchJobHandle, destination_dir: Path) -> ProviderBatchArtifacts:
            calls.append(("fetch", destination_dir))
            return ProviderBatchArtifacts(
                provider_job_id="batch_123",
                artifacts=(ProviderBatchArtifactRef("output", destination_dir / "output.jsonl"),),
            )

        monkeypatch.setattr(image_annotator_lib, "submit_batch", submit_batch, raising=False)
        monkeypatch.setattr(image_annotator_lib, "retrieve_batch", retrieve_batch, raising=False)
        monkeypatch.setattr(image_annotator_lib, "cancel_batch", cancel_batch, raising=False)
        monkeypatch.setattr(image_annotator_lib, "fetch_batch_results", fetch_batch_results, raising=False)

        request = BatchSubmitRequest(
            provider="openai",
            endpoint="responses",
            litellm_model_id="openai/gpt-test",
            prompt_profile="default",
            api_keys={},
            items=(),
        )
        handle = BatchJobHandle(provider="openai", provider_job_id="batch_123", api_keys={})

        assert adapter.submit_batch(request).provider_status == "validating"
        assert adapter.retrieve_batch(handle).provider_status == "completed"
        assert adapter.cancel_batch(handle).provider_status == "cancelled"
        assert adapter.fetch_batch_results(handle, tmp_path).artifacts[0].local_path == (
            tmp_path / "output.jsonl"
        )
        assert [name for name, _value in calls] == ["submit", "retrieve", "cancel", "fetch"]

    def test_provider_batch_methods_raise_when_library_api_is_unavailable(
        self,
        adapter: AnnotatorLibraryAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delattr(image_annotator_lib, "submit_batch", raising=False)

        request = BatchSubmitRequest(
            provider="openai",
            endpoint="responses",
            litellm_model_id="openai/gpt-test",
            prompt_profile="default",
            api_keys={},
            items=(),
        )

        with pytest.raises(ProviderBatchError, match="submit_batch"):
            adapter.submit_batch(request)
