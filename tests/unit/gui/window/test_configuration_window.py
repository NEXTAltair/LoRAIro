"""ConfigurationWindow Unit Tests

再設計された設定ダイアログのUIテスト。
ConfigurationServiceをモックで差し替え、ウィジェットの生成・値反映・収集を検証する。
"""

from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QComboBox, QLabel, QLineEdit, QMessageBox, QTabWidget

from lorairo.gui import theme
from lorairo.gui.window.configuration_window import ConfigurationWindow
from lorairo.services.configuration_service import ConfigurationService
from lorairo.utils.config import DEFAULT_CLI_LOG_PATH, DEFAULT_LOG_PATH


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

    def test_populate_does_not_echo_saved_api_keys(self, dialog: ConfigurationWindow) -> None:
        """Issue #755: 保存済キーは欄に echo back せず「保存済」ステータスのみ表示する。"""
        for object_name in ("lineEditOpenAiKey", "lineEditGoogleKey", "lineEditClaudeKey"):
            key_edit = dialog.findChild(QLineEdit, object_name)
            assert key_edit is not None
            assert key_edit.text() == ""
            assert key_edit.placeholderText() == "保存済（変更する場合のみ入力）"
            status = dialog.findChild(QLabel, f"{object_name}Status")
            assert status is not None
            assert status.text() == "保存済"

    def test_unset_api_key_shows_unset_status(self, dialog: ConfigurationWindow) -> None:
        """Issue #755: 未設定キー (openrouter) は「未設定」ステータスを表示する。"""
        key_edit = dialog.findChild(QLineEdit, "lineEditOpenRouterKey")
        assert key_edit is not None
        assert key_edit.text() == ""
        assert key_edit.placeholderText() == "未設定"
        status = dialog.findChild(QLabel, "lineEditOpenRouterKeyStatus")
        assert status is not None
        assert status.text() == "未設定"

    def test_api_keys_masked_with_password_echo(self, dialog: ConfigurationWindow) -> None:
        """Issue #755: 全 API キー欄はマスク入力 (表示切替なし)。"""
        for object_name in (
            "lineEditOpenAiKey",
            "lineEditGoogleKey",
            "lineEditClaudeKey",
            "lineEditOpenRouterKey",
        ):
            key_edit = dialog.findChild(QLineEdit, object_name)
            assert key_edit is not None
            assert key_edit.echoMode() == QLineEdit.EchoMode.Password

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

    def test_collect_settings_returns_all_sections(self, dialog: ConfigurationWindow) -> None:
        """全セクション含む辞書を返す (Issue #249 で model_selection を追加)。"""
        settings = dialog._collect_settings()
        expected_sections = {
            "api",
            "directories",
            "log",
            "image_processing",
            "prompts",
            "model_selection",
        }
        assert set(settings.keys()) == expected_sections

    def test_populate_and_collect_roundtrip(self, dialog: ConfigurationWindow) -> None:
        """populate→collectで値が保持される (Issue #755: 空欄 = 保存済キー維持)。"""
        settings = dialog._collect_settings()
        assert settings["api"]["openai_key"] == "sk-test-openai"
        assert settings["api"]["google_key"] == "google-test-key"
        assert settings["api"]["claude_key"] == "claude-test-key"
        assert settings["log"]["level"] == "WARNING"
        assert settings["prompts"]["additional"] == "test prompt text"

    def test_collect_uses_typed_api_key_when_entered(self, dialog: ConfigurationWindow) -> None:
        """Issue #755: 入力した新キーは保存済の値を上書きする。"""
        key_edit = dialog.findChild(QLineEdit, "lineEditClaudeKey")
        assert key_edit is not None
        key_edit.setText("  sk-new-claude-key  ")
        settings = dialog._collect_settings()
        assert settings["api"]["claude_key"] == "sk-new-claude-key"
        # 触っていない欄は保存済の値を維持
        assert settings["api"]["openai_key"] == "sk-test-openai"

    def test_focus_api_key_field_highlights_provider_row(self, dialog: ConfigurationWindow) -> None:
        """Issue #755: needs key 導線で該当プロバイダ欄をハイライトする。"""
        # 詳細設定タブへ移しておき、基本設定タブへ戻ることを検証
        tab_widget = dialog.findChild(QTabWidget)
        assert tab_widget is not None
        tab_widget.setCurrentIndex(1)

        assert dialog.focus_api_key_field("anthropic") is True

        assert tab_widget.currentIndex() == 0
        key_edit = dialog.findChild(QLineEdit, "lineEditClaudeKey")
        assert key_edit is not None
        assert theme.WARN in key_edit.styleSheet()

    def test_focus_api_key_field_unknown_provider_returns_false(self, dialog: ConfigurationWindow) -> None:
        """未知 provider は False を返し例外を出さない。"""
        assert dialog.focus_api_key_field("xai") is False

    def test_ok_saves_and_accepts(
        self, dialog: ConfigurationWindow, config_service: MagicMock, qtbot
    ) -> None:
        """OKで保存→accept。"""
        with qtbot.waitSignal(dialog.accepted, timeout=3000):
            dialog._on_accepted()
        config_service.save_settings.assert_called_once()

    def test_ok_reinitializes_logging(
        self, dialog: ConfigurationWindow, config_service: MagicMock, qtbot
    ) -> None:
        """OK保存時にinitialize_loggingが新しいログ設定で呼ばれる。"""
        with (
            patch("lorairo.gui.window.configuration_window.initialize_logging") as mock_init_log,
            qtbot.waitSignal(dialog.accepted, timeout=3000),
        ):
            dialog._on_accepted()
        mock_init_log.assert_called_once_with({"level": "WARNING", "file_path": str(DEFAULT_LOG_PATH)})

    def test_ok_reinitializes_logging_with_gui_log_file_when_config_has_cli_path(
        self, dialog: ConfigurationWindow, config_service: MagicMock, qtbot
    ) -> None:
        """Issue #546: 設定保存後も GUI ログを CLI 専用ログへ戻さない。"""
        config_service.get_all_settings.return_value["log"]["file_path"] = str(DEFAULT_CLI_LOG_PATH)

        with (
            patch("lorairo.gui.window.configuration_window.initialize_logging") as mock_init_log,
            qtbot.waitSignal(dialog.accepted, timeout=3000),
        ):
            dialog._on_accepted()

        mock_init_log.assert_called_once_with({"level": "WARNING", "file_path": str(DEFAULT_LOG_PATH)})

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


@pytest.mark.gui
class TestConfigurationWindowRoutePreference:
    """Issue #249: route_preference ComboBox の populate / collect / fallback。"""

    def test_route_preference_combobox_populated_with_three_values(
        self, dialog: ConfigurationWindow
    ) -> None:
        """ComboBox に auto/direct/openrouter の 3 値が並ぶ (Issue #249 PR #250 review)。

        ``all`` は CLI 専用 (--route all)。GUI checkbox UI は preferred 1 行のみ
        描画する設計と整合しないため、GUI dropdown には含めない。
        """
        combo = dialog.findChild(QComboBox, "comboBoxRoutePreference")
        assert combo is not None
        items = [combo.itemText(i) for i in range(combo.count())]
        assert items == ["auto", "direct", "openrouter"]
        assert "all" not in items

    def test_route_preference_default_to_auto_when_section_missing(
        self, dialog: ConfigurationWindow
    ) -> None:
        """model_selection section が config に無い場合、auto がセットされる。"""
        combo = dialog.findChild(QComboBox, "comboBoxRoutePreference")
        assert combo is not None
        # _make_mock_config_service は model_selection を返さないため auto fallback
        assert combo.currentText() == "auto"

    def test_route_preference_populated_from_config(self, qtbot, config_service: MagicMock) -> None:
        """config の model_selection.route_preference が ComboBox に反映される。"""
        config_service.get_all_settings.return_value = {
            "api": {},
            "directories": {},
            "log": {"level": "INFO"},
            "image_processing": {"upscaler": "RealESRGAN_x4plus"},
            "prompts": {"additional": ""},
            "model_selection": {"route_preference": "openrouter"},
        }
        dlg = ConfigurationWindow(config_service=config_service)
        qtbot.addWidget(dlg)
        combo = dlg.findChild(QComboBox, "comboBoxRoutePreference")
        assert combo is not None
        assert combo.currentText() == "openrouter"

    def test_route_preference_invalid_config_falls_back_to_auto(
        self, qtbot, config_service: MagicMock
    ) -> None:
        """config の不正値は parse_route_preference 経由で auto に fallback。"""
        config_service.get_all_settings.return_value = {
            "api": {},
            "directories": {},
            "log": {"level": "INFO"},
            "image_processing": {"upscaler": "RealESRGAN_x4plus"},
            "prompts": {"additional": ""},
            "model_selection": {"route_preference": "bogus"},
        }
        dlg = ConfigurationWindow(config_service=config_service)
        qtbot.addWidget(dlg)
        combo = dlg.findChild(QComboBox, "comboBoxRoutePreference")
        assert combo is not None
        assert combo.currentText() == "auto"

    def test_route_preference_all_config_falls_back_to_auto_in_gui(
        self, qtbot, config_service: MagicMock
    ) -> None:
        """config に "all" がある場合、GUI ComboBox には項目が無いため auto fallback (PR #250 review)。

        CLI 経路では "all" は valid だが、GUI dropdown には項目が無いため
        ``findText("all") == -1`` で auto fallback。warning log が出ること自体は
        loguru 経路で副作用、本テストでは ComboBox の最終状態のみ検証。
        """
        config_service.get_all_settings.return_value = {
            "api": {},
            "directories": {},
            "log": {"level": "INFO"},
            "image_processing": {"upscaler": "RealESRGAN_x4plus"},
            "prompts": {"additional": ""},
            "model_selection": {"route_preference": "all"},
        }
        dlg = ConfigurationWindow(config_service=config_service)
        qtbot.addWidget(dlg)
        combo = dlg.findChild(QComboBox, "comboBoxRoutePreference")
        assert combo is not None
        # GUI 上は auto として表示 (CLI 専用値のため)
        assert combo.currentText() == "auto"

    def test_route_preference_all_warning_renders_value(self, qtbot, config_service: MagicMock) -> None:
        """GUI 専用 fallback warning は route_preference の実値をログへ出す。"""
        from lorairo.utils.log import logger

        config_service.get_all_settings.return_value = {
            "api": {},
            "directories": {},
            "log": {"level": "INFO"},
            "image_processing": {"upscaler": "RealESRGAN_x4plus"},
            "prompts": {"additional": ""},
            "model_selection": {"route_preference": "all"},
        }
        sink = StringIO()
        sink_id = logger.add(sink, format="{message}", level="WARNING")
        try:
            dlg = ConfigurationWindow(config_service=config_service)
            qtbot.addWidget(dlg)
        finally:
            logger.remove(sink_id)

        log_output = sink.getvalue()
        assert "route_preference='all'" in log_output
        assert "%r" not in log_output

    def test_collect_settings_includes_model_selection(self, dialog: ConfigurationWindow) -> None:
        """_collect_settings に model_selection.route_preference が含まれる。"""
        settings = dialog._collect_settings()
        assert "model_selection" in settings
        assert settings["model_selection"]["route_preference"] in {
            "auto",
            "direct",
            "openrouter",
            "all",
        }

    def test_ok_saves_route_preference(
        self, dialog: ConfigurationWindow, config_service: MagicMock, qtbot
    ) -> None:
        """OK で model_selection.route_preference が update_setting されて save される。"""
        combo = dialog.findChild(QComboBox, "comboBoxRoutePreference")
        assert combo is not None
        combo.setCurrentText("direct")
        with qtbot.waitSignal(dialog.accepted, timeout=3000):
            dialog._on_accepted()
        # update_setting が ("model_selection", "route_preference", "direct") で呼ばれている
        update_calls = config_service.update_setting.call_args_list
        assert any(
            call.args == ("model_selection", "route_preference", "direct") for call in update_calls
        ), f"expected update_setting('model_selection', 'route_preference', 'direct') in {update_calls}"
