"""SettingsController Unit Tests

設定ダイアログの表示制御をテスト。
ConfigurationServiceの有無、ConfigurationWindowの生成を検証。
"""

from unittest.mock import Mock, patch

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

    def test_open_settings_dialog_returns_true_when_accepted(self, qtbot):
        """設定ダイアログが Accepted を返す場合、True を返す"""
        parent = QWidget()
        qtbot.addWidget(parent)

        mock_config = Mock()
        controller = SettingsController(config_service=mock_config, parent=parent)

        mock_dialog = Mock()
        mock_dialog.exec.return_value = QDialog.DialogCode.Accepted

        # ConfigurationWindow は open_settings_dialog 内で from ... import される
        with patch(
            "lorairo.gui.window.configuration_window.ConfigurationWindow",
            return_value=mock_dialog,
        ):
            result = controller.open_settings_dialog()

        # Accepted → True
        assert result is True

    def test_open_settings_dialog_returns_false_when_rejected(self, qtbot):
        """設定ダイアログが Rejected を返す場合、False を返す"""
        parent = QWidget()
        qtbot.addWidget(parent)

        mock_config = Mock()
        controller = SettingsController(config_service=mock_config, parent=parent)

        mock_dialog = Mock()
        mock_dialog.exec.return_value = QDialog.DialogCode.Rejected

        with patch(
            "lorairo.gui.window.configuration_window.ConfigurationWindow",
            return_value=mock_dialog,
        ):
            result = controller.open_settings_dialog()

        assert result is False

    def test_open_settings_dialog_highlights_provider_field(self, qtbot):
        """Issue #755: highlight_provider 指定で該当 API キー欄をフォーカスする。"""
        parent = QWidget()
        qtbot.addWidget(parent)

        mock_config = Mock()
        controller = SettingsController(config_service=mock_config, parent=parent)

        mock_dialog = Mock()
        mock_dialog.exec.return_value = QDialog.DialogCode.Accepted

        with patch(
            "lorairo.gui.window.configuration_window.ConfigurationWindow",
            return_value=mock_dialog,
        ):
            result = controller.open_settings_dialog(highlight_provider="anthropic")

        assert result is True
        mock_dialog.focus_api_key_field.assert_called_once_with("anthropic")

    def test_open_settings_dialog_without_highlight_skips_focus(self, qtbot):
        """highlight_provider 未指定では focus_api_key_field を呼ばない。"""
        parent = QWidget()
        qtbot.addWidget(parent)

        mock_config = Mock()
        controller = SettingsController(config_service=mock_config, parent=parent)

        mock_dialog = Mock()
        mock_dialog.exec.return_value = QDialog.DialogCode.Rejected

        with patch(
            "lorairo.gui.window.configuration_window.ConfigurationWindow",
            return_value=mock_dialog,
        ):
            controller.open_settings_dialog()

        mock_dialog.focus_api_key_field.assert_not_called()

    def test_open_settings_dialog_import_error_uses_fallback(self, qtbot, monkeypatch):
        """ConfigurationWindow の ImportError 時はフォールバックダイアログを表示して False を返す。

        sys.modules に None をセットすることで open_settings_dialog() 内の
        `from ..window.configuration_window import ConfigurationWindow` を
        ImportError に変換し、実際の except ImportError パスを通る。
        """
        import sys

        parent = QWidget()
        qtbot.addWidget(parent)

        mock_config = Mock()
        controller = SettingsController(config_service=mock_config, parent=parent)

        information_called = []
        monkeypatch.setattr(QMessageBox, "information", lambda *args: information_called.append(args))

        # sys.modules[key] = None は Python が ImportError を raise するネガティブキャッシュ
        # monkeypatch.setitem でテスト終了時に自動的に元の値へ復元される
        monkeypatch.setitem(sys.modules, "lorairo.gui.window.configuration_window", None)

        result = controller.open_settings_dialog()

        assert result is False
        assert len(information_called) == 1

    def test_open_settings_dialog_general_exception_shows_critical(self, qtbot, monkeypatch):
        """一般的な例外が発生したとき critical ダイアログを表示して False を返す。

        ConfigurationWindow.exec() が RuntimeError を投げるシナリオを検証する。
        """
        parent = QWidget()
        qtbot.addWidget(parent)

        mock_config = Mock()
        controller = SettingsController(config_service=mock_config, parent=parent)

        critical_called = []
        monkeypatch.setattr(QMessageBox, "critical", lambda *args: critical_called.append(args))

        mock_dialog = Mock()
        mock_dialog.exec.side_effect = RuntimeError("Unexpected error")

        with patch(
            "lorairo.gui.window.configuration_window.ConfigurationWindow",
            return_value=mock_dialog,
        ):
            result = controller.open_settings_dialog()

        assert result is False
        assert len(critical_called) == 1


class TestSettingsControllerInit:
    """初期化テスト"""

    def test_init_stores_config_service(self):
        """ConfigurationService が正しく格納される"""
        mock_config = Mock()
        controller = SettingsController(config_service=mock_config)
        assert controller.config_service is mock_config

    def test_init_stores_parent(self, qtbot):
        """parent ウィジェットが正しく格納される"""
        parent = QWidget()
        qtbot.addWidget(parent)
        controller = SettingsController(config_service=None, parent=parent)
        assert controller.parent is parent

    def test_init_defaults_parent_to_none(self):
        """parent のデフォルトは None"""
        controller = SettingsController(config_service=None)
        assert controller.parent is None
