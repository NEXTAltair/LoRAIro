"""AI rating 保存・検索フィルタの統合テスト (Issue #333)。

AnnotationSaveService → rating_mapper → ImageRepository → DB → AI rating filter
の end-to-end フローを実 SQLite (in-memory) で検証する。
"""

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from lorairo.database.filter_criteria import ImageFilterCriteria
from lorairo.database.repository.annotation_record import AnnotationRepository
from lorairo.database.repository.image import ImageRepository
from lorairo.database.schema import Caption, Image, Model, Rating, Score, ScoreLabel, Tag
from lorairo.services.annotation_save_service import AnnotationSaveService

_PHASH = "phash_rating_test_001"
_LITELLM_ID = "wd-vit-tagger-v3"


@pytest.fixture
def rating_repository(db_session_factory) -> ImageRepository:
    """session_factory ベースの ImageRepository (get_images_by_filter 等が動作する)。"""
    return ImageRepository(db_session_factory)


@pytest.fixture
def annotation_repository(db_session_factory) -> AnnotationRepository:
    """session_factory ベースの AnnotationRepository。"""
    return AnnotationRepository(db_session_factory)


@pytest.fixture
def seeded_ids(db_session_factory) -> dict[str, int]:
    """rating テスト用に Image 1 件と AI Model 1 件を投入する。"""
    with db_session_factory() as session:
        image = Image(
            uuid="rating-test-uuid-001",
            phash=_PHASH,
            original_image_path="/tmp/rating_test.png",
            stored_image_path="/tmp/rating_test.png",
            width=256,
            height=256,
            format="PNG",
            extension=".png",
        )
        model = Model(name="wd-vit-tagger-v3", provider="local", litellm_model_id=_LITELLM_ID)
        session.add_all([image, model])
        session.commit()
        return {"image_id": image.id, "model_id": model.id}


def _result_with_rating(raw_label: str, source_scheme: str, confidence: float) -> SimpleNamespace:
    """ratings のみを持つ UnifiedAnnotationResult 相当のテストダブル。"""
    return SimpleNamespace(
        error=None,
        tags=None,
        captions=None,
        scores=None,
        score_labels=None,
        ratings=[
            SimpleNamespace(raw_label=raw_label, source_scheme=source_scheme, confidence_score=confidence)
        ],
    )


@pytest.mark.integration
def test_structured_rating_persisted_with_canonical_value(
    rating_repository: ImageRepository,
    annotation_repository: AnnotationRepository,
    seeded_ids: dict[str, int],
    db_session_factory,
) -> None:
    """model-native rating が canonical 値で ratings テーブルへ保存される。"""
    service = AnnotationSaveService(annotation_repository, image_repo=rating_repository)

    results = {_PHASH: {_LITELLM_ID: _result_with_rating("questionable", "danbooru4", 0.83)}}
    save_result = service.save_annotation_results(results)

    assert save_result.success_count == 1
    assert save_result.error_count == 0

    with db_session_factory() as session:
        rating = session.execute(
            select(Rating).where(Rating.image_id == seeded_ids["image_id"])
        ).scalar_one()
        assert rating.raw_rating_value == "questionable"
        assert rating.normalized_rating == "R"
        assert rating.confidence_score == pytest.approx(0.83)


@pytest.mark.integration
def test_saved_ai_rating_excluded_from_unrated_and_matched_by_value(
    rating_repository: ImageRepository,
    annotation_repository: AnnotationRepository,
    seeded_ids: dict[str, int],
) -> None:
    """保存後の画像が AI rating UNRATED から外れ、該当 rating 検索でヒットする。"""
    service = AnnotationSaveService(annotation_repository, image_repo=rating_repository)
    service.save_annotation_results(
        {_PHASH: {_LITELLM_ID: _result_with_rating("questionable", "danbooru4", 0.83)}}
    )

    # 保存前は対象だった「AIレーティング: 未設定のみ」から外れる
    unrated_images, unrated_count = rating_repository.get_images_by_filter(
        ImageFilterCriteria(ai_rating_filter="UNRATED")
    )
    assert unrated_count == 0
    assert unrated_images == []

    # canonical 値 "R" で検索するとヒットする
    matched_images, matched_count = rating_repository.get_images_by_filter(
        ImageFilterCriteria(ai_rating_filter="R")
    )
    assert matched_count == 1
    assert matched_images[0]["id"] == seeded_ids["image_id"]


@pytest.mark.integration
def test_only_unrated_filter_returns_images_without_any_rating(
    rating_repository: ImageRepository,
    seeded_ids: dict[str, int],
    db_session_factory,
) -> None:
    """only_unrated=True は Rating 行が無い画像のみを返す。"""
    with db_session_factory() as session:
        rated_image_id = seeded_ids["image_id"]
        unrated_image = Image(
            uuid="rating-test-uuid-002",
            phash="phash_rating_test_002",
            original_image_path="/tmp/rating_test_2.png",
            stored_image_path="/tmp/rating_test_2.png",
            width=256,
            height=256,
            format="PNG",
            extension=".png",
        )
        session.add(unrated_image)
        session.flush()
        session.add(
            Rating(
                image_id=rated_image_id,
                model_id=seeded_ids["model_id"],
                raw_rating_value="general",
                normalized_rating="PG",
                confidence_score=0.9,
            )
        )
        session.commit()
        unrated_image_id = unrated_image.id

    unrated_images, unrated_count = rating_repository.get_images_by_filter(
        ImageFilterCriteria(include_nsfw=True, only_unrated=True)
    )
    rated_images, rated_count = rating_repository.get_images_by_filter(
        ImageFilterCriteria(include_nsfw=True, include_unrated=False)
    )
    precedence_images, precedence_count = rating_repository.get_images_by_filter(
        ImageFilterCriteria(include_nsfw=True, include_unrated=False, only_unrated=True)
    )

    assert unrated_count == 1
    assert unrated_images[0]["id"] == unrated_image_id
    assert rated_count == 1
    assert rated_images[0]["id"] == rated_image_id
    assert precedence_count == 1
    assert precedence_images[0]["id"] == unrated_image_id


@pytest.mark.integration
def test_missing_model_filter_excludes_any_annotation_type_for_model(
    rating_repository: ImageRepository,
    seeded_ids: dict[str, int],
    db_session_factory,
) -> None:
    """missing_model_litellm_id は指定モデルの全annotation種別を処理済み扱いにする。"""
    with db_session_factory() as session:
        images: list[Image] = []
        for index in range(6):
            image = Image(
                uuid=f"missing-model-test-uuid-{index}",
                phash=f"phash_missing_model_{index:03d}",
                original_image_path=f"/tmp/missing_model_{index}.png",
                stored_image_path=f"/tmp/missing_model_{index}.png",
                width=256,
                height=256,
                format="PNG",
                extension=".png",
            )
            session.add(image)
            images.append(image)
        session.flush()

        model_id = seeded_ids["model_id"]
        session.add_all(
            [
                Tag(image_id=images[0].id, model_id=model_id, tag="tagged"),
                Caption(image_id=images[1].id, model_id=model_id, caption="captioned"),
                Score(image_id=images[2].id, model_id=model_id, score=0.8),
                ScoreLabel(image_id=images[3].id, model_id=model_id, label="aesthetic"),
                Rating(
                    image_id=images[4].id,
                    model_id=model_id,
                    raw_rating_value="general",
                    normalized_rating="PG",
                    confidence_score=0.9,
                ),
            ]
        )
        session.commit()
        missing_image_id = images[5].id

    missing_images, missing_count = rating_repository.get_images_by_filter(
        ImageFilterCriteria(include_nsfw=True, missing_model_litellm_id=_LITELLM_ID)
    )

    assert missing_count == 2
    assert {image["id"] for image in missing_images} == {seeded_ids["image_id"], missing_image_id}


@pytest.mark.integration
def test_missing_model_filter_combines_with_only_unrated(
    rating_repository: ImageRepository,
    seeded_ids: dict[str, int],
    db_session_factory,
) -> None:
    """missing_model_litellm_id と only_unrated=True は AND 条件で絞り込む。"""
    with db_session_factory() as session:
        rated_without_target_model = Image(
            uuid="missing-model-rated-uuid",
            phash="phash_missing_model_rated",
            original_image_path="/tmp/missing_model_rated.png",
            stored_image_path="/tmp/missing_model_rated.png",
            width=256,
            height=256,
            format="PNG",
            extension=".png",
        )
        unrated_without_target_model = Image(
            uuid="missing-model-unrated-uuid",
            phash="phash_missing_model_unrated",
            original_image_path="/tmp/missing_model_unrated.png",
            stored_image_path="/tmp/missing_model_unrated.png",
            width=256,
            height=256,
            format="PNG",
            extension=".png",
        )
        other_model = Model(
            name="openai/gpt-4o-mini",
            provider="openai",
            litellm_model_id="openai/gpt-4o-mini",
        )
        session.add_all([rated_without_target_model, unrated_without_target_model, other_model])
        session.flush()
        session.add(
            Rating(
                image_id=rated_without_target_model.id,
                model_id=other_model.id,
                raw_rating_value="general",
                normalized_rating="PG",
                confidence_score=0.9,
            )
        )
        session.commit()
        unrated_without_target_model_id = unrated_without_target_model.id

    missing_unrated_images, missing_unrated_count = rating_repository.get_images_by_filter(
        ImageFilterCriteria(
            include_nsfw=True,
            only_unrated=True,
            missing_model_litellm_id=_LITELLM_ID,
        )
    )

    assert missing_unrated_count == 2
    assert {image["id"] for image in missing_unrated_images} == {
        seeded_ids["image_id"],
        unrated_without_target_model_id,
    }


@pytest.mark.integration
def test_unmappable_scheme_is_skipped(
    rating_repository: ImageRepository,
    annotation_repository: AnnotationRepository,
    seeded_ids: dict[str, int],
    db_session_factory,
) -> None:
    """未知 source_scheme の rating は保存されず、AI rating UNRATED のままになる。"""
    service = AnnotationSaveService(annotation_repository, image_repo=rating_repository)
    service.save_annotation_results({_PHASH: {_LITELLM_ID: _result_with_rating("general", "unknown", 0.9)}})

    with db_session_factory() as session:
        ratings = (
            session.execute(select(Rating).where(Rating.image_id == seeded_ids["image_id"])).scalars().all()
        )
        assert ratings == []

    _, unrated_count = rating_repository.get_images_by_filter(
        ImageFilterCriteria(ai_rating_filter="UNRATED")
    )
    assert unrated_count == 1


@pytest.mark.integration
def test_manual_rating_isolated_from_ai_rating(
    rating_repository: ImageRepository,
    annotation_repository: AnnotationRepository,
    seeded_ids: dict[str, int],
) -> None:
    """manual rating (MANUAL_EDIT) が共存しても AI rating フィルタは AI 行のみ対象とする。

    AI / manual とも非 NSFW 値 (PG / PG-13) を使い、NSFW 除外フィルタの影響を避ける。
    """
    service = AnnotationSaveService(annotation_repository, image_repo=rating_repository)
    # AI rating は "PG" (general -> PG)
    service.save_annotation_results(
        {_PHASH: {_LITELLM_ID: _result_with_rating("general", "danbooru4", 0.7)}}
    )
    # 同じ画像に AI とは異なる手動 rating "PG-13" を付与 (MANUAL_EDIT モデル行)
    annotation_repository.update_manual_rating(seeded_ids["image_id"], "PG-13")

    # AI rating フィルタ "PG" は AI 行のみ対象 -> ヒットする
    pg_images, pg_count = rating_repository.get_images_by_filter(ImageFilterCriteria(ai_rating_filter="PG"))
    assert pg_count == 1
    assert pg_images[0]["id"] == seeded_ids["image_id"]

    # AI rating フィルタ "PG-13" は manual の "PG-13" に引きずられず 0 件 (AI 行に PG-13 は無い)
    _, ai_pg13_count = rating_repository.get_images_by_filter(ImageFilterCriteria(ai_rating_filter="PG-13"))
    assert ai_pg13_count == 0

    # 手動 rating フィルタ "PG-13" はヒットする
    _, manual_count = rating_repository.get_images_by_filter(
        ImageFilterCriteria(manual_rating_filter="PG-13")
    )
    assert manual_count == 1
