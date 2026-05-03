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
    api_model_id: str | None = None,
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
        api_model_id=api_model_id,
    )


@pytest.mark.unit
def test_refresh_available_models_returns_discovered_models() -> None:
    adapter = AnnotatorLibraryAdapter(MagicMock())

    with patch(
        "lorairo.annotations.annotator_adapter.discover_available_vision_models",
        return_value={"models": ["openai/gpt-4.1-mini"], "toml_data": {}},
    ) as mock_discover:
        result = adapter.refresh_available_models(force_refresh=True)

    assert result == ["openai/gpt-4.1-mini"]
    mock_discover.assert_called_once_with(force_refresh=True)


@pytest.mark.unit
def test_refresh_available_models_raises_on_discovery_error() -> None:
    adapter = AnnotatorLibraryAdapter(MagicMock())

    with patch(
        "lorairo.annotations.annotator_adapter.discover_available_vision_models",
        return_value={"error": "network unavailable"},
    ):
        with pytest.raises(RuntimeError, match="network unavailable"):
            adapter.refresh_available_models(force_refresh=True)


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
