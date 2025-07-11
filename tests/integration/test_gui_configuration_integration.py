"""
GUI コンポーネントと設定システムの統合テスト
image_processing_service.py とGUIの相互作用をテストする
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from lorairo.services.configuration_service import ConfigurationService
from lorairo.services.image_processing_service import ImageProcessingService


class TestGUIConfigurationIntegration:
    """GUI と設定システムの統合テスト"""

    def test_image_processing_service_configuration_integration(self, tmp_path):
        """ImageProcessingService と ConfigurationService の統合テスト"""
        # テスト用設定ファイル作成
        config_file = tmp_path / "test_config.toml"
        config_file.write_text("""
[directories]
database_dir = "test_project"
export_dir = "test_export"

[image_processing]
target_resolution = 1024
realesrgan_upscale = true
""")

        with patch("lorairo.services.configuration_service.get_config") as mock_get_config:
            mock_get_config.return_value = {
                "directories": {"database_dir": "test_project", "export_dir": "test_export"},
                "image_processing": {"target_resolution": 1024, "realesrgan_upscale": True},
            }

            # 依存関係をモック
            mock_fsm = Mock()
            mock_idm = Mock()

            config_service = ConfigurationService(config_file)

            # ImageProcessingService が設定を正しく読み込むこと
            with patch("lorairo.services.image_processing_service.ImageProcessingManager") as mock_ipm:
                service = ImageProcessingService(config_service, mock_fsm, mock_idm)

                # 設定値が正しく渡されることを確認
                assert service.config_service == config_service

                # get_export_directory (旧 get_output_directory) の修正が反映されていること
                export_dir = config_service.get_export_directory()
                assert str(export_dir) == "test_export"

    def test_shared_configuration_gui_integration(self, tmp_path):
        """共有設定とGUIコンポーネントの統合テスト"""
        config_file = tmp_path / "shared_test_config.toml"
        config_file.write_text("""
[api]
openai_key = "test_key"
claude_key = ""

[image_processing]
target_resolution = 512
""")

        with patch("lorairo.services.configuration_service.get_config") as mock_get_config:
            mock_get_config.return_value = {
                "api": {"openai_key": "test_key", "claude_key": ""},
                "image_processing": {"target_resolution": 512},
            }

            # 共有設定オブジェクトを使用して複数のサービスを作成
            shared_config = {}

            config_service_1 = ConfigurationService(config_file, shared_config)
            config_service_2 = ConfigurationService(config_file, shared_config)

            # 一方のサービスで設定変更
            config_service_1.update_image_processing_setting("target_resolution", 1024)

            # 他方のサービスで即座に反映されること
            assert config_service_2.get_image_processing_config()["target_resolution"] == 1024

    def test_api_key_masking_gui_integration(self, tmp_path):
        """APIキーマスキングとGUI表示の統合テスト"""
        config_file = tmp_path / "api_test_config.toml"
        config_file.write_text("""
[api]
openai_key = "sk-1234567890abcdefghij"
claude_key = "claude-key-abcdefghijklmnop"
google_key = ""
""")

        with patch("lorairo.services.configuration_service.get_config") as mock_get_config:
            mock_get_config.return_value = {
                "api": {
                    "openai_key": "sk-1234567890abcdefghij",
                    "claude_key": "claude-key-abcdefghijklmnop",
                    "google_key": "",
                }
            }

            config_service = ConfigurationService(config_file)

            # APIキーが適切にマスキングされること（GUI表示用）
            masked_openai = config_service._mask_api_key("sk-1234567890abcdefghij")
            masked_claude = config_service._mask_api_key("claude-key-abcdefghijklmnop")

            assert masked_openai == "sk-1***ghij"
            assert masked_claude == "clau***mnop"

            # 利用可能プロバイダがGUIで適切に判定されること
            available_providers = config_service.get_available_providers()
            assert "openai" in available_providers
            assert "anthropic" in available_providers  # ConfigurationServiceは"anthropic"を返す
            assert "google" not in available_providers  # 空キーは除外

    def test_directory_path_gui_integration(self, tmp_path):
        """ディレクトリパスとGUIファイル選択の統合テスト"""
        # プロジェクトディレクトリ構造を作成
        project_dir = tmp_path / "gui_project_20250708_001"
        project_dir.mkdir()

        export_dir = tmp_path / "gui_export"
        export_dir.mkdir()

        config_file = tmp_path / "gui_config.toml"
        config_file.write_text(f"""
[directories]
database_dir = "{project_dir}"
export_dir = "{export_dir}"
batch_results_dir = "{tmp_path}/batch_results"
""")

        with patch("lorairo.services.configuration_service.get_config") as mock_get_config:
            mock_get_config.return_value = {
                "directories": {
                    "database_dir": str(project_dir),
                    "export_dir": str(export_dir),
                    "batch_results_dir": str(tmp_path / "batch_results"),
                }
            }

            config_service = ConfigurationService(config_file)

            # GUIで使用される各ディレクトリパスが正しく解決されること
            assert Path(config_service.get_database_directory()) == project_dir
            assert Path(config_service.get_export_directory()) == export_dir
            assert Path(config_service.get_batch_results_directory()) == tmp_path / "batch_results"

    def test_configuration_validation_gui_integration(self, tmp_path):
        """設定値検証とGUIエラー表示の統合テスト"""
        config_file = tmp_path / "validation_config.toml"
        config_file.write_text("""
[api]
openai_key = "invalid_key_format"
claude_key = ""

[image_processing]
target_resolution = 999  # 非標準値
""")

        with patch("lorairo.services.configuration_service.get_config") as mock_get_config:
            mock_get_config.return_value = {
                "api": {"openai_key": "invalid_key_format", "claude_key": ""},
                "image_processing": {"target_resolution": 999},
            }

            config_service = ConfigurationService(config_file)

            # 設定値の検証（GUI でエラー表示に使用）
            openai_key = config_service.get_setting("api", "openai_key")
            assert openai_key == "invalid_key_format"

            # 優先解像度リストが適切に処理されること
            preferred_resolutions = config_service.get_preferred_resolutions()
            assert isinstance(preferred_resolutions, list)
            assert all(isinstance(res, int) for res in preferred_resolutions)

    def test_error_handling_gui_integration(self, tmp_path):
        """エラーハンドリングとGUI通知の統合テスト"""
        # 存在しない設定ファイルでのテスト
        missing_config_file = tmp_path / "missing_config.toml"

        with patch("lorairo.services.configuration_service.get_config") as mock_get_config:
            from lorairo.utils.config import DEFAULT_CONFIG

            mock_get_config.return_value = DEFAULT_CONFIG

            # 存在しないファイルでもエラーなく初期化されること
            config_service = ConfigurationService(missing_config_file)

            # デフォルト値が使用されること（ファイル作成は別途必要）
            # assert missing_config_file.exists()  # ファイル作成は save_settings() で行われる

            # デフォルト値が使用されること
            assert config_service.get_setting("directories", "database_base_dir") == "lorairo_data"

    def test_unicode_handling_gui_integration(self, tmp_path):
        """Unicode 文字の GUI 表示統合テスト"""
        # Unicode文字を含む設定ファイル
        config_file = tmp_path / "unicode_config.toml"
        unicode_content = """
[directories]
database_dir = "データベース_ディレクトリ"
export_dir = "出力_フォルダ" 
"""
        config_file.write_text(unicode_content, encoding="utf-8")

        with patch("lorairo.services.configuration_service.get_config") as mock_get_config:
            mock_get_config.return_value = {
                "directories": {"database_dir": "データベース_ディレクトリ", "export_dir": "出力_フォルダ"}
            }

            config_service = ConfigurationService(config_file)

            # Unicode文字がGUIで正しく表示されること
            db_dir = config_service.get_database_directory()
            export_dir = config_service.get_export_directory()

            assert "データベース" in str(db_dir)
            assert "出力" in str(export_dir)

    def test_performance_gui_integration(self, tmp_path):
        """パフォーマンスとGUIレスポンシブネスの統合テスト"""
        config_file = tmp_path / "performance_config.toml"
        config_file.write_text("""
[api]
openai_key = "sk-test123456789"
claude_key = "claude-test123456789"
google_key = "google-test123456789"

[directories]
database_dir = "performance_test"
export_dir = "performance_export"

[image_processing]
target_resolution = 1024
""")

        with patch("lorairo.services.configuration_service.get_config") as mock_get_config:
            mock_get_config.return_value = {
                "api": {
                    "openai_key": "sk-test123456789",
                    "claude_key": "claude-test123456789",
                    "google_key": "google-test123456789",
                },
                "directories": {"database_dir": "performance_test", "export_dir": "performance_export"},
                "image_processing": {"target_resolution": 1024},
            }

            config_service = ConfigurationService(config_file)

            # 多数の設定アクセスが高速であること
            import time

            start_time = time.time()

            for _ in range(100):
                config_service.get_setting("api", "openai_key")
                config_service.get_available_providers()
                config_service.get_setting("image_processing", "target_resolution")
                config_service.get_database_directory()

            end_time = time.time()
            processing_time = end_time - start_time

            # 100回のアクセスが 0.1秒以内に完了すること
            assert processing_time < 0.1
