"""AnnotatorLibraryAdapterユニットテスト

Phase 4-1: 実ライブラリ統合実装のテスト
Phase 4-5: APIキー管理統合テスト（引数ベース方式）
image-annotator-lib APIをモックして、アダプターの動作を検証
"""

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
        """アノテーション実行成功テスト（Phase 4-5: api_keys引数渡し）"""
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

        # api_keysパラメータが正しく渡されていることを確認
        mock_annotate.assert_called_once_with(
            images_list=[test_image],
            model_name_list=["gpt-4o"],
            phash_list=["test_phash"],
            api_keys={
                "openai": "test-openai-key",
                "anthropic": "test-claude-key",
                "google": "test-google-key",
            },
        )

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

    def test_prepare_api_keys_all_keys(self, adapter):
        """APIキー辞書準備テスト（全キー設定済み）"""
        # 実行
        api_keys = adapter._prepare_api_keys()

        # 検証
        assert api_keys == {
            "openai": "test-openai-key",
            "anthropic": "test-claude-key",
            "google": "test-google-key",
        }

    def test_prepare_api_keys_empty_keys(self):
        """APIキー辞書準備テスト（空のキーを除外）"""
        # 一部のキーのみ設定されているConfigServiceモック
        mock_config = MagicMock(spec=ConfigurationService)
        mock_config.get_setting.side_effect = lambda section, key, default: {
            ("api", "openai_key"): "sk-test-key",
            ("api", "claude_key"): "",  # 空文字列
            ("api", "google_key"): "  ",  # 空白のみ
        }.get((section, key), default)

        adapter = AnnotatorLibraryAdapter(mock_config)

        # 実行
        api_keys = adapter._prepare_api_keys()

        # 検証（空のキーは除外される）
        assert api_keys == {"openai": "sk-test-key"}

    def test_prepare_api_keys_no_keys(self):
        """APIキー辞書準備テスト（全キーが空）"""
        # 全て空のConfigServiceモック
        mock_config = MagicMock(spec=ConfigurationService)
        mock_config.get_setting.return_value = ""

        adapter = AnnotatorLibraryAdapter(mock_config)

        # 実行
        api_keys = adapter._prepare_api_keys()

        # 検証（空の辞書）
        assert api_keys == {}

    def test_mask_key(self, adapter):
        """APIキーマスキングテスト"""
        # 正常なキー（8文字以上）
        assert adapter._mask_key("sk-test-openai-key-12345") == "sk-t***2345"

        # 短いキー（8文字未満）
        assert adapter._mask_key("short") == "***"

        # 空文字列
        assert adapter._mask_key("") == "***"

        # ちょうど8文字
        assert adapter._mask_key("12345678") == "1234***5678"

    def test_get_adapter_info(self, adapter):
        """アダプター情報取得テスト"""
        info = adapter.get_adapter_info()

        assert info["adapter_type"] == "AnnotatorLibraryAdapter"
        assert info["library"] == "image-annotator-lib"
        assert info["mode"] == "production"
        assert "config_service" in info
