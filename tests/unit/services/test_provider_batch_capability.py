"""provider_batch_capability ユニットテスト。

ADR 0041: Qt-free helper の pure ロジックを検証する。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from lorairo.services.provider_batch_capability import (
    direct_provider_for_model,
    endpoint_for_task,
    litellm_id_from_batch_model,
    model_supports_task_type,
)


def _model(
    provider: str = "openai",
    litellm_model_id: str = "openai/gpt-4.1-mini",
    model_types: tuple = (),
) -> SimpleNamespace:
    """テスト用軽量 Model ファクトリ。"""
    return SimpleNamespace(
        provider=provider,
        litellm_model_id=litellm_model_id,
        model_types=model_types,
    )


def _model_type(name: str) -> SimpleNamespace:
    """テスト用 ModelType ファクトリ。"""
    return SimpleNamespace(name=name)


# ---------------------------------------------------------------------------
# direct_provider_for_model
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDirectProviderForModel:
    def test_openai_provider_returns_openai(self) -> None:
        model = _model(provider="openai", litellm_model_id="openai/gpt-4.1-mini")
        assert direct_provider_for_model(model) == "openai"

    def test_anthropic_provider_returns_anthropic(self) -> None:
        model = _model(provider="anthropic", litellm_model_id="anthropic/claude-3-5-sonnet")
        assert direct_provider_for_model(model) == "anthropic"

    def test_openrouter_provider_with_openai_litellm_id_returns_none(self) -> None:
        """OpenRouter route は direct でないため None を返す。"""
        model = _model(provider="openrouter", litellm_model_id="openrouter/openai/gpt-4.1-mini")
        assert direct_provider_for_model(model) is None

    def test_unknown_provider_with_openai_prefix_litellm_id_returns_openai(self) -> None:
        """provider フィールドが空でも litellm_id プレフィックスで解決できる。"""
        model = _model(provider="", litellm_model_id="openai/gpt-4.1-mini")
        assert direct_provider_for_model(model) == "openai"

    def test_unknown_provider_returns_none(self) -> None:
        model = _model(provider="google", litellm_model_id="google/gemini-pro")
        assert direct_provider_for_model(model) is None

    def test_provider_case_insensitive(self) -> None:
        model = _model(provider="OpenAI", litellm_model_id="openai/gpt-4o")
        assert direct_provider_for_model(model) == "openai"


# ---------------------------------------------------------------------------
# litellm_id_from_batch_model
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLitellmIdFromBatchModel:
    def test_string_input_returned_as_is(self) -> None:
        assert litellm_id_from_batch_model("openai/gpt-4.1-mini") == "openai/gpt-4.1-mini"

    def test_object_with_litellm_model_id_attr(self) -> None:
        raw = SimpleNamespace(litellm_model_id="anthropic/claude-3-5-sonnet")
        assert litellm_id_from_batch_model(raw) == "anthropic/claude-3-5-sonnet"

    def test_object_with_model_id_attr_fallback(self) -> None:
        raw = SimpleNamespace(model_id="openai/gpt-4o")
        assert litellm_id_from_batch_model(raw) == "openai/gpt-4o"

    def test_object_with_name_attr_fallback(self) -> None:
        raw = SimpleNamespace(name="openai/gpt-4o-mini")
        assert litellm_id_from_batch_model(raw) == "openai/gpt-4o-mini"

    def test_object_with_no_relevant_attr_returns_none(self) -> None:
        raw = SimpleNamespace(foo="bar")
        assert litellm_id_from_batch_model(raw) is None

    def test_none_value_returns_none(self) -> None:
        raw = SimpleNamespace(litellm_model_id=None)
        assert litellm_id_from_batch_model(raw) is None


# ---------------------------------------------------------------------------
# endpoint_for_task
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestEndpointForTask:
    def test_annotation_openai_returns_chat_completions(self) -> None:
        assert endpoint_for_task("openai", "annotation") == "/v1/chat/completions"

    def test_annotation_anthropic_returns_messages(self) -> None:
        assert endpoint_for_task("anthropic", "annotation") == "/v1/messages"

    def test_rating_preflight_openai_returns_moderations(self) -> None:
        assert endpoint_for_task("openai", "rating_preflight") == "/v1/moderations"

    def test_rating_preflight_anthropic_raises(self) -> None:
        """rating_preflight は anthropic をサポートしない。"""
        with pytest.raises(ValueError):
            endpoint_for_task("anthropic", "rating_preflight")

    def test_unknown_task_type_raises(self) -> None:
        with pytest.raises(ValueError):
            endpoint_for_task("openai", "unknown_task")


# ---------------------------------------------------------------------------
# model_supports_task_type
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestModelSupportsTaskType:
    # annotation: openai + anthropic 両方許可 (ADR 0041 修正)
    def test_annotation_openai_allowed(self) -> None:
        model = _model(provider="openai", litellm_model_id="openai/gpt-4.1-mini")
        assert model_supports_task_type(model, "openai", "annotation") is True

    def test_annotation_anthropic_allowed(self) -> None:
        """ADR 0041: annotation は anthropic も許可 (旧 GUI バグ修正)。"""
        model = _model(provider="anthropic", litellm_model_id="anthropic/claude-3-5-sonnet")
        assert model_supports_task_type(model, "anthropic", "annotation") is True

    def test_annotation_unknown_provider_not_allowed(self) -> None:
        model = _model(provider="google", litellm_model_id="google/gemini-pro")
        assert model_supports_task_type(model, "google", "annotation") is False

    def test_annotation_omni_moderation_excluded(self) -> None:
        """ADR 0038: moderation 専用モデルは annotation (/v1/chat/completions) では不可。"""
        model = _model(provider="openai", litellm_model_id="openai/omni-moderation-latest")
        assert model_supports_task_type(model, "openai", "annotation") is False

    # rating_preflight: openai かつ omni-moderation-* のみ
    def test_rating_preflight_omni_moderation_latest_allowed(self) -> None:
        model = _model(
            provider="openai",
            litellm_model_id="openai/omni-moderation-latest",
        )
        assert model_supports_task_type(model, "openai", "rating_preflight") is True

    def test_rating_preflight_omni_moderation_versioned_allowed(self) -> None:
        model = _model(
            provider="openai",
            litellm_model_id="openai/omni-moderation-2024-09-26",
        )
        assert model_supports_task_type(model, "openai", "rating_preflight") is True

    def test_rating_preflight_gpt4_not_allowed(self) -> None:
        """omni-moderation-* 以外の openai モデルは rating_preflight 不可。"""
        model = _model(provider="openai", litellm_model_id="openai/gpt-4.1-mini")
        assert model_supports_task_type(model, "openai", "rating_preflight") is False

    def test_rating_preflight_anthropic_not_allowed(self) -> None:
        """rating_preflight は anthropic をサポートしない。"""
        model = _model(provider="anthropic", litellm_model_id="anthropic/claude-3-5-sonnet")
        assert model_supports_task_type(model, "anthropic", "rating_preflight") is False

    def test_rating_preflight_openrouter_omni_mod_not_allowed(self) -> None:
        """openrouter 経由の omni-moderation は直接 openai でないため不可。"""
        model = _model(
            provider="openrouter",
            litellm_model_id="openrouter/openai/omni-moderation-latest",
        )
        assert model_supports_task_type(model, "openrouter", "rating_preflight") is False

    def test_unknown_task_type_returns_false(self) -> None:
        model = _model()
        assert model_supports_task_type(model, "openai", "unknown_task") is False
