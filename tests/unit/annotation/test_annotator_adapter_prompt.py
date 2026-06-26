"""AnnotatorLibraryAdapter.annotate() の additional_prompt 引数渡しテスト。"""

from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from lorairo.annotation.annotator_adapter import AnnotatorLibraryAdapter


@pytest.fixture
def dummy_image() -> Image.Image:
    return Image.new("RGB", (64, 64))


@pytest.fixture
def adapter_with_prompt() -> AnnotatorLibraryAdapter:
    config_service = MagicMock()

    def get_setting(section: str, key: str, default: str = "") -> str:
        if section == "prompts" and key == "additional":
            return "test instruction"
        return default

    config_service.get_setting.side_effect = get_setting
    return AnnotatorLibraryAdapter(config_service)


@pytest.fixture
def adapter_without_prompt() -> AnnotatorLibraryAdapter:
    config_service = MagicMock()

    def get_setting(section: str, key: str, default: str = "") -> str:
        if section == "prompts" and key == "additional":
            return ""
        return default

    config_service.get_setting.side_effect = get_setting
    return AnnotatorLibraryAdapter(config_service)


@pytest.mark.unit
def test_annotate_passes_additional_prompt_to_lib(
    adapter_with_prompt: AnnotatorLibraryAdapter,
    dummy_image: Image.Image,
) -> None:
    """config に additional が設定されている場合、annotate() に渡されることを確認。"""
    with patch("image_annotator_lib.annotate") as mock_annotate:
        mock_annotate.return_value = {}
        adapter_with_prompt.annotate([dummy_image], ["openai/gpt-4o"])

    call_kwargs = mock_annotate.call_args.kwargs
    assert call_kwargs["additional_prompt"] == "test instruction"


@pytest.mark.unit
def test_annotate_passes_none_when_prompt_empty(
    adapter_without_prompt: AnnotatorLibraryAdapter,
    dummy_image: Image.Image,
) -> None:
    """config の additional が空文字列の場合、additional_prompt=None が渡されることを確認。"""
    with patch("image_annotator_lib.annotate") as mock_annotate:
        mock_annotate.return_value = {}
        adapter_without_prompt.annotate([dummy_image], ["openai/gpt-4o"])

    call_kwargs = mock_annotate.call_args.kwargs
    assert call_kwargs["additional_prompt"] is None
