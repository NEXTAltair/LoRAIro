"""AnnotationSaveService ユニットテスト。"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from lorairo.domain.score_scaler import calibrate_to_display
from lorairo.services.annotation_save_service import AnnotationSaveService


def _rating(raw_label: str, source_scheme: str, confidence: float | None) -> SimpleNamespace:
    """RatingPrediction 相当のテストダブル (raw_label / source_scheme / confidence_score)。"""
    return SimpleNamespace(raw_label=raw_label, source_scheme=source_scheme, confidence_score=confidence)


@pytest.fixture
def mock_repository() -> MagicMock:
    """モック Repository (ADR 0035 段階 6: 全 Aggregate Repo に分離後、本 mock は
    annotation_repo / image_repo / model_repo / error_record_repo の共通スタブとして
    機能する。すべての操作が同じ Mock を経由するため既存テストの assert はそのまま通る)。"""
    repo = MagicMock()
    repo.find_image_ids_by_phashes.return_value = {}
    repo.find_image_ids_by_phashes_multi.return_value = {}
    repo.get_models_by_litellm_ids.return_value = {}
    repo.batch_resolve_tag_ids.return_value = {}
    return repo


@pytest.fixture
def service(mock_repository: MagicMock) -> AnnotationSaveService:
    """テスト対象サービス。

    ADR 0035 段階 6: facade 撤廃後、4 つの Repo を inject する。全て同じ mock を
    渡すことで既存テストの assertion (mock_repository.X.assert_called_*) を維持。
    """
    return AnnotationSaveService(
        annotation_repo=mock_repository,
        image_repo=mock_repository,
        model_repo=mock_repository,
        error_record_repo=mock_repository,
    )


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
    result.error_code = None
    result.retryable = False
    result.tags = tags or []
    result.captions = captions or []
    result.scores = scores
    result.score_labels = score_labels
    result.ratings = None
    return result


def _first_batch_save_args(mock_repository: MagicMock) -> tuple[int, dict]:
    item = mock_repository.save_annotations_batch.call_args[0][0][0]
    return item.image_id, item.annotations


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

    mock_repository.find_image_ids_by_phashes_multi.return_value = {"phash001": [1], "phash002": [2]}
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
    mock_repository.save_annotations_batch.assert_called_once()
    assert len(mock_repository.save_annotations_batch.call_args[0][0]) == 2
    mock_repository.save_annotations.assert_not_called()


@pytest.mark.unit
def test_save_annotation_results_fanout_scoped_to_allowed_image_ids(
    service: AnnotationSaveService,
    mock_repository: MagicMock,
) -> None:
    """#633 (codex P1): allowed_image_ids 指定時はバッチ内 image_id のみへ fan-out する。

    同一 pHash に別版 (image_id 1 と 2) が紐づくが、バッチで選択したのは 1 のみ。
    未選択の別版 2 へは書き込まない (汚染防止)。
    """
    mock_model = MagicMock()
    mock_model.id = 10
    mock_repository.find_image_ids_by_phashes_multi.return_value = {"phash001": [1, 2]}
    mock_repository.get_models_by_litellm_ids.return_value = {"wdtagger": mock_model}
    mock_repository.batch_resolve_tag_ids.return_value = {}

    results = {"phash001": {"wdtagger": _make_success_result(tags=["tag1"])}}

    result = service.save_annotation_results(results, allowed_image_ids={1})

    assert result.success_count == 1
    saved_items = mock_repository.save_annotations_batch.call_args[0][0]
    assert [item.image_id for item in saved_items] == [1]


@pytest.mark.unit
def test_save_annotation_results_fanout_covers_all_batch_variants(
    service: AnnotationSaveService,
    mock_repository: MagicMock,
) -> None:
    """#633: バッチに別版が両方含まれる場合は両 image_id へ保存する (取りこぼし防止)。"""
    mock_model = MagicMock()
    mock_model.id = 10
    mock_repository.find_image_ids_by_phashes_multi.return_value = {"phash001": [1, 2]}
    mock_repository.get_models_by_litellm_ids.return_value = {"wdtagger": mock_model}
    mock_repository.batch_resolve_tag_ids.return_value = {}

    results = {"phash001": {"wdtagger": _make_success_result(tags=["tag1"])}}

    result = service.save_annotation_results(results, allowed_image_ids={1, 2})

    assert result.success_count == 2
    saved_items = mock_repository.save_annotations_batch.call_args[0][0]
    assert sorted(item.image_id for item in saved_items) == [1, 2]


@pytest.mark.unit
def test_save_annotation_results_without_scope_saves_first_match_only(
    service: AnnotationSaveService,
    mock_repository: MagicMock,
) -> None:
    """#633 (codex P1): allowed_image_ids 未指定時は pHash ごと先頭 1 件のみ保存する。

    バッチ集合が不明な経路 (CLI 等) で複数別版へ無条件 fan-out すると未選択別版を
    汚染するため、pre-#633 の単一 image_id 挙動に縮退する。
    """
    mock_model = MagicMock()
    mock_model.id = 10
    mock_repository.find_image_ids_by_phashes_multi.return_value = {"phash001": [1, 2]}
    mock_repository.get_models_by_litellm_ids.return_value = {"wdtagger": mock_model}
    mock_repository.batch_resolve_tag_ids.return_value = {}

    results = {"phash001": {"wdtagger": _make_success_result(tags=["tag1"])}}

    result = service.save_annotation_results(results)

    assert result.success_count == 1
    saved_items = mock_repository.save_annotations_batch.call_args[0][0]
    assert [item.image_id for item in saved_items] == [1]


@pytest.mark.unit
def test_save_provider_batch_results_by_image_id_saves_without_phash_lookup(
    service: AnnotationSaveService,
    mock_repository: MagicMock,
) -> None:
    """Provider Batch import は image_id keyed result を直接保存する。"""
    mock_repository.batch_resolve_tag_ids.return_value = {}

    result = service.save_provider_batch_results_by_image_id(
        {7: _make_success_result(tags=["tag1"], captions=["caption"])},
        model_id=10,
        model_name="openai/gpt-test",
    )

    assert result.success_count == 1
    assert result.skip_count == 0
    assert result.error_count == 0
    mock_repository.find_image_ids_by_phashes_multi.assert_not_called()
    mock_repository.get_models_by_litellm_ids.assert_not_called()
    mock_repository.save_annotations_batch.assert_called_once()
    item = mock_repository.save_annotations_batch.call_args[0][0][0]
    annotations_arg = item.annotations
    assert item.image_id == 7
    assert annotations_arg["tags"][0]["model_id"] == 10
    assert annotations_arg["tags"][0]["tag"] == "tag1"
    assert annotations_arg["captions"][0]["caption"] == "caption"


@pytest.mark.unit
def test_provider_batch_import_commits_in_small_chunks(
    service: AnnotationSaveService,
    mock_repository: MagicMock,
) -> None:
    """#1158: provider-batch import は少数画像ごとに commit しロックを解放する。

    ``save_annotations_batch`` は呼び出しごとに独立セッション + commit なので、複数回
    呼ばれること = チャンク間で書き込みロックが解放されること。巨大単一トランザクション
    が >30s ロックを保持して並行 writer を ``database is locked`` にする回帰を防ぐ。
    """
    mock_repository.batch_resolve_tag_ids.return_value = {}
    # 120 画像 → commit_chunk=50 で 50 / 50 / 20 の 3 コミットに分割される
    results = {i: _make_success_result(tags=[f"t{i}"]) for i in range(1, 121)}

    service.save_provider_batch_results_by_image_id(results, model_id=10, model_name="m")

    assert mock_repository.save_annotations_batch.call_count == 3
    sizes = [len(call.args[0]) for call in mock_repository.save_annotations_batch.call_args_list]
    assert sizes == [50, 50, 20]
    # 1 コミットあたりの画像数は commit_chunk (50) を超えない = ロング・トランザクション回避
    assert all(size <= 50 for size in sizes)
    # 各バッチは自身のサイズを内側 chunk_size に渡す (チャンク内は all-or-nothing)
    for call in mock_repository.save_annotations_batch.call_args_list:
        assert call.kwargs["chunk_size"] == len(call.args[0])


@pytest.mark.unit
def test_sync_path_keeps_single_commit_by_default(
    service: AnnotationSaveService,
    mock_repository: MagicMock,
) -> None:
    """#1158: 既定 (sync/通常アノテ経路) は従来通り単一トランザクションで commit する。

    commit_chunk のオプトインは provider-batch のみ。既定引数を変えていないことを保証し、
    既存書き込み経路の意味論 (単一トランザクション) 不変を回帰テストする。
    """
    from lorairo.services.annotation_save_service import _PreparedAnnotationSave

    items = [
        _PreparedAnnotationSave(source_key=str(i), image_id=i, annotations={"tags": [{"tag": "x"}]})
        for i in range(1, 121)
    ]

    # 既定 (commit_chunk 未指定) で呼ぶ
    service._save_prepared_batch(
        items,
        tag_id_cache={},
        error_message=lambda item, e: "",
        log_message=lambda item, e: "",
    )

    # 120 画像でも 1 コミットに集約される (BATCH_CHUNK_SIZE=15000 の従来挙動)
    mock_repository.save_annotations_batch.assert_called_once()
    assert len(mock_repository.save_annotations_batch.call_args.args[0]) == 120


@pytest.mark.unit
def test_save_provider_batch_results_by_image_id_records_refusal(
    service: AnnotationSaveService,
    mock_repository: MagicMock,
) -> None:
    """Provider Batch 経由の refusal も image_id 付き error_records に残す。"""
    refusal_result = MagicMock()
    refusal_result.error = "policy refused"
    refusal_result.error_code = "SAFETY_REFUSAL"
    refusal_result.retryable = False
    refusal_result.tags = []
    refusal_result.captions = []
    refusal_result.scores = None
    refusal_result.score_labels = None
    refusal_result.ratings = None

    result = service.save_provider_batch_results_by_image_id(
        {7: refusal_result},
        model_id=10,
        model_name="openai/gpt-test",
    )

    assert result.success_count == 0
    assert result.skip_count == 1
    assert result.error_count == 0
    mock_repository.save_error_record.assert_called_once_with(
        operation_type="annotation",
        error_type="SAFETY_REFUSAL",
        error_message="policy refused",
        image_id=7,
        model_name="openai/gpt-test",
    )
    mock_repository.save_annotations.assert_not_called()


@pytest.mark.unit
def test_save_annotation_results_with_unknown_phash_skips_silently(
    service: AnnotationSaveService,
    mock_repository: MagicMock,
) -> None:
    """DBに存在しないphashはスキップして処理を継続する。"""
    mock_repository.find_image_ids_by_phashes_multi.return_value = {}

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
def test_save_annotation_results_excludes_legacy_sentinel_from_lookup(
    service: AnnotationSaveService,
    mock_repository: MagicMock,
) -> None:
    """sentinel モデルは lookup 対象外になり、通常モデルのみ保存する。"""
    mock_model = MagicMock()
    mock_model.id = 10

    mock_repository.find_image_ids_by_phashes_multi.return_value = {"phash001": [1]}
    mock_repository.get_models_by_litellm_ids.return_value = {"wdtagger": mock_model}
    mock_repository.batch_resolve_tag_ids.return_value = {}

    results = {
        "phash001": {
            "__legacy_17__": _make_success_result(tags=["legacy"]),
            "wdtagger": _make_success_result(tags=["tag1"]),
        },
    }

    result = service.save_annotation_results(results)

    assert result.success_count == 1
    assert result.skip_count == 0
    assert result.error_count == 0
    assert result.total_count == 1
    mock_repository.get_models_by_litellm_ids.assert_called_once_with({"wdtagger"})
    mock_repository.save_annotations_batch.assert_called_once()
    image_id_arg, annotations_dict = _first_batch_save_args(mock_repository)
    assert image_id_arg == 1
    assert annotations_dict["tags"] == [
        {
            "model_id": 10,
            "tag": "tag1",
            "existing": False,
            "is_edited_manually": False,
            "confidence_score": None,
            "tag_id": None,
        }
    ]


@pytest.mark.unit
def test_save_annotation_results_legacy_sentinel_only_is_skipped(
    service: AnnotationSaveService,
    mock_repository: MagicMock,
) -> None:
    """legacy sentinel のみなら保存対象がなく、スキップ件数に集計される。"""
    mock_repository.find_image_ids_by_phashes_multi.return_value = {"phash001": [1]}
    mock_repository.get_models_by_litellm_ids.return_value = {}
    mock_repository.batch_resolve_tag_ids.return_value = {}

    results = {"phash001": {"__legacy_17__": _make_success_result(tags=["legacy"])}}

    result = service.save_annotation_results(results)

    assert result.success_count == 0
    assert result.skip_count == 1
    assert result.error_count == 0
    assert result.total_count == 1
    mock_repository.get_models_by_litellm_ids.assert_called_once_with(set())
    mock_repository.save_annotations.assert_not_called()


@pytest.mark.unit
def test_save_annotation_results_handles_partial_save_failure(
    service: AnnotationSaveService,
    mock_repository: MagicMock,
) -> None:
    """save_annotations 例外発生時はエラー件数に集計して処理を継続する。"""
    mock_model = MagicMock()
    mock_model.id = 1
    mock_repository.find_image_ids_by_phashes_multi.return_value = {"phash001": [1]}
    mock_repository.get_models_by_litellm_ids.return_value = {"wdtagger": mock_model}
    mock_repository.save_annotations_batch.side_effect = RuntimeError("batch DB write error")
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
def test_process_model_result_legacy_sentinel_is_skipped_with_warning(
    service: AnnotationSaveService,
    mock_repository: MagicMock,
) -> None:
    """legacy sentinel は refusal/error 処理を経ず警告してスキップする。"""
    unified_result = MagicMock()
    unified_result.error = "ApiTimeoutError: timeout"
    result_dict = {"scores": [], "score_labels": [], "tags": [], "captions": [], "ratings": []}

    with patch("lorairo.services.annotation_save_service.logger.warning") as warn_mock:
        service._process_model_result(
            "__legacy_17__",
            unified_result,
            {},
            result_dict,
            image_id=1,
        )
        assert warn_mock.call_count >= 1
        warn_mock.assert_any_call(
            "legacy sentinel モデルID __legacy_17__ を保存対象外としてスキップ: image_id=1"
        )

    mock_repository.save_error_record.assert_not_called()
    assert result_dict["tags"] == []


@pytest.mark.unit
def test_save_annotation_results_uses_batch_resolution(
    service: AnnotationSaveService,
    mock_repository: MagicMock,
) -> None:
    """N+1を避けるため、find_image_ids_by_phashesとget_models_by_litellm_idsを各1回のみ呼ぶ。"""
    mock_model = MagicMock()
    mock_model.id = 1
    mock_repository.find_image_ids_by_phashes_multi.return_value = {
        "phash001": [1],
        "phash002": [2],
        "phash003": [3],
    }
    mock_repository.get_models_by_litellm_ids.return_value = {"wdtagger": mock_model}
    mock_repository.batch_resolve_tag_ids.return_value = {}

    results = {
        "phash001": {"wdtagger": _make_success_result(tags=["tag1"])},
        "phash002": {"wdtagger": _make_success_result(tags=["tag2"])},
        "phash003": {"wdtagger": _make_success_result(tags=["tag3"])},
    }

    service.save_annotation_results(results)

    mock_repository.find_image_ids_by_phashes_multi.assert_called_once()
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
    mock_repository.find_image_ids_by_phashes_multi.return_value = {"phash001": [1]}
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

    # save_annotations_batch 呼び出し時の annotations dict に score_labels が積まれている
    assert mock_repository.save_annotations_batch.called
    image_id_arg, annotations_arg = _first_batch_save_args(mock_repository)
    assert image_id_arg == 1
    assert annotations_arg["score_labels"] == [
        {"model_id": 42, "label": "very aesthetic", "is_edited_manually": False}
    ]
    # Issue #626: AI scorer は positive key (hq) 1 行だけ生値で保存し、complement
    # (lq) は保存しない。これにより DB で positive 判別が一意になる。
    assert annotations_arg["scores"] == [
        {
            "model_id": 42,
            "score": 0.85,
            "display_score": calibrate_to_display("aesthetic_shadow_v2", 0.85),
            "is_edited_manually": False,
        },
    ]


@pytest.mark.unit
def test_save_regression_scorer_no_score_labels(
    service: AnnotationSaveService,
    mock_repository: MagicMock,
) -> None:
    """regression scorer (ImprovedAesthetic 等) は score_labels=None で empty list が渡る。"""
    mock_model = MagicMock()
    mock_model.id = 7
    mock_repository.find_image_ids_by_phashes_multi.return_value = {"phash001": [1]}
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

    _image_id_arg, annotations_arg = _first_batch_save_args(mock_repository)
    assert annotations_arg["score_labels"] == []
    assert annotations_arg["scores"] == [
        {
            "model_id": 7,
            "score": 7.5,
            "display_score": calibrate_to_display("ImprovedAesthetic", 7.5),
            "is_edited_manually": False,
        }
    ]


# ===== Issue #626: AI scorer は positive key 1 行のみ保存 =====


@pytest.mark.unit
def test_save_cafe_scorer_persists_only_positive_key(
    service: AnnotationSaveService,
    mock_repository: MagicMock,
) -> None:
    """cafe_aesthetic は positive key (aesthetic) 1 行のみ保存し not_aesthetic は捨てる。"""
    mock_model = MagicMock()
    mock_model.id = 11
    mock_repository.find_image_ids_by_phashes_multi.return_value = {"phash001": [1]}
    mock_repository.get_models_by_litellm_ids.return_value = {"cafe_aesthetic": mock_model}

    results = {
        "phash001": {
            "cafe_aesthetic": _make_success_result(
                scores={"aesthetic": 0.67, "not_aesthetic": 0.33},
                score_labels=["aesthetic"],
            )
        },
    }

    service.save_annotation_results(results)

    _image_id_arg, annotations_arg = _first_batch_save_args(mock_repository)
    assert annotations_arg["scores"] == [
        {
            "model_id": 11,
            "score": 0.67,
            "display_score": calibrate_to_display("cafe_aesthetic", 0.67),
            "is_edited_manually": False,
        },
    ]


@pytest.mark.unit
def test_save_shadow_scorer_persists_only_hq(
    service: AnnotationSaveService,
    mock_repository: MagicMock,
) -> None:
    """aesthetic_shadow は hq 1 行のみ保存し lq は捨てる。"""
    mock_model = MagicMock()
    mock_model.id = 21
    mock_repository.find_image_ids_by_phashes_multi.return_value = {"phash001": [1]}
    mock_repository.get_models_by_litellm_ids.return_value = {"aesthetic_shadow_v1": mock_model}

    results = {
        "phash001": {
            "aesthetic_shadow_v1": _make_success_result(
                scores={"hq": 0.9, "lq": 0.1},
                score_labels=["very aesthetic"],
            )
        },
    }

    service.save_annotation_results(results)

    _image_id_arg, annotations_arg = _first_batch_save_args(mock_repository)
    assert annotations_arg["scores"] == [
        {
            "model_id": 21,
            "score": 0.9,
            "display_score": calibrate_to_display("aesthetic_shadow_v1", 0.9),
            "is_edited_manually": False,
        },
    ]


@pytest.mark.unit
def test_save_ai_scorer_missing_positive_key_skips_score(
    service: AnnotationSaveService,
    mock_repository: MagicMock,
) -> None:
    """positive key が scores に無い場合はスコア保存をスキップする (score_labels は維持)。"""
    mock_model = MagicMock()
    mock_model.id = 31
    mock_repository.find_image_ids_by_phashes_multi.return_value = {"phash001": [1]}
    mock_repository.get_models_by_litellm_ids.return_value = {"aesthetic_shadow_v1": mock_model}

    results = {
        "phash001": {
            "aesthetic_shadow_v1": _make_success_result(
                scores={"lq": 0.1},
                score_labels=["very displeasing"],
            )
        },
    }

    service.save_annotation_results(results)

    _image_id_arg, annotations_arg = _first_batch_save_args(mock_repository)
    assert annotations_arg["scores"] == []
    assert annotations_arg["score_labels"] == [
        {"model_id": 31, "label": "very displeasing", "is_edited_manually": False},
    ]


@pytest.mark.unit
def test_save_multiple_labels_per_model(
    service: AnnotationSaveService,
    mock_repository: MagicMock,
) -> None:
    """score_labels=['a', 'b'] で 2 row が積まれる (将来拡張対応)。"""
    mock_model = MagicMock()
    mock_model.id = 99
    mock_repository.find_image_ids_by_phashes_multi.return_value = {"phash001": [1]}
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

    _image_id_arg, annotations_arg = _first_batch_save_args(mock_repository)
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
    mock_repository.find_image_ids_by_phashes_multi.return_value = {"phash001": [1]}
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


# === rating マッピング (Issue #333) ===


@pytest.mark.unit
def test_build_rating_row_maps_structured_prediction(service: AnnotationSaveService) -> None:
    """list[RatingPrediction] が canonical rating 1 行に変換される。"""
    ratings = [_rating("explicit", "danbooru4", 0.92)]

    row = service._build_rating_row(model_id=5, ratings=ratings)

    assert row == {
        "model_id": 5,
        "raw_rating_value": "explicit",
        "normalized_rating": "X",
        "confidence_score": 0.92,
    }


@pytest.mark.unit
def test_build_rating_row_picks_highest_confidence(service: AnnotationSaveService) -> None:
    """複数候補のうち最高 confidence の予測が選ばれる。"""
    ratings = [
        _rating("general", "danbooru4", 0.10),
        _rating("questionable", "danbooru4", 0.75),
        _rating("sensitive", "danbooru4", 0.40),
    ]

    row = service._build_rating_row(model_id=5, ratings=ratings)

    assert row is not None
    assert row["raw_rating_value"] == "questionable"
    assert row["normalized_rating"] == "R"
    assert row["confidence_score"] == 0.75


@pytest.mark.unit
def test_build_rating_row_real_zero_confidence_beats_missing(
    service: AnnotationSaveService,
) -> None:
    """confidence 0.0 (実値) は欠損 (None) より高位扱いで選ばれる。"""
    ratings = [
        _rating("explicit", "danbooru4", None),
        _rating("general", "danbooru4", 0.0),
    ]

    row = service._build_rating_row(model_id=5, ratings=ratings)

    assert row is not None
    assert row["raw_rating_value"] == "general"
    assert row["normalized_rating"] == "PG"
    assert row["confidence_score"] == 0.0


@pytest.mark.unit
def test_build_rating_row_accepts_dict_prediction(service: AnnotationSaveService) -> None:
    """辞書形式の RatingPrediction も変換できる。"""
    ratings = [{"raw_label": "safe", "source_scheme": "e6213", "confidence_score": 0.5}]

    row = service._build_rating_row(model_id=7, ratings=ratings)

    assert row is not None
    assert row["normalized_rating"] == "PG"


@pytest.mark.unit
def test_build_rating_row_unknown_scheme_returns_none(service: AnnotationSaveService) -> None:
    """未知 source_scheme はマッピング不能のため None (保存しない)。"""
    ratings = [_rating("general", "unknown", 0.9)]

    assert service._build_rating_row(model_id=5, ratings=ratings) is None


@pytest.mark.unit
def test_build_rating_row_backward_compat_canonical_str(service: AnnotationSaveService) -> None:
    """後方互換: canonical な str rating はそのまま 1 行で保存される。"""
    row = service._build_rating_row(model_id=3, ratings="R")

    assert row == {
        "model_id": 3,
        "raw_rating_value": "R",
        "normalized_rating": "R",
        "confidence_score": None,
    }


@pytest.mark.unit
def test_build_rating_row_backward_compat_noncanonical_str_returns_none(
    service: AnnotationSaveService,
) -> None:
    """後方互換: canonical でない str rating は None (保存しない)。"""
    assert service._build_rating_row(model_id=3, ratings="general") is None


@pytest.mark.unit
def test_save_annotation_results_persists_mapped_rating(
    service: AnnotationSaveService,
    mock_repository: MagicMock,
) -> None:
    """structured ratings が save_annotations に canonical 値で渡る (end-to-end)。"""
    mock_model = MagicMock()
    mock_model.id = 42
    mock_repository.find_image_ids_by_phashes_multi.return_value = {"phash001": [1]}
    mock_repository.get_models_by_litellm_ids.return_value = {"wd-vit-tagger-v3": mock_model}

    rating_result = _make_success_result()
    rating_result.ratings = [_rating("questionable", "danbooru4", 0.81)]

    results = {"phash001": {"wd-vit-tagger-v3": rating_result}}

    service.save_annotation_results(results)

    _image_id_arg, annotations_arg = _first_batch_save_args(mock_repository)
    assert annotations_arg["ratings"] == [
        {
            "model_id": 42,
            "raw_rating_value": "questionable",
            "normalized_rating": "R",
            "confidence_score": 0.81,
        }
    ]


# ===== Issue #644: WebAPI モデル (slash 形式) の _append_scores 経路 =====


class TestAppendScoresWebApi:
    """WebAPI モデル (slash 形式) の _append_scores 経路テスト。"""

    @pytest.mark.unit
    def test_webapi_saves_only_overall_key(self, service: AnnotationSaveService) -> None:
        """WebAPI モデルは is_ai_scored_model=True 経路で 'overall' key のみ保存する。"""
        result: dict = {"scores": [], "score_labels": [], "tags": [], "captions": [], "ratings": []}
        service._append_scores(
            model_id=99,
            scores={"overall": 8.0},
            model_name="openai/o1",
            result=result,
        )
        assert len(result["scores"]) == 1
        assert result["scores"][0]["score"] == pytest.approx(8.0)
        assert result["scores"][0]["model_id"] == 99
        assert result["scores"][0]["is_edited_manually"] is False
        assert "display_score" in result["scores"][0]

    @pytest.mark.unit
    def test_webapi_missing_overall_key_skips(self, service: AnnotationSaveService) -> None:
        """WebAPI モデルで 'overall' key が scores に無い場合はスキップする。"""
        result: dict = {"scores": [], "score_labels": [], "tags": [], "captions": [], "ratings": []}
        service._append_scores(
            model_id=99,
            scores={"some_other_key": 5.0},
            model_name="openai/o1",
            result=result,
        )
        assert len(result["scores"]) == 0
