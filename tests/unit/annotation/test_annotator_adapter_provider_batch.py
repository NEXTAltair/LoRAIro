"""AnnotatorLibraryAdapter provider batch API forwarding tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import image_annotator_lib
import pytest

from lorairo.annotation.annotator_adapter import AnnotatorLibraryAdapter
from lorairo.services.provider_batch_service import (
    BatchJobHandle,
    BatchSubmitRequest,
    ProviderBatchError,
    ProviderBatchFetchResult,
    ProviderBatchResultItem,
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

        def submit_batch(request: object) -> ProviderBatchSubmission:
            calls.append(("submit", request))
            return ProviderBatchSubmission(provider_job_id="batch_123", provider_status="validating")

        def retrieve_batch(handle: object) -> ProviderBatchStatus:
            calls.append(("retrieve", handle))
            return ProviderBatchStatus(provider_job_id="batch_123", provider_status="completed")

        def cancel_batch(handle: object) -> ProviderBatchStatus:
            calls.append(("cancel", handle))
            return ProviderBatchStatus(provider_job_id="batch_123", provider_status="cancelled")

        def fetch_batch_results(handle: object) -> ProviderBatchFetchResult:
            calls.append(("fetch", handle))
            return ProviderBatchFetchResult(
                provider_job_id="batch_123",
                provider_status="completed",
                items=(ProviderBatchResultItem("img-1", "succeeded", annotation={"tags": ["tag"]}),),
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
        assert adapter.fetch_batch_results(handle, tmp_path).items[0].annotation == {"tags": ["tag"]}
        assert [name for name, _value in calls] == ["submit", "retrieve", "cancel", "fetch"]
        assert calls[0][1].provider == "openai"
        assert calls[3][1].provider_job_id == "batch_123"

    def test_list_batch_capable_models_forwards_to_image_annotator_lib(
        self,
        adapter: AnnotatorLibraryAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            image_annotator_lib,
            "list_batch_capable_models",
            lambda: ["anthropic/claude-test"],
            raising=False,
        )

        assert adapter.list_batch_capable_models() == ("anthropic/claude-test",)

    def test_fetch_batch_results_forwards_destination_dir_when_library_accepts_it(
        self,
        adapter: AnnotatorLibraryAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        calls: list[tuple[object, Path]] = []

        def fetch_batch_results(handle: object, destination_dir: Path) -> ProviderBatchFetchResult:
            calls.append((handle, destination_dir))
            return ProviderBatchFetchResult(
                provider_job_id="batch_123",
                provider_status="completed",
            )

        monkeypatch.setattr(image_annotator_lib, "fetch_batch_results", fetch_batch_results, raising=False)

        handle = BatchJobHandle(provider="openai", provider_job_id="batch_123", api_keys={})

        adapter.fetch_batch_results(handle, tmp_path)

        assert calls[0][1] == tmp_path

    @pytest.mark.parametrize("signature_error", [TypeError, ValueError])
    def test_fetch_batch_results_falls_back_when_signature_is_unavailable(
        self,
        adapter: AnnotatorLibraryAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        signature_error: type[Exception],
    ) -> None:
        calls: list[object] = []

        def fetch_batch_results(handle: object) -> ProviderBatchFetchResult:
            calls.append(handle)
            return ProviderBatchFetchResult(
                provider_job_id="batch_123",
                provider_status="completed",
            )

        monkeypatch.setattr(image_annotator_lib, "fetch_batch_results", fetch_batch_results, raising=False)
        monkeypatch.setattr("inspect.signature", lambda _method: (_ for _ in ()).throw(signature_error))

        handle = BatchJobHandle(provider="openai", provider_job_id="batch_123", api_keys={})

        adapter.fetch_batch_results(handle, tmp_path)

        assert len(calls) == 1

    def test_fetch_batch_results_tries_destination_dir_when_signature_is_unavailable(
        self,
        adapter: AnnotatorLibraryAdapter,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        calls: list[tuple[object, Path]] = []

        def fetch_batch_results(handle: object, destination_dir: Path) -> ProviderBatchFetchResult:
            calls.append((handle, destination_dir))
            return ProviderBatchFetchResult(
                provider_job_id="batch_123",
                provider_status="completed",
            )

        monkeypatch.setattr(image_annotator_lib, "fetch_batch_results", fetch_batch_results, raising=False)
        monkeypatch.setattr("inspect.signature", lambda _method: (_ for _ in ()).throw(ValueError))

        handle = BatchJobHandle(provider="openai", provider_job_id="batch_123", api_keys={})

        adapter.fetch_batch_results(handle, tmp_path)

        assert len(calls) == 1
        assert calls[0][1] == tmp_path

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
