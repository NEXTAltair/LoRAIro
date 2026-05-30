"""ModerationPreflightService tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from lorairo.services.annotation_save_service import AnnotationSaveResult
from lorairo.services.moderation_preflight_service import (
    MODERATION_ERROR_TYPE_BLOCKED,
    MODERATION_ERROR_TYPE_FAILED,
    MODERATION_ERROR_TYPE_MISSING_KEY,
    MODERATION_ERROR_TYPE_NO_RATING,
    MODERATION_LITELLM_MODEL_ID,
    ModerationPreflightService,
)


@pytest.fixture
def deps() -> dict[str, Mock]:
    image_repo = Mock()
    model_repo = Mock()
    annotation_repo = Mock()
    error_record_repo = Mock()
    save_service = Mock()
    config_service = Mock()
    runner = Mock()
    config_service.get_setting.return_value = "sk-test"
    model_repo.get_model_by_litellm_id.return_value = SimpleNamespace(id=42)
    save_service.save_annotation_results.return_value = AnnotationSaveResult(
        success_count=1,
        skip_count=0,
        error_count=0,
        total_count=1,
    )
    return {
        "image_repo": image_repo,
        "model_repo": model_repo,
        "annotation_repo": annotation_repo,
        "error_record_repo": error_record_repo,
        "save_service": save_service,
        "config_service": config_service,
        "runner": runner,
    }


def _service(deps: dict[str, Mock]) -> ModerationPreflightService:
    return ModerationPreflightService(
        image_repo=deps["image_repo"],
        model_repo=deps["model_repo"],
        error_record_repo=deps["error_record_repo"],
        annotation_save_service=deps["save_service"],
        config_service=deps["config_service"],
        moderation_runner=deps["runner"],
    )


@pytest.mark.unit
def test_existing_ratings_allow_and_block_without_moderation(deps: dict[str, Mock]) -> None:
    deps["image_repo"].get_image_ids_by_filepaths.return_value = {
        "/img/pg.png": 1,
        "/img/r.png": 2,
        "/img/x.png": 3,
        "/img/missing.png": None,
    }
    deps["image_repo"].get_latest_normalized_ratings_by_image_ids.return_value = {
        1: "PG",
        2: "R",
        3: "XXX",
    }

    result = _service(deps).apply(["/img/pg.png", "/img/r.png", "/img/x.png", "/img/missing.png"])

    assert result.allowed_paths == ["/img/pg.png", "/img/r.png", "/img/missing.png"]
    assert [skip.reason for skip in result.skipped] == [MODERATION_ERROR_TYPE_BLOCKED]
    assert result.existing_rating_allowed_count == 2
    assert result.existing_rating_blocked_count == 1
    deps["runner"].assert_not_called()


@pytest.mark.unit
def test_unrated_moderation_allows_after_saved_safe_rating(deps: dict[str, Mock]) -> None:
    deps["image_repo"].get_image_ids_by_filepaths.return_value = {"/img/unrated.png": 10}
    deps["image_repo"].get_latest_normalized_ratings_by_image_ids.side_effect = [
        {},
        {10: "PG"},
    ]
    deps["image_repo"].get_phashes_by_filepaths.return_value = {"/img/unrated.png": "phash-10"}
    deps["runner"].return_value = {"phash-10": {MODERATION_LITELLM_MODEL_ID: {"ratings": []}}}

    result = _service(deps).apply(["/img/unrated.png"])

    assert result.allowed_paths == ["/img/unrated.png"]
    assert result.skipped == []
    assert result.moderated_count == 1
    deps["runner"].assert_called_once_with(
        image_paths=["/img/unrated.png"],
        litellm_model_ids=[MODERATION_LITELLM_MODEL_ID],
        phash_list=["phash-10"],
    )
    deps["save_service"].save_annotation_results.assert_called_once()


@pytest.mark.unit
def test_unrated_moderation_blocks_after_saved_x_rating(deps: dict[str, Mock]) -> None:
    deps["image_repo"].get_image_ids_by_filepaths.return_value = {"/img/unrated.png": 10}
    deps["image_repo"].get_latest_normalized_ratings_by_image_ids.side_effect = [
        {},
        {10: "X"},
    ]
    deps["image_repo"].get_phashes_by_filepaths.return_value = {"/img/unrated.png": "phash-10"}

    result = _service(deps).apply(["/img/unrated.png"])

    assert result.allowed_paths == []
    assert [skip.reason for skip in result.skipped] == [MODERATION_ERROR_TYPE_BLOCKED]
    assert result.moderated_count == 1


@pytest.mark.unit
def test_missing_openai_key_fails_closed_for_unrated(deps: dict[str, Mock]) -> None:
    deps["config_service"].get_setting.return_value = ""
    deps["image_repo"].get_image_ids_by_filepaths.return_value = {"/img/unrated.png": 10}
    deps["image_repo"].get_latest_normalized_ratings_by_image_ids.return_value = {}

    result = _service(deps).apply(["/img/unrated.png"])

    assert result.allowed_paths == []
    assert [skip.reason for skip in result.skipped] == [MODERATION_ERROR_TYPE_MISSING_KEY]
    assert result.failure_count == 1
    deps["runner"].assert_not_called()


@pytest.mark.unit
def test_moderation_exception_fails_closed_for_unrated(deps: dict[str, Mock]) -> None:
    deps["image_repo"].get_image_ids_by_filepaths.return_value = {"/img/unrated.png": 10}
    deps["image_repo"].get_latest_normalized_ratings_by_image_ids.return_value = {}
    deps["image_repo"].get_phashes_by_filepaths.return_value = {"/img/unrated.png": "phash-10"}
    deps["runner"].side_effect = RuntimeError("rate limited")

    result = _service(deps).apply(["/img/unrated.png"])

    assert result.allowed_paths == []
    assert [skip.reason for skip in result.skipped] == [MODERATION_ERROR_TYPE_FAILED]
    assert result.failure_count == 1


@pytest.mark.unit
def test_moderation_without_saved_rating_fails_closed(deps: dict[str, Mock]) -> None:
    deps["image_repo"].get_image_ids_by_filepaths.return_value = {"/img/unrated.png": 10}
    deps["image_repo"].get_latest_normalized_ratings_by_image_ids.side_effect = [
        {},
        {},
    ]
    deps["image_repo"].get_phashes_by_filepaths.return_value = {"/img/unrated.png": "phash-10"}

    result = _service(deps).apply(["/img/unrated.png"])

    assert result.allowed_paths == []
    assert [skip.reason for skip in result.skipped] == [MODERATION_ERROR_TYPE_NO_RATING]
    assert result.failure_count == 1


@pytest.mark.unit
def test_batch_moderation_failure_retries_per_image(deps: dict[str, Mock]) -> None:
    deps["image_repo"].get_image_ids_by_filepaths.return_value = {
        "/img/bad.png": 1,
        "/img/good.png": 2,
    }
    deps["image_repo"].get_latest_normalized_ratings_by_image_ids.side_effect = [
        {},
        {2: "PG"},
    ]
    deps["image_repo"].get_phashes_by_filepaths.return_value = {
        "/img/bad.png": "phash-1",
        "/img/good.png": "phash-2",
    }
    deps["runner"].side_effect = [
        RuntimeError("batch load failed"),
        RuntimeError("bad file"),
        {"phash-2": {MODERATION_LITELLM_MODEL_ID: {"ratings": []}}},
    ]

    result = _service(deps).apply(["/img/bad.png", "/img/good.png"])

    assert result.allowed_paths == ["/img/good.png"]
    assert [skip.reason for skip in result.skipped] == [MODERATION_ERROR_TYPE_FAILED]
    assert result.failure_count == 1
    assert deps["runner"].call_count == 3
