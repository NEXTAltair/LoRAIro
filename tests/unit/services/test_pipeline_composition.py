# tests/unit/services/test_pipeline_composition.py
"""PipelineCompositionService の計算ロジックのユニットテスト (Phase 6a Track A)。

Wireframes v11 Frame 2A のリファレンス構成 (タガー2 + multimodal1 +
スコアラー2 + レーター1) を中心に、自動仕分け・派生チップ・推論台帳を検証する。
"""

import pytest

from lorairo.services.pipeline_composition import (
    MULTIMODAL_FILL_STAGES,
    DerivedChip,
    PipelineCompositionService,
    PipelineStage,
    StageModelInfo,
)

pytestmark = pytest.mark.unit


def _model(
    model_id: str,
    capabilities: set[str],
    *,
    is_api: bool = False,
    provider: str | None = None,
) -> StageModelInfo:
    """テスト用 StageModelInfo を生成するヘルパー。"""
    return StageModelInfo(
        litellm_model_id=model_id,
        display_name=model_id,
        provider=provider,
        is_api=is_api,
        capabilities=frozenset(capabilities),
    )


@pytest.fixture
def v11_reference_models() -> list[StageModelInfo]:
    """v11 リファレンス構成: タガー2 + multimodal1 + スコアラー2 + レーター1。"""
    return [
        _model("wd-v1-4", {"tags"}),
        _model("wd-eva02", {"tags"}),
        _model("openai/gpt-4o", {"multimodal"}, is_api=True, provider="openai"),
        _model("aesthetic-shadow", {"scores"}),
        _model("cafe-aesthetic", {"scores"}),
        _model("classification-rater", {"ratings"}),
    ]


@pytest.fixture
def service() -> PipelineCompositionService:
    return PipelineCompositionService()


class TestStageModelInfo:
    def test_fill_stages_multimodal_returns_fill_stages_without_rating(self) -> None:
        model = _model("openai/gpt-4o", {"multimodal"}, is_api=True)
        assert model.fill_stages() == MULTIMODAL_FILL_STAGES
        assert model.fill_stages() == frozenset(
            {PipelineStage.TAGS, PipelineStage.CAPTION, PipelineStage.SCORE}
        )
        assert PipelineStage.RATING not in model.fill_stages()

    def test_fill_stages_tags_only_returns_tags(self) -> None:
        model = _model("wd-v1-4", {"tags"})
        assert model.fill_stages() == frozenset({PipelineStage.TAGS})

    def test_fill_stages_ratings_returns_rating(self) -> None:
        model = _model("classification-rater", {"ratings"})
        assert model.fill_stages() == frozenset({PipelineStage.RATING})

    def test_fill_stages_multi_capability_local_returns_each_stage(self) -> None:
        model = _model("local-tagger-captioner", {"tags", "caption"})
        assert model.fill_stages() == frozenset({PipelineStage.TAGS, PipelineStage.CAPTION})

    def test_is_multimodal_local_model_is_false(self) -> None:
        # ローカルモデルは "multimodal" capability があっても multimodal 扱いしない
        model = _model("local-multi", {"multimodal"}, is_api=False)
        assert model.is_multimodal is False

    def test_is_multimodal_api_model_is_true(self) -> None:
        model = _model("openai/gpt-4o", {"multimodal"}, is_api=True)
        assert model.is_multimodal is True


class TestComposeFromModels:
    def test_v11_reference_stage_rows(
        self, service: PipelineCompositionService, v11_reference_models: list[StageModelInfo]
    ) -> None:
        service.compose_from_models(v11_reference_models)
        rows = service.stage_rows()

        assert [row.stage for row in rows] == list(PipelineStage)
        rows_by_stage = {row.stage: row for row in rows}

        # TAGS: primary 2 + derived 1 (gpt-4o from CAPTION)
        tags_row = rows_by_stage[PipelineStage.TAGS]
        assert [m.litellm_model_id for m in tags_row.primary_models] == ["wd-v1-4", "wd-eva02"]
        assert [c.model.litellm_model_id for c in tags_row.derived_chips] == ["openai/gpt-4o"]
        assert tags_row.derived_chips[0].origin_stage == PipelineStage.CAPTION

        # CAPTION: primary 1 (gpt-4o)、derived 0
        caption_row = rows_by_stage[PipelineStage.CAPTION]
        assert [m.litellm_model_id for m in caption_row.primary_models] == ["openai/gpt-4o"]
        assert caption_row.derived_chips == ()

        # SCORE: primary 2 + derived 1 (gpt-4o from CAPTION)
        score_row = rows_by_stage[PipelineStage.SCORE]
        assert [m.litellm_model_id for m in score_row.primary_models] == [
            "aesthetic-shadow",
            "cafe-aesthetic",
        ]
        assert score_row.derived_chips == (
            DerivedChip(model=v11_reference_models[2], origin_stage=PipelineStage.CAPTION),
        )

        # RATING: primary 1、derived は決して出ない
        rating_row = rows_by_stage[PipelineStage.RATING]
        assert [m.litellm_model_id for m in rating_row.primary_models] == ["classification-rater"]
        assert rating_row.derived_chips == ()

    def test_duplicate_model_ids_are_deduped(self, service: PipelineCompositionService) -> None:
        tagger = _model("wd-v1-4", {"tags"})
        service.compose_from_models([tagger, tagger, _model("wd-v1-4", {"tags"})])
        rows_by_stage = {row.stage: row for row in service.stage_rows()}
        assert len(rows_by_stage[PipelineStage.TAGS].primary_models) == 1

    def test_multi_capability_local_model_assigned_to_each_stage(
        self, service: PipelineCompositionService
    ) -> None:
        # 非 multimodal の複数 capability は対応する複数ステージそれぞれに明示割当
        model = _model("local-tagger-captioner", {"tags", "caption"})
        service.compose_from_models([model])
        rows_by_stage = {row.stage: row for row in service.stage_rows()}
        assert rows_by_stage[PipelineStage.TAGS].primary_models == (model,)
        assert rows_by_stage[PipelineStage.CAPTION].primary_models == (model,)
        # 非 multimodal は派生を出さない
        assert all(row.derived_chips == () for row in service.stage_rows())

    def test_recompose_clears_previous_assignments(
        self, service: PipelineCompositionService, v11_reference_models: list[StageModelInfo]
    ) -> None:
        service.compose_from_models(v11_reference_models)
        rater_only = [_model("classification-rater", {"ratings"})]
        service.compose_from_models(rater_only)

        rows_by_stage = {row.stage: row for row in service.stage_rows()}
        assert rows_by_stage[PipelineStage.TAGS].primary_models == ()
        assert rows_by_stage[PipelineStage.TAGS].derived_chips == ()
        assert rows_by_stage[PipelineStage.CAPTION].primary_models == ()
        assert rows_by_stage[PipelineStage.SCORE].primary_models == ()
        assert [m.litellm_model_id for m in rows_by_stage[PipelineStage.RATING].primary_models] == [
            "classification-rater"
        ]
        assert service.unique_model_ids() == ["classification-rater"]

    def test_empty_input_yields_empty_rows_and_zero_ledger(
        self, service: PipelineCompositionService
    ) -> None:
        service.compose_from_models([])
        rows = service.stage_rows()
        assert len(rows) == 4
        assert all(row.primary_models == () and row.derived_chips == () for row in rows)

        ledger = service.ledger(staged_count=9)
        assert ledger.entries == ()
        assert ledger.unique_model_count == 0
        assert ledger.total_jobs == 0
        assert ledger.local_count == 0
        assert ledger.api_count == 0
        assert service.unique_model_ids() == []


class TestAssignRemove:
    def test_assign_is_idempotent_per_stage(self, service: PipelineCompositionService) -> None:
        model = _model("wd-v1-4", {"tags"})
        service.assign(PipelineStage.TAGS, model)
        service.assign(PipelineStage.TAGS, model)
        rows_by_stage = {row.stage: row for row in service.stage_rows()}
        assert rows_by_stage[PipelineStage.TAGS].primary_models == (model,)

    def test_remove_missing_model_is_noop(self, service: PipelineCompositionService) -> None:
        model = _model("wd-v1-4", {"tags"})
        service.assign(PipelineStage.TAGS, model)
        service.remove(PipelineStage.TAGS, "unknown-model")
        rows_by_stage = {row.stage: row for row in service.stage_rows()}
        assert rows_by_stage[PipelineStage.TAGS].primary_models == (model,)

    def test_same_multimodal_assigned_to_two_stages_dedupes(
        self, service: PipelineCompositionService
    ) -> None:
        gpt4o = _model("openai/gpt-4o", {"multimodal"}, is_api=True, provider="openai")
        service.assign(PipelineStage.TAGS, gpt4o)
        service.assign(PipelineStage.CAPTION, gpt4o)

        rows_by_stage = {row.stage: row for row in service.stage_rows()}
        # 明示割当されたステージには derived を出さない
        assert rows_by_stage[PipelineStage.TAGS].primary_models == (gpt4o,)
        assert rows_by_stage[PipelineStage.TAGS].derived_chips == ()
        assert rows_by_stage[PipelineStage.CAPTION].primary_models == (gpt4o,)
        assert rows_by_stage[PipelineStage.CAPTION].derived_chips == ()
        # SCORE のみ derived。origin は最初の割当ステージ (TAGS)
        assert rows_by_stage[PipelineStage.SCORE].derived_chips == (
            DerivedChip(model=gpt4o, origin_stage=PipelineStage.TAGS),
        )
        assert rows_by_stage[PipelineStage.RATING].derived_chips == ()

        # 台帳は 1 エントリのまま (dedupe)、届くステージは 3 つ
        ledger = service.ledger(staged_count=10)
        assert ledger.unique_model_count == 1
        assert ledger.entries[0].stage_count == 3
        assert ledger.total_jobs == 10

    def test_remove_multimodal_from_caption_clears_all_derived(
        self, service: PipelineCompositionService, v11_reference_models: list[StageModelInfo]
    ) -> None:
        service.compose_from_models(v11_reference_models)
        service.remove(PipelineStage.CAPTION, "openai/gpt-4o")

        rows = service.stage_rows()
        assert all(row.derived_chips == () for row in rows)
        rows_by_stage = {row.stage: row for row in rows}
        assert rows_by_stage[PipelineStage.CAPTION].primary_models == ()

        ledger = service.ledger(staged_count=9)
        assert ledger.unique_model_count == 5
        assert ledger.api_count == 0
        assert "openai/gpt-4o" not in service.unique_model_ids()


class TestLedger:
    def test_v11_reference_ledger(
        self, service: PipelineCompositionService, v11_reference_models: list[StageModelInfo]
    ) -> None:
        service.compose_from_models(v11_reference_models)
        ledger = service.ledger(staged_count=9)

        assert ledger.unique_model_count == 6
        assert ledger.staged_count == 9
        assert ledger.total_jobs == 54
        assert ledger.local_count == 5
        assert ledger.api_count == 1

        entries_by_id = {entry.model.litellm_model_id: entry for entry in ledger.entries}
        assert entries_by_id["openai/gpt-4o"].stage_count == 3
        assert entries_by_id["wd-v1-4"].stage_count == 1
        assert entries_by_id["aesthetic-shadow"].stage_count == 1
        assert entries_by_id["classification-rater"].stage_count == 1

    def test_unique_model_ids_in_assignment_order(
        self, service: PipelineCompositionService, v11_reference_models: list[StageModelInfo]
    ) -> None:
        service.compose_from_models(v11_reference_models)
        assert service.unique_model_ids() == [
            "wd-v1-4",
            "wd-eva02",
            "openai/gpt-4o",
            "aesthetic-shadow",
            "cafe-aesthetic",
            "classification-rater",
        ]


class TestLedgerDispatchRoute:
    """#884 Phase 4b: dispatch_mode + batch-capable 集合からの route 分割。"""

    def test_default_dispatch_all_sync(
        self, service: PipelineCompositionService, v11_reference_models: list[StageModelInfo]
    ) -> None:
        service.compose_from_models(v11_reference_models)
        ledger = service.ledger(staged_count=9)
        assert all(e.route == "sync" for e in ledger.entries)
        assert len(ledger.sync_entries) == 6
        assert ledger.batch_entries == ()

    def test_batch_api_splits_batch_capable_to_batch_lane(
        self, service: PipelineCompositionService, v11_reference_models: list[StageModelInfo]
    ) -> None:
        service.compose_from_models(v11_reference_models)
        ledger = service.ledger(
            staged_count=9,
            dispatch_mode="batch_api",
            batch_capable_litellm_ids={"openai/gpt-4o"},
        )
        routes = {e.model.litellm_model_id: e.route for e in ledger.entries}
        assert routes["openai/gpt-4o"] == "batch"
        assert routes["wd-v1-4"] == "sync"
        assert len(ledger.batch_entries) == 1
        assert ledger.batch_entries[0].model.litellm_model_id == "openai/gpt-4o"
        assert len(ledger.sync_entries) == 5

    def test_batch_api_local_never_batch_even_if_in_set(
        self, service: PipelineCompositionService, v11_reference_models: list[StageModelInfo]
    ) -> None:
        # local モデル ID を誤って batch 集合に入れても batch 扱いしない (is_api False)
        service.compose_from_models(v11_reference_models)
        ledger = service.ledger(
            staged_count=9,
            dispatch_mode="batch_api",
            batch_capable_litellm_ids={"openai/gpt-4o", "wd-v1-4"},
        )
        routes = {e.model.litellm_model_id: e.route for e in ledger.entries}
        assert routes["wd-v1-4"] == "sync"
        assert routes["openai/gpt-4o"] == "batch"

    def test_batch_api_non_capable_api_stays_sync(self, service: PipelineCompositionService) -> None:
        # batch 非対応の API モデル (集合に無い) は sync レーンに残る
        service.compose_from_models(
            [_model("google/gemini-2.5", {"multimodal"}, is_api=True, provider="google")]
        )
        ledger = service.ledger(
            staged_count=4,
            dispatch_mode="batch_api",
            batch_capable_litellm_ids=set(),
        )
        assert ledger.entries[0].route == "sync"
        assert ledger.batch_entries == ()

    def test_sync_mode_ignores_batch_capable_set(
        self, service: PipelineCompositionService, v11_reference_models: list[StageModelInfo]
    ) -> None:
        # dispatch_mode=sync では batch_capable 集合があっても全 sync
        service.compose_from_models(v11_reference_models)
        ledger = service.ledger(
            staged_count=9,
            dispatch_mode="sync",
            batch_capable_litellm_ids={"openai/gpt-4o"},
        )
        assert all(e.route == "sync" for e in ledger.entries)
        assert ledger.batch_entries == ()
