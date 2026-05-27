"""アノテーション結果保存・安全性拒否ハンドリングの BDD ステップ定義。

AnnotationSaveService の振る舞いを Gherkin で仕様化する。
WebAPI / image-annotator-lib 推論は呼ばず、推論結果 dict を直接組み立てる。
refusal は型 import せず error 文字列の prefix で表現する。
"""

import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from PIL import Image
from pytest_bdd import given, parsers, scenarios, then, when
from sqlalchemy.orm import sessionmaker

from lorairo.database.repository.annotation_record import AnnotationRepository
from lorairo.database.repository.image import ImageRepository
from lorairo.services.annotation_save_service import (
    AnnotationSaveResult,
    AnnotationSaveService,
)

_FEATURE_FILE = Path(__file__).parent.parent / "features" / "annotation_result_save.feature"
scenarios(str(_FEATURE_FILE))


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


@dataclass
class SaveContext:
    """ステップ間で受け渡す保存処理の状態。"""

    repo: ImageRepository | None = None
    mock_repository: MagicMock | None = None
    save_service: AnnotationSaveService | None = None
    image_id: int | None = None
    image_path: str | None = None
    annotations_dict: dict[str, Any] = field(default_factory=dict)
    filtered_paths: list[str] = field(default_factory=list)
    save_result: AnnotationSaveResult | None = None
    inference_results: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Given
# ---------------------------------------------------------------------------


@given("DB に登録済みの画像が 1 件ある", target_fixture="ctx")
def given_registered_image(test_engine_with_schema, tmp_path: Path) -> SaveContext:
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=test_engine_with_schema)
    repo = ImageRepository(session_local)

    img = Image.new("RGB", (16, 16), color="red")
    file_path = tmp_path / "sample.png"
    img.save(file_path)

    info = {
        "uuid": "bdd-refusal-uuid-1",
        "phash": "phash_bdd_refusal_1",
        "original_image_path": str(file_path),
        "stored_image_path": str(file_path),
        "width": 16,
        "height": 16,
        "format": "PNG",
        "mode": "RGB",
        "has_alpha": False,
        "filename": "sample.png",
        "extension": ".png",
        "color_space": "RGB",
        "icc_profile": None,
    }
    image_id = repo.add_original_image(info)
    return SaveContext(repo=repo, image_id=image_id, image_path=str(file_path))


@given("AnnotationSaveService が初期化されている")
def given_save_service_initialized(ctx: SaveContext) -> None:
    assert ctx.repo is not None
    ctx.save_service = AnnotationSaveService(
        AnnotationRepository(ctx.repo.session_factory),
        image_repo=ctx.repo,
    )


@given("AnnotationSaveService がモックリポジトリで初期化されている", target_fixture="ctx")
def given_save_service_mock_repo() -> SaveContext:
    repo = MagicMock()
    repo.find_image_ids_by_phashes.return_value = {}
    repo.get_models_by_litellm_ids.return_value = {}
    repo.batch_resolve_tag_ids.return_value = {}
    return SaveContext(
        mock_repository=repo,
        save_service=AnnotationSaveService(
            repo,
            image_repo=repo,
            model_repo=repo,
            error_record_repo=repo,
        ),
    )


@given("その画像に未解決の安全性拒否履歴がある")
def given_unresolved_refusal(ctx: SaveContext) -> None:
    assert ctx.repo is not None and ctx.image_id is not None
    ctx.repo.save_error_record(
        operation_type="annotation",
        error_type="SafetyRefusalError",
        error_message="blocked",
        image_id=ctx.image_id,
        model_name="openai/gpt-4o",
    )


@given("その画像に解決済みの安全性拒否履歴がある")
def given_resolved_refusal(ctx: SaveContext) -> None:
    assert ctx.repo is not None and ctx.image_id is not None
    error_id = ctx.repo.save_error_record(
        operation_type="annotation",
        error_type="SafetyRefusalError",
        error_message="blocked",
        image_id=ctx.image_id,
        model_name="openai/gpt-4o",
    )
    with ctx.repo.session_factory() as session:
        from lorairo.database.schema import ErrorRecord

        record = session.get(ErrorRecord, error_id)
        record.resolved_at = datetime.datetime.now(datetime.UTC)
        session.commit()


@given("DB に存在する phash が 2 件、存在しない phash が 1 件ある")
def given_mixed_phashes(ctx: SaveContext) -> None:
    assert ctx.mock_repository is not None
    mock_model = MagicMock()
    mock_model.id = 10
    ctx.mock_repository.find_image_ids_by_phashes.return_value = {
        "phash_known_1": 1,
        "phash_known_2": 2,
    }
    ctx.mock_repository.get_models_by_litellm_ids.return_value = {"wdtagger": mock_model}
    ctx.inference_results = {
        "phash_known_1": {"wdtagger": _make_success_result(tags=["tag1", "tag2"])},
        "phash_known_2": {"wdtagger": _make_success_result(tags=["tag1"])},
        "phash_unknown": {"wdtagger": _make_success_result(tags=["tag3"])},
    }


def _make_success_result(tags: list[str]) -> MagicMock:
    """正常系 UnifiedAnnotationResult モックを生成する。"""
    result = MagicMock()
    result.error = None
    result.tags = tags
    result.captions = []
    result.scores = None
    result.score_labels = None
    result.ratings = None
    return result


# ---------------------------------------------------------------------------
# When
# ---------------------------------------------------------------------------


@when(parsers.parse('その画像に対し "{error_string}" の結果を処理する'))
def when_process_refusal_result(ctx: SaveContext, error_string: str) -> None:
    assert ctx.save_service is not None and ctx.image_id is not None
    ctx.annotations_dict = {"scores": [], "tags": [], "captions": [], "ratings": []}
    ctx.save_service._process_model_result(
        model_name="openai/gpt-4o",
        unified_result={"error": error_string},
        models_cache={},
        result=ctx.annotations_dict,
        image_id=ctx.image_id,
    )


@when("その画像パスを WebAPI 送信前フィルタにかける")
def when_filter_paths(ctx: SaveContext) -> None:
    assert ctx.save_service is not None and ctx.image_path is not None
    ctx.filtered_paths = ctx.save_service.filter_refused_image_paths([ctx.image_path])


@when("3 件の推論結果を保存する")
def when_save_results(ctx: SaveContext) -> None:
    assert ctx.save_service is not None
    ctx.save_result = ctx.save_service.save_annotation_results(ctx.inference_results)


# ---------------------------------------------------------------------------
# Then
# ---------------------------------------------------------------------------


@then(parsers.parse('エラーレコードに 1 件の "{error_type}" が記録される'))
def then_error_record_recorded(ctx: SaveContext, error_type: str) -> None:
    assert ctx.repo is not None
    records = ctx.repo.get_error_records(operation_type="annotation")
    assert len(records) == 1
    record = records[0]
    assert record.error_type == error_type
    assert record.image_id == ctx.image_id
    assert record.resolved_at is None


@then("アノテーションは保存されない")
def then_no_annotation_saved(ctx: SaveContext) -> None:
    assert not any(ctx.annotations_dict.values())


@then("フィルタ結果は空である")
def then_filter_empty(ctx: SaveContext) -> None:
    assert ctx.filtered_paths == []


@then("フィルタ結果にその画像パスが含まれる")
def then_filter_contains_path(ctx: SaveContext) -> None:
    assert ctx.image_path in ctx.filtered_paths


@then(
    parsers.parse(
        "保存結果は成功 {success:d} 件・スキップ {skip:d} 件・エラー {error:d} 件・合計 {total:d} 件である"
    )
)
def then_save_result_aggregation(ctx: SaveContext, success: int, skip: int, error: int, total: int) -> None:
    assert ctx.save_result is not None
    assert ctx.save_result.success_count == success
    assert ctx.save_result.skip_count == skip
    assert ctx.save_result.error_count == error
    assert ctx.save_result.total_count == total
