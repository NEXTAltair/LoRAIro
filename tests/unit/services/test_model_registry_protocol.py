# tests/unit/services/test_model_registry_protocol.py

"""model_registry_protocol.py のユニットテスト"""

from unittest.mock import patch

import pytest

from lorairo.services.model_registry_protocol import (
    ModelInfo,
    NullModelRegistry,
    _infer_capabilities_min,
    map_annotator_metadata_to_model_info,
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


class TestMapAnnotatorMetadataToModelInfo:
    """map_annotator_metadata_to_model_info() の変換ロジックテスト"""

    def test_empty_list_returns_empty(self) -> None:
        assert map_annotator_metadata_to_model_info([]) == []

    def test_full_fields_mapped_correctly(self) -> None:
        items = [
            {
                "name": "gpt-4-vision",
                "provider": "openai",
                "api_model_id": "gpt-4-vision-preview",
                "requires_api_key": True,
                "estimated_size_gb": 0.5,
                "model_type": "multimodal",
            }
        ]
        result = map_annotator_metadata_to_model_info(items)
        assert len(result) == 1
        info = result[0]
        assert info.name == "gpt-4-vision"
        assert info.provider == "openai"
        assert info.api_model_id == "gpt-4-vision-preview"
        assert info.requires_api_key is True
        assert info.estimated_size_gb == 0.5

    def test_returns_model_info_instances(self) -> None:
        result = map_annotator_metadata_to_model_info([{"name": "test-model"}])
        assert isinstance(result[0], ModelInfo)

    def test_multiple_items_all_processed(self) -> None:
        items = [
            {"name": "model-a", "provider": "openai"},
            {"name": "model-b", "provider": "anthropic"},
            {"name": "model-c", "provider": "google"},
        ]
        result = map_annotator_metadata_to_model_info(items)
        assert len(result) == 3
        assert result[0].name == "model-a"
        assert result[2].name == "model-c"

    # name フィールドの正規化
    def test_name_none_becomes_empty_string(self) -> None:
        result = map_annotator_metadata_to_model_info([{"name": None}])
        assert result[0].name == ""

    def test_name_missing_becomes_empty_string(self) -> None:
        result = map_annotator_metadata_to_model_info([{}])
        assert result[0].name == ""

    # provider フィールドの正規化
    def test_provider_none_becomes_unknown(self) -> None:
        result = map_annotator_metadata_to_model_info([{"provider": None}])
        assert result[0].provider == "unknown"

    def test_provider_non_string_becomes_unknown(self) -> None:
        result = map_annotator_metadata_to_model_info([{"provider": 42}])
        assert result[0].provider == "unknown"

    def test_provider_empty_string_becomes_unknown(self) -> None:
        result = map_annotator_metadata_to_model_info([{"provider": ""}])
        assert result[0].provider == "unknown"

    def test_provider_missing_becomes_unknown(self) -> None:
        result = map_annotator_metadata_to_model_info([{}])
        assert result[0].provider == "unknown"

    def test_provider_valid_string_preserved(self) -> None:
        result = map_annotator_metadata_to_model_info([{"provider": "openai"}])
        assert result[0].provider == "openai"

    # api_model_id フィールドの正規化
    def test_api_model_id_string_preserved(self) -> None:
        result = map_annotator_metadata_to_model_info([{"api_model_id": "claude-3-5-sonnet-20241022"}])
        assert result[0].api_model_id == "claude-3-5-sonnet-20241022"

    def test_api_model_id_none_stays_none(self) -> None:
        result = map_annotator_metadata_to_model_info([{"api_model_id": None}])
        assert result[0].api_model_id is None

    def test_api_model_id_missing_becomes_none(self) -> None:
        result = map_annotator_metadata_to_model_info([{}])
        assert result[0].api_model_id is None

    def test_api_model_id_int_becomes_none(self) -> None:
        result = map_annotator_metadata_to_model_info([{"api_model_id": 123}])
        assert result[0].api_model_id is None

    # requires_api_key フィールド
    def test_requires_api_key_true(self) -> None:
        result = map_annotator_metadata_to_model_info([{"requires_api_key": True}])
        assert result[0].requires_api_key is True

    def test_requires_api_key_defaults_to_false(self) -> None:
        result = map_annotator_metadata_to_model_info([{}])
        assert result[0].requires_api_key is False

    # estimated_size_gb フィールドの正規化
    def test_estimated_size_gb_float_preserved(self) -> None:
        result = map_annotator_metadata_to_model_info([{"estimated_size_gb": 7.5}])
        assert result[0].estimated_size_gb == 7.5

    def test_estimated_size_gb_int_cast_to_float(self) -> None:
        result = map_annotator_metadata_to_model_info([{"estimated_size_gb": 7}])
        assert result[0].estimated_size_gb == 7.0
        assert isinstance(result[0].estimated_size_gb, float)

    def test_estimated_size_gb_none_stays_none(self) -> None:
        result = map_annotator_metadata_to_model_info([{"estimated_size_gb": None}])
        assert result[0].estimated_size_gb is None

    def test_estimated_size_gb_string_becomes_none(self) -> None:
        result = map_annotator_metadata_to_model_info([{"estimated_size_gb": "7.5"}])
        assert result[0].estimated_size_gb is None

    def test_estimated_size_gb_missing_becomes_none(self) -> None:
        result = map_annotator_metadata_to_model_info([{}])
        assert result[0].estimated_size_gb is None


class TestInferCapabilitiesMin:
    """_infer_capabilities_min() の全分岐テスト"""

    # model_type による分岐
    def test_model_type_multimodal_returns_caption_tags(self) -> None:
        assert _infer_capabilities_min({"model_type": "multimodal"}) == ["caption", "tags"]

    def test_model_type_vision_returns_caption_tags(self) -> None:
        assert _infer_capabilities_min({"model_type": "vision"}) == ["caption", "tags"]

    def test_model_type_caption_returns_caption(self) -> None:
        assert _infer_capabilities_min({"model_type": "caption"}) == ["caption"]

    def test_model_type_tag_returns_tags(self) -> None:
        assert _infer_capabilities_min({"model_type": "tag"}) == ["tags"]

    def test_model_type_tagger_returns_tags(self) -> None:
        assert _infer_capabilities_min({"model_type": "tagger"}) == ["tags"]

    def test_model_type_score_returns_scores(self) -> None:
        assert _infer_capabilities_min({"model_type": "score"}) == ["scores"]

    def test_model_type_uppercase_normalized_before_match(self) -> None:
        assert _infer_capabilities_min({"model_type": "VISION"}) == ["caption", "tags"]

    def test_model_type_unknown_falls_through_to_name_logic(self) -> None:
        result = _infer_capabilities_min({"model_type": "custom_type", "name": "claude-3-sonnet"})
        assert result == ["caption", "tags"]

    # name による分岐（model_type なし）
    def test_name_gpt4_returns_caption_tags(self) -> None:
        assert _infer_capabilities_min({"name": "gpt-4-vision"}) == ["caption", "tags"]

    def test_name_claude_returns_caption_tags(self) -> None:
        assert _infer_capabilities_min({"name": "claude-3-5-sonnet"}) == ["caption", "tags"]

    def test_name_gemini_returns_caption_tags(self) -> None:
        assert _infer_capabilities_min({"name": "gemini-pro-vision"}) == ["caption", "tags"]

    def test_name_dalle_returns_caption(self) -> None:
        assert _infer_capabilities_min({"name": "dall-e-3"}) == ["caption"]

    def test_name_wd_prefix_returns_tags(self) -> None:
        assert _infer_capabilities_min({"name": "wd-1.4-tagger"}) == ["tags"]

    def test_name_danbooru_returns_tags(self) -> None:
        assert _infer_capabilities_min({"name": "danbooru-tagger"}) == ["tags"]

    def test_name_deepdanbooru_returns_tags(self) -> None:
        assert _infer_capabilities_min({"name": "deepdanbooru"}) == ["tags"]

    def test_name_swinv2_returns_tags(self) -> None:
        assert _infer_capabilities_min({"name": "swinv2-tagger"}) == ["tags"]

    def test_name_aesthetic_returns_scores(self) -> None:
        assert _infer_capabilities_min({"name": "aesthetic-predictor"}) == ["scores"]

    def test_name_musiq_returns_scores(self) -> None:
        assert _infer_capabilities_min({"name": "musiq-spaq"}) == ["scores"]

    def test_name_quality_returns_scores(self) -> None:
        assert _infer_capabilities_min({"name": "quality-evaluator"}) == ["scores"]

    def test_name_score_keyword_returns_scores(self) -> None:
        assert _infer_capabilities_min({"name": "score-predictor"}) == ["scores"]

    def test_name_clip_returns_scores(self) -> None:
        assert _infer_capabilities_min({"name": "clip-scorer"}) == ["scores"]

    # provider による分岐（model_type・name なし）
    def test_provider_openai_returns_caption_tags(self) -> None:
        assert _infer_capabilities_min({"provider": "openai"}) == ["caption", "tags"]

    def test_provider_anthropic_returns_caption_tags(self) -> None:
        assert _infer_capabilities_min({"provider": "anthropic"}) == ["caption", "tags"]

    def test_provider_google_returns_caption_tags(self) -> None:
        assert _infer_capabilities_min({"provider": "google"}) == ["caption", "tags"]

    # フォールバック
    def test_empty_dict_returns_caption_fallback(self) -> None:
        assert _infer_capabilities_min({}) == ["caption"]

    def test_unknown_provider_returns_caption_fallback(self) -> None:
        assert _infer_capabilities_min({"provider": "unknown_vendor", "name": "unknown-model"}) == [
            "caption"
        ]
