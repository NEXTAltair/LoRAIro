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

# ADR 0062: _insert_image が設定する phash / width / height (=100) から導かれる
# custom_id 規約。submit と result 突合の両方でこの規約に揃える。
_INSERT_IMAGE_LONG_EDGE = 100


def _expected_custom_id(image_id: int) -> str:
    """``_insert_image`` で登録した画像の ADR 0062 custom_id を返す。"""
    return f"ph:providerbatch{image_id:04d}:le:{_INSERT_IMAGE_LONG_EDGE}"


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


def _insert_image(
    session_factory: sessionmaker,
    image_id: int,
    stored_path: str,
    *,
    phash: str | None = None,
    width: int = 100,
    height: int = 100,
) -> None:
    with session_factory() as session:
        session.add(
            Image(
                id=image_id,
                uuid=f"test-provider-batch-{image_id}",
                phash=phash if phash is not None else f"providerbatch{image_id:04d}",
                original_image_path=stored_path,
                stored_image_path=stored_path,
                width=width,
                height=height,
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
            (_expected_custom_id(1), 1, Path("/tmp/images/one.webp"), "annotation"),
            (_expected_custom_id(2), 2, Path("/tmp/images/two.webp"), "annotation"),
        ]
        job = test_provider_batch_repository.get_provider_batch_job(job_id)
        assert job is not None
        assert job.provider_job_id == "batch_123"
        assert [
            item.custom_id for item in test_provider_batch_repository.list_provider_batch_items(job_id)
        ] == [
            _expected_custom_id(1),
            _expected_custom_id(2),
        ]

    def test_submit_images_dedupes_same_phash_and_long_edge(
        self,
        workflow: tuple[ProviderBatchWorkflowService, FakeProviderBatchAdapter],
        test_provider_batch_repository: ProviderBatchRepository,
        db_session_factory: sessionmaker,
    ) -> None:
        """ADR 0062: 同一 pHash+長辺の重複素材は 1 リクエストに dedupe する。"""
        service, adapter = workflow
        # 画像 1 と 2 は同一 pHash・同一長辺 (同一素材)、画像 3 は別素材。
        _insert_image(
            db_session_factory, 1, "/tmp/images/a.webp", phash="dupdupdupdupdup0", width=1024, height=768
        )
        _insert_image(
            db_session_factory, 2, "/tmp/images/b.webp", phash="dupdupdupdupdup0", width=1024, height=768
        )
        _insert_image(
            db_session_factory, 3, "/tmp/images/c.webp", phash="otherotherother0", width=512, height=512
        )

        job_id = service.submit_images(
            provider="anthropic",
            endpoint="/v1/messages",
            litellm_model_id="anthropic/claude-test",
            prompt_profile="default",
            image_ids=[1, 2, 3],
        )

        assert adapter.submitted_request is not None
        submitted = [(item.custom_id, item.image_id) for item in adapter.submitted_request.items]
        # 重複素材は代表 image_id=1 の 1 件に統合され、別素材は別 custom_id で残る。
        assert submitted == [
            ("ph:dupdupdupdupdup0:le:1024", 1),
            ("ph:otherotherother0:le:512", 3),
        ]
        items = test_provider_batch_repository.list_provider_batch_items(job_id)
        assert {item.custom_id for item in items} == {
            "ph:dupdupdupdupdup0:le:1024",
            "ph:otherotherother0:le:512",
        }
        # 対応表 (custom_id -> image_id[]) は raw_request に保持される。
        dup_item = next(item for item in items if item.custom_id == "ph:dupdupdupdupdup0:le:1024")
        assert dup_item.raw_request == '{"lorairo_image_ids": [1, 2]}'

    def test_import_results_fans_out_to_deduped_image_ids(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
        test_repository,
        test_annotation_repository,
        batch_config: Mock,
        db_session_factory: sessionmaker,
    ) -> None:
        """ADR 0062: dedupe で統合した全 image_id へ annotation を反映する。"""
        adapter = FakeProviderBatchAdapter()
        annotation_save = Mock()
        annotation_save.save_provider_batch_results_by_image_id.return_value = AnnotationSaveResult(
            success_count=2,
            skip_count=0,
            error_count=0,
            total_count=2,
        )
        service = ProviderBatchWorkflowService(
            provider_batch_repo=test_provider_batch_repository,
            image_repo=test_repository,
            annotation_repo=test_annotation_repository,
            config_service=batch_config,
            adapters={"anthropic": adapter, "openai": adapter},
            annotation_save_service=annotation_save,
        )
        _insert_image(
            db_session_factory, 1, "/tmp/images/a.webp", phash="dupdupdupdupdup0", width=1024, height=768
        )
        _insert_image(
            db_session_factory, 2, "/tmp/images/b.webp", phash="dupdupdupdupdup0", width=1024, height=768
        )
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
                    ProviderBatchResultItem(
                        "ph:dupdupdupdupdup0:le:1024", "succeeded", annotation={"tags": ["tag"]}
                    ),
                ),
            ),
        )

        # 単一 result が重複統合した image_id 1 と 2 の両方へ反映される。
        annotation_save.save_provider_batch_results_by_image_id.assert_called_once_with(
            {1: {"tags": ["tag"]}, 2: {"tags": ["tag"]}},
            model_id=10,
            model_name="__provider_batch_model_10__",
        )
        assert result.imported_count == 2
        # Codex #646 P1 リグレッション: fan-out で save 件数 (image=2) が
        # provider item 件数 (=1) と一致しなくても、custom_id 単位で完了判定し
        # job / item を imported にする。
        assert result.job_imported is True
        # Codex #646 round3: サマリは image 単位で一貫 (2 image 保存 → 2/2)。
        assert result.total_count == 2
        assert result.skipped_count == 0
        item = test_provider_batch_repository.list_provider_batch_items(job_id)[0]
        assert item.status == "imported"
        job = test_provider_batch_repository.get_provider_batch_job(job_id)
        assert job is not None
        assert job.status == "imported"

    def test_import_results_counts_deduped_non_importable_per_image(
        self,
        test_provider_batch_repository: ProviderBatchRepository,
        test_repository,
        test_annotation_repository,
        batch_config: Mock,
        db_session_factory: sessionmaker,
    ) -> None:
        """Codex #646 round3: dedupe された失敗 item は fan-out 込みの image 数で skip 集計する。"""
        adapter = FakeProviderBatchAdapter()
        annotation_save = Mock()
        annotation_save.save_provider_batch_results_by_image_id.return_value = AnnotationSaveResult(
            success_count=0, skip_count=0, error_count=0, total_count=0
        )
        service = ProviderBatchWorkflowService(
            provider_batch_repo=test_provider_batch_repository,
            image_repo=test_repository,
            annotation_repo=test_annotation_repository,
            config_service=batch_config,
            adapters={"anthropic": adapter, "openai": adapter},
            annotation_save_service=annotation_save,
        )
        # 同一素材 (image 1, 2) が 1 custom_id に dedupe される。
        _insert_image(
            db_session_factory, 1, "/tmp/images/a.webp", phash="dupdupdupdupdup0", width=1024, height=768
        )
        _insert_image(
            db_session_factory, 2, "/tmp/images/b.webp", phash="dupdupdupdupdup0", width=1024, height=768
        )
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
                # provider が失敗を返す (non-importable)。dedupe で 2 image が未注釈のまま。
                items=(ProviderBatchResultItem("ph:dupdupdupdupdup0:le:1024", "failed", annotation=None),),
            ),
        )

        annotation_save.save_provider_batch_results_by_image_id.assert_not_called()
        # 1 provider item の失敗だが、fan-out 込みで 2 image が skip / total に算入される。
        assert result.imported_count == 0
        assert result.skipped_count == 2
        assert result.total_count == 2
        assert result.job_imported is False

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
            items=(
                ProviderBatchResultItem(_expected_custom_id(1), "succeeded", annotation={"tags": ["tag"]}),
            ),
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
                ProviderBatchResultItem(_expected_custom_id(1), "succeeded", raw_response={"ok": True}),
                {
                    "custom_id": _expected_custom_id(2),
                    "status": "failed",
                    "error_type": "PARSE",
                    "error_message": "bad",
                },
                SimpleNamespace(custom_id="ph:missing404:le:100", status="failed", error_message="missing"),
            ],
        )

        assert result.updated_count == 2
        assert result.missing_count == 1
        assert result.missing_custom_ids == ("ph:missing404:le:100",)
        items = {
            item.custom_id: item
            for item in test_provider_batch_repository.list_provider_batch_items(job_id)
        }
        assert items[_expected_custom_id(1)].status == "succeeded"
        assert items[_expected_custom_id(1)].raw_response == '{"ok": true}'
        assert items[_expected_custom_id(2)].status == "failed"
        assert items[_expected_custom_id(2)].error_type == "PARSE"
        assert items[_expected_custom_id(2)].error_message == "bad"

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
                [ProviderBatchResultItem(_expected_custom_id(1), "succeeded")],
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
            items=(
                ProviderBatchResultItem(_expected_custom_id(1), "succeeded", annotation={"tags": ["tag"]}),
            ),
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
                        _expected_custom_id(1),
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
                    ProviderBatchResultItem(
                        _expected_custom_id(1), "succeeded", annotation={"tags": ["tag"]}
                    ),
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
            job_id, {_expected_custom_id(1): {"status": "imported"}}
        )
        adapter.fetch_result = ProviderBatchFetchResult(
            provider_job_id="batch_123",
            provider_status="completed",
            items=(
                ProviderBatchResultItem(_expected_custom_id(1), "succeeded", annotation={"tags": ["tag"]}),
            ),
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
            job_id, {_expected_custom_id(1): {"status": "imported"}}
        )

        result = service.import_results(
            job_id,
            ProviderBatchFetchResult(
                provider_job_id="batch_123",
                provider_status="completed",
                items=(
                    ProviderBatchResultItem(
                        _expected_custom_id(1), "succeeded", annotation={"tags": ["old"]}
                    ),
                    ProviderBatchResultItem(
                        _expected_custom_id(2), "succeeded", annotation={"tags": ["new"]}
                    ),
                ),
            ),
        )

        assert result.error_count == 1
        assert result.skipped_count == 1
        items = {
            item.custom_id: item
            for item in test_provider_batch_repository.list_provider_batch_items(job_id)
        }
        assert items[_expected_custom_id(1)].status == "imported"
        assert items[_expected_custom_id(2)].status == "succeeded"
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
            {_expected_custom_id(2): {"model_id": model_id_2}},
        )

        result = service.import_results(
            job_id,
            ProviderBatchFetchResult(
                provider_job_id="batch_123",
                provider_status="completed",
                items=(
                    ProviderBatchResultItem(
                        _expected_custom_id(1), "succeeded", annotation={"tags": ["one"]}
                    ),
                    ProviderBatchResultItem(
                        _expected_custom_id(2), "succeeded", annotation={"tags": ["two"]}
                    ),
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
                    ProviderBatchResultItem(_expected_custom_id(1), "failed", annotation=None),
                    ProviderBatchResultItem(
                        _expected_custom_id(2), "succeeded", annotation={"tags": ["tag"]}
                    ),
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
            items=(
                ProviderBatchResultItem(_expected_custom_id(1), "succeeded", annotation={"tags": ["tag"]}),
            ),
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
                        "custom_id": _expected_custom_id(1),
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
                items=(
                    ProviderBatchResultItem(
                        _expected_custom_id(1), "failed", error_message="provider failed"
                    ),
                ),
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
                    items=(
                        ProviderBatchResultItem(
                            _expected_custom_id(1), "succeeded", annotation={"tags": ["tag"]}
                        ),
                    ),
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
                            "custom_id": _expected_custom_id(1),
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
                items=(
                    ProviderBatchResultItem(
                        _expected_custom_id(1), "succeeded", annotation={"tags": ["tag"]}
                    ),
                ),
            ),
        )

        assert result.error_count == 1
        assert result.job_imported is False
        job = test_provider_batch_repository.get_provider_batch_job(job_id)
        assert job is not None
        assert job.status == "completed"
        assert job.imported_at is None
