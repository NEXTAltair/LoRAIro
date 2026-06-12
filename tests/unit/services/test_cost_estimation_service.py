"""CostEstimationService 単体テスト (Issue #747)。"""

from __future__ import annotations

import pytest

from lorairo.services.cost_estimation_service import (
    INPUT_TOKENS_PER_IMAGE,
    OUTPUT_TOKENS_PER_IMAGE,
    SECONDS_PER_JOB,
    CostEstimationService,
    format_duration,
    format_per_image_cost,
)
from lorairo.services.pipeline_composition import (
    InferenceLedger,
    LedgerEntry,
    StageModelInfo,
)

pytestmark = [pytest.mark.unit]


def _api_model(model_id: str, in_cost: float | None, out_cost: float | None) -> StageModelInfo:
    return StageModelInfo(
        litellm_model_id=model_id,
        display_name=model_id,
        provider="openai",
        is_api=True,
        capabilities=frozenset({"tags"}),
        input_cost_per_token=in_cost,
        output_cost_per_token=out_cost,
    )


def _local_model(model_id: str) -> StageModelInfo:
    return StageModelInfo(
        litellm_model_id=model_id,
        display_name=model_id,
        provider=None,
        is_api=False,
        capabilities=frozenset({"tags"}),
    )


class TestPerImageUsd:
    def test_local_model_is_zero(self):
        service = CostEstimationService()
        assert service.per_image_usd(_local_model("wd-tagger")) == 0.0

    def test_api_model_uses_fixed_token_assumptions(self):
        service = CostEstimationService()
        model = _api_model("openai/gpt-4o", 2.5e-06, 1.0e-05)
        expected = INPUT_TOKENS_PER_IMAGE * 2.5e-06 + OUTPUT_TOKENS_PER_IMAGE * 1.0e-05
        assert service.per_image_usd(model) == pytest.approx(expected)

    def test_api_model_missing_input_cost_is_none(self):
        service = CostEstimationService()
        assert service.per_image_usd(_api_model("x", None, 1.0e-05)) is None

    def test_api_model_missing_output_cost_is_none(self):
        service = CostEstimationService()
        assert service.per_image_usd(_api_model("x", 2.5e-06, None)) is None


class TestEstimateBatch:
    def test_empty_ledger_is_zero(self):
        service = CostEstimationService()
        estimate = service.estimate_batch(InferenceLedger(entries=(), staged_count=0))
        assert estimate.total_usd == 0.0
        assert estimate.has_unknown is False
        assert estimate.est_seconds == 0.0

    def test_api_cost_multiplied_by_staged_count(self):
        service = CostEstimationService()
        model = _api_model("openai/gpt-4o", 2.5e-06, 1.0e-05)
        ledger = InferenceLedger(entries=(LedgerEntry(model=model, stage_count=1),), staged_count=9)
        per_image = service.per_image_usd(model)
        assert per_image is not None
        estimate = service.estimate_batch(ledger)
        assert estimate.total_usd == pytest.approx(per_image * 9)
        assert estimate.has_unknown is False
        # 1 ユニークモデル × 9 枚 = 9 ジョブ
        assert estimate.est_seconds == pytest.approx(9 * SECONDS_PER_JOB)

    def test_local_models_contribute_zero_cost_but_time(self):
        service = CostEstimationService()
        ledger = InferenceLedger(
            entries=(LedgerEntry(model=_local_model("wd-tagger"), stage_count=1),),
            staged_count=5,
        )
        estimate = service.estimate_batch(ledger)
        assert estimate.total_usd == 0.0
        assert estimate.has_unknown is False
        assert estimate.est_seconds == pytest.approx(5 * SECONDS_PER_JOB)

    def test_unknown_pricing_sets_flag_and_excludes_from_total(self):
        service = CostEstimationService()
        priced = _api_model("openai/gpt-4o", 2.5e-06, 1.0e-05)
        unpriced = _api_model("anthropic/claude-x", None, None)
        ledger = InferenceLedger(
            entries=(
                LedgerEntry(model=priced, stage_count=1),
                LedgerEntry(model=unpriced, stage_count=1),
            ),
            staged_count=4,
        )
        per_image = service.per_image_usd(priced)
        assert per_image is not None
        estimate = service.estimate_batch(ledger)
        assert estimate.has_unknown is True
        # unpriced は合計から除外され priced のみ寄与
        assert estimate.total_usd == pytest.approx(per_image * 4)


class TestFormatHelpers:
    def test_format_local_is_free(self):
        assert format_per_image_cost(0.0, is_api=False) == "ローカル（無料）"

    def test_format_unknown_is_dash(self):
        assert format_per_image_cost(None, is_api=True) == "—"

    def test_format_api_cost_4_decimals(self):
        assert format_per_image_cost(0.00775, is_api=True) == "$0.0077/img"

    def test_format_duration_seconds(self):
        assert format_duration(48) == "48s"

    def test_format_duration_minutes(self):
        assert format_duration(162) == "2m42s"
