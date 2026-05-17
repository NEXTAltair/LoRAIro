"""AnnotationSaveService ユニットテスト。"""

from unittest.mock import MagicMock

import pytest

from lorairo.services.annotation_save_service import AnnotationSaveResult, AnnotationSaveService


@pytest.fixture
def mock_repository() -> MagicMock:
    """モック ImageRepository。"""
    repo = MagicMock()
    repo.find_image_ids_by_phashes.return_value = {}
    repo.get_models_by_litellm_ids.return_value = {}
    repo.batch_resolve_tag_ids.return_value = {}
    return repo


@pytest.fixture
def service(mock_repository: MagicMock) -> AnnotationSaveService:
    """テスト対象サービス。"""
    return AnnotationSaveService(mock_repository)


def _make_success_result(
    tags: list[str] | None = None,
    captions: list[str] | None = None,
    scores: dict | None = None,
    score_labels: list[str] | None = None,
) -> MagicMock:
    """正常系 UnifiedAnnotationResult モックを生成する。

    Issue #281 / ADR 0027: ``score_labels`` は canonical scorer (aesthetic_shadow,
    cafe_aesthetic) 用の categorical label。regression scorer は ``None``。
    """
    result = MagicMock()
    result.error = None
    result.tags = tags or []
    result.captions = captions or []
    result.scores = scores
    result.score_labels = score_labels
    result.ratings = None
    return result


@pytest.mark.unit
def test_save_annotation_results_with_empty_results_returns_zeros(
    service: AnnotationSaveService,
) -> None:
    """空の結果を渡した場合、すべてゼロの AnnotationSaveResult を返す。"""
    result = service.save_annotation_results({})

    assert result.success_count == 0
    assert result.skip_count == 0
    assert result.error_count == 0
    assert result.total_count == 0
    assert result.error_details == []


@pytest.mark.unit
def test_save_annotation_results_with_known_phashes_saves_all(
    service: AnnotationSaveService,
    mock_repository: MagicMock,
) -> None:
    """DBに存在するphashのアノテーションを全件保存する。"""
    mock_model = MagicMock()
    mock_model.id = 10

    mock_repository.find_image_ids_by_phashes.return_value = {"phash001": 1, "phash002": 2}
    mock_repository.get_models_by_litellm_ids.return_value = {"wdtagger": mock_model}
    mock_repository.batch_resolve_tag_ids.return_value = {}

    results = {
        "phash001": {"wdtagger": _make_success_result(tags=["tag1", "tag2"])},
        "phash002": {"wdtagger": _make_success_result(tags=["tag1"])},
    }

    result = service.save_annotation_results(results)

    assert result.success_count == 2
    assert result.skip_count == 0
    assert result.error_count == 0
    assert result.total_count == 2
    assert mock_repository.save_annotations.call_count == 2


@pytest.mark.unit
def test_save_annotation_results_with_unknown_phash_skips_silently(
    service: AnnotationSaveService,
    mock_repository: MagicMock,
) -> None:
    """DBに存在しないphashはスキップして処理を継続する。"""
    mock_repository.find_image_ids_by_phashes.return_value = {}

    results = {
        "unknown_phash": {"wdtagger": _make_success_result(tags=["tag1"])},
    }

    result = service.save_annotation_results(results)

    assert result.success_count == 0
    assert result.skip_count == 1
    assert result.error_count == 0
    assert result.total_count == 1
    mock_repository.save_annotations.assert_not_called()


@pytest.mark.unit
def test_save_annotation_results_handles_partial_save_failure(
    service: AnnotationSaveService,
    mock_repository: MagicMock,
) -> None:
    """save_annotations 例外発生時はエラー件数に集計して処理を継続する。"""
    mock_model = MagicMock()
    mock_model.id = 1
    mock_repository.find_image_ids_by_phashes.return_value = {"phash001": 1}
    mock_repository.get_models_by_litellm_ids.return_value = {"wdtagger": mock_model}
    mock_repository.save_annotations.side_effect = RuntimeError("DB write error")

    results = {
        "phash001": {"wdtagger": _make_success_result(tags=["tag1"])},
    }

    result = service.save_annotation_results(results)

    assert result.success_count == 0
    assert result.error_count == 1
    assert result.skip_count == 0
    assert len(result.error_details) == 1
    assert "phash001" in result.error_details[0]


@pytest.mark.unit
def test_save_annotation_results_uses_batch_resolution(
    service: AnnotationSaveService,
    mock_repository: MagicMock,
) -> None:
    """N+1を避けるため、find_image_ids_by_phashesとget_models_by_litellm_idsを各1回のみ呼ぶ。"""
    mock_model = MagicMock()
    mock_model.id = 1
    mock_repository.find_image_ids_by_phashes.return_value = {
        "phash001": 1,
        "phash002": 2,
        "phash003": 3,
    }
    mock_repository.get_models_by_litellm_ids.return_value = {"wdtagger": mock_model}
    mock_repository.batch_resolve_tag_ids.return_value = {}

    results = {
        "phash001": {"wdtagger": _make_success_result(tags=["tag1"])},
        "phash002": {"wdtagger": _make_success_result(tags=["tag2"])},
        "phash003": {"wdtagger": _make_success_result(tags=["tag3"])},
    }

    service.save_annotation_results(results)

    mock_repository.find_image_ids_by_phashes.assert_called_once()
    mock_repository.get_models_by_litellm_ids.assert_called_once()


# ===== Issue #281 / ADR 0027: score_labels persistence =====


@pytest.mark.unit
def test_save_canonical_scorer_persists_score_labels(
    service: AnnotationSaveService,
    mock_repository: MagicMock,
) -> None:
    """canonical scorer (aesthetic_shadow 等) の score_labels が save_annotations に渡される。"""
    mock_model = MagicMock()
    mock_model.id = 42
    mock_repository.find_image_ids_by_phashes.return_value = {"phash001": 1}
    mock_repository.get_models_by_litellm_ids.return_value = {"aesthetic_shadow_v2": mock_model}

    results = {
        "phash001": {
            "aesthetic_shadow_v2": _make_success_result(
                scores={"hq": 0.85, "lq": 0.15},
                score_labels=["very aesthetic"],
            )
        },
    }

    service.save_annotation_results(results)

    # save_annotations 呼び出し時の annotations dict に score_labels が積まれている
    assert mock_repository.save_annotations.called
    image_id_arg = mock_repository.save_annotations.call_args[0][0]
    annotations_arg = mock_repository.save_annotations.call_args[0][1]
    assert image_id_arg == 1
    assert annotations_arg["score_labels"] == [
        {"model_id": 42, "label": "very aesthetic", "is_edited_manually": False}
    ]
    # ADR 0002 / 0027: canonical scorer は tags=None / scores は dict のまま流す
    assert annotations_arg["scores"] == [
        {"model_id": 42, "score": 0.85, "is_edited_manually": False},
        {"model_id": 42, "score": 0.15, "is_edited_manually": False},
    ]


@pytest.mark.unit
def test_save_regression_scorer_no_score_labels(
    service: AnnotationSaveService,
    mock_repository: MagicMock,
) -> None:
    """regression scorer (ImprovedAesthetic 等) は score_labels=None で empty list が渡る。"""
    mock_model = MagicMock()
    mock_model.id = 7
    mock_repository.find_image_ids_by_phashes.return_value = {"phash001": 1}
    mock_repository.get_models_by_litellm_ids.return_value = {"ImprovedAesthetic": mock_model}

    results = {
        "phash001": {
            "ImprovedAesthetic": _make_success_result(
                scores={"aesthetic": 7.5},
                score_labels=None,
            )
        },
    }

    service.save_annotation_results(results)

    annotations_arg = mock_repository.save_annotations.call_args[0][1]
    assert annotations_arg["score_labels"] == []
    assert annotations_arg["scores"] == [{"model_id": 7, "score": 7.5, "is_edited_manually": False}]


@pytest.mark.unit
def test_save_multiple_labels_per_model(
    service: AnnotationSaveService,
    mock_repository: MagicMock,
) -> None:
    """score_labels=['a', 'b'] で 2 row が積まれる (将来拡張対応)。"""
    mock_model = MagicMock()
    mock_model.id = 99
    mock_repository.find_image_ids_by_phashes.return_value = {"phash001": 1}
    mock_repository.get_models_by_litellm_ids.return_value = {"future_scorer": mock_model}

    results = {
        "phash001": {
            "future_scorer": _make_success_result(
                scores={"primary": 0.8},
                score_labels=["aesthetic", "high_quality"],
            )
        },
    }

    service.save_annotation_results(results)

    annotations_arg = mock_repository.save_annotations.call_args[0][1]
    assert annotations_arg["score_labels"] == [
        {"model_id": 99, "label": "aesthetic", "is_edited_manually": False},
        {"model_id": 99, "label": "high_quality", "is_edited_manually": False},
    ]


@pytest.mark.unit
def test_save_score_labels_skipped_when_error_present(
    service: AnnotationSaveService,
    mock_repository: MagicMock,
) -> None:
    """error ありの result は score_labels も含めて save_annotations が呼ばれない。"""
    mock_model = MagicMock()
    mock_model.id = 1
    mock_repository.find_image_ids_by_phashes.return_value = {"phash001": 1}
    mock_repository.get_models_by_litellm_ids.return_value = {"aesthetic_shadow_v2": mock_model}

    error_result = MagicMock()
    error_result.error = "ModelLoadError: GPU OOM"
    error_result.tags = None
    error_result.captions = None
    error_result.scores = None
    error_result.score_labels = ["very aesthetic"]
    error_result.ratings = None

    results = {"phash001": {"aesthetic_shadow_v2": error_result}}

    service.save_annotation_results(results)

    # error 検出時は _save_single 内で空 dict 判定で skip され save_annotations は呼ばれない
    mock_repository.save_annotations.assert_not_called()
