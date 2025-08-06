# src/lorairo/gui/services/model_info_adapter.py

"""ModelInfo compatibility adapter for legacy code migration."""

from typing import Any

from ...services.model_registry_protocol import ModelInfo as ProtocolModelInfo


class ModelInfoDictAdapter:
    """Dict-style access adapter for Protocol-based ModelInfo.
    
    This adapter enables legacy code using dict-style access (model["key"])
    to work seamlessly with the new Protocol-based ModelInfo dataclass.
    
    Usage:
        protocol_model = ModelInfo(name="test", provider="openai", ...)
        dict_model = ModelInfoDictAdapter(protocol_model)
        name = dict_model["name"]  # Works like a dict
    """

    def __init__(self, model_info: ProtocolModelInfo):
        self._model_info = model_info

    def __getitem__(self, key: str) -> Any:
        """Enable dict-style access to ModelInfo fields."""
        if hasattr(self._model_info, key):
            return getattr(self._model_info, key)
        
        # Handle legacy field mappings
        legacy_mappings = {
            "model_type": self._infer_model_type(),
        }
        
        if key in legacy_mappings:
            return legacy_mappings[key]
            
        raise KeyError(f"Key '{key}' not found in ModelInfo")

    def __contains__(self, key: str) -> bool:
        """Check if key exists in ModelInfo."""
        return hasattr(self._model_info, key) or key in ["model_type"]

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-style get method with default fallback."""
        try:
            return self[key]
        except KeyError:
            return default

    def _infer_model_type(self) -> str:
        """Infer model_type from capabilities for legacy compatibility."""
        capabilities = self._model_info.capabilities
        
        # Legacy model_type inference based on capabilities
        if "caption" in capabilities and "tags" in capabilities:
            return "multimodal"
        elif "caption" in capabilities:
            return "caption"
        elif "tags" in capabilities:
            return "tag"
        elif "scores" in capabilities:
            return "score"
        else:
            return "unknown"

    # Direct access to underlying ModelInfo for type-safe code
    @property
    def model_info(self) -> ProtocolModelInfo:
        """Access underlying Protocol-based ModelInfo."""
        return self._model_info


def adapt_models_for_legacy(models: list[ProtocolModelInfo]) -> list[ModelInfoDictAdapter]:
    """Convert list of Protocol ModelInfo to dict-accessible adapters."""
    return [ModelInfoDictAdapter(model) for model in models]