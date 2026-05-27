"""`filter_excluded_by_rating` の Unit テスト。"""

from unittest.mock import MagicMock

import pytest

from lorairo.services.annotation_save_service import AnnotationSaveService


@pytest.fixture
def mock_repository() -> MagicMock:
    """Repository mock (ImageRepository + 依存を stub）。"""
    repo = MagicMock()
    return repo


@pytest.fixture
def service(mock_repository: MagicMock) -> AnnotationSaveService:
    """テスト対象サービス。"""
    return AnnotationSaveService(
        annotation_repo=mock_repository,
        image_repo=mock_repository,
        model_repo=mock_repository,
        error_record_repo=mock_repository,
    )


@pytest.mark.unit
def test_filter_excluded_by_rating_excludes_x_and_xxx(
    service: AnnotationSaveService, mock_repository: MagicMock
) -> None:
    """X / XXX は除外される。"""
    mock_repository.get_image_ids_by_filepaths.return_value = {
        "/img/a.png": 1,
        "/img/b.png": 2,
        "/img/c.png": 3,
        "/img/d.png": 4,
    }
    mock_repository.get_latest_normalized_ratings_by_image_ids.return_value = {
        1: "PG",
        2: "X",
        3: "XXX",
        4: None,
    }

    assert service.filter_excluded_by_rating(["/img/a.png", "/img/b.png", "/img/c.png", "/img/d.png"]) == [
        "/img/a.png",
        "/img/d.png",
    ]
    mock_repository.get_latest_normalized_ratings_by_image_ids.assert_called_once()


@pytest.mark.unit
def test_filter_excluded_by_rating_allows_safe_levels(
    service: AnnotationSaveService, mock_repository: MagicMock
) -> None:
    """PG / PG-13 / R / UNRATED / None は通過する。"""
    mock_repository.get_image_ids_by_filepaths.return_value = {
        "/img/a.png": 10,
        "/img/b.png": 11,
        "/img/c.png": 12,
        "/img/d.png": 13,
        "/img/e.png": 14,
    }
    mock_repository.get_latest_normalized_ratings_by_image_ids.return_value = {
        10: "PG",
        11: "PG-13",
        12: "R",
        13: "UNRATED",
        14: None,
    }

    assert service.filter_excluded_by_rating(
        ["/img/a.png", "/img/b.png", "/img/c.png", "/img/d.png", "/img/e.png"]
    ) == ["/img/a.png", "/img/b.png", "/img/c.png", "/img/d.png", "/img/e.png"]


@pytest.mark.unit
def test_filter_excluded_by_rating_keeps_unknown_paths(
    service: AnnotationSaveService, mock_repository: MagicMock
) -> None:
    """DB 未登録 path はそのまま通過する。"""
    mock_repository.get_image_ids_by_filepaths.return_value = {
        "/img/missing.png": None,
    }
    mock_repository.get_latest_normalized_ratings_by_image_ids.return_value = {}

    assert service.filter_excluded_by_rating(["/img/missing.png"]) == ["/img/missing.png"]
    mock_repository.get_latest_normalized_ratings_by_image_ids.assert_not_called()


@pytest.mark.unit
def test_filter_excluded_by_rating_empty_input_returns_empty(service: AnnotationSaveService) -> None:
    """空入力は空で返る。"""
    assert service.filter_excluded_by_rating([]) == []
