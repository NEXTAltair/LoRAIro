# tests/unit/services/test_model_registry_protocol.py

"""model_registry_protocol.py のユニットテスト

Issue #225: dict ヘルパー (`map_annotator_metadata_to_model_info`,
`_infer_capabilities_min`) を削除。Protocol と NullModelRegistry のみ残存。
"""

from unittest.mock import Mock, patch

import pytest

from lorairo.services.model_registry_protocol import (
    NullModelRegistry,
    selection_includes_webapi_model,
)


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


class TestSelectionIncludesWebApiModel:
    """`selection_includes_webapi_model()` の単体テスト。

    ADR 0023 Phase 1.5 (Issue #42) / Codex P1 (PR #233 r3208397315):
    refusal 送信前 filter は WebAPI モデル選択時のみ適用すべきという contract を
    回帰テストで保証する。Codex P2 (PR #233 r3209342204) の Worker 移動に伴い、
    helper 自体は services/ 層 (Qt-free) に移設された。
    """

    @staticmethod
    def _model_info(name: str, requires_api_key: bool):
        info = Mock()
        info.name = name
        info.requires_api_key = requires_api_key
        return info

    def _registry(self, models):
        registry = Mock()
        registry.get_available_models.return_value = list(models)
        return registry

    def test_returns_true_when_webapi_model_selected(self) -> None:
        """少なくとも 1 つ requires_api_key=True のモデルが選択されていれば True。"""
        registry = self._registry(
            [
                self._model_info("openai/gpt-4o", requires_api_key=True),
                self._model_info("wd-v1-4-tagger", requires_api_key=False),
            ]
        )
        assert selection_includes_webapi_model(["openai/gpt-4o"], registry) is True

    def test_returns_false_when_only_local_models_selected(self) -> None:
        """ローカルモデル単独選択時は False (Codex P1 回帰防止: filter 適用しない)。"""
        registry = self._registry(
            [
                self._model_info("openai/gpt-4o", requires_api_key=True),
                self._model_info("wd-v1-4-tagger", requires_api_key=False),
                self._model_info("aesthetic-predictor", requires_api_key=False),
            ]
        )
        assert selection_includes_webapi_model(["wd-v1-4-tagger", "aesthetic-predictor"], registry) is False

    def test_returns_true_with_mixed_selection(self) -> None:
        """ローカル + WebAPI の混在選択時は True (1 つでも WebAPI なら filter 適用)。"""
        registry = self._registry(
            [
                self._model_info("openai/gpt-4o", requires_api_key=True),
                self._model_info("wd-v1-4-tagger", requires_api_key=False),
            ]
        )
        assert selection_includes_webapi_model(["wd-v1-4-tagger", "openai/gpt-4o"], registry) is True

    def test_returns_false_for_unknown_model_name(self) -> None:
        """registry に未登録のモデル名は WebAPI 扱いしない (defensive default)。"""
        registry = self._registry([self._model_info("openai/gpt-4o", requires_api_key=True)])
        assert selection_includes_webapi_model(["unknown-model"], registry) is False

    def test_returns_false_for_empty_selection(self) -> None:
        """空リストは False (early return、registry を引かない)。"""
        registry = self._registry([self._model_info("openai/gpt-4o", requires_api_key=True)])
        assert selection_includes_webapi_model([], registry) is False
        registry.get_available_models.assert_not_called()

    def test_propagates_registry_exception(self) -> None:
        """registry が例外を raise した場合は呼び出し元で吸収する契約。

        本 helper は pure な分類関数で、例外吸収は caller (`AnnotationWorker._apply_refusal_prefilter`)
        の責務 (Codex P2: PR #233 r3208793528)。
        """
        registry = Mock()
        registry.get_available_models.side_effect = RuntimeError("registry unavailable")
        with pytest.raises(RuntimeError, match="registry unavailable"):
            selection_includes_webapi_model(["openai/gpt-4o"], registry)
