from pathlib import Path

from PySide6.QtCore import Slot
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from ...services.configuration_service import ConfigurationService
from ..designer.ConfigurationWindow_ui import Ui_ConfigurationWindow


class ConfigurationWindow(QWidget, Ui_ConfigurationWindow):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setupUi(self)
        self.config_service: ConfigurationService | None = None

    def initialize(self, config_service: ConfigurationService) -> None:
        self.config_service = config_service
        self.initialize_ui()
        self.connect_custom_widgets()

    def initialize_ui(self) -> None:
        if not self.config_service:
            print("Error: ConfigurationService is not initialized.")
            return
        self.initialize_directory_pickers()
        self.initialize_api_settings()
        self.initialize_huggingface_settings()
        self.initialize_log_settings()

    def initialize_directory_pickers(self) -> None:
        if not self.config_service:
            return
        directories = {
            "output": self.dirPickerOutput,
            "response_file": self.dirPickerResponse,
            "edited_output": self.dirPickerEditedOutput,
        }
        for key, picker in directories.items():
            picker.set_label_text(f"{key.capitalize()} Directory")
            picker.set_path(self.config_service.get_setting("directories", key, ""))

    def initialize_api_settings(self) -> None:
        if not self.config_service:
            return
        api_settings = {
            "openai_key": self.lineEditOpenAiKey,
            "google_key": self.lineEditGoogleVisionKey,
            "claude_key": self.lineEditAnthropicKey,
        }
        for key, widget in api_settings.items():
            widget.setText(self.config_service.get_setting("api", key, ""))

    def initialize_huggingface_settings(self) -> None:
        if not self.config_service:
            return
        hf_settings = {
            "hf_username": self.lineEditHfUsername,
            "repo_name": self.lineEditHfRepoName,
            "token": self.lineEditHfToken,
        }
        for key, widget in hf_settings.items():
            widget.setText(self.config_service.get_setting("huggingface", key, ""))

    def initialize_log_settings(self) -> None:
        if not self.config_service:
            return
        self.comboBoxLogLevel.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self.comboBoxLogLevel.setCurrentText(self.config_service.get_setting("log", "level", "INFO"))
        self.filePickerLogFile.set_label_text("Log File")
        self.filePickerLogFile.set_path(self.config_service.get_setting("log", "file_path", ""))

    @Slot()
    def on_buttonSave_clicked(self) -> None:
        if not self.config_service:
            return
        if self.config_service.save_settings():
            QMessageBox.information(self, "保存成功", "設定を保存しました。")
        else:
            QMessageBox.critical(self, "保存エラー", "設定ファイルの保存に失敗しました。")

    @Slot()
    def on_buttonSaveAs_clicked(self) -> None:
        if not self.config_service:
            return
        filename, _ = QFileDialog.getSaveFileName(self, "名前を付けて保存", "", "TOML Files (*.toml)")
        if filename and self.config_service.save_settings(Path(filename)):
            QMessageBox.information(self, "保存成功", f"設定を {filename} に保存しました。")
        elif filename:
            QMessageBox.critical(self, "保存エラー", f"設定ファイル '{filename}' の保存に失敗しました。")

    @Slot()
    def on_lineEditOpenAiKey_editingFinished(self) -> None:
        if not self.config_service:
            return
        self.config_service.update_setting("api", "openai_key", self.lineEditOpenAiKey.text())

    @Slot()
    def on_lineEditGoogleVisionKey_editingFinished(self) -> None:
        if not self.config_service:
            return
        self.config_service.update_setting("api", "google_key", self.lineEditGoogleVisionKey.text())

    @Slot()
    def on_lineEditAnthropicKey_editingFinished(self) -> None:
        if not self.config_service:
            return
        self.config_service.update_setting("api", "claude_key", self.lineEditAnthropicKey.text())

    @Slot()
    def on_lineEditHfUsername_editingFinished(self) -> None:
        if not self.config_service:
            return
        self.config_service.update_setting("huggingface", "hf_username", self.lineEditHfUsername.text())

    @Slot()
    def on_lineEditHfRepoName_editingFinished(self) -> None:
        if not self.config_service:
            return
        self.config_service.update_setting("huggingface", "repo_name", self.lineEditHfRepoName.text())

    @Slot()
    def on_lineEditHfToken_editingFinished(self) -> None:
        if not self.config_service:
            return
        self.config_service.update_setting("huggingface", "token", self.lineEditHfToken.text())

    def on_comboBoxLogLevel_currentIndexChanged(self, index: int) -> None:
        if not self.config_service:
            return
        self.config_service.update_setting("log", "level", self.comboBoxLogLevel.itemText(index))

    @Slot()
    def connect_custom_widgets(self) -> None:
        self.dirPickerOutput.DirectoryPicker.lineEditPicker.textChanged.connect(
            self.on_dirPickerOutput_changed
        )
        self.dirPickerResponse.DirectoryPicker.lineEditPicker.textChanged.connect(
            self.on_dirPickerResponse_changed
        )
        self.dirPickerEditedOutput.DirectoryPicker.lineEditPicker.textChanged.connect(
            self.on_dirPickerEditedOutput_changed
        )
        self.filePickerLogFile.FilePicker.lineEditPicker.textChanged.connect(
            self.on_filePickerLogFile_changed
        )

    @Slot()
    def on_dirPickerOutput_changed(self, new_path: str) -> None:
        if not self.config_service:
            return
        self.config_service.update_setting("directories", "output", new_path)

    @Slot()
    def on_dirPickerResponse_changed(self, new_path: str) -> None:
        if not self.config_service:
            return
        self.config_service.update_setting("directories", "response_file", new_path)

    @Slot()
    def on_dirPickerEditedOutput_changed(self, new_path: str) -> None:
        if not self.config_service:
            return
        self.config_service.update_setting("directories", "edited_output", new_path)

    @Slot()
    def on_filePickerLogFile_changed(self, new_path: str) -> None:
        if not self.config_service:
            return
        self.config_service.update_setting("log", "file_path", new_path)


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    # 絶対パスでインポート
    from lorairo.services.configuration_service import ConfigurationService

    app = QApplication(sys.argv)
    config_service = ConfigurationService()
    config_page = ConfigurationWindow()
    config_page.initialize(config_service)
    config_page.show()
    sys.exit(app.exec())
