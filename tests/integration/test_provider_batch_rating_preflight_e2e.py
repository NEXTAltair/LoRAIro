"""Provider Batch rating preflight end-to-end deterministic test (Issue #505).

ADR 0026 (On-Demand Runtime Validation) に従い、本テストは実 OpenAI Batch API を
呼ばずに fake `ProviderBatchAdapter` を注入し、LoRAIro 側の wiring (submit →
download → import → annotation save → filter_excluded_by_rating) が rating
preflight task_type で end-to-end に動作することを deterministic に検証する。

実 OpenAI API smoke は image-annotator-lib repo の `tests/runtime_validation/`
配下で行う (ADR 0026 / ADR 0001 amended)。本ファイルはそれと相補的に、
LoRAIro 側の boundary 配線を CI で継続的に守る。

Plan: docs/plans/plan_507_remaining_e2e_smoke_agentteams.md §4 T3
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

_MODEL_LITELLM_ID = "openai/omni-moderation-latest"
_PROVIDER = "openai"


class _FakeRatingPreflightAdapter:
    """Deterministic fake adapter that emulates OpenAI Moderations batch lifecycle.

    submit_batch → validating, retrieve_batch → completed,
    fetch_batch_results → 3 RatingPrediction (PG / R / XXX) を返す。
    """

    provider = _PROVIDER

    def __init__(self, items_by_custom_id: dict[str, dict[str, Any]]) -> None:
        self._items = items_by_custom_id
        self.submitted_request: BatchSubmitRequest | None = None
        self.fetch_called_with: tuple[BatchJobHandle, Path] | None = None

    def submit_batch(self, request: BatchSubmitRequest) -> ProviderBatchSubmission:
        self.submitted_request = request
        return ProviderBatchSubmission(
            provider_job_id="batch_rating_preflight_001",
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
            succeeded_count=len(self._items),
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
        self.fetch_called_with = (handle, destination_dir)
        result_items = tuple(
            ProviderBatchResultItem(
                custom_id=custom_id,
                status="succeeded",
                annotation=annotation,
            )
            for custom_id, annotation in self._items.items()
        )
        return ProviderBatchFetchResult(
            provider_job_id=handle.provider_job_id,
            provider_status="completed",
            status="completed",
            request_count=len(result_items),
            succeeded_count=len(result_items),
            items=result_items,
        )


def _make_moderation_annotation(raw_label: str, confidence: float) -> dict[str, Any]:
    """UnifiedAnnotationResult-shape dict carrying a single openai_moderation_v1 rating.

    ADR 0031 amendment の threshold table と整合する `raw_label` を渡す。
    `_build_annotations_dict` / `rating_mapper` が canonical rating
    (PG / PG-13 / R / X / XXX) へ写像する。
    """
    return {
        "ratings": [
            {
                "raw_label": raw_label,
                "source_scheme": "openai_moderation_v1",
                "confidence_score": confidence,
            }
        ],
        "tags": [],
        "captions": [],
        "scores": {},
        "score_labels": [],
    }


def _insert_image(session_factory: sessionmaker, image_id: int, stored_path: Path) -> None:
    """Register a minimal Image row matching schema requirements."""
    with session_factory() as session:
        session.add(
            Image(
                id=image_id,
                uuid=f"e2e-rating-preflight-{image_id}-{uuid4()}",
                phash=f"e2eratingpref{image_id:04d}",
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


def _insert_moderation_model(session_factory: sessionmaker) -> int:
    """Register omni-moderation-latest as a Model row and return its id."""
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
    config.get_api_keys.return_value = {_PROVIDER: "sk-test-e2e"}
    config.get_batch_results_directory.return_value = tmp_path / "batch_results"
    return config


@pytest.fixture
def workflow_setup(
    db_session_factory: sessionmaker,
    batch_config_mock: Mock,
    tmp_path: Path,
) -> dict[str, Any]:
    """Construct repositories, fake adapter, and workflow service for the E2E scenario.

    DB / image / model 登録までを行い、3 image_id と 1 model_id を返す。
    """
    image_paths = [tmp_path / f"image_{i}.png" for i in range(1, 4)]
    for image_id, image_path in enumerate(image_paths, start=1):
        image_path.touch()
        _insert_image(db_session_factory, image_id, image_path)

    model_id = _insert_moderation_model(db_session_factory)

    image_repo = ImageRepository(session_factory=db_session_factory)
    annotation_repo = AnnotationRepository(session_factory=db_session_factory)
    provider_batch_repo = ProviderBatchRepository(session_factory=db_session_factory)
    annotation_save_service = AnnotationSaveService(
        annotation_repo=annotation_repo,
        image_repo=image_repo,
    )

    items_by_custom_id = {
        "img-1": _make_moderation_annotation("pg", confidence=0.10),
        "img-2": _make_moderation_annotation("r", confidence=0.65),
        "img-3": _make_moderation_annotation("xxx", confidence=0.99),
    }
    adapter = _FakeRatingPreflightAdapter(items_by_custom_id)

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
        "image_repo": image_repo,
        "annotation_repo": annotation_repo,
        "annotation_save_service": annotation_save_service,
        "provider_batch_repo": provider_batch_repo,
        "model_id": model_id,
        "image_ids": [1, 2, 3],
        "image_paths": image_paths,
        "session_factory": db_session_factory,
    }


@pytest.mark.integration
def test_rating_preflight_e2e_marks_xxx_image_as_excluded(workflow_setup: dict[str, Any]) -> None:
    """Provider batch submit → import → ratings 保存 → annotation 送信判定までを通す。

    シナリオ:
        1. workflow_service.submit_images(task_type="rating_preflight", model_id=<omni>)
        2. provider_batch_jobs / provider_batch_items が task_type="rating_preflight" で作成
        3. fake adapter が retrieve_batch="completed" + fetch_batch_results で 3 RatingPrediction を返す
        4. workflow_service.import_results → ratings table に PG / R / XXX が保存
        5. annotation_save_service.filter_excluded_by_rating で XXX のみが除外
    """
    service: ProviderBatchWorkflowService = workflow_setup["service"]
    adapter: _FakeRatingPreflightAdapter = workflow_setup["adapter"]
    provider_batch_repo: ProviderBatchRepository = workflow_setup["provider_batch_repo"]
    annotation_save_service: AnnotationSaveService = workflow_setup["annotation_save_service"]
    image_paths: list[Path] = workflow_setup["image_paths"]
    image_ids: list[int] = workflow_setup["image_ids"]
    model_id: int = workflow_setup["model_id"]

    job_id = service.submit_images(
        provider=_PROVIDER,
        endpoint="/v1/moderations",
        litellm_model_id=_MODEL_LITELLM_ID,
        prompt_profile="default",
        image_ids=image_ids,
        model_id=model_id,
        task_type="rating_preflight",
    )

    assert adapter.submitted_request is not None
    assert adapter.submitted_request.endpoint == "/v1/moderations"
    assert adapter.submitted_request.litellm_model_id == _MODEL_LITELLM_ID
    assert all(item.task_type == "rating_preflight" for item in adapter.submitted_request.items)

    job = provider_batch_repo.get_provider_batch_job(job_id)
    assert job is not None
    assert job.model_id == model_id
    assert job.provider_job_id == "batch_rating_preflight_001"
    db_items = provider_batch_repo.list_provider_batch_items(job_id)
    assert {item.custom_id for item in db_items} == {"img-1", "img-2", "img-3"}
    assert {item.task_type for item in db_items} == {"rating_preflight"}
    assert {item.model_id for item in db_items} == {model_id}

    import_result = service.import_results(job_id)

    assert import_result.imported_count == 3
    assert import_result.error_count == 0
    assert import_result.job_imported is True

    refreshed_job = provider_batch_repo.get_provider_batch_job(job_id)
    assert refreshed_job is not None
    assert refreshed_job.status == "imported"

    str_image_paths = [str(p) for p in image_paths]
    accepted_paths = annotation_save_service.filter_excluded_by_rating(str_image_paths)
    assert accepted_paths == str_image_paths[:2]
    excluded_path = str_image_paths[2]
    assert excluded_path not in accepted_paths

    latest_ratings = workflow_setup["image_repo"].get_latest_normalized_ratings_by_image_ids(image_ids)
    assert latest_ratings.get(1) == "PG"
    assert latest_ratings.get(2) == "R"
    assert latest_ratings.get(3) == "XXX"
