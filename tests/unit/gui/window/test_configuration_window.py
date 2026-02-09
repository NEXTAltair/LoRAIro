"""ConfigurationWindow Unit Tests

設定ダイアログのUIデータ収集・適用をテスト。
ConfigurationServiceとの連携を検証。

Note: Ui_ConfigurationWindowは複雑なQt Designerファイルのため、
基本的な初期化とメソッド呼び出しのみテスト。
"""

from unittest.mock import Mock, patch

import pytest


class TestConfigurationWindowInitialization:
    """初期化テスト"""

    def test_initialization_with_mock_ui(self, qtbot):
        """ConfigurationWindowが正しく初期化される（モックUI）"""
        mock_config = Mock()
        mock_config.get_all_settings.return_value = {
            "api": {},
            "huggingface": {},
            "directories": {},
            "log": {},
        }

        # Ui_ConfigurationWindowをモック化
        with patch("lorairo.gui.window.configuration_window.Ui_ConfigurationWindow") as mock_ui_class:
            mock_ui_instance = Mock()
            # 必要な属性を設定
            for attr in [
                "lineEditOpenAiKey",
                "lineEditGoogleVisionKey",
                "lineEditAnthropicKey",
                "lineEditHfUsername",
                "lineEditHfRepoName",
                "lineEditHfToken",
                "dirPickerExportDir",
                "dirPickerBatchResults",
                "dirPickerDatabaseDir",
                "comboBoxLogLevel",
                "filePickerLogFile",
            ]:
                setattr(mock_ui_instance, attr, Mock())

            mock_ui_class.return_value = mock_ui_instance

            from lorairo.gui.window.configuration_window import ConfigurationWindow

            window = ConfigurationWindow(config_service=mock_config)
            qtbot.addWidget(window)

            assert window._config_service == mock_config
            mock_ui_instance.setupUi.assert_called_once()


class TestConfigurationWindowMethods:
    """メソッド呼び出しテスト"""

    def test_collect_settings_method_exists(self):
        """_collect_settings_from_ui メソッドが存在する"""
        with patch("lorairo.gui.window.configuration_window.Ui_ConfigurationWindow"):
            from lorairo.gui.window.configuration_window import ConfigurationWindow

            assert hasattr(ConfigurationWindow, "_collect_settings_from_ui")

    def test_populate_method_exists(self):
        """_populate_from_config メソッドが存在する"""
        with patch("lorairo.gui.window.configuration_window.Ui_ConfigurationWindow"):
            from lorairo.gui.window.configuration_window import ConfigurationWindow

            assert hasattr(ConfigurationWindow, "_populate_from_config")

    def test_apply_settings_method_exists(self):
        """_apply_settings メソッドが存在する"""
        with patch("lorairo.gui.window.configuration_window.Ui_ConfigurationWindow"):
            from lorairo.gui.window.configuration_window import ConfigurationWindow

            assert hasattr(ConfigurationWindow, "_apply_settings")
