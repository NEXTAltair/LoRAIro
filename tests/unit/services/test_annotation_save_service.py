"""AnnotationSaveService ユニットテスト。"""

from unittest.mock import MagicMock

import pytest

from lorairo.services.annotation_save_service import AnnotationSaveResult, AnnotationSaveService


@pytest.fixture
def mock_repository() -> MagicMock:
    """モック ImageRepository。"""
    repo = MagicMock()
    repo.find_image_ids_by_phashes.return_value = {}
    repo.get_models_by_names.return_value = {}
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
) -> MagicMock:
    """正常系 UnifiedAnnotationResult モックを生成する。"""
    result = MagicMock()
    result.error = None
    result.tags = tags or []
    result.captions = captions or []
    result.scores = scores
    result.ratings = None
    result.formatted_output = None
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
    mock_repository.get_models_by_names.return_value = {"wdtagger": mock_model}
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
    mock_repository.get_models_by_names.return_value = {"wdtagger": mock_model}
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
    """N+1を避けるため、find_image_ids_by_phashesとget_models_by_namesを各1回のみ呼ぶ。"""
    mock_model = MagicMock()
    mock_model.id = 1
    mock_repository.find_image_ids_by_phashes.return_value = {
        "phash001": 1,
        "phash002": 2,
        "phash003": 3,
    }
    mock_repository.get_models_by_names.return_value = {"wdtagger": mock_model}
    mock_repository.batch_resolve_tag_ids.return_value = {}

    results = {
        "phash001": {"wdtagger": _make_success_result(tags=["tag1"])},
        "phash002": {"wdtagger": _make_success_result(tags=["tag2"])},
        "phash003": {"wdtagger": _make_success_result(tags=["tag3"])},
    }

    service.save_annotation_results(results)

    mock_repository.find_image_ids_by_phashes.assert_called_once()
    mock_repository.get_models_by_names.assert_called_once()
