"""AnnotatorLibAdapter ユニットテスト

Phase 4実装のアノテーターライブラリアダプター（Mock版・実装版）をテスト
"""

from unittest.mock import Mock, patch

import pytest
from PIL import Image

from lorairo.services.annotator_lib_adapter import AnnotatorLibAdapter, MockAnnotatorLibAdapter


class TestMockAnnotatorLibAdapter:
    """MockAnnotatorLibAdapter テスト"""

    @pytest.fixture
    def mock_config_service(self):
        """モック設定サービス"""
        mock_config = Mock()
        mock_config.get_setting.return_value = "test_key"
        return mock_config

    @pytest.fixture
    def mock_adapter(self, mock_config_service):
        """MockAnnotatorLibAdapter インスタンス"""
        return MockAnnotatorLibAdapter(mock_config_service)

    def test_initialization(self, mock_adapter, mock_config_service):
        """初期化テスト"""
        assert mock_adapter.config_service is mock_config_service

    def test_get_available_models_with_metadata(self, mock_adapter):
        """利用可能モデル一覧取得（Mock版）"""
        models = mock_adapter.get_available_models_with_metadata()

        assert isinstance(models, list)
        assert len(models) > 0

        # 各モデルの構造確認
        for model in models:
            assert "name" in model
            assert "class" in model
            assert "provider" in model
            assert "model_type" in model
            assert "requires_api_key" in model

        # 特定のモデルが含まれることを確認
        model_names = [m["name"] for m in models]
        assert "gpt-4o" in model_names
        assert "claude-3-5-sonnet" in model_names
        assert "wd-v1-4-swinv2-tagger" in model_names

    def test_get_unified_api_keys(self, mock_adapter, mock_config_service):
        """統合APIキー取得"""

        # 設定サービスのモック設定
        def mock_get_setting(section, key, default):
            api_keys = {
                ("api", "openai_key"): "test_openai_key",
                ("api", "claude_key"): "test_claude_key",
                ("api", "google_key"): "test_google_key",
            }
            return api_keys.get((section, key), default)

        mock_config_service.get_setting.side_effect = mock_get_setting

        api_keys = mock_adapter.get_unified_api_keys()

        assert isinstance(api_keys, dict)
        assert "openai" in api_keys
        assert "anthropic" in api_keys
        assert "google" in api_keys
        assert api_keys["openai"] == "test_openai_key"
        assert api_keys["anthropic"] == "test_claude_key"
        assert api_keys["google"] == "test_google_key"

    def test_call_annotate_with_mock_images(self, mock_adapter):
        """モック画像でのアノテーション実行"""
        # テスト用画像作成
        test_images = [Image.new("RGB", (100, 100), "red"), Image.new("RGB", (150, 150), "blue")]
        test_models = ["gpt-4o", "claude-3-5-sonnet"]
        test_phash_list = ["test_hash_1", "test_hash_2"]

        results = mock_adapter.call_annotate(
            images=test_images, models=test_models, phash_list=test_phash_list
        )

        assert isinstance(results, dict)
        assert len(results) == len(test_images)

        # 各画像の結果確認
        for phash in test_phash_list:
            assert phash in results
            for model in test_models:
                assert model in results[phash]
                result = results[phash][model]
                assert "formatted_output" in result
                assert "raw_response" in result

    def test_call_annotate_without_phash(self, mock_adapter):
        """pHashなしでのアノテーション実行"""
        test_images = [Image.new("RGB", (100, 100), "green")]
        test_models = ["gpt-4o"]

        results = mock_adapter.call_annotate(images=test_images, models=test_models)

        assert isinstance(results, dict)
        assert len(results) == len(test_images)

        # 自動生成されたpHashキーが存在することを確認
        phash_keys = list(results.keys())
        assert len(phash_keys) == 1
        assert phash_keys[0].startswith("mock_phash_")

    def test_call_annotate_with_api_keys(self, mock_adapter):
        """外部APIキー使用でのアノテーション実行"""
        test_images = [Image.new("RGB", (100, 100), "yellow")]
        test_models = ["gpt-4o"]
        external_api_keys = {"openai": "external_openai_key", "anthropic": "external_claude_key"}

        results = mock_adapter.call_annotate(
            images=test_images, models=test_models, api_keys=external_api_keys
        )

        assert isinstance(results, dict)
        assert len(results) == len(test_images)

    def test_call_annotate_empty_inputs(self, mock_adapter):
        """空入力でのアノテーション実行"""
        results = mock_adapter.call_annotate(images=[], models=[])

        assert isinstance(results, dict)
        assert len(results) == 0

    def test_mock_response_structure(self, mock_adapter):
        """モックレスポンス構造確認"""
        test_images = [Image.new("RGB", (100, 100), "white")]
        test_models = ["gpt-4o"]

        results = mock_adapter.call_annotate(images=test_images, models=test_models)

        phash = next(iter(results.keys()))
        model_result = results[phash]["gpt-4o"]

        # 期待される構造
        assert "formatted_output" in model_result
        assert "raw_response" in model_result

        formatted = model_result["formatted_output"]
        if isinstance(formatted, dict):
            # vision モデルの場合
            assert "captions" in formatted or "tags" in formatted

        # raw_response構造
        raw = model_result["raw_response"]
        assert isinstance(raw, dict)


class TestAnnotatorLibAdapter:
    """AnnotatorLibAdapter (実装版) テスト"""

    @pytest.fixture
    def mock_config_service(self):
        """モック設定サービス"""
        mock_config = Mock()
        mock_config.get_setting.return_value = "test_key"
        return mock_config

    @pytest.fixture
    def real_adapter(self, mock_config_service):
        """AnnotatorLibAdapter インスタンス"""
        return AnnotatorLibAdapter(mock_config_service)

    def test_initialization(self, real_adapter, mock_config_service):
        """初期化テスト"""
        assert real_adapter.config_service is mock_config_service

    @patch("image_annotator_lib.core.registry.list_available_annotators_with_metadata")
    def test_get_available_models_with_metadata_success(self, mock_list_func, real_adapter):
        """実ライブラリから利用可能モデル一覧取得成功"""
        # モックライブラリレスポンス（実装では辞書の値のリストを返す）
        mock_library_response = {
            "gpt-4o": {
                "name": "gpt-4o",
                "class": "PydanticAIWebAPIAnnotator",
                "provider": "openai",
                "api_model_id": "gpt-4o",
                "model_type": "vision",
                "requires_api_key": True,
            },
            "wd-tagger": {
                "name": "wd-tagger",
                "class": "WDTagger",
                "provider": None,
                "api_model_id": None,
                "model_type": "tagger",
                "requires_api_key": False,
            },
        }
        mock_list_func.return_value = mock_library_response

        models = real_adapter.get_available_models_with_metadata()

        assert isinstance(models, list)
        assert len(models) == 2

        # 実装では list(raw_metadata.values()) を返すため、辞書の値を確認
        for model in models:
            assert "name" in model
            assert "class" in model
            assert "provider" in model
            assert "model_type" in model
            assert "requires_api_key" in model

        # 特定のモデルが含まれることを確認
        model_names = [m["name"] for m in models]
        assert "gpt-4o" in model_names
        assert "wd-tagger" in model_names

    @patch("image_annotator_lib.core.registry.list_available_annotators_with_metadata")
    def test_get_available_models_with_metadata_import_error(self, mock_list_func, real_adapter):
        """ImportError時のフォールバック"""
        mock_list_func.side_effect = ImportError("Library not available")

        models = real_adapter.get_available_models_with_metadata()

        # MockAnnotatorLibAdapterにフォールバック
        assert isinstance(models, list)
        assert len(models) > 0  # モックデータが返される
        # モックアダプターの既知のモデルが含まれることを確認
        model_names = [m["name"] for m in models]
        assert "gpt-4o" in model_names
        assert "claude-3-5-sonnet" in model_names

    def test_call_annotate_success_mock_fallback(self, real_adapter):
        """実ライブラリでのアノテーション実行（フォールバック動作確認）"""
        # 実際の実装では常にMockProviderManagerを使用
        test_images = [Image.new("RGB", (100, 100), "red")]
        test_models = ["gpt-4o"]
        test_phash_list = ["test_phash"]

        results = real_adapter.call_annotate(
            images=test_images, models=test_models, phash_list=test_phash_list
        )

        assert isinstance(results, dict)
        assert len(results) > 0

        # MockProviderManagerの実際のレスポンス構造確認
        first_phash = next(iter(results.keys()))
        assert "gpt-4o" in results[first_phash]

        model_result = results[first_phash]["gpt-4o"]
        assert "tags" in model_result
        assert "formatted_output" in model_result
        assert "error" in model_result
        assert model_result["error"] is None  # 成功時はエラーなし

    def test_call_annotate_with_api_keys(self, real_adapter):
        """外部APIキー使用でのアノテーション実行"""
        test_images = [Image.new("RGB", (100, 100), "blue")]
        test_models = ["gpt-4o"]
        external_api_keys = {"openai": "external_key"}

        # MockProviderManagerでの処理確認
        with patch.object(real_adapter.provider_manager, "run_inference_with_model") as mock_inference:
            mock_inference.return_value = {
                "mock_phash_0": {
                    "tags": ["test_tag"],
                    "formatted_output": {"captions": ["Test caption"]},
                    "error": None,
                }
            }

            results = real_adapter.call_annotate(
                images=test_images, models=test_models, api_keys=external_api_keys
            )

            # MockProviderManagerが正しい引数で呼ばれたことを確認
            mock_inference.assert_called_once_with(
                model_name="gpt-4o",
                images_list=test_images,
                api_model_id="gpt-4o",
                api_keys=external_api_keys,
            )

            assert isinstance(results, dict)
            assert len(results) > 0

    def test_call_annotate_provider_error_fallback(self, real_adapter):
        """ProviderManager実行時エラーのハンドリング"""
        test_images = [Image.new("RGB", (100, 100), "green")]
        test_models = ["gpt-4o"]

        # ProviderManagerがエラーを投げる場合のテスト
        with patch.object(real_adapter.provider_manager, "run_inference_with_model") as mock_inference:
            mock_inference.side_effect = Exception("Provider error")

            results = real_adapter.call_annotate(images=test_images, models=test_models)

            # エラーでも空の結果が返される（continue処理）
            assert isinstance(results, dict)
            # エラー時は結果が空になる
            assert len(results) == 0

    def test_call_annotate_multiple_models_error_handling(self, real_adapter):
        """複数モデル処理時のエラーハンドリング"""
        test_images = [Image.new("RGB", (100, 100), "purple")]
        test_models = ["gpt-4o", "claude-3-5-sonnet"]

        # 一つのモデルでエラー、もう一つで成功
        def mock_inference_side_effect(model_name, **kwargs):
            if model_name == "gpt-4o":
                raise Exception("GPT-4 error")
            else:
                return {
                    "mock_phash_0": {
                        "tags": ["claude_tag"],
                        "formatted_output": {"captions": ["Claude caption"]},
                        "error": None,
                    }
                }

        with patch.object(real_adapter.provider_manager, "run_inference_with_model") as mock_inference:
            mock_inference.side_effect = mock_inference_side_effect

            results = real_adapter.call_annotate(images=test_images, models=test_models)

            # 成功したモデルの結果のみが含まれる
            assert isinstance(results, dict)
            assert len(results) == 1
            first_phash = next(iter(results.keys()))
            assert "claude-3-5-sonnet" in results[first_phash]


# 境界値・エッジケーステスト
class TestAnnotatorLibAdapterEdgeCases:
    """AnnotatorLibAdapter 境界値・エッジケーステスト"""

    @pytest.fixture
    def mock_config_service(self):
        mock_config = Mock()
        mock_config.get_setting.return_value = ""  # 空のAPIキー
        return mock_config

    def test_empty_api_keys_handling(self, mock_config_service):
        """空のAPIキー処理"""
        adapter = MockAnnotatorLibAdapter(mock_config_service)
        api_keys = adapter.get_unified_api_keys()

        # 空文字列は除外される
        for _, value in api_keys.items():
            assert value != ""

    def test_large_image_handling(self):
        """大きな画像の処理"""
        mock_config = Mock()
        adapter = MockAnnotatorLibAdapter(mock_config)

        # 大きな画像作成
        large_image = Image.new("RGB", (4000, 4000), "black")

        results = adapter.call_annotate(images=[large_image], models=["gpt-4o"])

        # 正常に処理されることを確認
        assert isinstance(results, dict)
        assert len(results) == 1

    def test_many_models_handling(self):
        """多数モデルでの処理"""
        mock_config = Mock()
        adapter = MockAnnotatorLibAdapter(mock_config)

        test_image = Image.new("RGB", (100, 100), "cyan")
        many_models = [f"model-{i}" for i in range(20)]

        results = adapter.call_annotate(images=[test_image], models=many_models)

        # 全モデルが処理されることを確認
        assert isinstance(results, dict)
        phash = next(iter(results.keys()))
        assert len(results[phash]) == len(many_models)


@pytest.mark.integration
class TestAnnotatorLibAdapterIntegration:
    """AnnotatorLibAdapter 統合テスト"""

    def test_real_library_integration_placeholder(self):
        """実ライブラリとの統合テスト（プレースホルダー）"""
        # 実際のimage-annotator-libとの統合テスト
        # 現在のPhase 4実装では常にMockProviderManagerを使用
        # 実ライブラリ統合は将来の改修で実装予定

        # プレースホルダーとして基本的な動作確認
        mock_config = Mock()
        adapter = AnnotatorLibAdapter(mock_config)

        # MockProviderManagerが正しく設定されていることを確認
        assert adapter.provider_manager is not None
        assert hasattr(adapter.provider_manager, "run_inference_with_model")

        # 基本的なメタデータ取得が動作することを確認
        models = adapter.get_available_models_with_metadata()
        assert isinstance(models, list)
        assert len(models) > 0  # MockAnnotatorLibAdapterにフォールバック
