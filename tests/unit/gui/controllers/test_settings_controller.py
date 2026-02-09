"""SettingsController Unit Tests

設定ダイアログの表示制御をテスト。
ConfigurationServiceの有無、ConfigurationWindowの生成を検証。
"""

from unittest.mock import Mock, patch

import pytest
from PySide6.QtWidgets import QDialog, QMessageBox, QWidget

from lorairo.gui.controllers.settings_controller import SettingsController


class TestSettingsControllerValidation:
    """サービス検証テスト"""

    def test_validate_services_with_config(self, qtbot):
        """ConfigurationService設定済みで検証成功"""
        parent = QWidget()
        qtbot.addWidget(parent)

        controller = SettingsController(config_service=Mock(), parent=parent)

        assert controller._validate_services() is True

    def test_validate_services_without_config(self, qtbot, monkeypatch):
        """ConfigurationService未設定で検証失敗"""
        parent = QWidget()
        qtbot.addWidget(parent)

        controller = SettingsController(config_service=None, parent=parent)

        warning_called = []
        monkeypatch.setattr(QMessageBox, "warning", lambda *args: warning_called.append(args))

        assert controller._validate_services() is False
        assert len(warning_called) == 1

    def test_validate_services_without_parent(self):
        """親ウィジェットなし・ConfigurationService未設定"""
        controller = SettingsController(config_service=None, parent=None)

        # QMessageBox表示なし（parentがNone）、False返却
        assert controller._validate_services() is False


class TestSettingsControllerDialog:
    """設定ダイアログ表示テスト"""

    def test_open_settings_dialog_no_config_service(self, qtbot, monkeypatch):
        """ConfigurationServiceなしでダイアログを開こうとすると警告"""
        parent = QWidget()
        qtbot.addWidget(parent)

        controller = SettingsController(config_service=None, parent=parent)

        warning_called = []
        monkeypatch.setattr(QMessageBox, "warning", lambda *args: warning_called.append(args))

        controller.open_settings_dialog()

        assert len(warning_called) == 1

    @patch("lorairo.gui.window.configuration_window.ConfigurationWindow")
    def test_open_settings_dialog_accepted(self, mock_cw_class, qtbot):
        """設定ダイアログが承認された場合"""
        parent = QWidget()
        qtbot.addWidget(parent)

        mock_config = Mock()
        controller = SettingsController(config_service=mock_config, parent=parent)

        mock_dialog = Mock()
        mock_dialog.exec.return_value = QDialog.DialogCode.Accepted
        mock_cw_class.return_value = mock_dialog

        controller.open_settings_dialog()

        mock_cw_class.assert_called_once_with(config_service=mock_config, parent=parent)
        mock_dialog.setModal.assert_called_once_with(True)
        mock_dialog.exec.assert_called_once()

    @patch("lorairo.gui.window.configuration_window.ConfigurationWindow")
    def test_open_settings_dialog_rejected(self, mock_cw_class, qtbot):
        """設定ダイアログがキャンセルされた場合"""
        parent = QWidget()
        qtbot.addWidget(parent)

        mock_config = Mock()
        controller = SettingsController(config_service=mock_config, parent=parent)

        mock_dialog = Mock()
        mock_dialog.exec.return_value = QDialog.DialogCode.Rejected
        mock_cw_class.return_value = mock_dialog

        controller.open_settings_dialog()

        mock_dialog.exec.assert_called_once()
