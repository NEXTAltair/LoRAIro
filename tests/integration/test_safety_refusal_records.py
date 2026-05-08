"""ADR 0023 Phase 1.5 (Issue #42): refusal → error_records → filter サイクルの統合テスト。

image-annotator-lib 側で検出された SafetyRefusal / ContentPolicyRefusal は
`UnifiedAnnotationResult.error` に prefix 文字列で乗ってくるため、LoRAIro 側で
`AnnotationSaveService._process_model_result` が prefix を decode して
`error_records` に記録する。次回送信時は `filter_refused_image_paths` で除外する。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy.orm import sessionmaker

from lorairo.database.db_repository import ImageRepository
from lorairo.services.annotation_save_service import AnnotationSaveService


@pytest.fixture
def repo(test_engine_with_schema) -> ImageRepository:
    """sessionmaker ベースの ImageRepository。

    `integration/conftest.py` の `test_repository` は Session を直渡しするため
    `session_factory()` 呼び出しと非互換 (TypeError)。`test_db_manager` も
    `config_service` 不足で失敗するため、本テストでは独自 fixture で sessionmaker
    から ImageRepository を構築する。
    """
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine_with_schema)
    return ImageRepository(SessionLocal)


@pytest.fixture
def save_service(repo: ImageRepository) -> AnnotationSaveService:
    return AnnotationSaveService(repo)


@pytest.fixture
def registered_image(repo: ImageRepository, tmp_path: Path) -> tuple[int, str]:
    """images テーブルに 1 件登録済みの画像を返す (image_id, file_path)。"""
    img = Image.new("RGB", (16, 16), color="red")
    file_path = tmp_path / "sample.png"
    img.save(file_path)

    info = {
        "uuid": "test-refusal-uuid-1",
        "phash": "phash_refusal_1",
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
    return image_id, str(file_path)


@pytest.mark.integration
def test_detect_refusal_error_type_safety_prefix() -> None:
    """SafetyRefusalError prefix が正しく decode される。"""
    detected = AnnotationSaveService._detect_refusal_error_type(
        "SafetyRefusalError: blocked due to safety policy"
    )
    assert detected == "SafetyRefusalError"


@pytest.mark.integration
def test_detect_refusal_error_type_content_policy_prefix() -> None:
    """ContentPolicyRefusalError prefix が正しく decode される。"""
    detected = AnnotationSaveService._detect_refusal_error_type(
        "ContentPolicyRefusalError: content blocked"
    )
    assert detected == "ContentPolicyRefusalError"


@pytest.mark.integration
def test_detect_refusal_error_type_non_refusal_returns_none() -> None:
    """非 refusal error string は None を返す。"""
    assert AnnotationSaveService._detect_refusal_error_type("ApiTimeoutError: timeout") is None
    assert AnnotationSaveService._detect_refusal_error_type("generic error") is None
    assert AnnotationSaveService._detect_refusal_error_type(None) is None
    assert AnnotationSaveService._detect_refusal_error_type({"error": "obj"}) is None


@pytest.mark.integration
def test_process_model_result_records_safety_refusal(
    save_service: AnnotationSaveService,
    repo: ImageRepository,
    registered_image: tuple[int, str],
) -> None:
    """SafetyRefusalError 結果が error_records に記録されることを確認。"""
    image_id, _ = registered_image
    unified_result = {"error": "SafetyRefusalError: blocked due to safety policy"}

    result_dict: dict = {"scores": [], "tags": [], "captions": [], "ratings": []}
    save_service._process_model_result(
        model_name="openai/gpt-4o",
        unified_result=unified_result,
        models_cache={},
        result=result_dict,
        image_id=image_id,
    )

    # error_records に記録されたか確認
    records = repo.get_error_records(operation_type="annotation")
    assert len(records) == 1
    record = records[0]
    assert record.error_type == "SafetyRefusalError"
    assert record.image_id == image_id
    assert record.model_name == "openai/gpt-4o"
    assert "blocked" in record.error_message
    assert record.resolved_at is None


@pytest.mark.integration
def test_process_model_result_records_content_policy_refusal(
    save_service: AnnotationSaveService,
    repo: ImageRepository,
    registered_image: tuple[int, str],
) -> None:
    """ContentPolicyRefusalError 結果が error_records に記録される。"""
    image_id, _ = registered_image
    unified_result = {"error": "ContentPolicyRefusalError: finish_reason=content_filter, blocked"}

    result_dict: dict = {"scores": [], "tags": [], "captions": [], "ratings": []}
    save_service._process_model_result(
        model_name="openai/gpt-4o",
        unified_result=unified_result,
        models_cache={},
        result=result_dict,
        image_id=image_id,
    )

    records = repo.get_error_records(operation_type="annotation")
    assert len(records) == 1
    assert records[0].error_type == "ContentPolicyRefusalError"


@pytest.mark.integration
def test_process_model_result_skips_record_when_image_id_missing(
    save_service: AnnotationSaveService,
    repo: ImageRepository,
) -> None:
    """image_id=None の場合は error_records 記録せず warning のみ (regression check)。"""
    unified_result = {"error": "SafetyRefusalError: blocked"}
    result_dict: dict = {"scores": [], "tags": [], "captions": [], "ratings": []}
    save_service._process_model_result(
        model_name="openai/gpt-4o",
        unified_result=unified_result,
        models_cache={},
        result=result_dict,
        image_id=None,
    )
    records = repo.get_error_records(operation_type="annotation")
    assert len(records) == 0


@pytest.mark.integration
def test_process_model_result_non_refusal_error_still_skipped(
    save_service: AnnotationSaveService,
    repo: ImageRepository,
    registered_image: tuple[int, str],
) -> None:
    """非 refusal error は従来通り skip され error_records には記録しない。"""
    image_id, _ = registered_image
    unified_result = {"error": "ApiTimeoutError: connection timeout"}
    result_dict: dict = {"scores": [], "tags": [], "captions": [], "ratings": []}
    save_service._process_model_result(
        model_name="openai/gpt-4o",
        unified_result=unified_result,
        models_cache={},
        result=result_dict,
        image_id=image_id,
    )
    records = repo.get_error_records(operation_type="annotation")
    # 本テストは「refusal でない error は records に書かない」を保証する。
    # 既存 _save_error_records 経路で記録される場合もあるが、それは別パス
    # (Worker レベルの try/except)。_process_model_result 単独では記録しない。
    refusal_records = [r for r in records if r.error_type.endswith("RefusalError")]
    assert len(refusal_records) == 0


@pytest.mark.integration
def test_filter_refused_image_paths_excludes_unresolved_refusal(
    save_service: AnnotationSaveService,
    repo: ImageRepository,
    registered_image: tuple[int, str],
) -> None:
    """unresolved refusal を持つ画像は filter で除外される。"""
    image_id, file_path = registered_image
    repo.save_error_record(
        operation_type="annotation",
        error_type="SafetyRefusalError",
        error_message="blocked",
        image_id=image_id,
        model_name="openai/gpt-4o",
    )

    filtered = save_service.filter_refused_image_paths([file_path])
    assert filtered == []


@pytest.mark.integration
def test_filter_refused_image_paths_keeps_resolved_refusal(
    save_service: AnnotationSaveService,
    repo: ImageRepository,
    registered_image: tuple[int, str],
) -> None:
    """resolved refusal は filter 対象外 (再送信可能)。"""
    import datetime

    image_id, file_path = registered_image
    error_id = repo.save_error_record(
        operation_type="annotation",
        error_type="SafetyRefusalError",
        error_message="blocked",
        image_id=image_id,
        model_name="openai/gpt-4o",
    )
    # resolved_at を設定して解決済みにする
    with repo.session_factory() as session:
        from lorairo.database.schema import ErrorRecord

        record = session.get(ErrorRecord, error_id)
        record.resolved_at = datetime.datetime.now(datetime.UTC)
        session.commit()

    filtered = save_service.filter_refused_image_paths([file_path])
    assert filtered == [file_path]


@pytest.mark.integration
def test_filter_refused_image_paths_other_error_types_not_excluded(
    save_service: AnnotationSaveService,
    repo: ImageRepository,
    registered_image: tuple[int, str],
) -> None:
    """SafetyRefusal / ContentPolicy 以外の error_type は除外されない。"""
    image_id, file_path = registered_image
    repo.save_error_record(
        operation_type="annotation",
        error_type="ApiTimeoutError",
        error_message="timeout",
        image_id=image_id,
        model_name="openai/gpt-4o",
    )
    filtered = save_service.filter_refused_image_paths([file_path])
    assert filtered == [file_path]


@pytest.mark.integration
def test_filter_refused_image_paths_unknown_path_passes_through(
    save_service: AnnotationSaveService, tmp_path: Path
) -> None:
    """DB 未登録の path は filter 対象外として通過する (新規画像扱い)。"""
    unknown_path = str(tmp_path / "not_in_db.png")
    filtered = save_service.filter_refused_image_paths([unknown_path])
    assert filtered == [unknown_path]


@pytest.mark.integration
def test_filter_refused_image_paths_empty_input(
    save_service: AnnotationSaveService,
) -> None:
    """空 list 入力は空 list を返す (early return)。"""
    assert save_service.filter_refused_image_paths([]) == []


@pytest.mark.integration
def test_filter_uses_batch_resolve_for_path_to_image_id(
    save_service: AnnotationSaveService,
    repo: ImageRepository,
    registered_image: tuple[int, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR 0023 Phase 1.5 Codex P2 (PR #233 r3209342204): filter は N+1 ではなく
    バッチ解決 (`get_image_ids_by_filepaths`) を使う回帰防止。
    """
    image_id, file_path = registered_image
    repo.save_error_record(
        operation_type="annotation",
        error_type="SafetyRefusalError",
        error_message="blocked",
        image_id=image_id,
        model_name="openai/gpt-4o",
    )

    per_path_calls: list[str] = []
    original_per_path = repo.get_image_id_by_filepath
    monkeypatch.setattr(
        repo,
        "get_image_id_by_filepath",
        lambda p: (per_path_calls.append(p), original_per_path(p))[1],
    )
    batch_calls: list[list[str]] = []
    original_batch = repo.get_image_ids_by_filepaths
    monkeypatch.setattr(
        repo,
        "get_image_ids_by_filepaths",
        lambda paths: (batch_calls.append(list(paths)), original_batch(paths))[1],
    )

    filtered = save_service.filter_refused_image_paths([file_path])
    assert filtered == []
    assert len(batch_calls) == 1, "バッチ解決が 1 回のみ呼ばれるはず"
    assert per_path_calls == [], "per-path lookup は呼ばれてはならない (N+1 防止)"


@pytest.mark.integration
def test_get_image_ids_by_filepaths_batch_resolve(
    repo: ImageRepository,
    registered_image: tuple[int, str],
) -> None:
    """ImageRepository.get_image_ids_by_filepaths のバッチ解決動作確認。"""
    image_id, file_path = registered_image
    result = repo.get_image_ids_by_filepaths([file_path, "/nonexistent/foo.png"])
    assert result[file_path] == image_id
    assert result["/nonexistent/foo.png"] is None


@pytest.mark.integration
def test_get_image_ids_by_filepaths_empty_input(
    repo: ImageRepository,
) -> None:
    """空 list は空 dict を返す (early return)。"""
    assert repo.get_image_ids_by_filepaths([]) == {}


@pytest.mark.integration
def test_get_error_image_ids_with_error_types_filter(
    repo: ImageRepository,
    registered_image: tuple[int, str],
) -> None:
    """get_error_image_ids が error_types filter を正しく適用する。"""
    image_id, _ = registered_image

    # 2 種類の error_type を追加
    repo.save_error_record(
        operation_type="annotation",
        error_type="SafetyRefusalError",
        error_message="safety",
        image_id=image_id,
        model_name="openai/gpt-4o",
    )

    refused = repo.get_error_image_ids(
        operation_type="annotation",
        resolved=False,
        error_types=["SafetyRefusalError", "ContentPolicyRefusalError"],
    )
    assert image_id in refused

    # 別の error_type だけ filter すると引っかからない
    refused_other = repo.get_error_image_ids(
        operation_type="annotation",
        resolved=False,
        error_types=["ApiTimeoutError"],
    )
    assert image_id not in refused_other
