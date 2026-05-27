"""Provider Batch annotation end-to-end deterministic test (Issue #518).

ADR 0026 (On-Demand Runtime Validation) に従い、本テストは実 OpenAI Batch API を
呼ばずに fake `ProviderBatchAdapter` を注入し、LoRAIro 側 wiring (submit →
download → import → annotations save) が `task_type="annotation"` で end-to-end
に動作することを deterministic に検証する。

実 OpenAI /v1/chat/completions Batch contract の runtime validation は
image-annotator-lib repo の `tests/runtime_validation/test_openai_chat_completions_batch_runtime.py`
で行う (ADR 0026 / ADR 0001 amended)。

カバー範囲:
- 成功 item: tags / captions / scores が `annotations` 系テーブルに保存
- refusal item: `provider_batch_items.error_type` / `error_message` に記録、annotations
  には保存されない (non_importable_count に算入)

Plan: docs/plans/plan_518_openai_annotation_batch_agentteams.md §4 T3
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy.orm import sessionmaker

from lorairo.database.repository.annotation_record import AnnotationRepository
from lorairo.database.repository.image import ImageRepository
from lorairo.database.repository.provider_batch import ProviderBatchRepository
from lorairo.database.schema import Image, Model
from lorairo.services.annotation_save_service import AnnotationSaveService
from lorairo.services.provider_batch_service import (
    BatchJobHandle,
    BatchSubmitRequest,
    ProviderBatchFetchResult,
    ProviderBatchResultItem,
    ProviderBatchStatus,
    ProviderBatchSubmission,
)
from lorairo.services.provider_batch_workflow_service import (
    ProviderBatchWorkflowService,
)

_MODEL_LITELLM_ID = "openai/gpt-4o-mini"
_PROVIDER = "openai"


class _FakeAnnotationBatchAdapter:
    """Deterministic fake adapter that emulates OpenAI Chat Completions batch lifecycle."""

    provider = _PROVIDER

    def __init__(self, items: list[ProviderBatchResultItem]) -> None:
        self._items = items
        self.submitted_request: BatchSubmitRequest | None = None

    def submit_batch(self, request: BatchSubmitRequest) -> ProviderBatchSubmission:
        self.submitted_request = request
        return ProviderBatchSubmission(
            provider_job_id="batch_annotation_e2e_001",
            provider_status="validating",
            status="submitted",
            request_count=len(request.items),
        )

    def retrieve_batch(self, handle: BatchJobHandle) -> ProviderBatchStatus:
        return ProviderBatchStatus(
            provider_job_id=handle.provider_job_id,
            provider_status="completed",
            status="completed",
            request_count=len(self._items),
            succeeded_count=sum(1 for it in self._items if it.status == "succeeded"),
            failed_count=sum(1 for it in self._items if it.status == "failed"),
        )

    def cancel_batch(self, handle: BatchJobHandle) -> ProviderBatchStatus:
        return ProviderBatchStatus(
            provider_job_id=handle.provider_job_id,
            provider_status="cancelled",
            status="canceled",
        )

    def fetch_batch_results(
        self, handle: BatchJobHandle, destination_dir: Path
    ) -> ProviderBatchFetchResult:
        return ProviderBatchFetchResult(
            provider_job_id=handle.provider_job_id,
            provider_status="completed",
            status="completed",
            request_count=len(self._items),
            succeeded_count=sum(1 for it in self._items if it.status == "succeeded"),
            failed_count=sum(1 for it in self._items if it.status == "failed"),
            items=tuple(self._items),
        )


def _make_succeeded_item(
    custom_id: str, tags: list[str], captions: list[str], score: float
) -> ProviderBatchResultItem:
    """Construct a succeeded fetch result item with UnifiedAnnotationResult-shape annotation."""
    annotation = {
        "model_name": "openai_batch",
        "capabilities": ["tags", "captions", "scores"],
        "tags": tags,
        "captions": captions,
        "scores": {"score": score},
        "score_labels": [],
        "ratings": [],
    }
    return ProviderBatchResultItem(
        custom_id=custom_id,
        status="succeeded",
        annotation=annotation,
    )


def _make_refusal_item(custom_id: str) -> ProviderBatchResultItem:
    return ProviderBatchResultItem(
        custom_id=custom_id,
        status="failed",
        annotation=None,
        error_type="provider_safety_refusal",
        error_message="OpenAI safety filter refused the request",
    )


def _insert_image(session_factory: sessionmaker, image_id: int, stored_path: Path) -> None:
    with session_factory() as session:
        session.add(
            Image(
                id=image_id,
                uuid=f"e2e-annotation-{image_id}-{uuid4()}",
                phash=f"e2eannotation{image_id:04d}",
                original_image_path=str(stored_path),
                stored_image_path=str(stored_path),
                width=64,
                height=64,
                format="PNG",
                mode="RGB",
                has_alpha=False,
                filename=stored_path.name,
                extension=stored_path.suffix,
            )
        )
        session.commit()


def _insert_annotation_model(session_factory: sessionmaker) -> int:
    with session_factory() as session:
        model = Model(
            name=_MODEL_LITELLM_ID,
            litellm_model_id=_MODEL_LITELLM_ID,
            provider=_PROVIDER,
        )
        session.add(model)
        session.flush()
        session.commit()
        return int(model.id)


@pytest.fixture
def batch_config_mock(tmp_path: Path) -> Mock:
    config = Mock()
    config.get_api_keys.return_value = {_PROVIDER: "sk-test-e2e-annotation"}
    config.get_batch_results_directory.return_value = tmp_path / "batch_results"
    return config


@pytest.fixture
def workflow_setup(
    db_session_factory: sessionmaker,
    batch_config_mock: Mock,
    tmp_path: Path,
) -> dict[str, Any]:
    image_paths = [tmp_path / f"image_{i}.png" for i in range(1, 4)]
    for image_id, image_path in enumerate(image_paths, start=1):
        image_path.touch()
        _insert_image(db_session_factory, image_id, image_path)

    model_id = _insert_annotation_model(db_session_factory)

    image_repo = ImageRepository(session_factory=db_session_factory)
    annotation_repo = AnnotationRepository(session_factory=db_session_factory)
    provider_batch_repo = ProviderBatchRepository(session_factory=db_session_factory)
    annotation_save_service = AnnotationSaveService(
        annotation_repo=annotation_repo,
        image_repo=image_repo,
    )

    items = [
        _make_succeeded_item(
            "img-1",
            tags=["1girl", "blue_eyes", "school_uniform"],
            captions=["A girl with blue eyes wearing a school uniform."],
            score=7.5,
        ),
        _make_succeeded_item(
            "img-2",
            tags=["sunset", "landscape"],
            captions=["A sunset over a mountain landscape."],
            score=8.2,
        ),
        _make_refusal_item("img-3"),
    ]
    adapter = _FakeAnnotationBatchAdapter(items)

    service = ProviderBatchWorkflowService(
        provider_batch_repo=provider_batch_repo,
        image_repo=image_repo,
        annotation_repo=annotation_repo,
        config_service=batch_config_mock,
        adapters={_PROVIDER: adapter},
        annotation_save_service=annotation_save_service,
    )

    return {
        "service": service,
        "adapter": adapter,
        "annotation_repo": annotation_repo,
        "image_repo": image_repo,
        "provider_batch_repo": provider_batch_repo,
        "model_id": model_id,
        "image_ids": [1, 2, 3],
        "image_paths": image_paths,
        "session_factory": db_session_factory,
    }


@pytest.mark.integration
def test_annotation_batch_e2e_persists_success_and_skips_refusal(
    workflow_setup: dict[str, Any],
) -> None:
    """submit → import の wiring で成功 annotation は保存、refusal は skip される。"""
    service: ProviderBatchWorkflowService = workflow_setup["service"]
    adapter: _FakeAnnotationBatchAdapter = workflow_setup["adapter"]
    provider_batch_repo: ProviderBatchRepository = workflow_setup["provider_batch_repo"]
    image_repo: ImageRepository = workflow_setup["image_repo"]
    image_ids: list[int] = workflow_setup["image_ids"]
    model_id: int = workflow_setup["model_id"]

    job_id = service.submit_images(
        provider=_PROVIDER,
        endpoint="/v1/chat/completions",
        litellm_model_id=_MODEL_LITELLM_ID,
        prompt_profile="default",
        image_ids=image_ids,
        model_id=model_id,
        task_type="annotation",
    )

    assert adapter.submitted_request is not None
    assert adapter.submitted_request.endpoint == "/v1/chat/completions"
    assert all(item.task_type == "annotation" for item in adapter.submitted_request.items)

    job = provider_batch_repo.get_provider_batch_job(job_id)
    assert job is not None
    assert job.model_id == model_id

    import_result = service.import_results(job_id)

    # 成功 2 件保存、refusal 1 件は non-importable
    assert import_result.imported_count == 2
    assert import_result.skipped_count >= 1
    # provider_batch_items の状態を確認
    db_items = provider_batch_repo.list_provider_batch_items(job_id)
    items_by_custom_id = {item.custom_id: item for item in db_items}
    assert items_by_custom_id["img-1"].status == "imported"
    assert items_by_custom_id["img-2"].status == "imported"
    refusal_item = items_by_custom_id["img-3"]
    assert refusal_item.status == "failed"
    assert refusal_item.error_type == "provider_safety_refusal"

    # 成功 image_id=1 / 2 で annotations が保存されていることを確認
    metadata_image_1 = image_repo.get_image_annotations(1)
    tags_for_1 = [t["tag"] for t in metadata_image_1.get("tags", [])]
    captions_for_1 = [c["caption"] for c in metadata_image_1.get("captions", [])]
    scores_for_1 = [s["score"] for s in metadata_image_1.get("scores", [])]
    assert "1girl" in tags_for_1
    assert any("blue eyes" in c.lower() for c in captions_for_1)
    assert 7.5 in scores_for_1

    metadata_image_2 = image_repo.get_image_annotations(2)
    tags_for_2 = [t["tag"] for t in metadata_image_2.get("tags", [])]
    assert "sunset" in tags_for_2

    # refusal image_id=3 には annotation が保存されないこと
    metadata_image_3 = image_repo.get_image_annotations(3)
    assert not metadata_image_3.get("tags")
    assert not metadata_image_3.get("captions")
    assert not metadata_image_3.get("scores")
