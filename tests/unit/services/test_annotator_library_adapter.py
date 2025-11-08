"""AnnotatorLibraryAdapterユニットテスト

Phase 4-1: 実ライブラリ統合実装のテスト
image-annotator-lib APIをモックして、アダプターの動作を検証
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from lorairo.services.annotator_library_adapter import AnnotatorLibraryAdapter
from lorairo.services.configuration_service import ConfigurationService


@pytest.fixture
def mock_config_service():
    """ConfigurationServiceのモックフィクスチャ"""
    config = MagicMock(spec=ConfigurationService)
    config.get_setting.side_effect = lambda section, key, default: {
        ("api", "openai_key"): "test-openai-key",
        ("api", "claude_key"): "test-claude-key",
        ("api", "google_key"): "test-google-key",
    }.get((section, key), default)
    return config


@pytest.fixture
def adapter(mock_config_service):
    """AnnotatorLibraryAdapterフィクスチャ"""
    return AnnotatorLibraryAdapter(mock_config_service)


class TestAnnotatorLibraryAdapter:
    """AnnotatorLibraryAdapterユニットテスト"""

    def test_initialization(self, mock_config_service):
        """初期化テスト"""
        adapter = AnnotatorLibraryAdapter(mock_config_service)

        assert adapter.config_service == mock_config_service
        assert adapter.get_adapter_info()["adapter_type"] == "AnnotatorLibraryAdapter"
        assert adapter.get_adapter_info()["mode"] == "production"

    @patch("lorairo.services.annotator_library_adapter.list_available_annotators_with_metadata")
    def test_get_available_models_with_metadata_success(self, mock_list_annotators, adapter):
        """モデルメタデータ取得成功テスト"""
        # モックデータ準備
        mock_models = [
            {
                "name": "gpt-4o",
                "provider": "openai",
                "class": "PydanticAIWebAPIAnnotator",
                "requires_api_key": True,
            },
            {
                "name": "wd-tagger",
                "provider": None,
                "class": "WDTagger",
                "requires_api_key": False,
            },
        ]
        mock_list_annotators.return_value = mock_models

        # 実行
        result = adapter.get_available_models_with_metadata()

        # 検証
        assert result == mock_models
        assert len(result) == 2
        mock_list_annotators.assert_called_once()

    @patch("lorairo.services.annotator_library_adapter.list_available_annotators_with_metadata")
    def test_get_available_models_with_metadata_error(self, mock_list_annotators, adapter):
        """モデルメタデータ取得エラーテスト"""
        # モックでエラー発生
        mock_list_annotators.side_effect = Exception("Library error")

        # 実行・検証
        with pytest.raises(Exception, match="Library error"):
            adapter.get_available_models_with_metadata()

    @patch("image_annotator_lib.annotate")
    def test_annotate_success(self, mock_annotate, adapter):
        """アノテーション実行成功テスト"""
        # モックデータ準備
        test_image = Image.new("RGB", (100, 100))
        mock_results = {
            "test_phash": {
                "gpt-4o": {
                    "tags": ["cat", "animal"],
                    "formatted_output": {"captions": ["A cat sitting"]},
                    "error": None,
                }
            }
        }
        mock_annotate.return_value = mock_results

        # 実行
        result = adapter.annotate(
            images=[test_image],
            model_names=["gpt-4o"],
            phash_list=["test_phash"],
        )

        # 検証
        assert result == mock_results
        mock_annotate.assert_called_once_with(
            images_list=[test_image],
            model_name_list=["gpt-4o"],
            phash_list=["test_phash"],
        )

        # 環境変数が設定されていることを確認
        assert os.environ.get("OPENAI_API_KEY") == "test-openai-key"
        assert os.environ.get("ANTHROPIC_API_KEY") == "test-claude-key"
        assert os.environ.get("GOOGLE_API_KEY") == "test-google-key"

    @patch("image_annotator_lib.annotate")
    def test_annotate_error(self, mock_annotate, adapter):
        """アノテーション実行エラーテスト"""
        # モックでエラー発生
        mock_annotate.side_effect = Exception("Annotation error")

        test_image = Image.new("RGB", (100, 100))

        # 実行・検証
        with pytest.raises(Exception, match="Annotation error"):
            adapter.annotate(
                images=[test_image],
                model_names=["gpt-4o"],
            )

    def test_set_api_keys_to_env(self, adapter):
        """APIキー環境変数設定テスト"""
        # クリーンアップ（既存の環境変数を削除）
        for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"]:
            if key in os.environ:
                del os.environ[key]

        # 実行
        adapter._set_api_keys_to_env()

        # 検証
        assert os.environ["OPENAI_API_KEY"] == "test-openai-key"
        assert os.environ["ANTHROPIC_API_KEY"] == "test-claude-key"
        assert os.environ["GOOGLE_API_KEY"] == "test-google-key"

    def test_set_api_keys_to_env_empty_keys(self):
        """APIキーが空の場合の環境変数設定テスト"""
        # 空のAPIキーを返すConfigServiceモック
        mock_config = MagicMock(spec=ConfigurationService)
        mock_config.get_setting.return_value = ""

        adapter = AnnotatorLibraryAdapter(mock_config)

        # クリーンアップ
        for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"]:
            if key in os.environ:
                del os.environ[key]

        # 実行
        adapter._set_api_keys_to_env()

        # 検証（空の場合は環境変数設定されない）
        assert "OPENAI_API_KEY" not in os.environ
        assert "ANTHROPIC_API_KEY" not in os.environ
        assert "GOOGLE_API_KEY" not in os.environ

    def test_get_adapter_info(self, adapter):
        """アダプター情報取得テスト"""
        info = adapter.get_adapter_info()

        assert info["adapter_type"] == "AnnotatorLibraryAdapter"
        assert info["library"] == "image-annotator-lib"
        assert info["mode"] == "production"
        assert "config_service" in info
