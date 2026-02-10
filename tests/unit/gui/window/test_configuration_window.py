"""ConfigurationWindow Unit Tests

再設計された設定ダイアログのUIテスト。
ConfigurationServiceをモックで差し替え、ウィジェットの生成・値反映・収集を検証する。
"""

from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QComboBox, QLineEdit, QMessageBox, QTabWidget

from lorairo.gui.window.configuration_window import ConfigurationWindow
from lorairo.services.configuration_service import ConfigurationService


def _make_mock_config_service() -> MagicMock:
    """テスト用のConfigurationServiceモックを作成する。"""
    mock = MagicMock(spec=ConfigurationService)
    mock.get_all_settings.return_value = {
        "api": {
            "openai_key": "sk-test-openai",
            "google_key": "google-test-key",
            "claude_key": "claude-test-key",
        },
        "directories": {
            "database_base_dir": "/tmp/db",
            "database_project_name": "test_project",
            "export_dir": "/tmp/export",
            "batch_results_dir": "/tmp/batch",
        },
        "log": {"level": "WARNING"},
        "image_processing": {"upscaler": "RealESRGAN_x4plus"},
        "prompts": {"additional": "test prompt text"},
    }
    mock.get_available_upscaler_names.return_value = [
        "RealESRGAN_x4plus",
        "RealESRGAN_x4plus_anime_6B",
    ]
    mock.get_default_upscaler_name.return_value = "RealESRGAN_x4plus"
    mock.save_settings.return_value = True
    return mock


@pytest.fixture()
def config_service() -> MagicMock:
    """ConfigurationServiceモックフィクスチャ。"""
    return _make_mock_config_service()


@pytest.fixture()
def dialog(qtbot, config_service: MagicMock) -> ConfigurationWindow:
    """ConfigurationWindowフィクスチャ。"""
    dlg = ConfigurationWindow(config_service=config_service)
    qtbot.addWidget(dlg)
    return dlg


@pytest.mark.gui
class TestConfigurationWindow:
    """ConfigurationWindow テストスイート。"""

    def test_init_creates_dialog(self, dialog: ConfigurationWindow) -> None:
        """ダイアログが正常作成される。"""
        assert dialog is not None
        assert dialog.windowTitle() == "設定"

    def test_has_two_tabs(self, dialog: ConfigurationWindow) -> None:
        """QTabWidgetに2タブある。"""
        tab_widget = dialog.findChild(QTabWidget)
        assert tab_widget is not None
        assert tab_widget.count() == 2
        assert tab_widget.tabText(0) == "基本設定"
        assert tab_widget.tabText(1) == "詳細設定"

    def test_populate_sets_api_keys(self, dialog: ConfigurationWindow) -> None:
        """APIキーがUIに反映される。"""
        openai = dialog.findChild(QLineEdit, "lineEditOpenAiKey")
        google = dialog.findChild(QLineEdit, "lineEditGoogleKey")
        claude = dialog.findChild(QLineEdit, "lineEditClaudeKey")
        assert openai is not None
        assert openai.text() == "sk-test-openai"
        assert google is not None
        assert google.text() == "google-test-key"
        assert claude is not None
        assert claude.text() == "claude-test-key"

    def test_populate_sets_log_level(self, dialog: ConfigurationWindow) -> None:
        """ログレベルが選択される。"""
        combo = dialog.findChild(QComboBox, "comboBoxLogLevel")
        assert combo is not None
        assert combo.currentText() == "WARNING"

    def test_populate_sets_directories(self, dialog: ConfigurationWindow) -> None:
        """ディレクトリがUIに反映される。"""
        project_name = dialog.findChild(QLineEdit, "lineEditProjectName")
        assert project_name is not None
        assert project_name.text() == "test_project"

    def test_collect_settings_returns_all_sections(
        self, dialog: ConfigurationWindow
    ) -> None:
        """全セクション含む辞書を返す。"""
        settings = dialog._collect_settings()
        expected_sections = {"api", "directories", "log", "image_processing", "prompts"}
        assert set(settings.keys()) == expected_sections

    def test_populate_and_collect_roundtrip(self, dialog: ConfigurationWindow) -> None:
        """populate→collectで値が保持される。"""
        settings = dialog._collect_settings()
        assert settings["api"]["openai_key"] == "sk-test-openai"
        assert settings["api"]["google_key"] == "google-test-key"
        assert settings["api"]["claude_key"] == "claude-test-key"
        assert settings["log"]["level"] == "WARNING"
        assert settings["prompts"]["additional"] == "test prompt text"

    def test_ok_saves_and_accepts(
        self, dialog: ConfigurationWindow, config_service: MagicMock, qtbot
    ) -> None:
        """OKで保存→accept。"""
        with qtbot.waitSignal(dialog.accepted, timeout=3000):
            dialog._on_accepted()
        config_service.save_settings.assert_called_once()

    def test_save_failure_shows_error(
        self,
        dialog: ConfigurationWindow,
        config_service: MagicMock,
        monkeypatch,
    ) -> None:
        """保存失敗でエラー表示。"""
        config_service.save_settings.return_value = False
        called = []
        monkeypatch.setattr(
            QMessageBox,
            "critical",
            lambda *args, **kwargs: called.append(True),
        )
        dialog._on_accepted()
        assert len(called) == 1

    def test_upscaler_combobox_populated(self, dialog: ConfigurationWindow) -> None:
        """アップスケーラーComboBoxに動的値が反映される。"""
        upscaler = dialog.findChild(QComboBox, "comboBoxUpscaler")
        assert upscaler is not None
        assert upscaler.count() == 2
        items = [upscaler.itemText(i) for i in range(upscaler.count())]
        assert "RealESRGAN_x4plus" in items
        assert "RealESRGAN_x4plus_anime_6B" in items
