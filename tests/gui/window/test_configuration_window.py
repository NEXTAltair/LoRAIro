import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication

from lorairo.gui.window.configuration_window import ConfigurationWindow
from lorairo.services.configuration_service import ConfigurationService


# QApplication Fixture
@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


@pytest.fixture
def mock_config_service():
    mock = MagicMock(spec=ConfigurationService)
    mock.get_setting.side_effect = lambda section, key, default="": {
        ("directories", "output"): "/path/to/output",
        ("directories", "response_file"): "/path/to/response",
        ("directories", "edited_output"): "/path/to/edited",
        ("api", "openai_key"): "sk-openai-key",
        ("api", "google_key"): "google-api-key",
        ("api", "claude_key"): "claude-api-key",
        ("huggingface", "hf_username"): "testuser",
        ("huggingface", "repo_name"): "testrepo",
        ("huggingface", "token"): "hf_token",
        ("log", "level"): "DEBUG",
        ("log", "file_path"): "/path/to/app.log",
    }.get((section, key), default)
    return mock


# --- 新しいフィクスチャ: 初期化前のウィンドウとモック化されたメソッド --- #
@pytest.fixture
def uninitialized_config_window(qt_app):
    """ConfigurationWindowインスタンスを作成するが、initialize() は呼び出さない。
    子ウィジェットの set_path メソッドはモック化する。
    """
    window = ConfigurationWindow()
    # initialize() が呼ばれる前に set_path をモック化
    window.dirPickerOutput.set_path = MagicMock()
    window.dirPickerResponse.set_path = MagicMock()
    window.dirPickerEditedOutput.set_path = MagicMock()
    window.filePickerLogFile.set_path = MagicMock()
    return window


# ----------------------------------------------------------------- #


# --- 既存のフィクスチャ: 初期化済みウィンドウ (他のテストで使用) --- #
@pytest.fixture
def config_window(qt_app, mock_config_service):
    """テスト対象の ConfigurationWindow インスタンスを作成し、初期化。"""
    window = ConfigurationWindow()
    # このフィクスチャでは initialize を呼び出すので、set_path のモックは不要
    window.initialize(mock_config_service)
    return window


# ------------------------------------------------------------- #


# --- テストケース --- #


# --- test_initialize_ui_values を修正 --- #
def test_initialize_ui_values(uninitialized_config_window, mock_config_service):
    """initialize 時にサービスから取得した値が UI に正しく設定されるかテスト。"""
    window = uninitialized_config_window  # 初期化前のウィンドウを使用

    # ここで initialize を呼び出す
    window.initialize(mock_config_service)

    # ディレクトリピッカー (モック化された set_path の呼び出しを検証)
    window.dirPickerOutput.set_path.assert_called_once_with("/path/to/output")
    window.dirPickerResponse.set_path.assert_called_once_with("/path/to/response")
    window.dirPickerEditedOutput.set_path.assert_called_once_with("/path/to/edited")
    window.filePickerLogFile.set_path.assert_called_once_with("/path/to/app.log")

    # APIキー (実際のウィジェットの状態を検証)
    assert window.lineEditOpenAiKey.text() == "sk-openai-key"
    assert window.lineEditGoogleVisionKey.text() == "google-api-key"
    assert window.lineEditAnthropicKey.text() == "claude-api-key"

    # Hugging Face (実際のウィジェットの状態を検証)
    assert window.lineEditHfUsername.text() == "testuser"
    assert window.lineEditHfRepoName.text() == "testrepo"
    assert window.lineEditHfToken.text() == "hf_token"

    # ログ設定 (実際のウィジェットの状態を検証)
    assert window.comboBoxLogLevel.currentText() == "DEBUG"


# -------------------------------------- #


def test_save_settings_clicked(config_window, mock_config_service):
    """保存ボタンクリック時に service.save_settings が引数なしで呼ばれるかテスト。"""
    # このテストは初期化済みのウィンドウを使用 (config_window フィクスチャ)
    mock_config_service.save_settings.return_value = True
    with patch("lorairo.gui.window.configuration_window.QMessageBox") as mock_msgbox:
        config_window.buttonSave.click()
    mock_config_service.save_settings.assert_called_once_with()
    mock_msgbox.information.assert_called_once()


def test_save_settings_as_clicked(config_window, mock_config_service):
    """名前を付けて保存ボタンクリック時に適切な処理が行われるかテスト。"""
    save_path = Path("/new/path/config.toml")
    mock_config_service.save_settings.return_value = True
    with (
        patch("lorairo.gui.window.configuration_window.QFileDialog") as mock_file_dialog,
        patch("lorairo.gui.window.configuration_window.QMessageBox") as mock_msgbox,
    ):
        mock_file_dialog.getSaveFileName.return_value = (str(save_path), "TOML Files (*.toml)")
        config_window.buttonSaveAs.click()
    mock_file_dialog.getSaveFileName.assert_called_once()
    mock_config_service.save_settings.assert_called_once_with(save_path)
    mock_msgbox.information.assert_called_once()


def test_save_settings_as_cancel(config_window, mock_config_service):
    """名前を付けて保存でキャンセルした場合、保存処理が呼ばれないことをテスト。"""
    with (
        patch("lorairo.gui.window.configuration_window.QFileDialog") as mock_file_dialog,
        patch("lorairo.gui.window.configuration_window.QMessageBox") as mock_msgbox,
    ):
        mock_file_dialog.getSaveFileName.return_value = ("", "")
        config_window.buttonSaveAs.click()
    mock_file_dialog.getSaveFileName.assert_called_once()
    mock_config_service.save_settings.assert_not_called()
    mock_msgbox.information.assert_not_called()
    mock_msgbox.critical.assert_not_called()


def test_update_api_key(config_window, mock_config_service):
    """APIキーのQLineEdit編集完了時に service.update_setting が呼ばれるかテスト。"""
    new_key = "new-openai-key"
    config_window.lineEditOpenAiKey.setText(new_key)
    config_window.lineEditOpenAiKey.editingFinished.emit()
    mock_config_service.update_setting.assert_called_with("api", "openai_key", new_key)


def test_update_directory(config_window, mock_config_service):
    """ディレクトリピッカーのパス変更時に service.update_setting が呼ばれるかテスト。"""
    new_path = "/another/output/path"
    config_window.on_dirPickerOutput_changed(new_path)
    mock_config_service.update_setting.assert_called_with("directories", "output", new_path)


def test_update_log_level(config_window, mock_config_service):
    """ログレベルのQComboBox変更時に service.update_setting が呼ばれるかテスト。"""
    new_level = "WARNING"
    index = config_window.comboBoxLogLevel.findText(new_level)
    assert index != -1
    config_window.comboBoxLogLevel.setCurrentIndex(index)
    config_window.on_comboBoxLogLevel_currentIndexChanged(index)
    mock_config_service.update_setting.assert_called_with("log", "level", new_level)
