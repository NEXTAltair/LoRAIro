"""AnnotatorLibraryAdapter model registry tests."""

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from lorairo.annotations.annotator_adapter import AnnotatorLibraryAdapter

# --- _infer_provider のテスト用ダミー ---


@dataclass(frozen=True)
class _FakeAnnotatorInfo:
    name: str
    is_api: bool


@pytest.mark.unit
class TestInferProvider:
    """_infer_provider がモデル名からプロバイダーを推論することを検証する (P1修正)。"""

    def _make(self, name: str, is_api: bool) -> _FakeAnnotatorInfo:
        return _FakeAnnotatorInfo(name=name, is_api=is_api)

    def test_local_model_returns_none(self):
        info = self._make("wd-v1-4-tagger", is_api=False)
        assert AnnotatorLibraryAdapter._infer_provider(info) is None  # type: ignore[arg-type]

    def test_claude_returns_anthropic(self):
        info = self._make("Claude-3-Opus", is_api=True)
        assert AnnotatorLibraryAdapter._infer_provider(info) == "anthropic"  # type: ignore[arg-type]

    def test_gpt_returns_openai(self):
        info = self._make("GPT-4o", is_api=True)
        assert AnnotatorLibraryAdapter._infer_provider(info) == "openai"  # type: ignore[arg-type]

    def test_gemini_returns_google(self):
        info = self._make("gemini-2.5-pro", is_api=True)
        assert AnnotatorLibraryAdapter._infer_provider(info) == "google"  # type: ignore[arg-type]

    def test_unknown_api_model_returns_none(self):
        info = self._make("unknown-cloud-model", is_api=True)
        assert AnnotatorLibraryAdapter._infer_provider(info) is None  # type: ignore[arg-type]


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
    """adapter.list_annotator_info() がライブラリ戻り値をそのまま返すことを検証する (Issue #220)."""
    adapter = AnnotatorLibraryAdapter(MagicMock())
    fake_infos = [
        _FakeAnnotatorInfo(name="wd-v1-4-tagger", is_api=False),
        _FakeAnnotatorInfo(name="gpt-4o", is_api=True),
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
    """ライブラリ例外は呼び出し元に伝播することを検証する (Issue #220)."""
    adapter = AnnotatorLibraryAdapter(MagicMock())

    with patch(
        "lorairo.annotations.annotator_adapter.list_annotator_info",
        side_effect=RuntimeError("registry not initialized"),
    ):
        with pytest.raises(RuntimeError, match="registry not initialized"):
            adapter.list_annotator_info()
