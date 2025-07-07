"""ConfigurationService のユニットテスト

テスト方針:
- 他モジュールへの依存はなるべく避ける
- ファイルシステムのみ必要最小限でモック化
- 単一クラスの振る舞いに焦点を当てる
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

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
            assert config_service.get_setting("directories", "database_dir", None) == ""  # 新しいデフォルト値

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

    def test_get_available_providers_empty(self):
        """APIキーが設定されていない場合のプロバイダー取得テスト"""
        # Given: APIキーが設定されていない状態
        config_service = ConfigurationService(shared_config={"api": {}})

        # When: 利用可能プロバイダーを取得
        providers = config_service.get_available_providers()

        # Then: 空のリストが返される
        assert providers == []

    def test_get_available_providers_with_keys(self):
        """APIキーが設定されている場合のプロバイダー取得テスト"""
        # Given: APIキーが設定されている状態
        config = {
            "api": {
                "openai_key": "sk-test",
                "claude_key": "",  # 空文字列
                "google_key": "ai-test",
            }
        }
        config_service = ConfigurationService(shared_config=config)

        # When: 利用可能プロバイダーを取得
        providers = config_service.get_available_providers()

        # Then: 空でないAPIキーを持つプロバイダーのみ返される
        assert "openai" in providers
        assert "google" in providers
        assert "anthropic" not in providers  # claude_keyが空文字列

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
        assert config_service.get_database_directory() == Path("custom_db")
        assert config_service.get_batch_results_directory() == Path("custom_batch")

    def test_directory_getters_with_defaults(self):
        """デフォルト値でのディレクトリ取得テスト"""
        # Given: ディレクトリ設定が空の状態
        config_service = ConfigurationService(shared_config={})

        # When/Then: デフォルト値が返される
        assert config_service.get_export_directory() == Path("export")
        assert config_service.get_database_directory() == Path("database")  # メソッド内でデフォルト値指定
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
            "設定値を更新しました: [%s] %s = %s", "api", "openai_key", "sk-1***cdef"
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
            "設定値を更新しました: [%s] %s = %s", "huggingface", "token", "hf_1***cdef"
        )
