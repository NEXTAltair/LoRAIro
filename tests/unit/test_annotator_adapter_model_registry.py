"""AnnotatorLibraryAdapter model registry tests."""

from unittest.mock import MagicMock, patch

import pytest

from lorairo.annotations.annotator_adapter import AnnotatorLibraryAdapter


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
