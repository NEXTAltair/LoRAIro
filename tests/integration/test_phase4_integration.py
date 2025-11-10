"""Phase 4統合テスト: image-annotator-lib統合検証

Phase 4-6: 統合テスト・検証
argument-based APIキーフローの統合検証

テスト方針:
- モックベース（実APIコールなし）
- 高速実行（<30秒）
- CI/CD対応
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from lorairo.gui.workers.annotation_worker import AnnotationWorker
from lorairo.services.annotation_service import AnnotationService
from lorairo.services.annotator_library_adapter import AnnotatorLibraryAdapter
from lorairo.services.configuration_service import ConfigurationService


@pytest.fixture
def mock_config_with_api_keys():
    """APIキー設定済みのConfigurationServiceモック"""
    config = MagicMock(spec=ConfigurationService)
    config.get_setting.side_effect = lambda section, key, default: {
        ("api", "openai_key"): "sk-test-openai-key-1234567890",
        ("api", "claude_key"): "sk-ant-test-claude-key-1234567890",
        ("api", "google_key"): "test-google-api-key-1234567890",
    }.get((section, key), default)
    return config


@pytest.fixture
def sample_annotation_result():
    """サンプルアノテーション結果"""
    return {
        "test_phash_001": {
            "gpt-4o": {
                "tags": ["cat", "animal", "cute"],
                "formatted_output": {"captions": ["A cute cat sitting on a chair"]},
                "error": None,
            }
        }
    }


@pytest.mark.integration
@pytest.mark.fast_integration
class TestPhase4Integration:
    """Phase 4統合テスト: argument-based API key flow"""

    def test_api_key_argument_flow_end_to_end(self, mock_config_with_api_keys, sample_annotation_result):
        """APIキー引数フロー完全検証

        ConfigurationService → AnnotatorLibraryAdapter → image-annotator-lib
        のフロー全体でAPIキーが引数として正しく渡されることを検証
        """
        # Arrange
        test_image = Image.new("RGB", (100, 100))

        # image-annotator-lib.annotate()をモック
        with patch("image_annotator_lib.annotate") as mock_annotate:
            mock_annotate.return_value = sample_annotation_result

            # Act
            adapter = AnnotatorLibraryAdapter(mock_config_with_api_keys)
            result = adapter.annotate(
                images=[test_image],
                model_names=["gpt-4o"],
                phash_list=["test_phash_001"],
            )

            # Assert
            # 1. annotate()が呼ばれたこと
            assert mock_annotate.called

            # 2. api_keysパラメータが渡されたこと
            call_kwargs = mock_annotate.call_args.kwargs
            assert "api_keys" in call_kwargs

            # 3. api_keysが正しい辞書形式であること
            api_keys = call_kwargs["api_keys"]
            assert isinstance(api_keys, dict)
            assert "openai" in api_keys
            assert "anthropic" in api_keys
            assert "google" in api_keys

            # 4. APIキーが正しく渡されていること
            assert api_keys["openai"] == "sk-test-openai-key-1234567890"
            assert api_keys["anthropic"] == "sk-ant-test-claude-key-1234567890"
            assert api_keys["google"] == "test-google-api-key-1234567890"

            # 5. 結果が正しく返されること
            assert result == sample_annotation_result

    def test_annotation_service_integration(self, mock_config_with_api_keys, sample_annotation_result):
        """AnnotationService統合検証

        ServiceContainer → AnnotationService → AnnotatorLibraryAdapter
        の統合フローを検証
        """
        # Arrange
        test_image = Image.new("RGB", (100, 100))

        with patch("image_annotator_lib.annotate") as mock_annotate:
            mock_annotate.return_value = sample_annotation_result

            with patch("lorairo.services.annotation_service.get_service_container") as mock_get_container:
                # ServiceContainerモック
                mock_container = MagicMock()
                mock_container.annotator_library = AnnotatorLibraryAdapter(mock_config_with_api_keys)
                mock_get_container.return_value = mock_container

                # Act
                service = AnnotationService()
                service.start_single_annotation(
                    images=[test_image],
                    phash_list=["test_phash_001"],
                    models=["gpt-4o"],
                )

                # Assert
                # AnnotatorLibraryAdapter経由でannotate()が呼ばれたこと
                assert mock_annotate.called

                # api_keysが渡されたこと
                call_kwargs = mock_annotate.call_args.kwargs
                assert "api_keys" in call_kwargs
                assert isinstance(call_kwargs["api_keys"], dict)

    def test_annotation_worker_integration(self, mock_config_with_api_keys, sample_annotation_result):
        """AnnotationWorker統合検証

        AnnotationWorker → AnnotationService → AnnotatorLibraryAdapter
        のWorker実行フローを検証
        """
        # Arrange
        test_image = Image.new("RGB", (100, 100))

        with patch("image_annotator_lib.annotate") as mock_annotate:
            mock_annotate.return_value = sample_annotation_result

            with patch("lorairo.services.annotation_service.get_service_container") as mock_get_container:
                mock_container = MagicMock()
                mock_container.annotator_library = AnnotatorLibraryAdapter(mock_config_with_api_keys)
                mock_get_container.return_value = mock_container

                # Act
                worker = AnnotationWorker(
                    images=[test_image],
                    phash_list=["test_phash_001"],
                    models=["gpt-4o"],
                    operation_mode="single",
                )
                result = worker.execute()

                # Assert
                # Worker実行完了
                assert result is not None
                assert "test_phash_001" in result

                # api_keysが渡されたこと
                assert mock_annotate.called
                call_kwargs = mock_annotate.call_args.kwargs
                assert "api_keys" in call_kwargs

    def test_error_propagation(self, mock_config_with_api_keys):
        """エラー伝播検証

        image-annotator-libからのエラーが適切に伝播されることを検証
        """
        # Arrange
        test_image = Image.new("RGB", (100, 100))

        with patch("image_annotator_lib.annotate") as mock_annotate:
            # エラーをシミュレート
            mock_annotate.side_effect = Exception("Invalid API key")

            # Act & Assert
            adapter = AnnotatorLibraryAdapter(mock_config_with_api_keys)

            with pytest.raises(Exception, match="Invalid API key"):
                adapter.annotate(
                    images=[test_image],
                    model_names=["gpt-4o"],
                    phash_list=["test_phash_001"],
                )

    def test_api_key_masking_in_logs(self, mock_config_with_api_keys, caplog):
        """ログAPIキーマスキング検証

        ログ出力時にAPIキーがマスキングされることを検証
        """
        # Arrange
        import logging

        caplog.set_level(logging.DEBUG)

        with patch("image_annotator_lib.annotate") as mock_annotate:
            mock_annotate.return_value = {}

            # Act
            adapter = AnnotatorLibraryAdapter(mock_config_with_api_keys)
            test_image = Image.new("RGB", (100, 100))
            adapter.annotate(
                images=[test_image],
                model_names=["gpt-4o"],
                phash_list=["test"],
            )

            # Assert
            log_output = caplog.text

            # フルAPIキーがログに含まれていないこと
            assert "sk-test-openai-key-1234567890" not in log_output
            assert "sk-ant-test-claude-key-1234567890" not in log_output
            assert "test-google-api-key-1234567890" not in log_output

            # マスキングされた形式が含まれていること（もしくはログ出力自体がある）
            # Note: DEBUGログが有効な場合のみマスキングされたキーが表示される
            if "masked" in log_output:
                # マスキング形式チェック（例: sk-t***890）
                assert "***" in log_output

    def test_no_environment_pollution(self, mock_config_with_api_keys, sample_annotation_result):
        """環境変数汚染なし検証

        アノテーション実行前後で環境変数が汚染されていないことを検証
        """
        # Arrange
        test_image = Image.new("RGB", (100, 100))

        # 実行前の環境変数状態を記録
        env_before = {
            "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY"),
            "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY"),
            "GOOGLE_API_KEY": os.environ.get("GOOGLE_API_KEY"),
        }

        with patch("image_annotator_lib.annotate") as mock_annotate:
            mock_annotate.return_value = sample_annotation_result

            # Act
            adapter = AnnotatorLibraryAdapter(mock_config_with_api_keys)
            adapter.annotate(
                images=[test_image],
                model_names=["gpt-4o"],
                phash_list=["test_phash_001"],
            )

            # Assert
            # 実行後の環境変数状態を確認
            env_after = {
                "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY"),
                "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY"),
                "GOOGLE_API_KEY": os.environ.get("GOOGLE_API_KEY"),
            }

            # 環境変数が変更されていないこと
            assert env_before == env_after

            # 具体的に、新しいAPIキーが設定されていないこと
            # （元々設定されていた場合はそのまま、なかった場合はNoneのまま）
            if env_before["OPENAI_API_KEY"] is None:
                assert env_after["OPENAI_API_KEY"] is None
            if env_before["ANTHROPIC_API_KEY"] is None:
                assert env_after["ANTHROPIC_API_KEY"] is None
            if env_before["GOOGLE_API_KEY"] is None:
                assert env_after["GOOGLE_API_KEY"] is None

    def test_empty_api_keys_filtered(self):
        """空APIキー除外検証

        空文字列・空白のみのAPIキーが除外されることを検証
        """
        # Arrange
        mock_config = MagicMock(spec=ConfigurationService)
        mock_config.get_setting.side_effect = lambda section, key, default: {
            ("api", "openai_key"): "sk-valid-key",
            ("api", "claude_key"): "",  # 空文字列
            ("api", "google_key"): "   ",  # 空白のみ
        }.get((section, key), default)

        with patch("image_annotator_lib.annotate") as mock_annotate:
            mock_annotate.return_value = {}

            # Act
            adapter = AnnotatorLibraryAdapter(mock_config)
            test_image = Image.new("RGB", (100, 100))
            adapter.annotate(
                images=[test_image],
                model_names=["gpt-4o"],
                phash_list=["test"],
            )

            # Assert
            call_kwargs = mock_annotate.call_args.kwargs
            api_keys = call_kwargs["api_keys"]

            # 有効なキーのみが含まれること
            assert "openai" in api_keys
            assert api_keys["openai"] == "sk-valid-key"

            # 空のキーが除外されていること
            assert "anthropic" not in api_keys
            assert "google" not in api_keys

    def test_multiple_models_annotation(self, mock_config_with_api_keys):
        """複数モデルアノテーション検証

        複数モデルでの同時アノテーションが正しく動作することを検証
        """
        # Arrange
        test_image = Image.new("RGB", (100, 100))
        multi_model_result = {
            "test_phash": {
                "gpt-4o": {
                    "tags": ["cat", "animal"],
                    "formatted_output": {"captions": ["A cat"]},
                    "error": None,
                },
                "claude-sonnet-4": {
                    "tags": ["feline", "pet"],
                    "formatted_output": {"captions": ["A feline pet"]},
                    "error": None,
                },
            }
        }

        with patch("image_annotator_lib.annotate") as mock_annotate:
            mock_annotate.return_value = multi_model_result

            # Act
            adapter = AnnotatorLibraryAdapter(mock_config_with_api_keys)
            result = adapter.annotate(
                images=[test_image],
                model_names=["gpt-4o", "claude-sonnet-4"],
                phash_list=["test_phash"],
            )

            # Assert
            # 両モデルの結果が返されること
            assert "test_phash" in result
            assert "gpt-4o" in result["test_phash"]
            assert "claude-sonnet-4" in result["test_phash"]

            # api_keysが両方のプロバイダーを含むこと
            call_kwargs = mock_annotate.call_args.kwargs
            api_keys = call_kwargs["api_keys"]
            assert "openai" in api_keys
            assert "anthropic" in api_keys
