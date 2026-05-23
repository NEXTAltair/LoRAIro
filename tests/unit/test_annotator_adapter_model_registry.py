"""AnnotatorLibraryAdapter model registry tests."""

from unittest.mock import MagicMock, patch

import pytest
from image_annotator_lib import AnnotatorInfo
from image_annotator_lib.core.types import TaskCapability

from lorairo.annotations.annotator_adapter import AnnotatorLibraryAdapter


def _make_info(
    name: str,
    *,
    is_api: bool,
    model_type: str = "vision",
    capabilities: set[TaskCapability] | None = None,
    provider: str | None = None,
    estimated_size_gb: float | None = None,
    litellm_model_id: str | None = None,
) -> AnnotatorInfo:
    return AnnotatorInfo(
        name=name,
        model_type=model_type,  # type: ignore[arg-type]
        capabilities=frozenset(capabilities or {TaskCapability.TAGS}),
        is_local=not is_api,
        is_api=is_api,
        device=None if is_api else "cuda",
        provider=provider,
        estimated_size_gb=estimated_size_gb,
        litellm_model_id=litellm_model_id,
    )


@pytest.mark.unit
def test_refresh_available_models_returns_discovered_models() -> None:
    adapter = AnnotatorLibraryAdapter(MagicMock())

    with patch(
        "lorairo.annotations.annotator_adapter.discover_available_vision_models",
        return_value={"models": ["openai/gpt-4.1-mini"], "metadata": {}},
    ) as mock_discover:
        result = adapter.refresh_available_models()

    assert result == ["openai/gpt-4.1-mini"]
    mock_discover.assert_called_once_with()


@pytest.mark.unit
def test_refresh_available_models_raises_on_discovery_error() -> None:
    """ADR 0023 Phase 1: 旧 API の `{"error": ...}` 戻り値経路は廃止された。

    新 `discover_available_vision_models()` は例外を内部で catch せず raise するため、
    adapter の `except Exception:` で受け再 raise されることを検証する。
    """
    adapter = AnnotatorLibraryAdapter(MagicMock())

    with patch(
        "lorairo.annotations.annotator_adapter.discover_available_vision_models",
        side_effect=RuntimeError("network unavailable"),
    ):
        with pytest.raises(RuntimeError, match="network unavailable"):
            adapter.refresh_available_models()


@pytest.mark.unit
def test_list_available_models_switches_active_and_all() -> None:
    adapter = AnnotatorLibraryAdapter(MagicMock())

    with (
        patch("lorairo.annotations.annotator_adapter.get_available_models", return_value=["active"]),
        patch("lorairo.annotations.annotator_adapter.list_all_models", return_value=["active", "old"]),
    ):
        assert adapter.list_available_models() == ["active"]
        assert adapter.list_available_models(include_deprecated=True) == ["active", "old"]


@pytest.mark.unit
def test_list_annotator_info_passes_through_library_result() -> None:
    """adapter.list_annotator_info() がライブラリ戻り値をそのまま返すことを検証する (Issue #220)"""
    adapter = AnnotatorLibraryAdapter(MagicMock())
    fake_infos = [
        _make_info("wd-v1-4-tagger", is_api=False, model_type="tagger"),
        _make_info("gpt-4o", is_api=True, model_type="vision"),
    ]

    with patch(
        "lorairo.annotations.annotator_adapter.list_annotator_info",
        return_value=fake_infos,
    ) as mock_lib:
        result = adapter.list_annotator_info()

    assert result == fake_infos
    mock_lib.assert_called_once_with()


@pytest.mark.unit
def test_list_annotator_info_propagates_library_exception() -> None:
    """ライブラリ例外は呼び出し元に伝播することを検証する (Issue #220)"""
    adapter = AnnotatorLibraryAdapter(MagicMock())

    with patch(
        "lorairo.annotations.annotator_adapter.list_annotator_info",
        side_effect=RuntimeError("registry not initialized"),
    ):
        with pytest.raises(RuntimeError, match="registry not initialized"):
            adapter.list_annotator_info()


# ---- Issue #225 follow-up: get_available_models のテスト ----


@pytest.mark.unit
def test_get_available_models_builds_model_info_with_provider() -> None:
    """登録済みモデルは AnnotatorInfo.provider から ModelInfo を組み立てる (Phase 2)"""
    adapter = AnnotatorLibraryAdapter(MagicMock())
    fake_infos = [
        _make_info(
            "wd-v1-4-tagger",
            is_api=False,
            model_type="tagger",
            capabilities={TaskCapability.TAGS},
            provider="smilingwolf",
            estimated_size_gb=1.2,
        )
    ]

    with patch("lorairo.annotations.annotator_adapter.list_annotator_info", return_value=fake_infos):
        models = adapter.get_available_models()

    assert len(models) == 1
    info = models[0]
    assert info.name == "wd-v1-4-tagger"
    assert info.provider == "smilingwolf"
    assert info.capabilities == ["tags"]
    assert info.requires_api_key is False
    assert info.estimated_size_gb == 1.2


@pytest.mark.unit
def test_get_available_models_unknown_provider_falls_back_to_unknown() -> None:
    """provider が未設定の API モデルは 'unknown' にフォールバック"""
    adapter = AnnotatorLibraryAdapter(MagicMock())
    fake_infos = [
        _make_info(
            "google/gemini-2.5-pro",
            is_api=True,
            model_type="vision",
            capabilities={TaskCapability.TAGS, TaskCapability.CAPTIONS},
            # provider=None (未設定) → "unknown" にフォールバック
        )
    ]

    with patch("lorairo.annotations.annotator_adapter.list_annotator_info", return_value=fake_infos):
        models = adapter.get_available_models()

    assert len(models) == 1
    assert models[0].provider == "unknown"
    assert models[0].requires_api_key is True
    assert set(models[0].capabilities) == {"tags", "captions"}


@pytest.mark.unit
def test_get_available_models_with_metadata_alias() -> None:
    """get_available_models_with_metadata は get_available_models と同じ結果を返す"""
    adapter = AnnotatorLibraryAdapter(MagicMock())

    with patch("lorairo.annotations.annotator_adapter.list_annotator_info", return_value=[]):
        assert adapter.get_available_models_with_metadata() == adapter.get_available_models()


# ---- Issue #366 regression: TaskCapability.RATINGS mapping ----


@pytest.mark.unit
def test_capability_values_includes_ratings() -> None:
    """`_CAPABILITY_VALUES` に `TaskCapability.RATINGS` mapping が存在することを保証する。

    Issue #366 回帰防止: ratings capability を宣言するモデル (canonical rater 等) で
    `_to_model_info()` が KeyError を投げ、`get_available_models()` が落ちて
    annotation 全体が degraded mode に入る事象を防ぐ。
    """
    from lorairo.annotations.annotator_adapter import _CAPABILITY_VALUES

    assert _CAPABILITY_VALUES[TaskCapability.RATINGS] == "ratings"


@pytest.mark.unit
def test_get_available_models_includes_ratings_capability() -> None:
    """ratings capability を含む AnnotatorInfo が KeyError なく ModelInfo へ変換される。

    Issue #366 回帰防止: `AnnotatorInfo.capabilities = {RATINGS, TAGS}` の
    フィクスチャを与え、`get_available_models()` が例外を出さず
    `ModelInfo.capabilities` に `"ratings"` を含むことを assert する。
    """
    adapter = AnnotatorLibraryAdapter(MagicMock())
    fake_infos = [
        _make_info(
            "wd-rating-v3",
            is_api=False,
            model_type="tagger",
            capabilities={TaskCapability.RATINGS, TaskCapability.TAGS},
            provider="smilingwolf",
        )
    ]

    with patch("lorairo.annotations.annotator_adapter.list_annotator_info", return_value=fake_infos):
        models = adapter.get_available_models()

    assert len(models) == 1
    assert set(models[0].capabilities) == {"ratings", "tags"}
