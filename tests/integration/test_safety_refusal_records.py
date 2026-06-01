"""ADR 0023 Phase 1.5 amendment (Issue #599): outcome → error_records → filter cycle.

iam-lib 側で検出された refusal / empty annotation は `UnifiedAnnotationResult.error_code`
に構造化 outcome として乗ってくる。LoRAIro 側では対象 code を error_records に記録し、
次回送信時は `filter_refused_image_paths` で除外する。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from sqlalchemy.orm import sessionmaker

from lorairo.database.repository.annotation_record import AnnotationRepository
from lorairo.database.repository.error_record import ErrorRecordRepository
from lorairo.database.repository.image import ImageRepository
from lorairo.services.annotation_save_service import AnnotationSaveService

SAFETY_REFUSAL = "SAFETY_REFUSAL"
CONTENT_POLICY_REFUSAL = "CONTENT_POLICY_REFUSAL"
EMPTY_ANNOTATION = "EMPTY_ANNOTATION"
PROVIDER_ERROR = "PROVIDER_ERROR"


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
    return AnnotationSaveService(AnnotationRepository(repo.session_factory), image_repo=repo)


@pytest.fixture
def error_repo(repo: ImageRepository) -> ErrorRecordRepository:
    return ErrorRecordRepository(repo.session_factory)


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
def test_detect_annotation_outcome_error_type_safety_refusal() -> None:
    """SAFETY_REFUSAL code が記録対象として検出される。"""
    detected = AnnotationSaveService._detect_annotation_outcome_error_type(SAFETY_REFUSAL)
    assert detected == SAFETY_REFUSAL


@pytest.mark.integration
def test_detect_annotation_outcome_error_type_content_policy_refusal() -> None:
    """CONTENT_POLICY_REFUSAL code が記録対象として検出される。"""
    detected = AnnotationSaveService._detect_annotation_outcome_error_type(CONTENT_POLICY_REFUSAL)
    assert detected == CONTENT_POLICY_REFUSAL


@pytest.mark.integration
def test_detect_annotation_outcome_error_type_empty_annotation() -> None:
    """EMPTY_ANNOTATION code が記録対象として検出される。"""
    detected = AnnotationSaveService._detect_annotation_outcome_error_type(EMPTY_ANNOTATION)
    assert detected == EMPTY_ANNOTATION


@pytest.mark.integration
def test_detect_annotation_outcome_error_type_accepts_strenum_like_value() -> None:
    """StrEnum 相当の value 属性を持つ code も文字列化して扱う。"""
    code = SimpleNamespace(value=SAFETY_REFUSAL)
    assert AnnotationSaveService._detect_annotation_outcome_error_type(code) == SAFETY_REFUSAL


@pytest.mark.integration
def test_detect_annotation_outcome_error_type_non_recorded_returns_none() -> None:
    """transport 系や不正型は記録対象外として None を返す。"""
    assert AnnotationSaveService._detect_annotation_outcome_error_type(PROVIDER_ERROR) is None
    assert AnnotationSaveService._detect_annotation_outcome_error_type("ApiTimeoutError") is None
    assert AnnotationSaveService._detect_annotation_outcome_error_type(None) is None
    assert AnnotationSaveService._detect_annotation_outcome_error_type({"error": "obj"}) is None


@pytest.mark.integration
def test_process_model_result_records_safety_refusal_code(
    save_service: AnnotationSaveService,
    error_repo: ErrorRecordRepository,
    registered_image: tuple[int, str],
) -> None:
    """SAFETY_REFUSAL outcome が error_records に code 文字列で記録される。"""
    image_id, _ = registered_image
    unified_result = {"error_code": SAFETY_REFUSAL, "error": "blocked due to safety policy"}

    result_dict: dict = {"scores": [], "tags": [], "captions": [], "ratings": []}
    save_service._process_model_result(
        model_name="openai/gpt-4o",
        unified_result=unified_result,
        models_cache={},
        result=result_dict,
        image_id=image_id,
    )

    # error_records に記録されたか確認
    records = error_repo.get_error_records(operation_type="annotation")
    assert len(records) == 1
    record = records[0]
    assert record.error_type == SAFETY_REFUSAL
    assert record.image_id == image_id
    assert record.model_name == "openai/gpt-4o"
    assert "blocked" in record.error_message
    assert record.resolved_at is None


@pytest.mark.integration
def test_process_model_result_records_content_policy_refusal_code(
    save_service: AnnotationSaveService,
    error_repo: ErrorRecordRepository,
    registered_image: tuple[int, str],
) -> None:
    """CONTENT_POLICY_REFUSAL outcome が error_records に記録される。"""
    image_id, _ = registered_image
    unified_result = {
        "error_code": CONTENT_POLICY_REFUSAL,
        "error": "finish_reason=content_filter, blocked",
    }

    result_dict: dict = {"scores": [], "tags": [], "captions": [], "ratings": []}
    save_service._process_model_result(
        model_name="openai/gpt-4o",
        unified_result=unified_result,
        models_cache={},
        result=result_dict,
        image_id=image_id,
    )

    records = error_repo.get_error_records(operation_type="annotation")
    assert len(records) == 1
    assert records[0].error_type == CONTENT_POLICY_REFUSAL


@pytest.mark.integration
def test_process_model_result_records_empty_annotation_code(
    save_service: AnnotationSaveService,
    error_repo: ErrorRecordRepository,
    registered_image: tuple[int, str],
) -> None:
    """EMPTY_ANNOTATION outcome が error_records に記録される。"""
    image_id, _ = registered_image
    unified_result = {"error_code": EMPTY_ANNOTATION, "error": "all requested capabilities were empty"}

    result_dict: dict = {"scores": [], "tags": [], "captions": [], "ratings": []}
    save_service._process_model_result(
        model_name="openai/o1",
        unified_result=unified_result,
        models_cache={},
        result=result_dict,
        image_id=image_id,
    )

    records = error_repo.get_error_records(operation_type="annotation")
    assert len(records) == 1
    assert records[0].error_type == EMPTY_ANNOTATION
    assert "empty" in records[0].error_message


@pytest.mark.integration
def test_process_model_result_skips_record_when_image_id_missing(
    save_service: AnnotationSaveService,
    error_repo: ErrorRecordRepository,
) -> None:
    """image_id=None の場合は error_records 記録せず warning のみ (regression check)。"""
    unified_result = {"error_code": SAFETY_REFUSAL, "error": "blocked"}
    result_dict: dict = {"scores": [], "tags": [], "captions": [], "ratings": []}
    save_service._process_model_result(
        model_name="openai/gpt-4o",
        unified_result=unified_result,
        models_cache={},
        result=result_dict,
        image_id=None,
    )
    records = error_repo.get_error_records(operation_type="annotation")
    assert len(records) == 0


@pytest.mark.integration
def test_process_model_result_provider_error_still_skipped(
    save_service: AnnotationSaveService,
    error_repo: ErrorRecordRepository,
    registered_image: tuple[int, str],
) -> None:
    """retryable transport outcome は従来通り skip され error_records には記録しない。"""
    image_id, _ = registered_image
    unified_result = {"error_code": PROVIDER_ERROR, "retryable": True, "error": "connection timeout"}
    result_dict: dict = {"scores": [], "tags": [], "captions": [], "ratings": []}
    save_service._process_model_result(
        model_name="openai/gpt-4o",
        unified_result=unified_result,
        models_cache={},
        result=result_dict,
        image_id=image_id,
    )
    records = error_repo.get_error_records(operation_type="annotation")
    # 本テストは「LoRAIro exclusion outcome でない error は records に書かない」を保証する。
    # 既存 _save_error_records 経路で記録される場合もあるが、それは別パス
    # (Worker レベルの try/except)。_process_model_result 単独では記録しない。
    outcome_records = [r for r in records if r.error_type in AnnotationSaveService.REFUSAL_ERROR_TYPES]
    assert len(outcome_records) == 0


@pytest.mark.integration
def test_filter_refused_image_paths_excludes_unresolved_outcome(
    save_service: AnnotationSaveService,
    error_repo: ErrorRecordRepository,
    registered_image: tuple[int, str],
) -> None:
    """unresolved refusal / empty outcome を持つ画像は filter で除外される。"""
    image_id, file_path = registered_image
    error_repo.save_error_record(
        operation_type="annotation",
        error_type=EMPTY_ANNOTATION,
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
    error_repo: ErrorRecordRepository,
    registered_image: tuple[int, str],
) -> None:
    """resolved refusal は filter 対象外 (再送信可能)。"""
    import datetime

    image_id, file_path = registered_image
    error_id = error_repo.save_error_record(
        operation_type="annotation",
        error_type=SAFETY_REFUSAL,
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
    error_repo: ErrorRecordRepository,
    registered_image: tuple[int, str],
) -> None:
    """refusal / empty outcome code 以外の error_type は除外されない。"""
    image_id, file_path = registered_image
    error_repo.save_error_record(
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
    error_repo: ErrorRecordRepository,
    registered_image: tuple[int, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR 0023 Phase 1.5 Codex P2 (PR #233 r3209342204): filter は N+1 ではなく
    バッチ解決 (`get_image_ids_by_filepaths`) を使う回帰防止。
    """
    image_id, file_path = registered_image
    error_repo.save_error_record(
        operation_type="annotation",
        error_type=SAFETY_REFUSAL,
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
def test_get_image_ids_by_filepaths_contains_input_resolve_runtime_error(
    repo: ImageRepository,
    registered_image: tuple[int, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """入力 path の symlink loop 相当 RuntimeError は該当 path だけ None にする。"""
    image_id, file_path = registered_image
    broken_path = str(tmp_path / "symlink_loop.png")
    original_resolve = Path.resolve

    def resolve_with_symlink_loop(self: Path, *args, **kwargs):
        if str(self) == broken_path:
            raise RuntimeError("Symlink loop from test")
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve_with_symlink_loop)

    result = repo.get_image_ids_by_filepaths([file_path, broken_path])

    assert result[file_path] == image_id
    assert result[broken_path] is None


@pytest.mark.integration
def test_get_image_ids_by_filepaths_empty_input(
    repo: ImageRepository,
) -> None:
    """空 list は空 dict を返す (early return)。"""
    assert repo.get_image_ids_by_filepaths([]) == {}


@pytest.mark.integration
def test_get_image_ids_by_filepaths_isolates_row_resolution_failures(
    repo: ImageRepository,
    registered_image: tuple[int, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR 0023 Phase 1.5 Codex P2 (PR #233 r3209511028): 1 行の corrupted
    stored_image_path で batch 全体を落とさず、健全な行は解決され続けることを確認する。

    `_safe_resolve_stored_path()` helper を patch することで row-level guard の
    動作を直接検証する。
    """
    image_id, file_path = registered_image

    # 既存 row に対する `_safe_resolve_stored_path` を OSError で失敗させる。
    # row-level guard で例外が吸収され、result["sample.png"] は None になる
    # (1 candidate しかないため skip 後に matches が空になる)。
    failures: list[int] = []

    def flaky_safe_resolve(image_id_arg: int, stored_image_path: str) -> Path | None:
        failures.append(image_id_arg)
        return None  # helper 自体が失敗をキャプチャした体で None 返却

    # ADR 0035 段階 4: `_safe_resolve_stored_path` は新 `repository.image.ImageRepository`
    # に移設済み。レガシー facade (`db_repository.ImageRepository`) は delegating wrapper
    # を持つだけなので、static helper の patch は新クラス側に当てる。
    from lorairo.database.repository.image import ImageRepository as _NewImageRepository

    monkeypatch.setattr(_NewImageRepository, "_safe_resolve_stored_path", staticmethod(flaky_safe_resolve))

    result = repo.get_image_ids_by_filepaths([file_path, "/nonexistent/foo.png"])

    # 全行が skip されても batch 全体は abort せず、各 path に対し None を返す
    assert result[file_path] is None
    assert result["/nonexistent/foo.png"] is None
    # 1 candidate の helper が呼ばれ、image_id が記録された
    assert image_id in failures, "row-level guard 経由で helper が呼ばれるはず"


@pytest.mark.integration
def test_safe_resolve_stored_path_returns_none_on_oserror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_safe_resolve_stored_path()` が OSError を吸収して None を返すことを確認。"""
    # ADR 0035 段階 6 (#423): legacy db_repository.py 撤廃に伴い、resolve_stored_path
    # は repository/image.py 内で local import される。実モジュールに patch を当てる。
    from lorairo.database.repository import image as image_repo_mod

    def raising_resolve(_path: str) -> Path:
        raise OSError("simulated symlink loop")

    monkeypatch.setattr(image_repo_mod, "resolve_stored_path", raising_resolve, raising=False)

    # _safe_resolve_stored_path 内の遅延 import より、db_core を patch
    from lorairo.database import db_core

    monkeypatch.setattr(db_core, "resolve_stored_path", raising_resolve)

    result = ImageRepository._safe_resolve_stored_path(image_id=42, stored_image_path="/bad/path")
    assert result is None


@pytest.mark.integration
def test_get_error_image_ids_with_error_types_filter(
    error_repo: ErrorRecordRepository,
    registered_image: tuple[int, str],
) -> None:
    """get_error_image_ids が error_types filter を正しく適用する。"""
    image_id, _ = registered_image

    # 2 種類の error_type を追加
    error_repo.save_error_record(
        operation_type="annotation",
        error_type=SAFETY_REFUSAL,
        error_message="safety",
        image_id=image_id,
        model_name="openai/gpt-4o",
    )

    refused = error_repo.get_error_image_ids(
        operation_type="annotation",
        resolved=False,
        error_types=[SAFETY_REFUSAL, CONTENT_POLICY_REFUSAL, EMPTY_ANNOTATION],
    )
    assert image_id in refused

    # 別の error_type だけ filter すると引っかからない
    refused_other = error_repo.get_error_image_ids(
        operation_type="annotation",
        resolved=False,
        error_types=["ApiTimeoutError"],
    )
    assert image_id not in refused_other
