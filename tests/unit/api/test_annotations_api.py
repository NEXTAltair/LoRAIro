"""Annotations API テスト。"""

from unittest.mock import MagicMock

import pytest

from lorairo.api.annotations import annotate_images
from lorairo.api.exceptions import APIKeyNotConfiguredError
from lorairo.api.types import AnnotationResult
from lorairo.services.service_container import ServiceContainer


@pytest.fixture
def mock_config_service(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """ConfigurationService をモック。

    Args:
        monkeypatch: pytest monkeypatch フィクスチャ

    Returns:
        MagicMock: モック化された ConfigurationService
    """
    mock_config = MagicMock()
    mock_config.get_setting.return_value = ""

    container = ServiceContainer()
    monkeypatch.setattr(container, "_config_service", mock_config)

    return mock_config


@pytest.mark.unit
class TestAnnotateImages:
    """annotate_images API テスト。"""

    def test_returns_annotation_result(self, mock_config_service: MagicMock) -> None:
        """AnnotationResult が返る。"""
        # APIキーチェックをバイパス（unknown model）
        result = annotate_images(["unknown-model"], image_ids=[1, 2, 3])

        assert isinstance(result, AnnotationResult)
        assert result.image_count == 3

    def test_no_image_ids(self, mock_config_service: MagicMock) -> None:
        """image_ids未指定で image_count=0。"""
        result = annotate_images(["unknown-model"])

        assert result.image_count == 0

    def test_openai_key_missing(self, mock_config_service: MagicMock) -> None:
        """OpenAI APIキー未設定で例外。"""
        mock_config_service.get_setting.return_value = ""

        with pytest.raises(APIKeyNotConfiguredError) as exc_info:
            annotate_images(["gpt-4o-mini"])

        assert "openai" in str(exc_info.value).lower()

    def test_claude_key_missing(self, mock_config_service: MagicMock) -> None:
        """Claude APIキー未設定で例外。"""
        mock_config_service.get_setting.return_value = ""

        with pytest.raises(APIKeyNotConfiguredError) as exc_info:
            annotate_images(["claude-opus"])

        assert "claude" in str(exc_info.value).lower()

    def test_google_key_missing(self, mock_config_service: MagicMock) -> None:
        """Google APIキー未設定で例外。"""
        mock_config_service.get_setting.return_value = ""

        with pytest.raises(APIKeyNotConfiguredError) as exc_info:
            annotate_images(["gemini-pro"])

        assert "google" in str(exc_info.value).lower()

    def test_openai_key_configured(self, mock_config_service: MagicMock) -> None:
        """OpenAI APIキー設定済みなら例外なし。"""
        mock_config_service.get_setting.side_effect = lambda section, key: (
            "sk-test" if key == "openai_key" else ""
        )

        result = annotate_images(["gpt-4o-mini"], image_ids=[1])
        assert isinstance(result, AnnotationResult)
