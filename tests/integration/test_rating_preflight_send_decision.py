"""rating preflight 送信判定（WebAPI/Annotation 事前判定）統合テスト。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from lorairo.database.repository.annotation_record import AnnotationRepository
from lorairo.database.repository.image import ImageRepository
from lorairo.database.schema import Model, Rating
from lorairo.services.annotation_save_service import AnnotationSaveService


@pytest.fixture
def annotation_service(db_session_factory) -> AnnotationSaveService:
    """AnnotationSaveService with 本物の ImageRepository を使った fixture。"""
    annotation_repo = AnnotationRepository(db_session_factory)
    image_repo = ImageRepository(db_session_factory)
    return AnnotationSaveService(annotation_repo=annotation_repo, image_repo=image_repo)


@pytest.fixture
def sample_image(tmp_path: Path, db_session_factory) -> tuple[ImageRepository, int, str]:
    """テスト用画像 1 件を登録して返す。"""
    repository = ImageRepository(db_session_factory)
    image_id, _ = repository.add_original_image(
        {
            "uuid": str(uuid4()),
            "phash": "rating-preflight-phash-001",
            "original_image_path": str(tmp_path / "sample.png"),
            "stored_image_path": str(tmp_path / "sample.png"),
            "filename": "sample.png",
            "width": 64,
            "height": 64,
            "format": "PNG",
            "extension": ".png",
            "has_alpha": False,
        }
    )
    return repository, image_id, str(tmp_path / "sample.png")


def _insert_model_and_ratings(
    db_session_factory, image_id: int, model_name: str, rows: list[tuple[str, datetime]]
) -> int:
    """image_id に対して normalized_rating 履歴を時系列順で投入し、model_id を返す。"""
    with db_session_factory() as session:
        model = session.query(Model).filter_by(litellm_model_id=model_name).first()
        if model is None:
            model = Model(
                name=model_name,
                litellm_model_id=model_name,
                provider="openai",
            )
            session.add(model)
            session.flush()

        for raw_rating, created_at in rows:
            session.add(
                Rating(
                    image_id=image_id,
                    model_id=model.id,
                    raw_rating_value=raw_rating,
                    normalized_rating=raw_rating,
                    confidence_score=0.75,
                    created_at=created_at,
                    updated_at=created_at,
                )
            )
        session.commit()
        return model.id


@pytest.mark.integration
def test_filter_excluded_by_rating_uses_latest_rating_row(
    annotation_service: AnnotationSaveService, sample_image: tuple[ImageRepository, int, str]
) -> None:
    """複数履歴がある場合は最新 created_at の rating を採用して判定する。"""
    repository, image_id, image_path = sample_image
    now = datetime(2026, 5, 27, 12, 0, 0, tzinfo=UTC)
    _insert_model_and_ratings(
        repository.session_factory,
        image_id,
        "openai/gpt-4o-mini",
        [
            ("PG", now),
            ("XXX", now + timedelta(minutes=5)),
        ],
    )

    assert annotation_service.filter_excluded_by_rating([image_path]) == []


@pytest.mark.integration
def test_filter_excluded_by_rating_allows_safe_rating_values(
    annotation_service: AnnotationSaveService, sample_image: tuple[ImageRepository, int, str]
) -> None:
    """PG / PG-13 / R / UNRATED / None は送信可である。"""
    repository, image_id, image_path = sample_image
    now = datetime(2026, 5, 27, 12, 0, 0, tzinfo=UTC)
    _insert_model_and_ratings(
        repository.session_factory,
        image_id,
        "openai/gpt-4o-mini",
        [
            ("R", now),
            ("UNRATED", now + timedelta(minutes=3)),
        ],
    )

    assert annotation_service.filter_excluded_by_rating([image_path]) == [image_path]


@pytest.mark.integration
def test_filter_excluded_by_rating_unknown_path_passes_through(
    annotation_service: AnnotationSaveService,
) -> None:
    """DB 未登録 path は prefilter で通過する。"""
    assert annotation_service.filter_excluded_by_rating(["/not/registerd/sample.png"]) == [
        "/not/registerd/sample.png"
    ]
