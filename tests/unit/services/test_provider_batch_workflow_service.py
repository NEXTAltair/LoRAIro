"""ProviderBatchWorkflowService tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import sessionmaker

from lorairo.database.repository.provider_batch import ProviderBatchRepository
from lorairo.database.schema import Image
from lorairo.services.annotation_save_service import AnnotationSaveResult
from lorairo.services.provider_batch_service import (
    BatchJobHandle,
    BatchSubmitRequest,
    ProviderBatchArtifactRef,
    ProviderBatchArtifacts,
    ProviderBatchError,
    ProviderBatchFetchResult,
    ProviderBatchResultItem,
    ProviderBatchStatus,
    ProviderBatchSubmission,
)
from lorairo.services.provider_batch_workflow_service import (
    ProviderBatchLibraryAdapter,
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
            provider_status="canceled",
        )
        self.artifacts = ProviderBatchArtifacts(
            provider_job_id="batch_123",
            artifacts=(
                ProviderBatchArtifactRef("output", Path("/tmp/output.jsonl")),
                ProviderBatchArtifactRef("error", Path("/tmp/error.jsonl")),
            ),
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


@pytest.fixture
def batch_config(tmp_path: Path) -> Mock:
    config = Mock()
    config.get_api_keys.return_value = {"openai_key": "sk-test"}
    config.get_batch_results_directory.return_value = tmp_path / "batch_results"
    return config


@pytest.fixture
def workflow(
    test_provider_batch_repository: ProviderBatchRepository,
    test_repository,
    test_annotation_repository,
    batch_config: Mock,
) -> tuple[ProviderBatchWorkflowService, FakeProviderBatchAdapter]:
    """ADR 0035 段階 6 (#423): 3 つの Aggregate Repo を inject する新シグネチャ。"""
    adapter = FakeProviderBatchAdapter()
    service = ProviderBatchWorkflowService(
        provider_batch_repo=test_provider_batch_repository,
        image_repo=test_repository,
        annotation_repo=test_annotation_repository,
        config_service=batch_config,
        adapters={"anthropic": adapter, "openai": adapter},
    )
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
        test_provider_batch_repository: ProviderBatchRepository,
        db_session_factory: sessionmaker,
    ) -> None:
        service, adapter = workflow
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")
        _insert_image(db_session_factory, 2, "/tmp/images/two.webp")

        job_id = service.submit_images(
            provider="anthropic",
            endpoint="/v1/messages",
            litellm_model_id="anthropic/claude-test",
            prompt_profile="default",
            image_ids=[1, 2],
        )

        assert adapter.submitted_request is not None
        assert adapter.submitted_request.api_keys == {"openai": "sk-test"}
        assert [
            (item.custom_id, item.image_id, item.image_path, item.task_type)
            for item in adapter.submitted_request.items
        ] == [
            ("img-1", 1, Path("/tmp/images/one.webp"), "annotation"),
            ("img-2", 2, Path("/tmp/images/two.webp"), "annotation"),
        ]
        job = test_provider_batch_repository.get_provider_batch_job(job_id)
        assert job is not None
        assert job.provider_job_id == "batch_123"
        assert [
            item.custom_id for item in test_provider_batch_repository.list_provider_batch_items(job_id)
        ] == [
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
            provider="anthropic",
            endpoint="/v1/messages",
            litellm_model_id="anthropic/claude-test",
            prompt_profile="default",
            image_ids=[1],
            image_paths={1: Path("/tmp/resized/one.webp")},
        )

        assert adapter.submitted_request is not None
        assert adapter.submitted_request.items[0].image_path == Path("/tmp/resized/one.webp")

    def test_submit_images_resolves_relative_stored_image_paths(
        self,
        workflow: tuple[ProviderBatchWorkflowService, FakeProviderBatchAdapter],
        db_session_factory: sessionmaker,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        service, adapter = workflow
        project_root = tmp_path / "main_dataset"
        stored_path = Path("image_dataset/original_images/2026/05/28/one.webp")
        resolved_path = project_root / stored_path
        resolved_path.parent.mkdir(parents=True)
        resolved_path.touch()
        _insert_image(db_session_factory, 1, str(stored_path))
        monkeypatch.setattr(
            "lorairo.database.db_core.get_current_project_root",
            lambda: project_root,
        )

        service.submit_images(
            provider="anthropic",
            endpoint="/v1/messages",
            litellm_model_id="anthropic/claude-test",
            prompt_profile="default",
            image_ids=[1],
        )

        assert adapter.submitted_request is not None
        item_path = adapter.submitted_request.items[0].image_path
        assert item_path == resolved_path
        assert item_path.is_absolute()
        assert item_path.exists()

    def test_submit_images_preserves_rating_preflight_task_type(
        self,
        workflow: tuple[ProviderBatchWorkflowService, FakeProviderBatchAdapter],
        test_provider_batch_repository: ProviderBatchRepository,
        db_session_factory: sessionmaker,
    ) -> None:
        service, adapter = workflow
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")

        job_id = service.submit_images(
            provider="openai",
            endpoint="/v1/moderations",
            litellm_model_id="openai/omni-moderation-latest",
            prompt_profile="moderation",
            image_ids=[1],
            model_id=10,
            task_type="rating_preflight",
        )

        assert adapter.submitted_request is not None
        assert adapter.submitted_request.items[0].task_type == "rating_preflight"
        assert adapter.submitted_request.items[0].model_id == 10
        item = test_provider_batch_repository.list_provider_batch_items(job_id)[0]
        assert item.task_type == "rating_preflight"
        assert item.model_id == 10

    def test_submit_images_accepts_legacy_bare_openai_moderation_model(
        self,
        workflow: tuple[ProviderBatchWorkflowService, FakeProviderBatchAdapter],
        db_session_factory: sessionmaker,
    ) -> None:
        service, adapter = workflow
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")

        service.submit_images(
            provider="openai",
            endpoint="/v1/moderations",
            litellm_model_id="omni-moderation-latest",
            prompt_profile="moderation",
            image_ids=[1],
            model_id=10,
            task_type="rating_preflight",
        )

        assert adapter.submitted_request is not None
        assert adapter.submitted_request.litellm_model_id == "omni-moderation-latest"

    def test_submit_images_canonicalizes_rating_preflight_endpoint(
        self,
        workflow: tuple[ProviderBatchWorkflowService, FakeProviderBatchAdapter],
        db_session_factory: sessionmaker,
    ) -> None:
        service, adapter = workflow
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")

        service.submit_images(
            provider="openai",
            endpoint="v1/moderations/",
            litellm_model_id="openai/omni-moderation-latest",
            prompt_profile="moderation",
            image_ids=[1],
            model_id=10,
            task_type="rating_preflight",
        )

        assert adapter.submitted_request is not None
        assert adapter.submitted_request.endpoint == "/v1/moderations"

    def test_submit_images_accepts_openai_annotation_submit(
        self,
        workflow: tuple[ProviderBatchWorkflowService, FakeProviderBatchAdapter],
        db_session_factory: sessionmaker,
    ) -> None:
        """OpenAI annotation Batch (#518) は `/v1/chat/completions` で submit できる。"""
        service, adapter = workflow
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")

        job_id = service.submit_images(
            provider="openai",
            endpoint="/v1/chat/completions",
            litellm_model_id="openai/gpt-4.1-mini",
            prompt_profile="default",
            image_ids=[1],
            task_type="annotation",
        )

        assert job_id is not None
        assert adapter.submitted_request is not None
        assert adapter.submitted_request.endpoint == "/v1/chat/completions"
        assert all(item.task_type == "annotation" for item in adapter.submitted_request.items)

    def test_submit_images_requires_model_id_for_rating_preflight(
        self,
        workflow: tuple[ProviderBatchWorkflowService, FakeProviderBatchAdapter],
        db_session_factory: sessionmaker,
    ) -> None:
        service, _adapter = workflow
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")

        with pytest.raises(ProviderBatchError, match="model_id"):
            service.submit_images(
                provider="openai",
                endpoint="/v1/moderations",
                litellm_model_id="openai/omni-moderation-latest",
                prompt_profile="moderation",
                image_ids=[1],
                task_type="rating_preflight",
            )

    def test_submit_images_rejects_non_openai_rating_preflight(
        self,
        workflow: tuple[ProviderBatchWorkflowService, FakeProviderBatchAdapter],
        db_session_factory: sessionmaker,
    ) -> None:
        service, _adapter = workflow
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")

        with pytest.raises(ProviderBatchError, match="task_type=rating_preflight"):
            service.submit_images(
                provider="anthropic",
                endpoint="/v1/messages",
                litellm_model_id="anthropic/claude-test",
                prompt_profile="default",
                image_ids=[1],
                model_id=10,
                task_type="rating_preflight",
            )

    def test_submit_images_rejects_non_moderations_rating_preflight_endpoint(
        self,
        workflow: tuple[ProviderBatchWorkflowService, FakeProviderBatchAdapter],
        db_session_factory: sessionmaker,
    ) -> None:
        service, _adapter = workflow
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")

        with pytest.raises(ProviderBatchError, match="/v1/moderations"):
            service.submit_images(
                provider="openai",
                endpoint="/v1/chat/completions",
                litellm_model_id="openai/omni-moderation-latest",
                prompt_profile="default",
                image_ids=[1],
                model_id=10,
                task_type="rating_preflight",
            )

    def test_submit_images_rejects_non_moderation_rating_preflight_model(
        self,
        workflow: tuple[ProviderBatchWorkflowService, FakeProviderBatchAdapter],
        db_session_factory: sessionmaker,
    ) -> None:
        service, _adapter = workflow
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")

        with pytest.raises(ProviderBatchError, match="openai moderation model"):
            service.submit_images(
                provider="openai",
                endpoint="/v1/moderations",
                litellm_model_id="openai/gpt-4o",
                prompt_profile="default",
                image_ids=[1],
                model_id=10,
                task_type="rating_preflight",
            )

    def test_submit_images_rejects_missing_image_id(
        self,
        workflow: tuple[ProviderBatchWorkflowService, FakeProviderBatchAdapter],
    ) -> None:
        service, _adapter = workflow

        with pytest.raises(ProviderBatchError, match="対象画像が見つかりません"):
            service.submit_images(
                provider="anthropic",
                endpoint="/v1/messages",
                litellm_model_id="anthropic/claude-test",
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
            provider="anthropic",
            endpoint="/v1/messages",
            litellm_model_id="anthropic/claude-test",
            prompt_profile="default",
            image_ids=[1],
        )

        service.download_results(job_id)

        assert adapter.fetch_destination == batch_config.get_batch_results_directory.return_value
        assert adapter.fetch_handle == BatchJobHandle(
            provider="anthropic",
            provider_job_id="batch_123",
            api_keys={"openai": "sk-test"},
        )

    def test_fetch_results_applies_normalized_item_state(
        self,
        workflow: tuple[ProviderBatchWorkflowService, FakeProviderBatchAdapter],
        test_provider_batch_repository: ProviderBatchRepository,
        db_session_factory: sessionmaker,
        batch_config: Mock,
    ) -> None:
        service, adapter = workflow
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")
        job_id = service.submit_images(
            provider="anthropic",
            endpoint="/v1/messages",
            litellm_model_id="anthropic/claude-test",
            prompt_profile="default",
            image_ids=[1],
        )
        adapter.fetch_result = ProviderBatchFetchResult(
            provider_job_id="batch_123",
            provider_status="completed",
            items=(ProviderBatchResultItem("img-1", "succeeded", annotation={"tags": ["tag"]}),),
        )

        fetch_result = service.fetch_results(job_id)

        assert fetch_result.items[0].annotation == {"tags": ["tag"]}
        assert adapter.fetch_destination == batch_config.get_batch_results_directory.return_value
        item = test_provider_batch_repository.list_provider_batch_items(job_id)[0]
        assert item.status == "succeeded"

    def test_refresh_uses_configured_api_keys(
        self,
        workflow: tuple[ProviderBatchWorkflowService, FakeProviderBatchAdapter],
        db_session_factory: sessionmaker,
    ) -> None:
        service, adapter = workflow
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")
        job_id = service.submit_images(
            provider="anthropic",
            endpoint="/v1/messages",
            litellm_model_id="anthropic/claude-test",
            prompt_profile="default",
            image_ids=[1],
        )

        refreshed = service.refresh(job_id)

        assert refreshed.status == "completed"
        assert adapter.retrieve_handle == BatchJobHandle(
            provider="anthropic",
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
            provider="anthropic",
            endpoint="/v1/messages",
            litellm_model_id="anthropic/claude-test",
            prompt_profile="default",
            image_ids=[1],
        )

        canceled = service.cancel(job_id)

        assert canceled.status == "canceled"
        assert adapter.cancel_handle == BatchJobHandle(
            provider="anthropic",
            provider_job_id="batch_123",
            api_keys={"openai": "sk-test"},
        )

    def test_apply_result_items_updates_normalized_item_state(
        self,
        workflow: tuple[ProviderBatchWorkflowService, FakeProviderBatchAdapter],
        test_provider_batch_repository: ProviderBatchRepository,
        db_session_factory: sessionmaker,
    ) -> None:
        service, _adapter = workflow
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")
        _insert_image(db_session_factory, 2, "/tmp/images/two.webp")
        job_id = service.submit_images(
            provider="anthropic",
            endpoint="/v1/messages",
            litellm_model_id="anthropic/claude-test",
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
        items = {
            item.custom_id: item
            for item in test_provider_batch_repository.list_provider_batch_items(job_id)
        }
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
            provider="anthropic",
            endpoint="/v1/messages",
            litellm_model_id="anthropic/claude-test",
            prompt_profile="default",
            image_ids=[1],
        )

        with pytest.raises(ProviderBatchError, match="job ID mismatch"):
            service.apply_result_items(
                job_id,
                "batch_other",
                [ProviderBatchResultItem("img-1", "succeeded")],
            )

    def test_import_results_uses_custom_id_mapping_and_marks_imported(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
        test_repository,
        test_annotation_repository,
        batch_config: Mock,
        db_session_factory: sessionmaker,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        annotation_save = Mock()
        annotation_save.save_provider_batch_results_by_image_id.return_value = AnnotationSaveResult(
            success_count=1,
            skip_count=0,
            error_count=0,
            total_count=1,
        )
        service = ProviderBatchWorkflowService(
            provider_batch_repo=test_provider_batch_repository,
            image_repo=test_repository,
            annotation_repo=test_annotation_repository,
            config_service=batch_config,
            adapters={"anthropic": adapter, "openai": adapter},
            annotation_save_service=annotation_save,
        )
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")
        job_id = service.submit_images(
            provider="anthropic",
            endpoint="/v1/messages",
            litellm_model_id="anthropic/claude-test",
            prompt_profile="default",
            image_ids=[1],
            model_id=10,
        )
        fetch_result = ProviderBatchFetchResult(
            provider_job_id="batch_123",
            provider_status="completed",
            items=(ProviderBatchResultItem("img-1", "succeeded", annotation={"tags": ["tag"]}),),
        )

        result = service.import_results(job_id, fetch_result)

        annotation_save.save_provider_batch_results_by_image_id.assert_called_once_with(
            {1: {"tags": ["tag"]}},
            model_id=10,
            model_name="__provider_batch_model_10__",
        )
        assert result.imported_count == 1
        assert result.job_imported is True
        job = test_provider_batch_repository.get_provider_batch_job(job_id)
        assert job is not None
        assert job.status == "imported"
        assert job.imported_at is not None
        assert test_provider_batch_repository.list_provider_batch_items(job_id)[0].status == "imported"

    def test_import_results_routes_rating_preflight_to_annotation_save_service(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
        test_repository,
        test_annotation_repository,
        batch_config: Mock,
        db_session_factory: sessionmaker,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        annotation_save = Mock()
        annotation_save.save_provider_batch_results_by_image_id.return_value = AnnotationSaveResult(
            success_count=1,
            skip_count=0,
            error_count=0,
            total_count=1,
        )
        service = ProviderBatchWorkflowService(
            provider_batch_repo=test_provider_batch_repository,
            image_repo=test_repository,
            annotation_repo=test_annotation_repository,
            config_service=batch_config,
            adapters={"anthropic": adapter, "openai": adapter},
            annotation_save_service=annotation_save,
        )
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")
        job_id = service.submit_images(
            provider="openai",
            endpoint="/v1/moderations",
            litellm_model_id="openai/omni-moderation-latest",
            prompt_profile="default",
            image_ids=[1],
            model_id=10,
            task_type="rating_preflight",
        )

        result = service.import_results(
            job_id,
            ProviderBatchFetchResult(
                provider_job_id="batch_123",
                provider_status="completed",
                items=(
                    ProviderBatchResultItem(
                        "img-1",
                        "succeeded",
                        annotation={
                            "ratings": [{"raw_label": "pg13", "source_scheme": "openai_moderation_v1"}]
                        },
                    ),
                ),
            ),
        )

        annotation_save.save_provider_batch_results_by_image_id.assert_called_once_with(
            {1: {"ratings": [{"raw_label": "pg13", "source_scheme": "openai_moderation_v1"}]}},
            model_id=10,
            model_name="__provider_batch_model_10__",
        )
        assert result.imported_count == 1
        item = test_provider_batch_repository.list_provider_batch_items(job_id)[0]
        assert item.task_type == "rating_preflight"
        assert item.model_id == 10
        assert item.status == "imported"

    def test_import_results_does_not_fallback_to_file_stem_for_missing_custom_id(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
        test_repository,
        test_annotation_repository,
        batch_config: Mock,
        db_session_factory: sessionmaker,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        annotation_save = Mock()
        annotation_save.save_provider_batch_results_by_image_id.return_value = AnnotationSaveResult(
            success_count=0,
            skip_count=0,
            error_count=0,
            total_count=0,
        )
        service = ProviderBatchWorkflowService(
            provider_batch_repo=test_provider_batch_repository,
            image_repo=test_repository,
            annotation_repo=test_annotation_repository,
            config_service=batch_config,
            adapters={"anthropic": adapter, "openai": adapter},
            annotation_save_service=annotation_save,
        )
        _insert_image(db_session_factory, 1, "/tmp/images/img-404.webp")
        job_id = service.submit_images(
            provider="anthropic",
            endpoint="/v1/messages",
            litellm_model_id="anthropic/claude-test",
            prompt_profile="default",
            image_ids=[1],
            model_id=10,
        )

        result = service.import_results(
            job_id,
            ProviderBatchFetchResult(
                provider_job_id="batch_123",
                provider_status="completed",
                items=(ProviderBatchResultItem("img-404", "succeeded", annotation={"tags": ["tag"]}),),
            ),
        )

        annotation_save.save_provider_batch_results_by_image_id.assert_not_called()
        assert result.missing_custom_ids == ("img-404",)
        assert result.job_imported is False
        job = test_provider_batch_repository.get_provider_batch_job(job_id)
        assert job is not None
        assert job.status == "completed"
        assert job.imported_at is None


@pytest.mark.unit
class TestProviderBatchLibraryAdapter:
    def test_fetch_batch_results_uses_handle_only_library_signature(self, tmp_path: Path) -> None:
        class Client:
            def __init__(self) -> None:
                self.handles: list[object] = []

            def fetch_batch_results(self, handle: object) -> ProviderBatchFetchResult:
                self.handles.append(handle)
                return ProviderBatchFetchResult(
                    provider_job_id="batch_123",
                    provider_status="completed",
                    items=(ProviderBatchResultItem("img-1", "succeeded", annotation={"ratings": []}),),
                )

        client = Client()
        adapter = ProviderBatchLibraryAdapter("openai", client)

        result = adapter.fetch_batch_results(
            BatchJobHandle(provider="openai", provider_job_id="batch_123", api_keys={}),
            tmp_path,
        )

        assert result.items[0].custom_id == "img-1"
        assert len(client.handles) == 1

    def test_fetch_batch_results_passes_destination_when_library_accepts_it(self, tmp_path: Path) -> None:
        class Client:
            def __init__(self) -> None:
                self.destination: Path | None = None

            def fetch_batch_results(
                self, handle: object, destination_dir: Path
            ) -> ProviderBatchFetchResult:
                self.destination = destination_dir
                return ProviderBatchFetchResult(provider_job_id="batch_123", provider_status="completed")

        client = Client()
        adapter = ProviderBatchLibraryAdapter("openai", client)

        adapter.fetch_batch_results(
            BatchJobHandle(provider="openai", provider_job_id="batch_123", api_keys={}),
            tmp_path,
        )

        assert client.destination == tmp_path

    def test_import_results_marks_saved_items_imported_when_job_has_missing_ids(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
        test_repository,
        test_annotation_repository,
        batch_config: Mock,
        db_session_factory: sessionmaker,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        annotation_save = Mock()
        annotation_save.save_provider_batch_results_by_image_id.return_value = AnnotationSaveResult(
            success_count=1,
            skip_count=0,
            error_count=0,
            total_count=1,
        )
        service = ProviderBatchWorkflowService(
            provider_batch_repo=test_provider_batch_repository,
            image_repo=test_repository,
            annotation_repo=test_annotation_repository,
            config_service=batch_config,
            adapters={"anthropic": adapter, "openai": adapter},
            annotation_save_service=annotation_save,
        )
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")
        job_id = service.submit_images(
            provider="anthropic",
            endpoint="/v1/messages",
            litellm_model_id="anthropic/claude-test",
            prompt_profile="default",
            image_ids=[1],
            model_id=10,
        )

        result = service.import_results(
            job_id,
            ProviderBatchFetchResult(
                provider_job_id="batch_123",
                provider_status="completed",
                items=(
                    ProviderBatchResultItem("img-1", "succeeded", annotation={"tags": ["tag"]}),
                    ProviderBatchResultItem("img-404", "succeeded", annotation={"tags": ["missing"]}),
                ),
            ),
        )

        assert result.job_imported is False
        assert result.missing_custom_ids == ("img-404",)
        item = test_provider_batch_repository.list_provider_batch_items(job_id)[0]
        assert item.status == "imported"
        job = test_provider_batch_repository.get_provider_batch_job(job_id)
        assert job is not None
        assert job.status == "completed"
        assert job.imported_at is None

    def test_fetch_results_preserves_imported_item_status(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
        test_repository,
        test_annotation_repository,
        batch_config: Mock,
        db_session_factory: sessionmaker,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        service = ProviderBatchWorkflowService(
            provider_batch_repo=test_provider_batch_repository,
            image_repo=test_repository,
            annotation_repo=test_annotation_repository,
            config_service=batch_config,
            adapters={"anthropic": adapter, "openai": adapter},
        )
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")
        job_id = service.submit_images(
            provider="anthropic",
            endpoint="/v1/messages",
            litellm_model_id="anthropic/claude-test",
            prompt_profile="default",
            image_ids=[1],
            model_id=10,
        )
        test_provider_batch_repository.update_provider_batch_job(job_id, {"status": "completed"})
        test_provider_batch_repository.update_provider_batch_items_by_custom_id(
            job_id, {"img-1": {"status": "imported"}}
        )
        adapter.fetch_result = ProviderBatchFetchResult(
            provider_job_id="batch_123",
            provider_status="completed",
            items=(ProviderBatchResultItem("img-1", "succeeded", annotation={"tags": ["tag"]}),),
        )

        service.fetch_results(job_id)

        assert test_provider_batch_repository.list_provider_batch_items(job_id)[0].status == "imported"

    def test_import_results_preserves_imported_item_status_on_retry_error(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
        test_repository,
        test_annotation_repository,
        batch_config: Mock,
        db_session_factory: sessionmaker,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        annotation_save = Mock()
        annotation_save.save_provider_batch_results_by_image_id.return_value = AnnotationSaveResult(
            success_count=0,
            skip_count=0,
            error_count=1,
            total_count=1,
            error_details=["image_id=2: write failed"],
        )
        service = ProviderBatchWorkflowService(
            provider_batch_repo=test_provider_batch_repository,
            image_repo=test_repository,
            annotation_repo=test_annotation_repository,
            config_service=batch_config,
            adapters={"anthropic": adapter, "openai": adapter},
            annotation_save_service=annotation_save,
        )
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")
        _insert_image(db_session_factory, 2, "/tmp/images/two.webp")
        job_id = service.submit_images(
            provider="anthropic",
            endpoint="/v1/messages",
            litellm_model_id="anthropic/claude-test",
            prompt_profile="default",
            image_ids=[1, 2],
            model_id=10,
        )
        test_provider_batch_repository.update_provider_batch_items_by_custom_id(
            job_id, {"img-1": {"status": "imported"}}
        )

        result = service.import_results(
            job_id,
            ProviderBatchFetchResult(
                provider_job_id="batch_123",
                provider_status="completed",
                items=(
                    ProviderBatchResultItem("img-1", "succeeded", annotation={"tags": ["old"]}),
                    ProviderBatchResultItem("img-2", "succeeded", annotation={"tags": ["new"]}),
                ),
            ),
        )

        assert result.error_count == 1
        assert result.skipped_count == 1
        items = {
            item.custom_id: item
            for item in test_provider_batch_repository.list_provider_batch_items(job_id)
        }
        assert items["img-1"].status == "imported"
        assert items["img-2"].status == "succeeded"
        annotation_save.save_provider_batch_results_by_image_id.assert_called_once_with(
            {2: {"tags": ["new"]}},
            model_id=10,
            model_name="__provider_batch_model_10__",
        )

    def test_import_results_preserves_per_item_model_ids(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
        test_repository,
        test_annotation_repository,
        test_model_repository,
        batch_config: Mock,
        db_session_factory: sessionmaker,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        annotation_save = Mock()
        annotation_save.save_provider_batch_results_by_image_id.return_value = AnnotationSaveResult(
            success_count=1,
            skip_count=0,
            error_count=0,
            total_count=1,
        )
        service = ProviderBatchWorkflowService(
            provider_batch_repo=test_provider_batch_repository,
            image_repo=test_repository,
            annotation_repo=test_annotation_repository,
            config_service=batch_config,
            adapters={"anthropic": adapter, "openai": adapter},
            annotation_save_service=annotation_save,
        )
        # ADR 0035 段階 6: insert_model は ModelRepository 経由
        model_id_1 = test_model_repository.insert_model(
            name="claude-test-a",
            provider="anthropic",
            model_types=["multimodal"],
            litellm_model_id="anthropic/claude-test-a",
        )
        model_id_2 = test_model_repository.insert_model(
            name="claude-test-b",
            provider="anthropic",
            model_types=["multimodal"],
            litellm_model_id="anthropic/claude-test-b",
        )
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")
        _insert_image(db_session_factory, 2, "/tmp/images/two.webp")
        job_id = service.submit_images(
            provider="anthropic",
            endpoint="/v1/messages",
            litellm_model_id="anthropic/claude-test-a",
            prompt_profile="default",
            image_ids=[1, 2],
            model_id=model_id_1,
        )
        test_provider_batch_repository.update_provider_batch_items_by_custom_id(
            job_id,
            {"img-2": {"model_id": model_id_2}},
        )

        result = service.import_results(
            job_id,
            ProviderBatchFetchResult(
                provider_job_id="batch_123",
                provider_status="completed",
                items=(
                    ProviderBatchResultItem("img-1", "succeeded", annotation={"tags": ["one"]}),
                    ProviderBatchResultItem("img-2", "succeeded", annotation={"tags": ["two"]}),
                ),
            ),
        )

        assert result.imported_count == 2
        annotation_save.save_provider_batch_results_by_image_id.assert_any_call(
            {1: {"tags": ["one"]}},
            model_id=model_id_1,
            model_name="anthropic/claude-test-a",
        )
        annotation_save.save_provider_batch_results_by_image_id.assert_any_call(
            {2: {"tags": ["two"]}},
            model_id=model_id_2,
            model_name=f"__provider_batch_model_{model_id_2}__",
        )

    def test_import_results_counts_non_importable_items_as_skipped(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
        test_repository,
        test_annotation_repository,
        batch_config: Mock,
        db_session_factory: sessionmaker,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        annotation_save = Mock()
        annotation_save.save_provider_batch_results_by_image_id.return_value = AnnotationSaveResult(
            success_count=1,
            skip_count=0,
            error_count=0,
            total_count=1,
        )
        service = ProviderBatchWorkflowService(
            provider_batch_repo=test_provider_batch_repository,
            image_repo=test_repository,
            annotation_repo=test_annotation_repository,
            config_service=batch_config,
            adapters={"anthropic": adapter, "openai": adapter},
            annotation_save_service=annotation_save,
        )
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")
        _insert_image(db_session_factory, 2, "/tmp/images/two.webp")
        job_id = service.submit_images(
            provider="anthropic",
            endpoint="/v1/messages",
            litellm_model_id="anthropic/claude-test",
            prompt_profile="default",
            image_ids=[1, 2],
            model_id=10,
        )

        result = service.import_results(
            job_id,
            ProviderBatchFetchResult(
                provider_job_id="batch_123",
                provider_status="completed",
                items=(
                    ProviderBatchResultItem("img-1", "failed", annotation=None),
                    ProviderBatchResultItem("img-2", "succeeded", annotation={"tags": ["tag"]}),
                ),
            ),
        )

        assert result.imported_count == 1
        assert result.skipped_count == 1
        assert result.error_count == 0
        assert result.total_count == 2
        assert result.job_imported is False

    def test_import_results_uses_fallback_job_id_when_object_result_omits_provider_job_id(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
        test_repository,
        test_annotation_repository,
        batch_config: Mock,
        db_session_factory: sessionmaker,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        annotation_save = Mock()
        annotation_save.save_provider_batch_results_by_image_id.return_value = AnnotationSaveResult(
            success_count=1,
            skip_count=0,
            error_count=0,
            total_count=1,
        )
        service = ProviderBatchWorkflowService(
            provider_batch_repo=test_provider_batch_repository,
            image_repo=test_repository,
            annotation_repo=test_annotation_repository,
            config_service=batch_config,
            adapters={"anthropic": adapter, "openai": adapter},
            annotation_save_service=annotation_save,
        )
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")
        job_id = service.submit_images(
            provider="anthropic",
            endpoint="/v1/messages",
            litellm_model_id="anthropic/claude-test",
            prompt_profile="default",
            image_ids=[1],
            model_id=10,
        )
        object_result = SimpleNamespace(
            provider_job_id=None,
            provider_status="completed",
            items=(ProviderBatchResultItem("img-1", "succeeded", annotation={"tags": ["tag"]}),),
        )

        result = service.import_results(job_id, object_result)

        assert result.job_imported is True
        annotation_save.save_provider_batch_results_by_image_id.assert_called_once()

    def test_import_results_preserves_mapping_fetch_counts_and_timestamps(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
        test_repository,
        test_annotation_repository,
        batch_config: Mock,
        db_session_factory: sessionmaker,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        annotation_save = Mock()
        annotation_save.save_provider_batch_results_by_image_id.return_value = AnnotationSaveResult(
            success_count=1,
            skip_count=0,
            error_count=0,
            total_count=1,
        )
        service = ProviderBatchWorkflowService(
            provider_batch_repo=test_provider_batch_repository,
            image_repo=test_repository,
            annotation_repo=test_annotation_repository,
            config_service=batch_config,
            adapters={"anthropic": adapter, "openai": adapter},
            annotation_save_service=annotation_save,
        )
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")
        job_id = service.submit_images(
            provider="anthropic",
            endpoint="/v1/messages",
            litellm_model_id="anthropic/claude-test",
            prompt_profile="default",
            image_ids=[1],
            model_id=10,
        )

        service.import_results(
            job_id,
            {
                "provider_job_id": "batch_123",
                "provider_status": "completed",
                "request_count": "1",
                "succeeded_count": "1",
                "failed_count": "0",
                "completed_at": "2026-05-25T02:00:00+00:00",
                "items": [
                    {
                        "custom_id": "img-1",
                        "status": "succeeded",
                        "annotation": {"tags": ["tag"]},
                    }
                ],
            },
        )

        job = test_provider_batch_repository.get_provider_batch_job(job_id)
        assert job is not None
        assert job.request_count == 1
        assert job.succeeded_count == 1
        assert job.failed_count == 0
        assert job.completed_at is not None
        assert job.completed_at.isoformat() == "2026-05-25T02:00:00"

    def test_import_results_does_not_mark_imported_when_no_annotations_were_saved(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
        test_repository,
        test_annotation_repository,
        batch_config: Mock,
        db_session_factory: sessionmaker,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        annotation_save = Mock()
        annotation_save.save_provider_batch_results_by_image_id.return_value = AnnotationSaveResult(
            success_count=0,
            skip_count=0,
            error_count=0,
            total_count=0,
        )
        service = ProviderBatchWorkflowService(
            provider_batch_repo=test_provider_batch_repository,
            image_repo=test_repository,
            annotation_repo=test_annotation_repository,
            config_service=batch_config,
            adapters={"anthropic": adapter, "openai": adapter},
            annotation_save_service=annotation_save,
        )
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")
        job_id = service.submit_images(
            provider="anthropic",
            endpoint="/v1/messages",
            litellm_model_id="anthropic/claude-test",
            prompt_profile="default",
            image_ids=[1],
            model_id=10,
        )

        result = service.import_results(
            job_id,
            ProviderBatchFetchResult(
                provider_job_id="batch_123",
                provider_status="completed",
                items=(ProviderBatchResultItem("img-1", "failed", error_message="provider failed"),),
            ),
        )

        assert result.imported_count == 0
        assert result.job_imported is False
        job = test_provider_batch_repository.get_provider_batch_job(job_id)
        assert job is not None
        assert job.status == "completed"
        assert job.imported_at is None

    def test_import_results_rejects_importable_items_before_completed(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
        test_repository,
        test_annotation_repository,
        batch_config: Mock,
        db_session_factory: sessionmaker,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        annotation_save = Mock()
        service = ProviderBatchWorkflowService(
            provider_batch_repo=test_provider_batch_repository,
            image_repo=test_repository,
            annotation_repo=test_annotation_repository,
            config_service=batch_config,
            adapters={"anthropic": adapter, "openai": adapter},
            annotation_save_service=annotation_save,
        )
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")
        job_id = service.submit_images(
            provider="anthropic",
            endpoint="/v1/messages",
            litellm_model_id="anthropic/claude-test",
            prompt_profile="default",
            image_ids=[1],
            model_id=10,
        )

        with pytest.raises(ProviderBatchError, match="running -> imported"):
            service.import_results(
                job_id,
                ProviderBatchFetchResult(
                    provider_job_id="batch_123",
                    provider_status="running",
                    items=(ProviderBatchResultItem("img-1", "succeeded", annotation={"tags": ["tag"]}),),
                ),
            )

        annotation_save.save_provider_batch_results_by_image_id.assert_not_called()
        job = test_provider_batch_repository.get_provider_batch_job(job_id)
        assert job is not None
        assert job.status == "running"
        assert job.imported_at is None

    def test_import_results_rejects_importable_mapping_without_provider_status(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
        test_repository,
        test_annotation_repository,
        batch_config: Mock,
        db_session_factory: sessionmaker,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        annotation_save = Mock()
        service = ProviderBatchWorkflowService(
            provider_batch_repo=test_provider_batch_repository,
            image_repo=test_repository,
            annotation_repo=test_annotation_repository,
            config_service=batch_config,
            adapters={"anthropic": adapter, "openai": adapter},
            annotation_save_service=annotation_save,
        )
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")
        job_id = service.submit_images(
            provider="anthropic",
            endpoint="/v1/messages",
            litellm_model_id="anthropic/claude-test",
            prompt_profile="default",
            image_ids=[1],
            model_id=10,
        )

        with pytest.raises(ProviderBatchError, match="validating -> imported"):
            service.import_results(
                job_id,
                {
                    "provider_job_id": "batch_123",
                    "items": [
                        {
                            "custom_id": "img-1",
                            "status": "succeeded",
                            "annotation": {"tags": ["tag"]},
                        }
                    ],
                },
            )

        annotation_save.save_provider_batch_results_by_image_id.assert_not_called()
        job = test_provider_batch_repository.get_provider_batch_job(job_id)
        assert job is not None
        assert job.status == "validating"
        assert job.imported_at is None

    def test_import_results_rejects_already_imported_job(
        self,
        workflow: tuple[ProviderBatchWorkflowService, FakeProviderBatchAdapter],
        test_provider_batch_repository: ProviderBatchRepository,
        db_session_factory: sessionmaker,
    ) -> None:
        service, _adapter = workflow
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")
        job_id = service.submit_images(
            provider="anthropic",
            endpoint="/v1/messages",
            litellm_model_id="anthropic/claude-test",
            prompt_profile="default",
            image_ids=[1],
        )
        test_provider_batch_repository.update_provider_batch_job(job_id, {"status": "imported"})

        with pytest.raises(ProviderBatchError, match="import 済み"):
            service.import_results(job_id, ProviderBatchFetchResult("batch_123", "completed"))

    def test_import_results_save_errors_leave_job_retryable(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
        test_repository,
        test_annotation_repository,
        batch_config: Mock,
        db_session_factory: sessionmaker,
    ) -> None:
        adapter = FakeProviderBatchAdapter()
        annotation_save = Mock()
        annotation_save.save_provider_batch_results_by_image_id.return_value = AnnotationSaveResult(
            success_count=0,
            skip_count=0,
            error_count=1,
            total_count=1,
            error_details=["image_id=1: write failed"],
        )
        service = ProviderBatchWorkflowService(
            provider_batch_repo=test_provider_batch_repository,
            image_repo=test_repository,
            annotation_repo=test_annotation_repository,
            config_service=batch_config,
            adapters={"anthropic": adapter, "openai": adapter},
            annotation_save_service=annotation_save,
        )
        _insert_image(db_session_factory, 1, "/tmp/images/one.webp")
        job_id = service.submit_images(
            provider="anthropic",
            endpoint="/v1/messages",
            litellm_model_id="anthropic/claude-test",
            prompt_profile="default",
            image_ids=[1],
            model_id=10,
        )

        result = service.import_results(
            job_id,
            ProviderBatchFetchResult(
                provider_job_id="batch_123",
                provider_status="completed",
                items=(ProviderBatchResultItem("img-1", "succeeded", annotation={"tags": ["tag"]}),),
            ),
        )

        assert result.error_count == 1
        assert result.job_imported is False
        job = test_provider_batch_repository.get_provider_batch_job(job_id)
        assert job is not None
        assert job.status == "completed"
        assert job.imported_at is None
