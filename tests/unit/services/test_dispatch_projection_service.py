"""dispatch_projection_service の単体テスト (#884 Phase 2b, ADR 0076 §2)。

Qt-free な射影ロジックを検証する。DB / Qt 依存なし、stub モデルで完結する。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from lorairo.services.dispatch_projection_service import (
    DispatchProjectionError,
    project_async_batch_dispatch,
)


class _StubModel:
    """provider_batch_capability helper が読む属性だけ持つ stub。"""

    def __init__(
        self,
        *,
        id: int,
        provider: str,
        litellm_model_id: str,
        model_types: tuple[Any, ...] = (),
    ) -> None:
        self.id = id
        self.provider = provider
        self.litellm_model_id = litellm_model_id
        self.model_types = model_types


def _resolver(models: list[_StubModel]) -> Callable[[str], _StubModel | None]:
    by_id = {m.litellm_model_id: m for m in models}
    return lambda litellm_id: by_id.get(litellm_id)


@pytest.mark.unit
class TestProjectAsyncBatchDispatch:
    def test_projects_one_entry_per_batch_capable_model(self) -> None:
        m1 = _StubModel(id=1, provider="openai", litellm_model_id="openai/gpt-4o")
        m2 = _StubModel(id=2, provider="anthropic", litellm_model_id="anthropic/claude-3-5-sonnet")
        proj = project_async_batch_dispatch(
            selected_litellm_model_ids=["openai/gpt-4o", "anthropic/claude-3-5-sonnet"],
            batch_capable_models=["openai/gpt-4o", "anthropic/claude-3-5-sonnet"],
            model_resolver=_resolver([m1, m2]),
            image_ids=[10, 11],
            prompt_profile="default",
        )
        assert proj.job_count == 2
        e1, e2 = proj.entries
        assert e1.litellm_model_id == "openai/gpt-4o"
        assert e1.model_id == 1
        assert e1.provider == "openai"
        assert e1.task_type == "annotation"
        assert e1.image_ids == (10, 11)
        assert e1.endpoint != ""
        assert e2.model_id == 2
        assert e2.provider == "anthropic"

    def test_partial_projection_routes_non_batch_to_ineligible(self) -> None:
        # #1133: 非 batch-capable 混在は拒否せず ineligible として返す (部分射影を許可)。
        m1 = _StubModel(id=1, provider="openai", litellm_model_id="openai/gpt-4o")
        m_local = _StubModel(id=9, provider="local", litellm_model_id="local/wd-tagger")
        proj = project_async_batch_dispatch(
            selected_litellm_model_ids=["openai/gpt-4o", "local/wd-tagger"],
            batch_capable_models=["openai/gpt-4o"],
            model_resolver=_resolver([m1, m_local]),
            image_ids=[10],
            prompt_profile="default",
        )
        assert proj.job_count == 1
        assert proj.entries[0].litellm_model_id == "openai/gpt-4o"
        assert proj.ineligible_litellm_model_ids == ("local/wd-tagger",)

    def test_unresolved_model_becomes_ineligible(self) -> None:
        # #1133: DB 解決できないモデルも拒否せず ineligible へ (呼び出し側が同期で扱う)。
        m1 = _StubModel(id=1, provider="openai", litellm_model_id="openai/gpt-4o")
        proj = project_async_batch_dispatch(
            selected_litellm_model_ids=["openai/gpt-4o", "openai/unknown"],
            batch_capable_models=["openai/gpt-4o", "openai/unknown"],
            model_resolver=_resolver([m1]),
            image_ids=[10],
            prompt_profile="default",
        )
        assert proj.job_count == 1
        assert proj.ineligible_litellm_model_ids == ("openai/unknown",)

    def test_empty_selection_raises(self) -> None:
        with pytest.raises(DispatchProjectionError):
            project_async_batch_dispatch(
                selected_litellm_model_ids=[],
                batch_capable_models=["openai/gpt-4o"],
                model_resolver=lambda _litellm_id: None,
                image_ids=[10],
                prompt_profile="default",
            )

    def test_empty_images_raises(self) -> None:
        m1 = _StubModel(id=1, provider="openai", litellm_model_id="openai/gpt-4o")
        with pytest.raises(DispatchProjectionError):
            project_async_batch_dispatch(
                selected_litellm_model_ids=["openai/gpt-4o"],
                batch_capable_models=["openai/gpt-4o"],
                model_resolver=_resolver([m1]),
                image_ids=[],
                prompt_profile="default",
            )

    def test_carries_prompt_profile_description_and_image_paths(self) -> None:
        # ADR 0076 §2: model_id / prompt_profile / description / processed パスを契約に含める。
        m1 = _StubModel(id=1, provider="openai", litellm_model_id="openai/gpt-4o")
        proj = project_async_batch_dispatch(
            selected_litellm_model_ids=["openai/gpt-4o"],
            batch_capable_models=["openai/gpt-4o"],
            model_resolver=_resolver([m1]),
            image_ids=[10, 11],
            prompt_profile="detailed",
            description="my batch",
            image_paths={10: "/data/p10.webp", 11: "/data/p11.webp"},
        )
        e = proj.entries[0]
        assert e.prompt_profile == "detailed"
        assert e.description == "my batch"
        assert e.image_paths == {10: "/data/p10.webp", 11: "/data/p11.webp"}

    def test_moderation_model_ineligible_for_annotation(self) -> None:
        # #1133: omni-moderation は annotation route 非対応 → 拒否せず ineligible。
        m_mod = _StubModel(id=5, provider="openai", litellm_model_id="openai/omni-moderation-latest")
        proj = project_async_batch_dispatch(
            selected_litellm_model_ids=["openai/omni-moderation-latest"],
            batch_capable_models=["openai/omni-moderation-latest"],
            model_resolver=_resolver([m_mod]),
            image_ids=[10],
            prompt_profile="default",
        )
        assert proj.entries == ()
        assert proj.ineligible_litellm_model_ids == ("openai/omni-moderation-latest",)

    def test_deduplicates_selected_ids_preserving_order(self) -> None:
        m1 = _StubModel(id=1, provider="openai", litellm_model_id="openai/gpt-4o")
        proj = project_async_batch_dispatch(
            selected_litellm_model_ids=["openai/gpt-4o", "openai/gpt-4o"],
            batch_capable_models=["openai/gpt-4o"],
            model_resolver=_resolver([m1]),
            image_ids=[10],
            prompt_profile="default",
        )
        assert proj.job_count == 1
