# tests/unit/services/test_model_registry_protocol.py

"""model_registry_protocol.py のユニットテスト

Issue #225: dict ヘルパー (`map_annotator_metadata_to_model_info`,
`_infer_capabilities_min`) を削除。Protocol と NullModelRegistry のみ残存。
"""

from unittest.mock import patch

from lorairo.services.model_registry_protocol import NullModelRegistry


class TestNullModelRegistry:
    """NullModelRegistry のユニットテスト"""

    def test_get_available_models_returns_empty_list(self) -> None:
        registry = NullModelRegistry()
        assert registry.get_available_models() == []

    def test_get_available_models_logs_info(self) -> None:
        registry = NullModelRegistry()
        with patch("lorairo.services.model_registry_protocol.logger") as mock_logger:
            registry.get_available_models()
            mock_logger.info.assert_called_once()

    def test_get_available_models_with_metadata_returns_empty_list(self) -> None:
        registry = NullModelRegistry()
        assert registry.get_available_models_with_metadata() == []

    def test_get_available_models_with_metadata_logs_info(self) -> None:
        registry = NullModelRegistry()
        with patch("lorairo.services.model_registry_protocol.logger") as mock_logger:
            registry.get_available_models_with_metadata()
            mock_logger.info.assert_called_once()
