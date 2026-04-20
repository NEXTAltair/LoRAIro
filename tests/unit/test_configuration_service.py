"""ConfigurationService のユニットテスト

テスト方針:
- 他モジュールへの依存はなるべく避ける
- ファイルシステムのみ必要最小限でモック化
- 単一クラスの振る舞いに焦点を当てる
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lorairo.services.configuration_service import ConfigurationService


class TestConfigurationService:
    """ConfigurationService のユニットテスト"""

    def test_initialization_with_default_config(self):
        """デフォルト設定での初期化テスト"""
        # Given: 設定ファイルが存在しない状況
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "test_config.toml"

            # When: ConfigurationServiceを初期化
            config_service = ConfigurationService(config_path=config_path)

            # Then: デフォルト設定が読み込まれる（ファイルは作成されない）
            assert not config_path.exists()  # ファイルは作成されない
            assert config_service.get_setting("api", "openai_key", None) == ""
            assert (
                config_service.get_setting("directories", "database_dir", None) == ""
            )  # 新しいデフォルト値

    def test_shared_config_initialization(self):
        """共有設定オブジェクトでの初期化テスト"""
        # Given: 共有設定オブジェクト
        shared_config = {"api": {"openai_key": "test_key"}, "directories": {"database_dir": "test_db"}}

        # When: 共有設定でConfigurationServiceを初期化
        config_service = ConfigurationService(shared_config=shared_config)

        # Then: 共有設定が使用される
        assert config_service.get_setting("api", "openai_key") == "test_key"
        assert config_service.get_setting("directories", "database_dir") == "test_db"

    def test_shared_config_immediate_reflection(self):
        """共有設定オブジェクトでの設定変更即時反映テスト"""
        # Given: 共有設定オブジェクトと複数のConfigurationServiceインスタンス
        shared_config = {"api": {"openai_key": ""}}
        config_service1 = ConfigurationService(shared_config=shared_config)
        config_service2 = ConfigurationService(shared_config=shared_config)

        # When: 一つのインスタンスで設定を変更
        config_service1.update_setting("api", "openai_key", "new_key")

        # Then: 他のインスタンスでも即座に反映される
        assert config_service2.get_setting("api", "openai_key") == "new_key"

    def test_get_setting_with_default(self):
        """デフォルト値を指定した設定取得テスト"""
        # Given: 空の設定
        config_service = ConfigurationService(shared_config={})

        # When: 存在しない設定をデフォルト値付きで取得
        result = config_service.get_setting("nonexistent", "key", "default_value")

        # Then: デフォルト値が返される
        assert result == "default_value"

    def test_update_setting_creates_section(self):
        """存在しないセクションへの設定更新テスト"""
        # Given: 空の設定
        config_service = ConfigurationService(shared_config={})

        # When: 存在しないセクションに設定を追加
        config_service.update_setting("new_section", "new_key", "new_value")

        # Then: セクションが作成され、設定が保存される
        assert config_service.get_setting("new_section", "new_key") == "new_value"

    def test_api_key_masking(self):
        """APIキーマスキング機能テスト"""
        # Given: ConfigurationService
        config_service = ConfigurationService(shared_config={})

        # When: 短いキーと長いキーをマスキング
        short_key_result = config_service._mask_api_key("short")
        long_key_result = config_service._mask_api_key("sk-1234567890abcdef1234567890abcdef")

        # Then: 適切にマスキングされる
        assert short_key_result == "***"
        assert long_key_result == "sk-1***cdef"

    def test_get_api_keys_empty(self):
        """APIキーが設定されていない場合のAPIキー取得テスト"""
        # Given: APIキーが設定されていない状態
        config_service = ConfigurationService(shared_config={"api": {}})

        # When: APIキーを取得
        api_keys = config_service.get_api_keys()

        # Then: 空の辞書が返される
        assert api_keys == {}

    def test_get_api_keys_with_keys(self):
        """APIキーが設定されている場合のAPIキー取得テスト"""
        # Given: APIキーが設定されている状態
        config = {
            "api": {
                "openai_key": "sk-test",
                "claude_key": "",  # 空文字列
                "google_key": "ai-test",
            }
        }
        config_service = ConfigurationService(shared_config=config)

        # When: APIキーを取得
        api_keys = config_service.get_api_keys()

        # Then: 空でないAPIキーのみ返される
        assert api_keys == {"openai_key": "sk-test", "google_key": "ai-test"}
        assert "claude_key" not in api_keys  # 空文字列は除外

    def test_is_provider_available(self):
        """プロバイダー可用性チェックテスト"""
        # Given: 一部のAPIキーが設定されている状態
        config = {"api": {"openai_key": "sk-test", "claude_key": ""}}
        config_service = ConfigurationService(shared_config=config)

        # When/Then: 各プロバイダーの可用性をチェック
        assert config_service.is_provider_available("openai") is True
        assert config_service.is_provider_available("anthropic") is False
        assert config_service.is_provider_available("google") is False
        assert config_service.is_provider_available("unknown") is False

    def test_directory_getters(self):
        """ディレクトリ取得メソッドテスト"""
        # Given: ディレクトリ設定
        config = {
            "directories": {
                "export_dir": "custom_export",
                "database_dir": "custom_db",
                "batch_results_dir": "custom_batch",
            }
        }
        config_service = ConfigurationService(shared_config=config)

        # When/Then: 各ディレクトリが正しく取得される
        assert config_service.get_export_directory() == Path("custom_export")
        # database_dir は絶対パスに変換される
        db_dir = config_service.get_database_directory()
        assert db_dir.is_absolute()
        assert db_dir.name == "custom_db"
        assert config_service.get_batch_results_directory() == Path("custom_batch")

    def test_directory_getters_with_defaults(self):
        """デフォルト値でのディレクトリ取得テスト"""
        # Given: ディレクトリ設定が空の状態
        config_service = ConfigurationService(shared_config={})

        # When/Then: デフォルト値が返される
        assert config_service.get_export_directory() == Path("export")
        # database_dir はデフォルト値が絶対パスに変換される
        db_dir = config_service.get_database_directory()
        assert db_dir.is_absolute()
        assert db_dir.name == "database"
        assert config_service.get_batch_results_directory() == Path("batch_results")

    def test_save_settings_success(self):
        """設定保存成功テスト"""
        # Given: 一時ディレクトリと設定
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "save_test.toml"
            config = {"test": {"key": "value"}}
            config_service = ConfigurationService(config_path=config_path, shared_config=config)

            # When: 設定を保存
            result = config_service.save_settings()

            # Then: 保存が成功し、ファイルが作成される
            assert result is True
            assert config_path.exists()

    @patch("lorairo.services.configuration_service.write_config_file")
    def test_save_settings_failure(self, mock_write):
        """設定保存失敗テスト"""
        # Given: 保存時にエラーが発生する状況
        mock_write.side_effect = OSError("Permission denied")
        config_service = ConfigurationService(shared_config={})

        # When: 設定を保存
        result = config_service.save_settings()

        # Then: 保存が失敗する
        assert result is False

    def test_get_shared_config(self):
        """共有設定オブジェクト取得テスト"""
        # Given: 設定オブジェクト
        original_config = {"test": "value"}
        config_service = ConfigurationService(shared_config=original_config)

        # When: 共有設定オブジェクトを取得
        shared = config_service.get_shared_config()

        # Then: 同じオブジェクトが返される（参照が同じ）
        assert shared is original_config

    @patch("lorairo.services.configuration_service.logger")
    def test_api_key_masking_in_logs(self, mock_logger):
        """ログ出力でのAPIキーマスキングテスト"""
        # Given: ConfigurationService
        config_service = ConfigurationService(shared_config={})

        # When: APIキーを更新
        config_service.update_setting("api", "openai_key", "sk-1234567890abcdef")

        # Then: ログにマスキングされた値が記録される
        mock_logger.debug.assert_called_with(
            "設定値を更新しました: [{}] {} = {}", "api", "openai_key", "sk-1***cdef"
        )

    @patch("lorairo.services.configuration_service.logger")
    def test_huggingface_token_masking_in_logs(self, mock_logger):
        """ログ出力でのHugging Faceトークンマスキングテスト"""
        # Given: ConfigurationService
        config_service = ConfigurationService(shared_config={})

        # When: Hugging Faceトークンを更新
        config_service.update_setting("huggingface", "token", "hf_1234567890abcdef")

        # Then: ログにマスキングされた値が記録される
        mock_logger.debug.assert_called_with(
            "設定値を更新しました: [{}] {} = {}", "huggingface", "token", "hf_1***cdef"
        )

    def test_get_database_directory_relative_path(self):
        """相対パスが絶対パスに変換されることを確認"""
        # Given: 相対パス設定
        config = {"directories": {"database_dir": "test_data"}}
        config_service = ConfigurationService(shared_config=config)

        # When: データベースディレクトリを取得
        result = config_service.get_database_directory()

        # Then: 絶対パスに変換されている
        assert result.is_absolute()
        assert result.name == "test_data"

    def test_get_database_directory_absolute_path(self):
        """絶対パスがそのまま返されることを確認"""
        # Given: 絶対パス設定
        abs_path = Path("/tmp/test_data").resolve()
        config = {"directories": {"database_dir": str(abs_path)}}
        config_service = ConfigurationService(shared_config=config)

        # When: データベースディレクトリを取得
        result = config_service.get_database_directory()

        # Then: 絶対パスがそのまま返される
        assert result == abs_path

    def test_get_database_directory_empty_path(self):
        """空文字列の場合の相対パス解決確認"""
        # Given: 空文字列設定（デフォルト値"database"が使用される）
        config = {"directories": {"database_dir": ""}}
        config_service = ConfigurationService(shared_config=config)

        # When: データベースディレクトリを取得
        result = config_service.get_database_directory()

        # Then: デフォルト値が絶対パスに変換されている
        assert result.is_absolute()
        assert result.name == "database"

    @patch("lorairo.services.configuration_service.logger")
    def test_get_database_directory_resolution_logging(self, mock_logger):
        """相対パス解決時のログ出力確認"""
        # Given: 相対パス設定
        config = {"directories": {"database_dir": "relative_path"}}
        config_service = ConfigurationService(shared_config=config)

        # When: データベースディレクトリを取得
        config_service.get_database_directory()

        # Then: 解決ログが出力される
        debug_calls = mock_logger.debug.call_args_list
        resolution_calls = [call for call in debug_calls if "Resolved relative database_dir" in call[0][0]]
        assert len(resolution_calls) == 1
        assert "relative_path" in resolution_calls[0][0][0]

    @patch("lorairo.services.configuration_service.logger")
    def test_get_database_directory_error_handling(self, mock_logger):
        """エラー時のフォールバック処理確認"""
        # Given: get_setting でエラーが発生する状況
        config_service = ConfigurationService(shared_config={})

        # get_setting メソッドを失敗させる
        with patch.object(config_service, "get_setting", side_effect=Exception("Test error")):
            # When: データベースディレクトリを取得
            result = config_service.get_database_directory()

            # Then: エラーログとフォールバックログが出力される
            mock_logger.error.assert_called_once()
            mock_logger.warning.assert_called_once()

            # フォールバックパスが返される
            expected_fallback = Path.cwd() / "database"
            assert result == expected_fallback


class TestConfigurationServiceInitBranches:
    """__init__ の例外分岐テスト"""

    @patch("lorairo.services.configuration_service.get_config")
    @patch("lorairo.services.configuration_service.write_config_file")
    def test_init_file_not_found_creates_default(self, mock_write, mock_get_config, tmp_path):
        """FileNotFoundError発生時に_create_default_config_fileが呼ばれる"""
        mock_get_config.side_effect = FileNotFoundError("File not found")
        config_path = tmp_path / "config.toml"
        service = ConfigurationService(config_path=config_path)
        mock_write.assert_called_once()
        assert service.get_setting("api", "openai_key") == ""

    @patch("lorairo.services.configuration_service.get_config")
    @patch("lorairo.services.configuration_service.write_config_file")
    def test_init_file_not_found_write_failure_fallback(self, mock_write, mock_get_config, tmp_path):
        """デフォルト設定ファイル作成失敗時にメモリ上のデフォルト設定を使用する"""
        mock_get_config.side_effect = FileNotFoundError("File not found")
        mock_write.side_effect = PermissionError("Permission denied")
        config_path = tmp_path / "config.toml"
        service = ConfigurationService(config_path=config_path)
        assert service.get_setting("api", "openai_key") == ""

    @patch("lorairo.services.configuration_service.get_config")
    def test_init_unexpected_exception_returns_empty(self, mock_get_config, tmp_path):
        """予期せぬエラー発生時に空の設定を使用する"""
        mock_get_config.side_effect = ValueError("Unexpected parse error")
        config_path = tmp_path / "config.toml"
        service = ConfigurationService(config_path=config_path)
        assert service._config == {}


class TestConfigurationServiceMiscMethods:
    """その他メソッドのテスト"""

    def test_get_all_settings(self):
        """get_all_settingsが設定辞書全体を返す"""
        config = {"section": {"key": "value"}}
        service = ConfigurationService(shared_config=config)
        result = service.get_all_settings()
        assert result is config

    def test_update_setting_non_secret_key(self):
        """非機密キーの更新で値がそのまま設定される"""
        service = ConfigurationService(shared_config={})
        service.update_setting("image_processing", "resolution", 1024)
        assert service.get_setting("image_processing", "resolution") == 1024

    @patch("lorairo.services.configuration_service.write_config_file")
    def test_save_settings_unexpected_exception(self, mock_write):
        """予期せぬ例外発生時はFalseを返す"""
        mock_write.side_effect = ValueError("Unexpected error")
        service = ConfigurationService(shared_config={})
        result = service.save_settings()
        assert result is False

    def test_update_image_processing_setting(self):
        """update_image_processing_settingがimage_processingセクションを更新する"""
        service = ConfigurationService(shared_config={})
        service.update_image_processing_setting("upscaler", "NewModel")
        assert service.get_setting("image_processing", "upscaler") == "NewModel"


class TestConfigurationServiceGetters:
    """各種ゲッターメソッドのテスト"""

    def test_get_image_processing_config_non_dict(self):
        """image_processingが辞書でない場合は空辞書を返す"""
        config = {"image_processing": "invalid_string"}
        service = ConfigurationService(shared_config=config)
        result = service.get_image_processing_config()
        assert result == {}

    def test_get_preferred_resolutions_non_list(self):
        """preferred_resolutionsがリストでない場合は空リストを返す"""
        config = {"preferred_resolutions": "invalid_string"}
        service = ConfigurationService(shared_config=config)
        result = service.get_preferred_resolutions()
        assert result == []

    def test_get_upscaler_models_non_list(self):
        """upscaler_modelsがリストでない場合は空リストを返す"""
        config = {"upscaler_models": "invalid_string"}
        service = ConfigurationService(shared_config=config)
        result = service.get_upscaler_models()
        assert result == []

    def test_get_upscaler_model_by_name_found(self):
        """指定名のアップスケーラーモデルを取得できる"""
        model = {"name": "TestModel", "path": "/models/test.pth", "scale": 4.0}
        config = {"upscaler_models": [model]}
        service = ConfigurationService(shared_config=config)
        result = service.get_upscaler_model_by_name("TestModel")
        assert result == model

    def test_get_upscaler_model_by_name_not_found(self):
        """存在しない名前の場合はNoneを返す"""
        model = {"name": "TestModel", "path": "/models/test.pth", "scale": 4.0}
        config = {"upscaler_models": [model]}
        service = ConfigurationService(shared_config=config)
        result = service.get_upscaler_model_by_name("NonExistent")
        assert result is None

    def test_get_available_upscaler_names(self):
        """アップスケーラーモデル名リストを取得できる"""
        config = {
            "upscaler_models": [
                {"name": "Model1", "path": "/p1", "scale": 4.0},
                {"name": "Model2", "path": "/p2", "scale": 2.0},
            ]
        }
        service = ConfigurationService(shared_config=config)
        result = service.get_available_upscaler_names()
        assert result == ["Model1", "Model2"]


class TestConfigurationServiceUpscaler:
    """アップスケーラー関連メソッドのテスト"""

    def test_get_default_upscaler_name_from_config(self):
        """image_processing.upscalerが設定されている場合はその値を返す"""
        config = {"image_processing": {"upscaler": "ConfiguredModel"}}
        service = ConfigurationService(shared_config=config)
        result = service.get_default_upscaler_name()
        assert result == "ConfiguredModel"

    def test_get_default_upscaler_name_from_models(self):
        """upscalerが未設定でもupscaler_modelsの最初の名前を返す"""
        config = {
            "image_processing": {},
            "upscaler_models": [
                {"name": "FirstModel", "path": "/p", "scale": 4.0},
            ],
        }
        service = ConfigurationService(shared_config=config)
        result = service.get_default_upscaler_name()
        assert result == "FirstModel"

    def test_get_default_upscaler_name_fallback(self):
        """設定もモデルもない場合はデフォルト値を返す"""
        service = ConfigurationService(shared_config={})
        result = service.get_default_upscaler_name()
        assert result == "RealESRGAN_x4plus"

    def test_validate_upscaler_config_no_models(self):
        """モデルが設定されていない場合はFalseを返す"""
        service = ConfigurationService(shared_config={})
        result = service.validate_upscaler_config()
        assert result is False

    def test_validate_upscaler_config_invalid_model(self):
        """必須キーが欠けているモデルがある場合はFalseを返す"""
        config = {"upscaler_models": [{"name": "Model1"}]}
        service = ConfigurationService(shared_config=config)
        result = service.validate_upscaler_config()
        assert result is False

    def test_validate_upscaler_config_valid(self):
        """全モデルに必須キーが揃っている場合はTrueを返す"""
        config = {
            "upscaler_models": [
                {"name": "Model1", "path": "/p1", "scale": 4.0},
                {"name": "Model2", "path": "/p2", "scale": 2.0},
            ]
        }
        service = ConfigurationService(shared_config=config)
        result = service.validate_upscaler_config()
        assert result is True


class TestConfigurationServiceAnnotationModels:
    """アノテーションモデル関連メソッドのテスト"""

    def test_get_available_annotation_models_import_error(self):
        """image_annotator_libのインポートが失敗した場合は空リストを返す"""
        service = ConfigurationService(shared_config={})
        with patch.dict("sys.modules", {"image_annotator_lib": None}):
            result = service.get_available_annotation_models()
        assert result == []

    def test_get_available_annotation_models_exception(self):
        """モデルリスト取得中に例外が発生した場合は空リストを返す"""
        service = ConfigurationService(shared_config={})
        with patch("image_annotator_lib.list_available_annotators", side_effect=RuntimeError("error")):
            result = service.get_available_annotation_models()
        assert result == []

    def test_get_available_annotation_models_success(self):
        """正常にモデルリストを取得できる"""
        service = ConfigurationService(shared_config={})
        with patch("image_annotator_lib.list_available_annotators", return_value=["model1", "model2"]):
            result = service.get_available_annotation_models()
        assert result == ["model1", "model2"]

    def test_get_default_annotation_model_from_config(self):
        """設定ファイルにデフォルトモデルが明示されている場合はその値を返す"""
        config = {"annotation": {"default_model": "configured-model"}}
        service = ConfigurationService(shared_config=config)
        result = service.get_default_annotation_model()
        assert result == "configured-model"

    def test_get_default_annotation_model_openai_key(self):
        """openai_keyがある場合はgpt-4o-miniを返す"""
        config = {"api": {"openai_key": "sk-test", "claude_key": "", "google_key": ""}}
        service = ConfigurationService(shared_config=config)
        result = service.get_default_annotation_model()
        assert result == "gpt-4o-mini"

    def test_get_default_annotation_model_claude_key(self):
        """openai_keyがなくclaude_keyがある場合はclaude-3-haiku-20240307を返す"""
        config = {"api": {"openai_key": "", "claude_key": "claude-test", "google_key": ""}}
        service = ConfigurationService(shared_config=config)
        result = service.get_default_annotation_model()
        assert result == "claude-3-haiku-20240307"

    def test_get_default_annotation_model_google_key(self):
        """openai_key/claude_keyがなくgoogle_keyがある場合はgemini-1.5-flash-latestを返す"""
        config = {"api": {"openai_key": "", "claude_key": "", "google_key": "google-test"}}
        service = ConfigurationService(shared_config=config)
        result = service.get_default_annotation_model()
        assert result == "gemini-1.5-flash-latest"

    def test_get_default_annotation_model_from_available_models(self):
        """APIキーがなく利用可能なモデルがある場合は最初のモデルを返す"""
        service = ConfigurationService(shared_config={"api": {}})
        with patch.object(service, "get_available_annotation_models", return_value=["local-model"]):
            result = service.get_default_annotation_model()
        assert result == "local-model"

    def test_get_default_annotation_model_none(self):
        """APIキーも利用可能なモデルもない場合はNoneを返す"""
        service = ConfigurationService(shared_config={"api": {}})
        with patch.object(service, "get_available_annotation_models", return_value=[]):
            result = service.get_default_annotation_model()
        assert result is None
